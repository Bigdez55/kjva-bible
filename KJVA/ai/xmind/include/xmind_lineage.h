/*
 * xmind_lineage.h — Lineage & Intelligence Estate (ADR-S49-01 Section 16)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Tracks the inheritance lineage of XMIND intelligence: every delta
 *   (retained learning event), generation advancement, and per-domain
 *   mastery level.  This is the "intelligence estate" — the complete
 *   provenance chain from initial weights through every assimilation
 *   cycle.
 *
 * MASTERY MODEL (ADR Section 5):
 *   0 = Understanding: surface pattern recognition, route-level only
 *   1 = Innerstanding: structural comprehension, can explain "why"
 *   2 = Overstanding: generative mastery, can extend and create novel
 *
 *   Mastery is per-domain (up to 64 domains tracked).  Advancement
 *   requires evidence_count >= 3 and improvement_score >= 0.3.
 *
 * GENERATION MODEL:
 *   Each entity (model instance) has a monotonic generation counter.
 *   A generation advances when a consolidation produces accepted deltas
 *   with sufficient evidence.  The generation index establishes lineage
 *   ordering: gen N+1 inherits from gen N.
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef XMIND_LINEAGE_H
#define XMIND_LINEAGE_H

#ifdef PAL_FREESTANDING
#include "../../../pal/include/pal.h"
#else
#include <stdint.h>
#include <stddef.h>
#endif

/* ===================================================================
 * S1  MASTERY LEVEL ENUM — per ADR Section 5
 * =================================================================== */

typedef enum {
    XM_MASTERY_UNDERSTANDING = 0,  /* Surface pattern recognition         */
    XM_MASTERY_INNERSTANDING = 1,  /* Structural comprehension            */
    XM_MASTERY_OVERSTANDING  = 2   /* Generative mastery                  */
} xmind_mastery_level_t;

/* ===================================================================
 * S2  LINEAGE DELTA — One inheritance event
 *
 * Records the provenance of a single retained learning event.
 * source_hash links back to the r1_per_signal_t that triggered it.
 * =================================================================== */

typedef struct {
    uint8_t   source_hash[32];     /* SHA-256 of source artifact          */
    uint16_t  domain_id;           /* Domain classification               */
    float     improvement_score;   /* Evidence of benefit (0.0-1.0)       */
    uint32_t  generation_index;    /* Generation when this delta recorded */
    uint8_t   mastery_reached;     /* XM_MASTERY_* level achieved         */
    uint8_t   retention_target;    /* 0=private, 1=archive, 2=both        */
    uint64_t  timestamp_ns;        /* PAL timestamp in nanoseconds        */
    uint32_t  evidence_count;      /* Supporting evidence instances       */
} xmind_lineage_delta_t;

/* 32 (hash) + 2 (domain) + 2 (pad) + 4 (score) + 4 (gen) + 1+1 (mastery,target)
 * + 2 (pad) + 8 (ts) + 4 (evidence) + 4 (pad) = 64 bytes with natural alignment */
_Static_assert(sizeof(xmind_lineage_delta_t) == 64u,
               "lineage delta must be 64 bytes");

/* ===================================================================
 * S3  PER-DOMAIN MASTERY RECORD — per ADR Section 5.4
 *
 * Tracks mastery metrics for a single knowledge domain.  The three
 * sub-scores (route, structure, memory) map to the mastery model:
 *   route     -> understanding (pattern matching accuracy)
 *   structure -> innerstanding (explanation quality)
 *   memory    -> overstanding  (generative novelty)
 * =================================================================== */

typedef struct {
    uint16_t              domain_id;       /* Domain identifier            */
    xmind_mastery_level_t level;           /* Current mastery level        */
    float                 route_score;     /* Understanding metric 0.0-1.0 */
    float                 structure_score; /* Innerstanding metric 0.0-1.0 */
    float                 memory_score;    /* Overstanding metric 0.0-1.0  */
    uint32_t              evidence_count;  /* Cumulative evidence count    */
    uint64_t              last_update_ts;  /* Last update timestamp (ns)   */
} xmind_domain_mastery_t;

/* ===================================================================
 * S4  LINEAGE STORE — Per-entity inheritance record
 *
 * Stores the complete provenance chain for one model instance.
 * Max 256 deltas and 64 domains are hard limits — exceeding them
 * requires a compaction pass (oldest deltas are merged).
 * =================================================================== */

#define XM_LINEAGE_MAX_DELTAS   256u
#define XM_LINEAGE_MAX_DOMAINS   64u

typedef struct {
    xmind_lineage_delta_t   deltas[XM_LINEAGE_MAX_DELTAS];
    uint32_t                delta_count;
    uint32_t                current_generation;
    xmind_domain_mastery_t  mastery[XM_LINEAGE_MAX_DOMAINS];
    uint32_t                mastery_count;
    uint8_t                 initialized;    /* 1 = store is valid          */
    uint8_t                 _pad[3];
} xmind_lineage_store_t;

/* ===================================================================
 * S5  PUBLIC API
 * =================================================================== */

/*
 * xmind_lineage_init — Initialize a lineage store.
 *
 * Zeroes all fields and sets initialized=1.
 *
 * @param store   Store to initialize (caller-allocated)
 * @return        0 on success, -1 if store is NULL
 */
int32_t xmind_lineage_init(xmind_lineage_store_t *store);

/*
 * xmind_lineage_record_delta — Record a new inheritance delta.
 *
 * Appends a delta to the store.  If the store is full (256 deltas),
 * the oldest delta is overwritten (ring buffer behavior).
 *
 * @param store       Lineage store
 * @param source_hash SHA-256 of source artifact (32 bytes)
 * @param domain_id   Domain classification
 * @param score       Improvement score (0.0-1.0)
 * @param mastery     Mastery level reached
 * @param target      Retention target (0=private, 1=archive, 2=both)
 * @param evidence    Evidence count
 * @param timestamp   Timestamp in nanoseconds
 * @return            0 on success, -1 on invalid params
 */
int32_t xmind_lineage_record_delta(xmind_lineage_store_t *store,
                                    const uint8_t *source_hash,
                                    uint16_t domain_id,
                                    float score,
                                    uint8_t mastery,
                                    uint8_t target,
                                    uint32_t evidence,
                                    uint64_t timestamp);

/*
 * xmind_lineage_advance_generation — Increment the generation counter.
 *
 * Only advances if the latest delta has sufficient evidence (>= 3).
 *
 * @param store   Lineage store
 * @return        New generation index, or current if insufficient evidence
 */
uint32_t xmind_lineage_advance_generation(xmind_lineage_store_t *store);

/*
 * xmind_lineage_update_mastery — Update mastery record for a domain.
 *
 * Creates a new domain entry if domain_id is not yet tracked.
 * Updates scores and recalculates mastery level based on thresholds:
 *   Understanding: route >= 0.3
 *   Innerstanding: route >= 0.5 AND structure >= 0.4
 *   Overstanding:  route >= 0.7 AND structure >= 0.6 AND memory >= 0.5
 *
 * @param store           Lineage store
 * @param domain_id       Domain to update
 * @param route_score     Understanding metric
 * @param structure_score Innerstanding metric
 * @param memory_score    Overstanding metric
 * @param evidence        Evidence count for this update
 * @param timestamp       Timestamp in nanoseconds
 * @return                0 on success, -1 on invalid, -2 if domains full
 */
int32_t xmind_lineage_update_mastery(xmind_lineage_store_t *store,
                                      uint16_t domain_id,
                                      float route_score,
                                      float structure_score,
                                      float memory_score,
                                      uint32_t evidence,
                                      uint64_t timestamp);

/*
 * xmind_lineage_get_mastery — Query mastery for a domain.
 *
 * @param store     Lineage store
 * @param domain_id Domain to query
 * @return          Pointer to mastery record, or NULL if not found
 */
const xmind_domain_mastery_t *xmind_lineage_get_mastery(
    const xmind_lineage_store_t *store,
    uint16_t domain_id);

/*
 * xmind_lineage_get_depth — Query total delta depth for a domain.
 *
 * Counts all deltas matching the given domain_id.
 *
 * @param store     Lineage store
 * @param domain_id Domain to query
 * @return          Number of deltas for this domain
 */
uint32_t xmind_lineage_get_depth(const xmind_lineage_store_t *store,
                                  uint16_t domain_id);

#endif /* XMIND_LINEAGE_H */
