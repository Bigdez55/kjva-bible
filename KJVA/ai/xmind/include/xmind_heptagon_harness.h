/*
 * xmind_heptagon_harness.h — Recursive Heptagon Harness (ADR-S49-01 Section 15)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Defines the END-STATE target structure for the Heptagon cognitive
 *   governance harness.  This is the 7-phase execution loop that drives
 *   XMIND through:
 *
 *     Phase 0: DETECT   — classify input, identify domain
 *     Phase 1: PLAN     — compute materialization plan
 *     Phase 2: MATERIALIZE — embody required layers
 *     Phase 3: STABILIZE — verify weight integrity, warm KV cache
 *     Phase 4: EVALUATE  — run inference, score output quality
 *     Phase 5: RETAIN    — consolidate retained learning
 *     Phase 6: RECURSE   — power-tower recursion (depth-guarded)
 *
 *   The harness ties together materialization (Phase 2), inference
 *   (Phases 3-4), write-back (Phase 5), and lineage (Phase 6).
 *
 * RECURSION GUARD:
 *   Maximum recursion depth is 3 (power-tower bound).  Beyond depth 3,
 *   the harness returns without recursing.  This prevents unbounded
 *   self-improvement loops while allowing bounded refinement.
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef XMIND_HEPTAGON_HARNESS_H
#define XMIND_HEPTAGON_HARNESS_H

#ifdef PAL_FREESTANDING
#include "../../../pal/include/pal.h"
#else
#include <stdint.h>
#include <stddef.h>
#endif

#include "xmind_materialize.h"
#include "xmind_writeback.h"
#include "xmind_lineage.h"

/* ===================================================================
 * S1  CONSTANTS
 * =================================================================== */

#define XM_HARNESS_PHASES       7u    /* detect, plan, materialize,
                                         stabilize, evaluate, retain,
                                         recurse                        */
#define XM_HARNESS_MAX_DEPTH    3u    /* Power-tower recursion bound    */
#define XM_HARNESS_MAX_SHARDS   7u    /* Law of seven (context shards)  */

/* Phase indices */
#define XM_PHASE_DETECT         0u
#define XM_PHASE_PLAN           1u
#define XM_PHASE_MATERIALIZE    2u
#define XM_PHASE_STABILIZE      3u
#define XM_PHASE_EVALUATE       4u
#define XM_PHASE_RETAIN         5u
#define XM_PHASE_RECURSE        6u

/* ===================================================================
 * S2  HARNESS STRUCTURE — per ADR Section 15.3
 * =================================================================== */

typedef struct xmind_heptagon_harness {
    /* ── Model and artifact ─────────────────────────────────────────── */
    void                       *model;          /* xmind_model_t*       */
    void                       *catalog;        /* gguf_catalog_t*      */
    const void                 *interp;         /* xmind_artifact_interp_t* */

    /* ── Materialization ────────────────────────────────────────────── */
    xmind_materialize_plan_t    mat_plan;
    xmind_materialize_state_t   mat_state;

    /* ── Cognitive state ────────────────────────────────────────────── */
    uint32_t                    depth;          /* Current recursion depth */
    float                       improvement_score;
    uint64_t                    context_shards[XM_HARNESS_MAX_SHARDS];

    /* ── Mastery — per-domain, NOT single byte ──────────────────────── */
    xmind_domain_mastery_t     *mastery_profile;
    uint32_t                    mastery_count;

    /* ── Seven-phase handlers ───────────────────────────────────────── */
    void (*phase_handlers[XM_HARNESS_PHASES])(struct xmind_heptagon_harness *);

    /* ── Lineage ────────────────────────────────────────────────────── */
    xmind_lineage_delta_t       current_delta;
    xmind_lineage_store_t      *lineage;

    /* ── Write-back ─────────────────────────────────────────────────── */
    xmind_writeback_target_t    default_wb_target;

    /* ── Session tracking ───────────────────────────────────────────── */
    uint32_t                    session_id;
    uint16_t                    domain_id;

    /* ── Phase execution state ──────────────────────────────────────── */
    uint8_t                     phase_completed[XM_HARNESS_PHASES];
    uint8_t                     halted;         /* 1 = abort cycle       */
    uint8_t                     _pad;
} xmind_heptagon_harness_t;

/* ===================================================================
 * S3  PUBLIC API
 * =================================================================== */

/*
 * xmind_harness_init — Initialize a heptagon harness.
 *
 * Zeroes all fields, sets recursion depth to 0, installs default
 * phase handlers, and links the lineage store.
 *
 * @param h        Harness to initialize (caller-allocated)
 * @param lineage  Lineage store (must be initialized separately)
 * @return         0 on success, -1 if h or lineage is NULL
 */
int32_t xmind_harness_init(xmind_heptagon_harness_t *h,
                             xmind_lineage_store_t *lineage);

/*
 * xmind_harness_execute — Run the 7-phase cycle.
 *
 * Executes: detect -> plan -> materialize -> stabilize -> evaluate
 *           -> retain -> recurse (if depth < XM_HARNESS_MAX_DEPTH).
 *
 * If any phase sets h->halted = 1, execution stops immediately.
 * The recurse phase increments depth and re-invokes execute()
 * only if improvement_score > 0.0 and depth < MAX_DEPTH.
 *
 * @param h   Harness with model, catalog, and interp set
 * @return    0 on success, -1 on halt, -2 on recursion limit
 */
int32_t xmind_harness_execute(xmind_heptagon_harness_t *h);

/*
 * xmind_harness_set_phase — Set a custom handler for a phase.
 *
 * @param h       Harness
 * @param phase   Phase index (0-6, use XM_PHASE_* constants)
 * @param handler Function pointer (NULL restores default)
 * @return        0 on success, -1 on invalid phase
 */
int32_t xmind_harness_set_phase(xmind_heptagon_harness_t *h,
                                  uint32_t phase,
                                  void (*handler)(xmind_heptagon_harness_t *));

/*
 * xmind_harness_get_mastery — Query domain mastery through harness.
 *
 * Convenience wrapper: queries the linked lineage store.
 *
 * @param h         Harness
 * @param domain_id Domain to query
 * @return          Pointer to mastery record, or NULL
 */
const xmind_domain_mastery_t *xmind_harness_get_mastery(
    const xmind_heptagon_harness_t *h,
    uint16_t domain_id);

#endif /* XMIND_HEPTAGON_HARNESS_H */
