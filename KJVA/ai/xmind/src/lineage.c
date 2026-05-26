/*
 * lineage.c — Lineage & Intelligence Estate (ADR-S49-01 Section 16)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Implements the lineage store: delta recording, generation advancement,
 * and per-domain mastery tracking.
 *
 * DELTA RING BUFFER:
 *   Max 256 deltas.  When full, the oldest delta is overwritten.
 *   delta_count saturates at XM_LINEAGE_MAX_DELTAS; the write index
 *   wraps around using modulo.
 *
 * MASTERY THRESHOLDS:
 *   Understanding: route >= 0.3
 *   Innerstanding: route >= 0.5 AND structure >= 0.4
 *   Overstanding:  route >= 0.7 AND structure >= 0.6 AND memory >= 0.5
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"
#include "../include/xmind_lineage.h"

/* ===================================================================
 * S1  INTERNAL HELPERS
 * =================================================================== */

static void lin_memzero(void *dst, uint64_t n)
{
    uint8_t *p = (uint8_t *)dst;
    uint64_t i;
    for (i = 0u; i < n; i++) {
        p[i] = 0u;
    }
}

static void lin_memcpy(void *dst, const void *src, uint64_t n)
{
    uint8_t       *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;
    uint64_t i;
    for (i = 0u; i < n; i++) {
        d[i] = s[i];
    }
}

/*
 * lin_compute_mastery — Determine mastery level from sub-scores.
 *
 * Thresholds per ADR Section 5.4:
 *   Understanding: route >= 0.3
 *   Innerstanding: route >= 0.5 AND structure >= 0.4
 *   Overstanding:  route >= 0.7 AND structure >= 0.6 AND memory >= 0.5
 */
static xmind_mastery_level_t lin_compute_mastery(float route,
                                                   float structure,
                                                   float memory)
{
    if (route >= 0.7f && structure >= 0.6f && memory >= 0.5f) {
        return XM_MASTERY_OVERSTANDING;
    }
    if (route >= 0.5f && structure >= 0.4f) {
        return XM_MASTERY_INNERSTANDING;
    }
    if (route >= 0.3f) {
        return XM_MASTERY_UNDERSTANDING;
    }
    /* Below threshold — default to understanding level 0 */
    return XM_MASTERY_UNDERSTANDING;
}

/* ===================================================================
 * S2  LINEAGE STORE INITIALIZATION
 * =================================================================== */

int32_t xmind_lineage_init(xmind_lineage_store_t *store)
{
    if (!store) {
        return XMIND_ERR_INVAL;
    }

    lin_memzero(store, sizeof(*store));
    store->initialized       = 1u;
    store->current_generation = 0u;
    store->delta_count       = 0u;
    store->mastery_count     = 0u;

    return XMIND_OK;
}

/* ===================================================================
 * S3  DELTA RECORDING — Ring buffer append
 * =================================================================== */

int32_t xmind_lineage_record_delta(xmind_lineage_store_t *store,
                                    const uint8_t *source_hash,
                                    uint16_t domain_id,
                                    float score,
                                    uint8_t mastery,
                                    uint8_t target,
                                    uint32_t evidence,
                                    uint64_t timestamp)
{
    uint32_t write_idx;
    xmind_lineage_delta_t *d;

    if (!store || !store->initialized) {
        return XMIND_ERR_INVAL;
    }
    if (!source_hash) {
        return XMIND_ERR_INVAL;
    }
    if (score < 0.0f || score > 1.0f) {
        return XMIND_ERR_INVAL;
    }
    if (mastery > 2u) {
        return XMIND_ERR_INVAL;
    }
    if (target > 2u) {
        return XMIND_ERR_INVAL;
    }

    /* Ring buffer: write at delta_count % MAX, saturate count at MAX */
    write_idx = store->delta_count % XM_LINEAGE_MAX_DELTAS;

    d = &store->deltas[write_idx];
    lin_memcpy(d->source_hash, source_hash, 32u);
    d->domain_id        = domain_id;
    d->improvement_score = score;
    d->generation_index = store->current_generation;
    d->mastery_reached  = mastery;
    d->retention_target = target;
    d->timestamp_ns     = timestamp;
    d->evidence_count   = evidence;

    if (store->delta_count < XM_LINEAGE_MAX_DELTAS) {
        store->delta_count++;
    }
    /* When full, delta_count stays at MAX and write_idx wraps,
     * overwriting the oldest entry. */

    return XMIND_OK;
}

/* ===================================================================
 * S4  GENERATION ADVANCEMENT
 * =================================================================== */

uint32_t xmind_lineage_advance_generation(xmind_lineage_store_t *store)
{
    uint32_t latest_idx;
    const xmind_lineage_delta_t *latest;

    if (!store || !store->initialized || store->delta_count == 0u) {
        return store ? store->current_generation : 0u;
    }

    /* Check the most recent delta for sufficient evidence.
     * The latest delta is at (delta_count - 1) % MAX. */
    latest_idx = (store->delta_count - 1u) % XM_LINEAGE_MAX_DELTAS;
    latest = &store->deltas[latest_idx];

    /* Advancement requires evidence_count >= 3 (quality gate) */
    if (latest->evidence_count >= 3u) {
        store->current_generation++;
    }

    return store->current_generation;
}

/* ===================================================================
 * S5  MASTERY UPDATE
 * =================================================================== */

int32_t xmind_lineage_update_mastery(xmind_lineage_store_t *store,
                                      uint16_t domain_id,
                                      float route_score,
                                      float structure_score,
                                      float memory_score,
                                      uint32_t evidence,
                                      uint64_t timestamp)
{
    uint32_t i;
    xmind_domain_mastery_t *m;

    if (!store || !store->initialized) {
        return XMIND_ERR_INVAL;
    }

    /* Clamp scores to [0.0, 1.0] */
    if (route_score < 0.0f) route_score = 0.0f;
    if (route_score > 1.0f) route_score = 1.0f;
    if (structure_score < 0.0f) structure_score = 0.0f;
    if (structure_score > 1.0f) structure_score = 1.0f;
    if (memory_score < 0.0f) memory_score = 0.0f;
    if (memory_score > 1.0f) memory_score = 1.0f;

    /* Search for existing domain entry */
    for (i = 0u; i < store->mastery_count; i++) {
        if (store->mastery[i].domain_id == domain_id) {
            m = &store->mastery[i];

            /* Exponential moving average: new = 0.7 * new + 0.3 * old
             * This prevents catastrophic forgetting while allowing
             * score updates to converge toward current performance. */
            m->route_score     = 0.7f * route_score     + 0.3f * m->route_score;
            m->structure_score = 0.7f * structure_score  + 0.3f * m->structure_score;
            m->memory_score    = 0.7f * memory_score     + 0.3f * m->memory_score;
            m->evidence_count += evidence;
            m->last_update_ts  = timestamp;

            /* Recompute mastery level */
            m->level = lin_compute_mastery(m->route_score,
                                            m->structure_score,
                                            m->memory_score);
            return XMIND_OK;
        }
    }

    /* Domain not found — create new entry */
    if (store->mastery_count >= XM_LINEAGE_MAX_DOMAINS) {
        return XMIND_ERR_NOMEM; /* -2: domains full */
    }

    m = &store->mastery[store->mastery_count];
    m->domain_id       = domain_id;
    m->route_score     = route_score;
    m->structure_score = structure_score;
    m->memory_score    = memory_score;
    m->evidence_count  = evidence;
    m->last_update_ts  = timestamp;
    m->level           = lin_compute_mastery(route_score, structure_score,
                                              memory_score);

    store->mastery_count++;
    return XMIND_OK;
}

/* ===================================================================
 * S6  MASTERY QUERY
 * =================================================================== */

const xmind_domain_mastery_t *xmind_lineage_get_mastery(
    const xmind_lineage_store_t *store,
    uint16_t domain_id)
{
    uint32_t i;

    if (!store || !store->initialized) {
        return (const xmind_domain_mastery_t *)0;
    }

    for (i = 0u; i < store->mastery_count; i++) {
        if (store->mastery[i].domain_id == domain_id) {
            return &store->mastery[i];
        }
    }

    return (const xmind_domain_mastery_t *)0;
}

/* ===================================================================
 * S7  DEPTH QUERY — Count deltas for a domain
 * =================================================================== */

uint32_t xmind_lineage_get_depth(const xmind_lineage_store_t *store,
                                  uint16_t domain_id)
{
    uint32_t i;
    uint32_t count = 0u;
    uint32_t limit;

    if (!store || !store->initialized) {
        return 0u;
    }

    /* Scan all valid deltas in the ring buffer */
    limit = (store->delta_count < XM_LINEAGE_MAX_DELTAS)
            ? store->delta_count
            : XM_LINEAGE_MAX_DELTAS;

    for (i = 0u; i < limit; i++) {
        if (store->deltas[i].domain_id == domain_id) {
            count++;
        }
    }

    return count;
}
