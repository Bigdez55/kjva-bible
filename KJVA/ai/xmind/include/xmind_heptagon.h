/*
 * xmind_heptagon.h — XMIND Heptagon Cognitive Governance Integration
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Forward-compatible hook API for the Heptagon cognitive governance
 *   layer inside the XMIND inference pipeline.  Conforms to FROZEN
 *   Sprint 49 contracts: r1_per.h, xcog.h, causal_log_cog.h.
 *
 *   The canonical input to XMIND inference is r1_per_signal_t (FROZEN).
 *   When R1_PER is not available (Sprint 46 mode), signal is NULL and
 *   the pre-inference hook falls back to keyword-based L1 classification.
 *
 * HOOK INSERTION POINTS (from deep-dive analysis):
 *   inference.c line ~509: xmind_heptagon_pre_inference() — before prompt prefill
 *   inference.c line ~548: xmind_heptagon_per_token()     — after forward, before sample
 *   inference.c line ~569: xmind_heptagon_post_inference() — after generation complete
 *
 * SAFETY HALT CHAIN:
 *   L5 detects divergence → XSEC_AUDIT_XCOG_DIVERGENCE event
 *   → L7 reads escalation → sets safety_halt=1
 *   → generation stops mid-stream
 *   → xmind_telemetry_emit() reports safety_halted=1 to Council
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef XMIND_HEPTAGON_H
#define XMIND_HEPTAGON_H

#ifdef PAL_FREESTANDING
#include "../../pal/include/pal.h"
#else
#include <stdint.h>
#endif

#include "r1_per.h"

/* ═══════════════════════════════════════════════════════════════════════
 * §1  INFERENCE INPUT — Unified type for R1_PER and raw token modes
 *
 * The canonical input is r1_per_signal_t (FROZEN Sprint 49).
 * When signal != NULL: reads intent, entities, salience from R1_PER.
 * When signal == NULL: falls back to keyword classifier (Sprint 46 L1).
 * Raw tokens are always passed — the transformer needs them.
 * ═══════════════════════════════════════════════════════════════════════ */

typedef struct {
    r1_per_signal_t *signal;       /* NULL = raw token mode (fallback)    */
    const uint32_t  *raw_tokens;   /* Token array for transformer         */
    uint32_t         raw_token_count;
    uint8_t          query_domain;  /* L1: 0=general 1=code 2=math 3=creative */
} xmind_inference_input_t;

/* ═══════════════════════════════════════════════════════════════════════
 * §2  HEPTAGON STATE — Tracked per inference session
 *
 * This struct lives alongside xmind_model_t (or per-session).
 * It carries the complete cognitive governance state through all 7 layers.
 * ═══════════════════════════════════════════════════════════════════════ */

typedef struct {
    /* L1 Ontology — input classification */
    uint8_t   query_domain;        /* 0=general 1=code 2=math 3=creative  */
    uint16_t  intent_code;         /* from XCOG_INTENT or 0 if raw tokens */

    /* L4 Instrumentation — per-token metrics */
    float     avg_confidence;      /* Running mean of token confidences   */
    float     attention_entropy;   /* Attention distribution entropy      */
    uint32_t  tokens_generated;    /* Count of tokens produced            */

    /* L5 Evaluation — post-generation scoring */
    float     eval_score;          /* 0.0-1.0 quality score               */
    uint32_t  invariant_violations;/* Count of L7 violations detected     */

    /* L6 Calibration — parameter adjustment */
    float     calibrated_temp;     /* Adjusted temperature                */
    float     calibrated_top_p;    /* Adjusted top-p                      */

    /* L7 Enforcement — safety halt */
    uint8_t   safety_halt;         /* 1 = stop generation immediately     */

    /* R1_PER signal reference */
    r1_per_signal_t *current_signal; /* Points to active R1_PER signal    */

    /* Telemetry emission state */
    uint32_t  telemetry_seq;       /* Monotonic sequence number           */
    int32_t   telemetry_fd;        /* XNET socket to Council, -1 if down */
    uint8_t   telemetry_enabled;   /* 1 = emit after each inference       */
} xmind_heptagon_t;

/* ═══════════════════════════════════════════════════════════════════════
 * §3  HOOK API — Called from inference.c at mapped insertion points
 * ═══════════════════════════════════════════════════════════════════════ */

/* Initialize heptagon state (call once per session or at XMIND init) */
void xmind_heptagon_init(xmind_heptagon_t *h);

/* Pre-inference: classify input, set domain, validate signal.
 * Returns 0 to proceed, negative to reject inference. */
int xmind_heptagon_pre_inference(xmind_heptagon_t *h,
                                  const xmind_inference_input_t *input);

/* Per-token: inspect logits, track confidence, check safety.
 * Called after xmind_forward(), before xmind_sample().
 * May modify logits (constraint injection, safety filtering).
 * Returns 0 to continue, -1 to halt (safety_halt). */
int xmind_heptagon_per_token(xmind_heptagon_t *h,
                              uint32_t token_id, float *logits,
                              uint32_t vocab_size);

/* Post-inference: evaluate output quality, calibrate parameters.
 * Returns 0 on success, negative on violation. */
int xmind_heptagon_post_inference(xmind_heptagon_t *h);

/* Get calibrated sampler parameters (L6 adjusted) */
void xmind_heptagon_get_sampler(const xmind_heptagon_t *h,
                                 float *temp_out, float *top_p_out);

#endif /* XMIND_HEPTAGON_H */
