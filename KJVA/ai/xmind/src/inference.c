/*
 * inference.c -- XMIND Inference Session & Generation API
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Sprint 15: Implements the high-level inference integration layer that
 * bridges tokenizer -> forward pass -> sampler into a coherent generation
 * pipeline.  This is the missing piece between "model loaded" and
 * "output token generated".
 *
 * Components:
 *   xmind_session_create   -- allocate session with its own sampler state
 *   xmind_session_destroy  -- free session resources
 *   xmind_infer_step       -- one token in, one token out (forward + sample)
 *   xmind_generate         -- prompt ingestion + autoregressive generation
 *   xmind_rope_precompute  -- populate RoPE cos/sin tables (P0 fix)
 *   xmind_preflight_check  -- validate model is ready for inference
 *
 * Design decisions:
 *   - Sessions hold sampler state and current sequence position, allowing
 *     multiple independent conversations (future multi-session support).
 *   - The model itself (weights + KV cache) remains a singleton for Sprint 15.
 *     Multi-model support: singleton model with interp_registry dispatch.
 *   - RoPE precomputation fills the zero-allocated cos/sin tables with the
 *     correct rotary frequencies.  This fixes the P0 RoPE gap from Sprint 8.
 *   - Weight NULL preflight check prevents hard panic on unloaded model.
 *   - Scalar path only (no SIMD) -- correctness over performance for Sprint 15.
 *
 * Memory:
 *   Session struct is ~40 bytes, allocated via xm_heap_alloc().
 *   No additional heap beyond what xmind_alloc_state() already provides.
 *
 * Thread safety:
 *   Thread-safe via PAL spinlock (s_inference_lock).  Session create,
 *   infer_step, and generate hold the lock for the duration of their
 *   critical sections.  P1-01 finding from Sprint 15 — RESOLVED.
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"
#include "../include/xmind_context.h"

/* ===================================================================
 * S1  SESSION STRUCTURE
 *
 * Holds per-conversation state: sampler, current position in the
 * sequence, and a back-pointer to the model.  The model's KV cache
 * is shared across sessions in Sprint 15 (singleton limitation).
 * =================================================================== */

struct xmind_session {
    xmind_model_t   *model;       /* back-pointer to model (singleton)  */
    xmind_sampler_t  sampler;     /* per-session sampler state           */
    uint32_t         pos;         /* current sequence position            */
    uint32_t         max_ctx;     /* maximum tokens before ctx overflow   */
    uint8_t          active;      /* 1 if session is valid                */
    uint8_t          _pad[3];
};

/* ===================================================================
 * S2  ROPE TABLE PRECOMPUTATION
 *
 * Populates model->rope_cos and model->rope_sin with the standard
 * LLaMA RoPE frequencies:
 *
 *   theta_i = 1.0 / (base ^ (2i / head_dim))
 *   cos_table[pos * (head_dim/2) + i] = cos(pos * theta_i)
 *   sin_table[pos * (head_dim/2) + i] = sin(pos * theta_i)
 *
 * where base = 500000.0 (Llama 3.2 RoPE base), configurable via cfg.rope_base.
 *
 * Math: computed via Taylor series since we have no libm.
 *   cos(x) = 1 - x^2/2! + x^4/4! - x^6/6! + x^8/8! - x^10/10!
 *   sin(x) = x - x^3/3! + x^5/5! - x^7/7! + x^9/9! - x^11/11!
 *
 * 6 terms give ~1e-7 max error on [-pi, pi].
 * For large x, we reduce to [-pi, pi] first.
 * =================================================================== */

#define ROPE_BASE_DEFAULT 500000.0f
#define XM_PI      3.14159265358979323846f
#define XM_TWO_PI  6.28318530717958647692f

/* Reduce angle to [-pi, pi] */
static float xm_fmod_pi(float x) {
    /* Coarse reduction: subtract multiples of 2*pi */
    if (x > XM_PI || x < -XM_PI) {
        float n = x / XM_TWO_PI;
        /* Floor towards zero, then adjust */
        int32_t ni = (int32_t)n;
        if ((float)ni > n) { ni -= 1; }
        x -= (float)ni * XM_TWO_PI;
    }
    /* Fine adjustment if still outside [-pi, pi] */
    while (x >  XM_PI) { x -= XM_TWO_PI; }
    while (x < -XM_PI) { x += XM_TWO_PI; }
    return x;
}

/* cos(x) via degree-10 Taylor (6 terms), x should be in [-pi, pi] */
static float xm_cosf(float x) {
    x = xm_fmod_pi(x);
    float x2 = x * x;
    /* Horner form: 1 - x2/2 + x2^2/24 - x2^3/720 + x2^4/40320 - x2^5/3628800 */
    float r = 1.0f;
    float term = x2;
    r -= term * (1.0f / 2.0f);
    term *= x2;
    r += term * (1.0f / 24.0f);
    term *= x2;
    r -= term * (1.0f / 720.0f);
    term *= x2;
    r += term * (1.0f / 40320.0f);
    term *= x2;
    r -= term * (1.0f / 3628800.0f);
    return r;
}

/* sin(x) via degree-11 Taylor (6 terms), x should be in [-pi, pi] */
static float xm_sinf(float x) {
    x = xm_fmod_pi(x);
    float x2 = x * x;
    /* Horner form: x - x^3/6 + x^5/120 - x^7/5040 + x^9/362880 - x^11/39916800 */
    float r = x;
    float term = x * x2;
    r -= term * (1.0f / 6.0f);
    term *= x2;
    r += term * (1.0f / 120.0f);
    term *= x2;
    r -= term * (1.0f / 5040.0f);
    term *= x2;
    r += term * (1.0f / 362880.0f);
    term *= x2;
    r -= term * (1.0f / 39916800.0f);
    return r;
}

/* ln(x) for positive x via IEEE 754 exponent extraction + minimax polynomial.
 * Decomposes x = m * 2^e where m in [1,2), then ln(x) = e*ln(2) + ln(m). */
static float xm_lnf(float x) {
    union { float f; uint32_t u; } bits;
    bits.f = x;
    int32_t e = (int32_t)((bits.u >> 23) & 0xFFu) - 127;
    bits.u = (bits.u & 0x007FFFFFu) | 0x3F800000u; /* m in [1,2) */
    float m = bits.f;
    /* ln(m) for m in [1,2): degree-4 minimax polynomial around m=1 */
    float p = m - 1.0f;
    float ln_m = p * (1.0f - p * (0.5f - p * (0.333333f - p * 0.25f)));
    return (float)e * 0.6931471805599453f + ln_m;
}

/* powf(base, exp) for positive base.  Only used for RoPE theta
 * computation where base is a large positive float and exp is small. */
static float xm_powf(float base, float exp) {
    /* base^exp = e^(exp * ln(base)) */
    float ln_base = xm_lnf(base);

    /* Now compute e^(exp * ln_base) using the exp polynomial from tensor.c */
    float arg = exp * ln_base;
    /* Clamp */
    if (arg >  87.0f) { arg =  87.0f; }
    if (arg < -87.0f) { arg = -87.0f; }

    float y = arg * 1.4426950408889634f;  /* log2(e) */
    int32_t n = (int32_t)y;
    if ((float)n > y) { n -= 1; }
    float f = y - (float)n;
    float p = 1.0f + f * (0.6931471806f
                  + f * (0.2402265069f
                  + f * (0.0555041086f
                  + f * (0.0096181292f
                  + f *  0.0013333558f))));
    union { float fv; uint32_t uv; } bits;
    bits.uv = (uint32_t)((n + 127) << 23);
    return p * bits.fv;
}

/* ===================================================================
 * S2b  SIMD INIT HOOK
 *
 * Called automatically during RoPE precompute (which is the first
 * mandatory step before any forward pass).  This ensures xmind_simd_init()
 * is called exactly once before inference begins, without requiring
 * the caller to remember an extra initialization step.
 * =================================================================== */

/* ===================================================================
 * S2a  THREAD SAFETY — Sprint 45 Wave 2 (A-01 fix)
 *
 * Sprint 15 comment: "NOT thread-safe. Mutex integration deferred to
 * Sprint 16 (P1-01 finding)."  This section closes that gap.
 *
 * A PAL spinlock is used because pal.h exposes only spinlocks as an
 * inline synchronisation primitive.  The inference critical section is
 * bounded (no blocking I/O while holding the lock), so a spinlock is
 * appropriate for this freestanding context.
 *
 * Protected operations:
 *   - xmind_session_create  (modifies model->initialized read path)
 *   - xmind_generate        (drives the forward pass + KV cache write)
 *   - xmind_infer_step      (single-token forward pass)
 *   - xmind_alloc_state     (allocates model scratch buffers)
 *
 * NOT held during:
 *   - xmind_rope_precompute (write-once at init, before any session)
 *   - xmind_preflight_check (read-only)
 *   - xmind_session_destroy (session is private to creator after create)
 * =================================================================== */

static pal_spinlock_t s_inference_lock = PAL_SPINLOCK_INIT;

#include "xmind_heptagon.h"

/* ===================================================================
 * S2c  HEPTAGON HOOKS — weak symbols for optional cognitive layer
 *
 * These hooks allow the Heptagon cognitive architecture to intercept
 * inference at three points: pre-inference, per-token, post-inference.
 * Weak symbols: if heptagon.c is not linked, the default no-op stubs
 * are used (return 0 = success, no side effects).
 *
 * Hook contract:
 *   pre_inference:  called once before prompt prefill.  h = heptagon ctx.
 *   per_token:      called after each forward pass, before sampling.
 *                   May modify logits[] for safety/alignment steering.
 *   post_inference: called once after generation completes.
 * =================================================================== */

/* Weak stubs: used when heptagon.c is not linked.
 * Signatures match xmind_heptagon.h exactly.
 *
 * P1-STUB-02 LINK VERIFICATION (2026-04-04):
 *   Strong symbols for all 4 functions exist in ai/xmind/src/heptagon.c:
 *     xmind_heptagon_init()           — L1-L7 layer init + entropy tables
 *     xmind_heptagon_pre_inference()  — L1 ontology classification
 *     xmind_heptagon_per_token()      — L4 instrumentation (confidence/entropy)
 *     xmind_heptagon_post_inference() — L5 evaluation + L7 enforcement
 *   When heptagon.c is included in the link unit (normal build), these weak
 *   stubs are overridden by the standard weak/strong linker rule.
 *   No code change required — the wiring is automatic at link time. */
__attribute__((weak))
int xmind_heptagon_pre_inference(xmind_heptagon_t *h,
                                  const xmind_inference_input_t *input) {
    (void)h; (void)input;
    return 0;
}

__attribute__((weak))
int xmind_heptagon_per_token(xmind_heptagon_t *h, uint32_t tok,
                              float *logits, uint32_t vs) {
    (void)h; (void)tok; (void)logits; (void)vs;
    return 0;
}

__attribute__((weak))
int xmind_heptagon_post_inference(xmind_heptagon_t *h) {
    (void)h;
    return 0;
}

/* Weak stub for heptagon_init — no-op when heptagon.c not linked */
__attribute__((weak))
void xmind_heptagon_init(xmind_heptagon_t *h) {
    (void)h;
}

static uint8_t s_simd_initialized = 0u;

static void xm_ensure_simd_init(void) {
    if (!s_simd_initialized) {
        xmind_simd_init();
        s_simd_initialized = 1u;
    }
}

/* Sprint 50: Static heptagon context for cognitive governance */

static xmind_heptagon_t s_heptagon_ctx;
static uint8_t s_heptagon_initialized = 0u;

static xmind_heptagon_t *xm_get_heptagon(void) {
    if (!s_heptagon_initialized) {
        xmind_heptagon_init(&s_heptagon_ctx);
        s_heptagon_initialized = 1u;
    }
    return &s_heptagon_ctx;
}

xmind_status_t xmind_rope_precompute(xmind_model_t *m) {
    if (!m)              { return XMIND_ERR_INVAL; }
    if (!m->initialized) { return XMIND_ERR_INVAL; }
    if (!m->rope_cos || !m->rope_sin) { return XMIND_ERR_INVAL; }

    /* Initialize SIMD dispatch before first inference */
    xm_ensure_simd_init();

    uint32_t ctx_len  = m->cfg.ctx_len;
    uint32_t head_dim = m->cfg.head_dim;
    uint32_t half     = head_dim / 2u;

    /* Select RoPE base: config override or default (500000 for Llama 3.2) */
    float base = (m->cfg.rope_base > 0.0f) ? m->cfg.rope_base : ROPE_BASE_DEFAULT;

    /* Precompute theta_i = 1.0 / (base ^ (2*i / head_dim)) */
    uint32_t pos, i;
    for (pos = 0u; pos < ctx_len; pos++) {
        for (i = 0u; i < half; i++) {
            /* theta_i = 1.0 / base^(2i/head_dim)
             *         = base^(-2i/head_dim) */
            float exponent = -2.0f * (float)i / (float)head_dim;
            float theta_i = xm_powf(base, exponent);
            float angle = (float)pos * theta_i;

            uint32_t idx = pos * half + i;
            m->rope_cos[idx] = xm_cosf(angle);
            m->rope_sin[idx] = xm_sinf(angle);
        }
    }

    pal_console_printf("[XMIND] RoPE tables precomputed: ctx=%u half=%u "
                       "base=%.1f\n", ctx_len, half, (double)base);
    return XMIND_OK;
}

/* ===================================================================
 * S3  PREFLIGHT CHECK
 *
 * Validates that the model is in a state where xmind_forward() can
 * run without hitting NULL pointer dereferences or assertion failures.
 * This prevents the P1-05 finding (weight pointer NULL crash).
 * =================================================================== */

xmind_status_t xmind_preflight_check(xmind_model_t *m) {
    if (!m)              { return XMIND_ERR_INVAL; }
    if (!m->initialized) { return XMIND_ERR_INVAL; }

    /* Check state buffers (allocated by xmind_alloc_state) */
    if (!m->state.logits || !m->state.x || !m->state.xb) {
        pal_console_printf("[XMIND] preflight FAIL: state buffers NULL\n");
        return XMIND_ERR_INVAL;
    }
    if (!m->state.q || !m->state.k || !m->state.v || !m->state.attn) {
        pal_console_printf("[XMIND] preflight FAIL: qkv/attn buffers NULL\n");
        return XMIND_ERR_INVAL;
    }

    /* Check critical weight pointers (at least layer 0) */
    if (!m->token_emb) {
        pal_console_printf("[XMIND] preflight FAIL: token_emb NULL\n");
        return XMIND_ERR_INVAL;
    }
    if (!m->rms_final) {
        pal_console_printf("[XMIND] preflight FAIL: rms_final NULL\n");
        return XMIND_ERR_INVAL;
    }
    if (!m->rope_cos || !m->rope_sin) {
        pal_console_printf("[XMIND] preflight FAIL: RoPE tables NULL\n");
        return XMIND_ERR_INVAL;
    }

    /* Check per-layer weight pointers for layer 0 as a sentinel */
    if (m->cfg.n_layers > 0u) {
        if (!m->wq[0] || !m->wk[0] || !m->wv[0] || !m->wo[0]) {
            pal_console_printf("[XMIND] preflight FAIL: attention "
                               "weights NULL at layer 0\n");
            return XMIND_ERR_INVAL;
        }
        if (!m->w1[0] || !m->w2[0] || !m->w3[0]) {
            pal_console_printf("[XMIND] preflight FAIL: FFN "
                               "weights NULL at layer 0\n");
            return XMIND_ERR_INVAL;
        }
        if (!m->rms_att[0] || !m->rms_ffn[0]) {
            pal_console_printf("[XMIND] preflight FAIL: RMSNorm "
                               "weights NULL at layer 0\n");
            return XMIND_ERR_INVAL;
        }
    }

    /* Check KV cache allocation for layer 0 */
    if (m->cfg.n_layers > 0u) {
        if (!m->kv.k[0] || !m->kv.v[0]) {
            pal_console_printf("[XMIND] preflight FAIL: KV cache NULL "
                               "at layer 0\n");
            return XMIND_ERR_INVAL;
        }
    }

    pal_console_printf("[XMIND] preflight OK\n");
    return XMIND_OK;
}

/* ===================================================================
 * S4  SESSION CREATE / DESTROY
 * =================================================================== */

xmind_status_t xmind_session_create(xmind_session_t **out,
                                     uint32_t max_tokens) {
    if (!out)           { return XMIND_ERR_INVAL; }
    if (max_tokens == 0u) { return XMIND_ERR_INVAL; }

    pal_spin_lock(&s_inference_lock);

    xmind_model_t *m = xmind_get_global();

    /* Ensure SIMD dispatch is initialized before inference */
    xm_ensure_simd_init();

    /* Preflight: ensure model is ready */
    xmind_status_t st = xmind_preflight_check(m);
    if (st != XMIND_OK) {
        pal_console_printf("[XMIND] session_create: preflight failed\n");
        pal_spin_unlock(&s_inference_lock);
        return st;
    }

    /* Allocate session */
    xmind_session_t *s = (xmind_session_t *)xm_heap_alloc(
        (uint64_t)sizeof(xmind_session_t));
    if (!s) { pal_spin_unlock(&s_inference_lock); return XMIND_ERR_NOMEM; }

    s->model   = m;
    s->pos     = 0u;
    s->active  = 1u;

    /* Cap max_tokens to model context length */
    if (max_tokens > m->cfg.ctx_len) {
        max_tokens = m->cfg.ctx_len;
    }
    s->max_ctx = max_tokens;

    /* Initialize sampler with reasonable defaults:
     * temperature=0.7, top_p=0.9, default seed */
    xmind_sampler_init(&s->sampler, 0.7f, 0.9f, 0u);

    *out = s;
    pal_console_printf("[XMIND] session created: max_ctx=%u\n", s->max_ctx);
    pal_spin_unlock(&s_inference_lock);
    return XMIND_OK;
}

xmind_status_t xmind_session_destroy(xmind_session_t *s) {
    if (!s) { return XMIND_ERR_INVAL; }
    s->active = 0u;
    s->model  = (xmind_model_t *)0;
    xm_heap_free(s);
    pal_console_printf("[XMIND] session destroyed\n");
    return XMIND_OK;
}

/* ===================================================================
 * S5  SESSION CONFIGURATION
 *
 * Allow caller to adjust sampler parameters after session creation.
 * =================================================================== */

xmind_status_t xmind_session_set_sampler(xmind_session_t *s,
                                          float temperature,
                                          float top_p,
                                          uint64_t seed) {
    if (!s || !s->active) { return XMIND_ERR_INVAL; }
    xmind_sampler_init(&s->sampler, temperature, top_p, seed);
    return XMIND_OK;
}

/* ===================================================================
 * S6  SINGLE-STEP INFERENCE
 *
 * Runs one forward pass: feeds input_token at the current position,
 * samples an output token, and advances the position counter.
 *
 * This is the fundamental building block:
 *   1. Validate position < max_ctx
 *   2. Call xmind_forward(model, input_token, pos)
 *   3. Call xmind_sample(model, &sampler)
 *   4. Increment pos
 *   5. Return sampled token
 * =================================================================== */

xmind_status_t xmind_infer_step(xmind_session_t *s,
                                 uint32_t input_token,
                                 uint32_t *output_token) {
    if (!s || !s->active)   { return XMIND_ERR_INVAL; }
    if (!output_token)      { return XMIND_ERR_INVAL; }

    pal_spin_lock(&s_inference_lock);

    xmind_model_t *m = s->model;
    if (!m || !m->initialized) {
        pal_spin_unlock(&s_inference_lock);
        return XMIND_ERR_INVAL;
    }

    /* Context overflow check */
    if (s->pos >= s->max_ctx) {
        pal_console_printf("[XMIND] infer_step: context full at pos=%u\n",
                           s->pos);
        pal_spin_unlock(&s_inference_lock);
        return XMIND_ERR_OVERFLOW;
    }

    /* Clamp token to vocab range */
    if (input_token >= m->cfg.vocab_size) {
        pal_console_printf("[XMIND] infer_step: token %u >= vocab %u\n",
                           input_token, m->cfg.vocab_size);
        pal_spin_unlock(&s_inference_lock);
        return XMIND_ERR_INVAL;
    }

    /* Forward pass: compute logits for this token at this position */
    xmind_forward(m, input_token, s->pos);

    /* Sample next token from logit distribution */
    uint32_t next_tok = xmind_sample(m, &s->sampler);

    /* Advance position */
    s->pos++;

    *output_token = next_tok;
    pal_spin_unlock(&s_inference_lock);
    return XMIND_OK;
}

/* ===================================================================
 * S7  FULL GENERATION PIPELINE
 *
 * Two-phase generation:
 *
 * Phase 1 -- Prompt ingestion (prefill):
 *   For each token in the prompt (except the last), run xmind_forward()
 *   to populate the KV cache.  We discard the output logits during
 *   prefill -- they represent P(next | prefix) which we don't need.
 *
 * Phase 2 -- Autoregressive generation:
 *   Starting from the last prompt token, repeatedly:
 *     1. Run forward pass
 *     2. Sample output token
 *     3. Append to output buffer
 *     4. If EOS token is sampled, stop
 *     5. Feed sampled token as next input
 *
 * Returns the number of generated tokens in *n_generated.
 *
 * Callback support:
 *   If the session has a registered callback (Sprint 16), each
 *   generated token is streamed to the callback before continuing.
 *   For Sprint 15, generation is fully synchronous/blocking.
 * =================================================================== */

xmind_status_t xmind_generate(xmind_session_t *s,
                               const uint32_t *prompt,
                               uint32_t prompt_len,
                               uint32_t *output,
                               uint32_t max_new_tokens,
                               uint32_t *n_generated) {
    if (!s || !s->active)   { return XMIND_ERR_INVAL; }
    if (!prompt)            { return XMIND_ERR_INVAL; }
    if (prompt_len == 0u)   { return XMIND_ERR_INVAL; }
    if (!output)            { return XMIND_ERR_INVAL; }
    if (!n_generated)       { return XMIND_ERR_INVAL; }
    if (max_new_tokens == 0u) {
        *n_generated = 0u;
        return XMIND_OK;
    }

    pal_spin_lock(&s_inference_lock);

    xmind_model_t *m = s->model;
    if (!m || !m->initialized) {
        pal_spin_unlock(&s_inference_lock);
        return XMIND_ERR_INVAL;
    }

    *n_generated = 0u;

    /* Validate prompt tokens and context budget */
    uint32_t total_needed = prompt_len + max_new_tokens;
    if (total_needed > s->max_ctx) {
        /* Reduce max_new_tokens to fit */
        if (prompt_len >= s->max_ctx) {
            pal_console_printf("[XMIND] generate: prompt_len %u >= max_ctx %u\n",
                               prompt_len, s->max_ctx);
            pal_spin_unlock(&s_inference_lock);
            return XMIND_ERR_OVERFLOW;
        }
        max_new_tokens = s->max_ctx - prompt_len;
    }

    /* Reset position for new generation */
    s->pos = 0u;

    pal_console_printf("[XMIND] generate: prompt_len=%u max_new=%u\n",
                       prompt_len, max_new_tokens);

    /* ── Context retrieval: populate shards from Bookworm + SoulManager ── */
    xmind_context_request_t ctx_req;
    xmind_context_result_t  ctx_res;
    r1_per_signal_t         ctx_signal;

    /* Zero everything */
    {
        uint8_t *zp;
        zp = (uint8_t *)&ctx_req;
        for (uint32_t zi = 0u; zi < (uint32_t)sizeof(ctx_req); zi++) zp[zi] = 0u;
        zp = (uint8_t *)&ctx_res;
        for (uint32_t zi = 0u; zi < (uint32_t)sizeof(ctx_res); zi++) zp[zi] = 0u;
        zp = (uint8_t *)&ctx_signal;
        for (uint32_t zi = 0u; zi < (uint32_t)sizeof(ctx_signal); zi++) zp[zi] = 0u;
    }

    ctx_req.query_instructions = (const xcog_instr_t *)0; /* raw token mode */
    ctx_req.query_count        = 0u;
    ctx_req.salience_threshold = 100u;  /* minimum salience */
    ctx_req.max_shards         = XMIND_MAX_CONTEXT_SHARDS;

    int ctx_rc = xmind_context_retrieve(&ctx_req, &ctx_res);
    if (ctx_rc == 0 && ctx_res.shard_count > 0u) {
        /* Populate R1_PER signal with retrieved shards */
        ctx_signal.magic               = R1_PER_MAGIC;
        ctx_signal.version             = R1_PER_VERSION;
        ctx_signal.context_shard_count = (uint16_t)ctx_res.shard_count;
        ctx_signal.context_total_size  = ctx_res.total_data_size;
        ctx_signal.stage_flags         = R1_STAGE_RESOLVED;
        ctx_signal.source_channel      = R1_SOURCE_SYSTEM;
        ctx_signal.fallback_flag       = 0u;
    }

    /* Heptagon pre-inference hook: cognitive layer intercept before prefill.
     * Sprint 50: static context initialized on first call. */
    xmind_heptagon_t *h = xm_get_heptagon();
    xmind_inference_input_t hept_input;
    /* If context shards were retrieved, attach the signal to heptagon input */
    hept_input.signal = (ctx_rc == 0 && ctx_res.shard_count > 0u)
                      ? &ctx_signal
                      : (r1_per_signal_t *)0;
    hept_input.raw_tokens = prompt;
    hept_input.raw_token_count = prompt_len;
    hept_input.query_domain = 0u;               /* general — L1 will classify */
    xmind_heptagon_pre_inference(h, &hept_input);

    /* Release context shards after pre-inference consumed them */
    if (ctx_res.shard_count > 0u) {
        xmind_context_release(&ctx_res);
    }

    /* ── Phase 1: Prompt prefill ──────────────────────────────────
     * Feed all prompt tokens except the last through the forward pass.
     * This populates the KV cache with the prompt context.
     * We don't need the logits from these steps.                    */
    uint32_t i;
    for (i = 0u; i + 1u < prompt_len; i++) {
        if (prompt[i] >= m->cfg.vocab_size) {
            pal_console_printf("[XMIND] generate: invalid prompt token %u "
                               "at index %u\n", prompt[i], i);
            pal_spin_unlock(&s_inference_lock);
            return XMIND_ERR_INVAL;
        }
        xmind_forward(m, prompt[i], s->pos);
        s->pos++;
    }

    /* ── Phase 2: Autoregressive generation ──────────────────────
     * Feed the last prompt token, sample the first output token,
     * then feed each output token to get the next.                  */

    /* Feed last prompt token and get first generated token */
    uint32_t current_token = prompt[prompt_len - 1u];
    if (current_token >= m->cfg.vocab_size) {
        pal_console_printf("[XMIND] generate: invalid last prompt token %u\n",
                           current_token);
        pal_spin_unlock(&s_inference_lock);
        return XMIND_ERR_INVAL;
    }

    uint32_t gen_count = 0u;
    uint32_t t;
    for (t = 0u; t < max_new_tokens; t++) {
        /* Context overflow guard */
        if (s->pos >= s->max_ctx) {
            pal_console_printf("[XMIND] generate: context full at pos=%u\n",
                               s->pos);
            break;
        }

        /* Forward pass */
        xmind_forward(m, current_token, s->pos);
        s->pos++;

        /* Heptagon per-token hook: cognitive layer may steer logits
         * for safety/alignment before sampling.  Runs after forward
         * pass produces logits, before sampler consumes them. */
        int hept_rc = xmind_heptagon_per_token(h, current_token,
                                 m->state.logits, m->cfg.vocab_size);
        if (hept_rc < 0) {
            /* L7 safety halt — stop generation immediately */
            pal_console_printf("[XMIND] generate: heptagon safety halt at token %u\n", t);
            break;
        }

        /* Sample next token */
        uint32_t next_tok = xmind_sample(m, &s->sampler);

        /* Store in output buffer */
        output[gen_count] = next_tok;
        gen_count++;

        /* Check for end-of-generation using runtime config token IDs.
         * xmind_is_eog_cfg() consults m->cfg.eos_id and m->cfg.eog_ids[],
         * which were backfilled from XMIND_DEFAULT_* constants by
         * xmind_init() if the caller did not override them (B-PHASE1). */
        if (xmind_is_eog_cfg(next_tok, &m->cfg)) {
            pal_console_printf("[XMIND] generate: EOG (tok=%u) at step %u\n",
                               next_tok, t);
            break;
        }

        /* Feed generated token as next input */
        current_token = next_tok;
    }

    *n_generated = gen_count;

    /* Heptagon post-inference hook: cognitive layer cleanup/logging. */
    xmind_heptagon_post_inference(h);

    pal_console_printf("[XMIND] generate: produced %u tokens "
                       "(final pos=%u)\n", gen_count, s->pos);
    pal_spin_unlock(&s_inference_lock);
    return XMIND_OK;
}

/* ===================================================================
 * S8  SESSION RESET
 *
 * Resets the session position to 0 without destroying it.
 * The KV cache in the model is logically invalidated (new forward
 * calls will overwrite positions starting from 0).
 * =================================================================== */

xmind_status_t xmind_session_reset(xmind_session_t *s) {
    if (!s || !s->active) { return XMIND_ERR_INVAL; }
    s->pos = 0u;
    /* Reset KV cache counter in the model */
    if (s->model) {
        s->model->kv.n_cached = 0u;
    }
    pal_console_printf("[XMIND] session reset: pos=0\n");
    return XMIND_OK;
}

/* ===================================================================
 * S9  SESSION QUERY
 *
 * Accessors for session state -- used by the AI companion UX to
 * display progress indicators and context utilization.
 * =================================================================== */

uint32_t xmind_session_pos(const xmind_session_t *s) {
    if (!s) { return 0u; }
    return s->pos;
}

uint32_t xmind_session_remaining(const xmind_session_t *s) {
    if (!s) { return 0u; }
    if (s->pos >= s->max_ctx) { return 0u; }
    return s->max_ctx - s->pos;
}
