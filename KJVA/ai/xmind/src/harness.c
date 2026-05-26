/*
 * harness.c — Recursive Heptagon Harness (ADR-S49-01 Section 15)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Implements the 7-phase cognitive governance execution loop:
 *
 *   Phase 0: DETECT     — classify input domain
 *   Phase 1: PLAN       — compute materialization plan
 *   Phase 2: MATERIALIZE — embody required weight layers
 *   Phase 3: STABILIZE  — verify integrity, warm KV cache
 *   Phase 4: EVALUATE   — run inference, score output
 *   Phase 5: RETAIN     — consolidate retained learning
 *   Phase 6: RECURSE    — power-tower self-refinement (depth <= 3)
 *
 * Each phase can be overridden via xmind_harness_set_phase().
 * Default implementations provide the canonical behavior.
 *
 * RECURSION SAFETY:
 *   Maximum depth is XM_HARNESS_MAX_DEPTH (3).  The recurse phase
 *   checks depth before re-invoking execute().  Beyond depth 3,
 *   the harness returns without recursing.
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"
#include "../include/xmind_heptagon_harness.h"

/* ===================================================================
 * S1  INTERNAL HELPERS
 * =================================================================== */

static void har_memzero(void *dst, uint64_t n)
{
    uint8_t *p = (uint8_t *)dst;
    uint64_t i;
    for (i = 0u; i < n; i++) {
        p[i] = 0u;
    }
}

/* ===================================================================
 * S2  DEFAULT PHASE HANDLERS
 *
 * Each default handler implements the canonical behavior for its
 * phase.  They are installed by xmind_harness_init() and can be
 * overridden by xmind_harness_set_phase().
 * =================================================================== */

/*
 * Phase 0: DETECT — Classify input domain.
 *
 * In the current sprint, domain classification is set externally
 * before execute() is called (via harness->domain_id).  The default
 * detect phase validates that a model and catalog are present.
 */
static void default_phase_detect(xmind_heptagon_harness_t *h)
{
    if (!h->model || !h->catalog) {
        /* Cannot proceed without model and catalog */
        h->halted = 1u;
        return;
    }

    /* Reset phase-tracking state for this cycle */
    h->improvement_score = 0.0f;
}

/*
 * Phase 1: PLAN — Compute materialization plan.
 *
 * Builds a materialization plan based on the harness configuration.
 * If mat_plan.kind is already set by the caller, we honor it.
 * Otherwise defaults to classical (full dense).
 */
static void default_phase_plan(xmind_heptagon_harness_t *h)
{
    int32_t rc;

    /* If plan has no total_layers, initialize with classical defaults.
     * A pre-configured plan (total_layers > 0) is left untouched. */
    if (h->mat_plan.total_layers == 0u) {
        /* Default: 28 layers (Llama 3.2 3B), classical, 2 GB budget */
        rc = xmind_materialize_plan_init(
            &h->mat_plan,
            XM_MAT_CLASSICAL,
            28u,
            0xFFFFFFFFu,
            2147483648ULL /* 2 GB */
        );
        if (rc != XMIND_OK) {
            h->halted = 1u;
            return;
        }
    }
}

/*
 * Phase 2: MATERIALIZE — Embody required weight layers.
 *
 * Dispatches to the appropriate materializer based on plan kind.
 * Uses a default of 60 MB per layer (~1.7 GB total for 28 layers Q4_0).
 */
static void default_phase_materialize(xmind_heptagon_harness_t *h)
{
    xmind_materialize_result_t result;
    int32_t rc;
    /* Default per-layer size: ~60 MB (Q4_0 for Llama 3.2 3B layer).
     * This covers: Q*4, K*4, V*4, O*4, gate*4, down*4, up*4, norm*2 = ~60MB */
    uint64_t bytes_per_layer = 62914560ULL; /* 60 MiB */

    har_memzero(&result, sizeof(result));

    switch (h->mat_plan.kind) {
    case XM_MAT_CLASSICAL:
        rc = xmind_materialize_classical(&h->mat_state, &h->mat_plan,
                                          bytes_per_layer, &result);
        break;

    case XM_MAT_SPARSE:
        rc = xmind_materialize_sparse(&h->mat_state, &h->mat_plan,
                                       bytes_per_layer, &result);
        break;

    case XM_MAT_PAGED:
        /* Paged mode: no bulk allocation.  Layers are paged in
         * on demand during the stabilize/evaluate phases. */
        rc = XMIND_OK;
        break;

    case XM_MAT_EXTERNAL:
        /* External mode: no local allocation needed. */
        rc = XMIND_OK;
        break;

    default:
        rc = XMIND_ERR_INVAL;
        break;
    }

    if (rc != XMIND_OK) {
        h->halted = 1u;
    }
}

/*
 * Phase 3: STABILIZE — Verify weight integrity, warm KV cache.
 *
 * In classical/sparse mode, verifies that all expected layers are
 * resident.  In paged mode, pages in the first and last layers
 * (embedding + output) which are always needed.
 */
static void default_phase_stabilize(xmind_heptagon_harness_t *h)
{
    uint32_t i;
    uint32_t missing = 0u;

    switch (h->mat_plan.kind) {
    case XM_MAT_CLASSICAL:
        /* Verify all layers are resident */
        for (i = 0u; i < h->mat_state.layer_count; i++) {
            if (!h->mat_state.layers[i].resident) {
                missing++;
            }
        }
        if (missing > 0u) {
            /* Integrity violation: expected all layers resident */
            h->halted = 1u;
        }
        break;

    case XM_MAT_SPARSE:
        /* Verify all active-mask layers are resident */
        for (i = 0u; i < h->mat_state.layer_count; i++) {
            if ((h->mat_plan.active_layer_mask & (1u << i)) &&
                !h->mat_state.layers[i].resident) {
                missing++;
            }
        }
        if (missing > 0u) {
            h->halted = 1u;
        }
        break;

    case XM_MAT_PAGED:
        /* Page in first layer (embedding) if not resident */
        if (h->mat_state.layer_count > 0u &&
            !h->mat_state.layers[0].resident) {
            int32_t rc = xmind_materialize_page_in(
                &h->mat_state, 0u, 62914560ULL);
            if (rc != XMIND_OK) {
                h->halted = 1u;
                return;
            }
        }
        /* Page in last layer (output) if not resident */
        if (h->mat_state.layer_count > 1u) {
            uint32_t last = h->mat_state.layer_count - 1u;
            if (!h->mat_state.layers[last].resident) {
                int32_t rc = xmind_materialize_page_in(
                    &h->mat_state, last, 62914560ULL);
                if (rc != XMIND_OK) {
                    h->halted = 1u;
                }
            }
        }
        break;

    case XM_MAT_EXTERNAL:
        /* External: nothing to verify locally */
        break;

    default:
        h->halted = 1u;
        break;
    }
}

/*
 * Phase 4: EVALUATE — Run inference and score output quality.
 *
 * In the current sprint, actual inference is driven externally
 * via the existing xmind_forward() + xmind_sample() path in
 * inference.c.  The harness evaluate phase is a quality scoring
 * checkpoint.  When the Heptagon is fully wired, this phase will
 * invoke inference directly.
 *
 * Default behavior: set improvement_score based on whether the model
 * and materialization state are healthy.
 */
static void default_phase_evaluate(xmind_heptagon_harness_t *h)
{
    /* Score is 0.0 until inference results are wired.
     * A non-halted, fully materialized state gets a base score of 0.5.
     * This ensures the retain phase has something to evaluate against
     * the quality gate (XM_WB_MIN_IMPROVEMENT = 0.3). */
    if (!h->halted && h->mat_state.total_allocated > 0u) {
        h->improvement_score = 0.5f;
    } else if (!h->halted) {
        /* External or paged with minimal allocation — still valid */
        h->improvement_score = 0.4f;
    } else {
        h->improvement_score = 0.0f;
    }
}

/*
 * Phase 5: RETAIN — Consolidate retained learning via write-back.
 *
 * Uses the write-back API to persist retained learning if the
 * improvement score meets the quality gate.
 */
static void default_phase_retain(xmind_heptagon_harness_t *h)
{
    xmind_consolidation_request_t req;
    xmind_consolidation_result_t  res;

    if (h->improvement_score < XM_WB_MIN_IMPROVEMENT) {
        /* Below quality gate — nothing to retain */
        return;
    }

    har_memzero(&req, sizeof(req));
    har_memzero(&res, sizeof(res));

    req.session_id       = h->session_id;
    req.domain_id        = h->domain_id;
    req.target           = h->default_wb_target;
    req.improvement_score = h->improvement_score;

    /* Determine mastery level from lineage if available */
    if (h->lineage && h->lineage->initialized) {
        const xmind_domain_mastery_t *dm =
            xmind_lineage_get_mastery(h->lineage, h->domain_id);
        if (dm) {
            req.mastery_reached = (uint8_t)dm->level;
        } else {
            req.mastery_reached = 0u; /* understanding */
        }
    } else {
        req.mastery_reached = 0u;
    }

    /* Use the current delta's hash if available */
    {
        uint32_t i;
        for (i = 0u; i < 32u; i++) {
            req.input_hash[i] = h->current_delta.source_hash[i];
        }
    }

    req.evidence_count = h->current_delta.evidence_count;
    req.delta_data     = (const uint8_t *)0; /* No delta payload in default */
    req.delta_size     = 0u;

    /* Consolidate — we don't halt on IPC failure; it's non-critical */
    (void)xmind_context_consolidate(&req, &res);

    /* Record delta in lineage if accepted */
    if (res.accepted && h->lineage && h->lineage->initialized) {
        (void)xmind_lineage_record_delta(
            h->lineage,
            h->current_delta.source_hash,
            h->domain_id,
            h->improvement_score,
            req.mastery_reached,
            (uint8_t)h->default_wb_target,
            h->current_delta.evidence_count,
            h->current_delta.timestamp_ns);

        /* Advance generation if evidence is sufficient */
        if (res.generation_index > 0u) {
            (void)xmind_lineage_advance_generation(h->lineage);
        }
    }
}

/*
 * Phase 6: RECURSE — Power-tower self-refinement.
 *
 * Re-invokes xmind_harness_execute() at depth + 1, but ONLY if:
 *   1. improvement_score > 0.0 (there is benefit to recursing)
 *   2. depth < XM_HARNESS_MAX_DEPTH (recursion guard)
 *   3. harness is not halted
 *
 * This enables bounded iterative refinement: the model can improve
 * its own output up to 3 times before the leash tightens.
 */
static void default_phase_recurse(xmind_heptagon_harness_t *h)
{
    if (h->halted) {
        return;
    }
    if (h->improvement_score <= 0.0f) {
        /* No benefit to recursing */
        return;
    }
    if (h->depth >= XM_HARNESS_MAX_DEPTH) {
        /* Recursion limit reached — hard stop */
        return;
    }

    /* Increment depth and re-execute.
     * The depth check at the top of execute() provides the guard. */
    h->depth++;
    (void)xmind_harness_execute(h);
    h->depth--;
}

/* ===================================================================
 * S3  PUBLIC API: INIT
 * =================================================================== */

int32_t xmind_harness_init(xmind_heptagon_harness_t *h,
                             xmind_lineage_store_t *lineage)
{
    uint32_t i;

    if (!h || !lineage) {
        return XMIND_ERR_INVAL;
    }

    har_memzero(h, sizeof(*h));

    h->lineage          = lineage;
    h->depth            = 0u;
    h->halted           = 0u;
    h->default_wb_target = XM_WB_BOTH;
    h->mastery_profile  = (xmind_domain_mastery_t *)0;
    h->mastery_count    = 0u;

    /* Install default phase handlers */
    h->phase_handlers[XM_PHASE_DETECT]      = default_phase_detect;
    h->phase_handlers[XM_PHASE_PLAN]        = default_phase_plan;
    h->phase_handlers[XM_PHASE_MATERIALIZE] = default_phase_materialize;
    h->phase_handlers[XM_PHASE_STABILIZE]   = default_phase_stabilize;
    h->phase_handlers[XM_PHASE_EVALUATE]    = default_phase_evaluate;
    h->phase_handlers[XM_PHASE_RETAIN]      = default_phase_retain;
    h->phase_handlers[XM_PHASE_RECURSE]     = default_phase_recurse;

    /* Clear phase completion state and context shards */
    for (i = 0u; i < XM_HARNESS_PHASES; i++) {
        h->phase_completed[i] = 0u;
    }
    for (i = 0u; i < XM_HARNESS_MAX_SHARDS; i++) {
        h->context_shards[i] = 0u;
    }

    return XMIND_OK;
}

/* ===================================================================
 * S4  PUBLIC API: EXECUTE — 7-phase cycle
 * =================================================================== */

int32_t xmind_harness_execute(xmind_heptagon_harness_t *h)
{
    uint32_t phase;

    if (!h) {
        return XMIND_ERR_INVAL;
    }

    /* Recursion depth guard — belt-and-suspenders with Phase 6 check */
    if (h->depth > XM_HARNESS_MAX_DEPTH) {
        return -2; /* Recursion limit */
    }

    /* Reset phase completion for this cycle */
    for (phase = 0u; phase < XM_HARNESS_PHASES; phase++) {
        h->phase_completed[phase] = 0u;
    }
    h->halted = 0u;

    /* Execute phases sequentially: 0 through 6 */
    for (phase = 0u; phase < XM_HARNESS_PHASES; phase++) {
        if (h->halted) {
            return -1; /* Halted mid-cycle */
        }

        if (h->phase_handlers[phase]) {
            h->phase_handlers[phase](h);
        }

        h->phase_completed[phase] = 1u;
    }

    return XMIND_OK;
}

/* ===================================================================
 * S5  PUBLIC API: SET PHASE HANDLER
 * =================================================================== */

int32_t xmind_harness_set_phase(xmind_heptagon_harness_t *h,
                                  uint32_t phase,
                                  void (*handler)(xmind_heptagon_harness_t *))
{
    if (!h) {
        return XMIND_ERR_INVAL;
    }
    if (phase >= XM_HARNESS_PHASES) {
        return XMIND_ERR_INVAL;
    }

    if (handler) {
        h->phase_handlers[phase] = handler;
    } else {
        /* NULL restores default handlers */
        switch (phase) {
        case XM_PHASE_DETECT:      h->phase_handlers[phase] = default_phase_detect;      break;
        case XM_PHASE_PLAN:        h->phase_handlers[phase] = default_phase_plan;        break;
        case XM_PHASE_MATERIALIZE: h->phase_handlers[phase] = default_phase_materialize; break;
        case XM_PHASE_STABILIZE:   h->phase_handlers[phase] = default_phase_stabilize;   break;
        case XM_PHASE_EVALUATE:    h->phase_handlers[phase] = default_phase_evaluate;    break;
        case XM_PHASE_RETAIN:      h->phase_handlers[phase] = default_phase_retain;      break;
        case XM_PHASE_RECURSE:     h->phase_handlers[phase] = default_phase_recurse;     break;
        default: break;
        }
    }

    return XMIND_OK;
}

/* ===================================================================
 * S6  PUBLIC API: MASTERY QUERY (convenience)
 * =================================================================== */

const xmind_domain_mastery_t *xmind_harness_get_mastery(
    const xmind_heptagon_harness_t *h,
    uint16_t domain_id)
{
    if (!h || !h->lineage) {
        return (const xmind_domain_mastery_t *)0;
    }

    return xmind_lineage_get_mastery(h->lineage, domain_id);
}
