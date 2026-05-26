/*
 * materialize.c — Role-Based Materialization Layer (ADR-S49-01 Phase 2)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Implements the materialization doctrine: classical (full dense),
 * sparse (active mask only), and paged (on-demand page-in/out).
 *
 * Memory allocation uses xm_heap_alloc / xm_heap_free which are
 * backed by PAL page pool with handle tracking (see xmind.c).
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"
#include "../include/xmind_materialize.h"

/* ===================================================================
 * S1  INTERNAL HELPERS
 * =================================================================== */

/* Count set bits in a 32-bit mask */
static uint32_t mat_popcount32(uint32_t x)
{
    uint32_t count = 0u;
    while (x) {
        count += (x & 1u);
        x >>= 1u;
    }
    return count;
}

/* Zero a block of memory */
static void mat_memzero(void *dst, uint64_t n)
{
    uint8_t *p = (uint8_t *)dst;
    uint64_t i;
    for (i = 0u; i < n; i++) {
        p[i] = 0u;
    }
}

/* ===================================================================
 * S2  PLAN INITIALIZATION
 * =================================================================== */

int32_t xmind_materialize_plan_init(xmind_materialize_plan_t *plan,
                                     xmind_materialization_kind_t kind,
                                     uint32_t total_layers,
                                     uint32_t active_mask,
                                     uint64_t budget_bytes)
{
    uint32_t i;
    uint32_t active_count;

    if (!plan) {
        return XMIND_ERR_INVAL;
    }
    if (total_layers == 0u || total_layers > XM_MAT_MAX_LAYERS) {
        return XMIND_ERR_INVAL;
    }
    if (kind == XM_MAT_QUDIT_SIM) {
        /* Qudit simulation is experimental — not yet implemented.
         * Reject gracefully so callers get a clear signal. */
        return XMIND_ERR_INVAL;
    }

    mat_memzero(plan, sizeof(*plan));

    plan->kind         = kind;
    plan->total_layers = total_layers;
    plan->budget_bytes = budget_bytes;

    switch (kind) {
    case XM_MAT_CLASSICAL:
        /* All layers embodied — mask covers total_layers bits */
        plan->active_layer_mask = (total_layers >= 32u)
            ? 0xFFFFFFFFu
            : ((1u << total_layers) - 1u);
        plan->sparsity_ratio = 0.0f;
        for (i = 0u; i < total_layers; i++) {
            plan->page_resident[i] = 1u;
        }
        break;

    case XM_MAT_SPARSE:
        /* Only layers in active_mask are embodied.
         * Mask bits beyond total_layers are cleared. */
        if (total_layers < 32u) {
            plan->active_layer_mask = active_mask & ((1u << total_layers) - 1u);
        } else {
            plan->active_layer_mask = active_mask;
        }
        active_count = mat_popcount32(plan->active_layer_mask);
        plan->sparsity_ratio = (total_layers > 0u)
            ? 1.0f - ((float)active_count / (float)total_layers)
            : 0.0f;
        for (i = 0u; i < total_layers; i++) {
            plan->page_resident[i] =
                (plan->active_layer_mask & (1u << i)) ? 1u : 0u;
        }
        break;

    case XM_MAT_PAGED:
        /* Paged: start with nothing resident.
         * Caller uses page_in/page_out to manage residence. */
        plan->active_layer_mask = 0u;
        plan->sparsity_ratio = 1.0f;
        /* All layers start as paged-out */
        break;

    case XM_MAT_EXTERNAL:
        /* External: no local materialization at all.
         * All computation is routed to a co-processor. */
        plan->active_layer_mask = 0u;
        plan->sparsity_ratio = 1.0f;
        break;

    default:
        return XMIND_ERR_INVAL;
    }

    plan->embodied_bytes = 0u; /* Filled after actual allocation */
    return XMIND_OK;
}

/* ===================================================================
 * S3  CLASSICAL MATERIALIZATION — Full dense
 * =================================================================== */

int32_t xmind_materialize_classical(xmind_materialize_state_t *state,
                                     const xmind_materialize_plan_t *plan,
                                     uint64_t bytes_per_layer,
                                     xmind_materialize_result_t *result)
{
    uint32_t i;
    uint64_t total_needed;
    void    *buf;

    if (!state || !plan || !result) {
        return XMIND_ERR_INVAL;
    }
    if (plan->kind != XM_MAT_CLASSICAL) {
        return XMIND_ERR_INVAL;
    }
    if (plan->total_layers == 0u || plan->total_layers > XM_MAT_MAX_LAYERS) {
        return XMIND_ERR_INVAL;
    }

    total_needed = (uint64_t)plan->total_layers * bytes_per_layer;
    if (plan->budget_bytes > 0u && total_needed > plan->budget_bytes) {
        return XMIND_ERR_NOMEM;
    }

    mat_memzero(state, sizeof(*state));
    state->plan       = *plan;
    state->layer_count = plan->total_layers;

    for (i = 0u; i < plan->total_layers; i++) {
        buf = xm_heap_alloc(bytes_per_layer);
        if (!buf) {
            /* OOM: roll back all previous allocations */
            uint32_t j;
            for (j = 0u; j < i; j++) {
                if (state->layers[j].data) {
                    xm_heap_free(state->layers[j].data);
                    state->layers[j].data     = (void *)0;
                    state->layers[j].resident = 0u;
                }
            }
            state->total_allocated = 0u;
            return XMIND_ERR_NOMEM;
        }

        state->layers[i].data        = buf;
        state->layers[i].size_bytes  = bytes_per_layer;
        state->layers[i].layer_index = i;
        state->layers[i].resident    = 1u;
        state->layers[i].dirty       = 0u;
        state->total_allocated      += bytes_per_layer;
    }

    if (state->total_allocated > state->peak_allocated) {
        state->peak_allocated = state->total_allocated;
    }

    result->realized_kind    = XM_MAT_CLASSICAL;
    result->layers_embodied  = plan->total_layers;
    result->bytes_used       = state->total_allocated;
    result->bytes_saved      = 0u;
    result->realized_sparsity = 0.0f;

    return XMIND_OK;
}

/* ===================================================================
 * S4  SPARSE MATERIALIZATION — Active mask only
 * =================================================================== */

int32_t xmind_materialize_sparse(xmind_materialize_state_t *state,
                                  const xmind_materialize_plan_t *plan,
                                  uint64_t bytes_per_layer,
                                  xmind_materialize_result_t *result)
{
    uint32_t i;
    uint64_t dense_total;
    uint32_t active_count = 0u;
    void    *buf;

    if (!state || !plan || !result) {
        return XMIND_ERR_INVAL;
    }
    if (plan->kind != XM_MAT_SPARSE) {
        return XMIND_ERR_INVAL;
    }
    if (plan->total_layers == 0u || plan->total_layers > XM_MAT_MAX_LAYERS) {
        return XMIND_ERR_INVAL;
    }

    mat_memzero(state, sizeof(*state));
    state->plan       = *plan;
    state->layer_count = plan->total_layers;

    dense_total = (uint64_t)plan->total_layers * bytes_per_layer;

    for (i = 0u; i < plan->total_layers; i++) {
        if (!(plan->active_layer_mask & (1u << i))) {
            /* Layer not in active mask — leave evicted */
            state->layers[i].data        = (void *)0;
            state->layers[i].size_bytes  = 0u;
            state->layers[i].layer_index = i;
            state->layers[i].resident    = 0u;
            continue;
        }

        /* Check budget before allocating */
        if (plan->budget_bytes > 0u &&
            (state->total_allocated + bytes_per_layer) > plan->budget_bytes) {
            /* Budget exceeded: stop allocating, report partial */
            break;
        }

        buf = xm_heap_alloc(bytes_per_layer);
        if (!buf) {
            /* OOM: roll back */
            uint32_t j;
            for (j = 0u; j < i; j++) {
                if (state->layers[j].data) {
                    xm_heap_free(state->layers[j].data);
                    state->layers[j].data     = (void *)0;
                    state->layers[j].resident = 0u;
                }
            }
            state->total_allocated = 0u;
            return XMIND_ERR_NOMEM;
        }

        state->layers[i].data        = buf;
        state->layers[i].size_bytes  = bytes_per_layer;
        state->layers[i].layer_index = i;
        state->layers[i].resident    = 1u;
        state->layers[i].dirty       = 0u;
        state->total_allocated      += bytes_per_layer;
        active_count++;
    }

    if (state->total_allocated > state->peak_allocated) {
        state->peak_allocated = state->total_allocated;
    }

    result->realized_kind     = XM_MAT_SPARSE;
    result->layers_embodied   = active_count;
    result->bytes_used        = state->total_allocated;
    result->bytes_saved       = dense_total - state->total_allocated;
    result->realized_sparsity = (plan->total_layers > 0u)
        ? 1.0f - ((float)active_count / (float)plan->total_layers)
        : 0.0f;

    return XMIND_OK;
}

/* ===================================================================
 * S5  PAGED MATERIALIZATION — page-in / page-out
 * =================================================================== */

int32_t xmind_materialize_page_in(xmind_materialize_state_t *state,
                                   uint32_t layer_index,
                                   uint64_t bytes)
{
    void *buf;

    if (!state) {
        return XMIND_ERR_INVAL;
    }
    if (layer_index >= state->layer_count) {
        return XMIND_ERR_INVAL;
    }
    if (state->layers[layer_index].resident) {
        /* Already resident — no-op success */
        return XMIND_OK;
    }

    /* Check budget */
    if (state->plan.budget_bytes > 0u &&
        (state->total_allocated + bytes) > state->plan.budget_bytes) {
        return XMIND_ERR_NOMEM;
    }

    buf = xm_heap_alloc(bytes);
    if (!buf) {
        return XMIND_ERR_NOMEM;
    }

    state->layers[layer_index].data       = buf;
    state->layers[layer_index].size_bytes = bytes;
    state->layers[layer_index].resident   = 1u;
    state->layers[layer_index].dirty      = 0u;
    state->total_allocated               += bytes;

    if (state->total_allocated > state->peak_allocated) {
        state->peak_allocated = state->total_allocated;
    }

    /* Update plan mask */
    state->plan.active_layer_mask |= (1u << layer_index);
    state->plan.page_resident[layer_index] = 1u;
    state->page_in_count++;

    /* Recalculate sparsity */
    {
        uint32_t active = mat_popcount32(state->plan.active_layer_mask);
        state->plan.sparsity_ratio = (state->layer_count > 0u)
            ? 1.0f - ((float)active / (float)state->layer_count)
            : 0.0f;
    }

    return XMIND_OK;
}

int32_t xmind_materialize_page_out(xmind_materialize_state_t *state,
                                    uint32_t layer_index)
{
    if (!state) {
        return XMIND_ERR_INVAL;
    }
    if (layer_index >= state->layer_count) {
        return XMIND_ERR_INVAL;
    }
    if (!state->layers[layer_index].resident) {
        /* Already evicted — no-op success */
        return XMIND_OK;
    }

    /* Free the buffer */
    if (state->layers[layer_index].data) {
        xm_heap_free(state->layers[layer_index].data);
    }

    state->total_allocated -= state->layers[layer_index].size_bytes;
    state->layers[layer_index].data       = (void *)0;
    state->layers[layer_index].size_bytes = 0u;
    state->layers[layer_index].resident   = 0u;
    state->layers[layer_index].dirty      = 0u;

    /* Update plan mask */
    state->plan.active_layer_mask &= ~(1u << layer_index);
    state->plan.page_resident[layer_index] = 0u;
    state->page_out_count++;

    /* Recalculate sparsity */
    {
        uint32_t active = mat_popcount32(state->plan.active_layer_mask);
        state->plan.sparsity_ratio = (state->layer_count > 0u)
            ? 1.0f - ((float)active / (float)state->layer_count)
            : 0.0f;
    }

    return XMIND_OK;
}

/* ===================================================================
 * S6  REPORT — Snapshot of current state
 * =================================================================== */

int32_t xmind_materialize_report(const xmind_materialize_state_t *state,
                                  xmind_materialize_result_t *result)
{
    uint32_t i;
    uint32_t resident_count = 0u;

    if (!state || !result) {
        return XMIND_ERR_INVAL;
    }

    for (i = 0u; i < state->layer_count; i++) {
        if (state->layers[i].resident) {
            resident_count++;
        }
    }

    result->realized_kind     = state->plan.kind;
    result->layers_embodied   = resident_count;
    result->bytes_used        = state->total_allocated;
    result->bytes_saved       = (state->peak_allocated > state->total_allocated)
        ? (state->peak_allocated - state->total_allocated)
        : 0u;
    result->realized_sparsity = (state->layer_count > 0u)
        ? 1.0f - ((float)resident_count / (float)state->layer_count)
        : 0.0f;

    return XMIND_OK;
}

/* ===================================================================
 * S7  TEARDOWN — Free all materialized buffers
 * =================================================================== */

void xmind_materialize_teardown(xmind_materialize_state_t *state)
{
    uint32_t i;

    if (!state) {
        return;
    }

    for (i = 0u; i < state->layer_count; i++) {
        if (state->layers[i].data) {
            xm_heap_free(state->layers[i].data);
            state->layers[i].data     = (void *)0;
            state->layers[i].resident = 0u;
        }
        state->layers[i].size_bytes = 0u;
    }

    state->total_allocated = 0u;
    state->layer_count     = 0u;
}
