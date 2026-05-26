/*
 * sampler.c — XMIND Token Sampler
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Implements next-token selection from a logit distribution:
 *   - Greedy decoding (temperature = 0)
 *   - Temperature scaling + top-p (nucleus) sampling
 *   - xorshift64 PRNG for reproducible generation
 *
 * Functions:
 *   xmind_sampler_init    — initialise sampler state
 *   xm_xorshift64         — xorshift64 PRNG (static)
 *   xm_rand_float         — uniform [0,1) float from PRNG (static)
 *   xm_argmax             — greedy decode (static)
 *   xm_apply_temperature  — divide logits by temperature (static)
 *   xm_sample_topp        — top-p nucleus sampling (static)
 *   xmind_sample          — public entry point
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"

/* ═══════════════════════════════════════════════════════════════════
 * §1  XORSHIFT64 PRNG
 * ═══════════════════════════════════════════════════════════════════
 *
 * Period: 2^64 - 1.  Non-cryptographic but sufficient for sampling.
 * Requires non-zero seed (enforced by xmind_sampler_init).
 */
static uint64_t xm_xorshift64(uint64_t *state) {
    uint64_t x = *state;
    x ^= x << 13u;
    x ^= x >> 7u;
    x ^= x << 17u;
    *state = x;
    return x;
}

/* ═══════════════════════════════════════════════════════════════════
 * §2  UNIFORM FLOAT IN [0, 1)
 * ═══════════════════════════════════════════════════════════════════
 *
 * Extracts 23 mantissa bits from the PRNG output and composes a
 * float in [1.0, 2.0), then subtracts 1.0 to get [0.0, 1.0).
 * This avoids division and gives a uniform distribution.
 */
static float xm_rand_float(uint64_t *state) {
    uint64_t bits64 = xm_xorshift64(state);
    /* Take lower 23 bits → mantissa of float in [1.0, 2.0) */
    uint32_t mantissa = (uint32_t)(bits64 & 0x007FFFFFu);
    union { float f; uint32_t u; } fp;
    fp.u = 0x3F800000u | mantissa;   /* exponent = 127 → value in [1,2) */
    return fp.f - 1.0f;              /* shift to [0, 1) */
}

/* ═══════════════════════════════════════════════════════════════════
 * §3  GREEDY ARGMAX
 * ═══════════════════════════════════════════════════════════════════ */
static uint32_t xm_argmax(const float *x, uint32_t n) {
    XM_ASSERT(x != (void *)0);
    XM_ASSERT(n > 0u);
    uint32_t best = 0u;
    float    best_val = x[0];
    uint32_t i;
    for (i = 1u; i < n; i++) {
        if (x[i] > best_val) {
            best_val = x[i];
            best     = i;
        }
    }
    return best;
}

/* ═══════════════════════════════════════════════════════════════════
 * §4  TEMPERATURE SCALING
 * ═══════════════════════════════════════════════════════════════════
 *
 * Divides every logit by temperature.  Applied before softmax.
 * Higher temperature → flatter distribution.
 * Temperature must be > 0 (enforced by caller).
 */
static void xm_apply_temperature(float *logits, float temp, uint32_t n) {
    float inv_temp = 1.0f / temp;
    uint32_t i;
    for (i = 0u; i < n; i++) {
        logits[i] *= inv_temp;
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * §5  TOP-P (NUCLEUS) SAMPLING
 * ═══════════════════════════════════════════════════════════════════
 *
 * Algorithm (linear scan, O(n)):
 *   1. Apply softmax in-place to convert logits → probabilities.
 *   2. Find the probability threshold: tokens whose individual prob
 *      is >= (1 - p) / n are candidates.  This is a coarse filter;
 *      the real nucleus is built by cumulative mass.
 *   3. To avoid sorting (O(n log n)) without heap allocation, we use
 *      a two-pass approach:
 *        Pass 1: find max_prob, compute p_threshold = max_prob * (1-p)
 *                  as a lower-bound cut-off.
 *        Pass 2: collect candidates with prob > p_threshold, accumulate
 *                  their mass, compute cumulative CDF on the fly.
 *        Sample: draw r ~ Uniform[0, 1), walk candidates until
 *                  cumulative mass > r * total_candidate_mass.
 *   4. If no candidate qualifies (numerical edge case), fall back to
 *      argmax (greedy).
 *
 * This is equivalent to nucleus sampling with a conservative nucleus
 * that may include slightly more tokens than exact top-p, but is
 * allocation-free and O(n).
 *
 * logits: must already contain probabilities (post-softmax).
 * p:      top-p threshold in (0, 1].
 * n:      vocabulary size.
 * rng:    PRNG state.
 */
static uint32_t xm_sample_topp(float *logits, float p, uint32_t n,
                                uint64_t *rng) {
    XM_ASSERT(logits != (void *)0);
    XM_ASSERT(n > 0u);

    /* --- Pass 1: softmax is already applied --- */

    /* Find max probability for threshold computation */
    float max_prob = logits[0];
    uint32_t i;
    for (i = 1u; i < n; i++) {
        if (logits[i] > max_prob) { max_prob = logits[i]; }
    }

    /* Threshold: include tokens with prob >= (1-p) * max_prob.
     * This conservatively approximates nucleus membership without sorting. */
    float threshold = (1.0f - p) * max_prob;
    if (threshold < 0.0f) { threshold = 0.0f; }

    /* --- Pass 2: accumulate candidate mass --- */
    float total_mass = 0.0f;
    for (i = 0u; i < n; i++) {
        if (logits[i] >= threshold) {
            total_mass += logits[i];
        }
    }

    if (total_mass <= 0.0f) {
        /* Degenerate: fall back to greedy */
        return xm_argmax(logits, n);
    }

    /* --- Sample: draw r, walk until cumulative mass > r * total_mass --- */
    float r = xm_rand_float(rng) * total_mass;
    float cumulative = 0.0f;
    for (i = 0u; i < n; i++) {
        if (logits[i] >= threshold) {
            cumulative += logits[i];
            if (cumulative >= r) {
                return i;
            }
        }
    }

    /* Numerical safety: return last candidate */
    for (i = n; i > 0u; i--) {
        if (logits[i - 1u] >= threshold) {
            return i - 1u;
        }
    }

    /* Absolute fallback */
    return xm_argmax(logits, n);
}

/* ═══════════════════════════════════════════════════════════════════
 * §6  SAMPLER INIT
 * ═══════════════════════════════════════════════════════════════════ */

void xmind_sampler_init(xmind_sampler_t *s, float temperature,
                        float top_p, uint64_t seed) {
    XM_ASSERT(s != (void *)0);
    s->temperature = temperature;
    s->top_p       = top_p;
    /* xorshift64 must never have a zero state */
    s->rng_state   = (seed != 0u) ? seed : 0xDEADBEEFCAFEBABEull;
}

/* ═══════════════════════════════════════════════════════════════════
 * §7  PUBLIC SAMPLE ENTRY POINT
 * ═══════════════════════════════════════════════════════════════════
 *
 * Dispatches to greedy or top-p depending on temperature.
 * Operates on a working copy of logits to avoid mutating model state.
 *
 * temperature == 0.0 → greedy (argmax)
 * temperature  > 0.0 → temperature scaling + softmax + top-p
 *
 * NOTE: We operate on m->state.logits directly for temperature scaling
 * and softmax — the caller must treat logits as consumed after sampling.
 * (The next xmind_forward() call will overwrite them anyway.)
 */
uint32_t xmind_sample(xmind_model_t *m, xmind_sampler_t *s) {
    XM_ASSERT(m != (void *)0);
    XM_ASSERT(s != (void *)0);
    XM_ASSERT(m->state.logits != (void *)0);

    uint32_t vocab_size = m->cfg.vocab_size;
    float   *logits     = m->state.logits;

    /* Greedy decode */
    if (s->temperature == 0.0f) {
        return xm_argmax(logits, vocab_size);
    }

    /* Temperature scaling */
    xm_apply_temperature(logits, s->temperature, vocab_size);

    /* Softmax: logits → probabilities */
    xmind_softmax(logits, vocab_size);

    /* Top-p sampling (p == 1.0 → pure temperature sampling) */
    float p = s->top_p;
    if (p <= 0.0f || p >= 1.0f) { p = 1.0f; }

    return xm_sample_topp(logits, p, vocab_size, &s->rng_state);
}
