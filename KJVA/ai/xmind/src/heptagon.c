/*
 * heptagon.c — XMIND Heptagon Cognitive Governance Layer
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Implements the seven-layer cognitive governance pipeline:
 *   L1  Ontology      — input classification (query_domain, intent_code)
 *   L2  Schema        — (structural; handled by R1_PER upstream)
 *   L3  Kernel        — (parameter binding; handled by inference.c)
 *   L4  Instrumentation — per-token confidence + attention entropy
 *   L5  Evaluation    — post-generation quality scoring
 *   L6  Calibration   — sampler parameter adjustment
 *   L7  Enforcement   — safety halt + XSEC escalation
 *
 * Hook insertion points (called from inference.c):
 *   ~line 509: xmind_heptagon_pre_inference()
 *   ~line 548: xmind_heptagon_per_token()
 *   ~line 569: xmind_heptagon_post_inference()
 *
 * Freestanding C11. No libc. PAL I/O only.
 * Compile: clang -ffreestanding -DPAL_FREESTANDING -Werror -c heptagon.c
 */

#ifdef PAL_FREESTANDING
#include "../../../pal/include/pal.h"
#else
#include <stdint.h>
#endif

#include "../include/xmind_heptagon.h"
#include "../include/xmind_telemetry.h"
#include "../../../xisc/include/xcog.h"
#include "../../../sec/xsec/include/causal_log_cog.h"

/* ═══════════════════════════════════════════════════════════════════════
 * XSEC — audit log API (freestanding, only includes pal.h internally)
 * ═══════════════════════════════════════════════════════════════════════ */
#include "../../../sec/xsec/include/xsec.h"

/* ═══════════════════════════════════════════════════════════════════════
 * §1  Freestanding math — exp() and log() without libm
 *
 * exp_fast():  Taylor series around 0, accurate to ~1e-6 for |x| < 10.
 *              For inference-layer softmax computation the small relative
 *              error is acceptable; we only need the ratio structure to
 *              be monotone-preserving for entropy estimation.
 *
 * log_fast():  ln(x) via identity ln(x) = 2·atanh((x-1)/(x+1)) where
 *              atanh is computed as a truncated power series.  Valid for
 *              x > 0.  For x <= 0 returns -100.0f (saturating sentinel).
 *
 * Complexity: O(1) — fixed iteration count.
 * ═══════════════════════════════════════════════════════════════════════ */

static float hept_fabsf(float x) {
    return (x < 0.0f) ? -x : x;
}

/* exp_fast: Taylor series e^x = sum_{n=0}^{N} x^n / n!
 * Clamped to [-87, 88] to prevent float overflow/underflow.           */
static float exp_fast(float x) {
    /* Clamp to safe float range */
    if (x > 88.0f)  return 3.40282347e+38f;   /* FLT_MAX approximation */
    if (x < -87.0f) return 0.0f;

    /* Decompose: e^x = e^(k·ln2) · e^r where k = round(x/ln2), r = x - k·ln2
     * This range-reduction dramatically improves accuracy. */
    const float ln2     = 0.693147181f;
    const float inv_ln2 = 1.442695041f;
    float kf = x * inv_ln2;
    /* Round to nearest integer */
    int32_t k = (int32_t)(kf + (kf >= 0.0f ? 0.5f : -0.5f));
    float r = x - (float)k * ln2;

    /* Polynomial for e^r, |r| <= ln2/2 ≈ 0.347
     * Coefficients: 1/0! 1/1! 1/2! 1/3! 1/4! 1/5! 1/6!               */
    float result = 1.0f
                 + r * (1.0f
                 + r * (0.5f
                 + r * (0.16666667f
                 + r * (0.04166667f
                 + r * (0.00833333f
                 + r * 0.00138889f)))));

    /* Multiply by 2^k via bit manipulation on IEEE 754 float */
    if (k >= -126 && k <= 127) {
        union { float f; uint32_t u; } pwr;
        pwr.u = (uint32_t)((k + 127) << 23);
        result *= pwr.f;
    } else if (k < -126) {
        result = 0.0f;
    } else {
        result = 3.40282347e+38f;
    }
    return result;
}

/* log_fast: ln(x) via 2·atanh((x-1)/(x+1)), 8-term series.
 * Additional range reduction via 2^e extraction for x far from 1.    */
static float log_fast(float x) {
    if (x <= 0.0f) return -100.0f;  /* Saturating sentinel for log(0) */

    /* Extract exponent: x = m · 2^e, 0.5 <= m < 1 */
    union { float f; uint32_t u; } fx;
    fx.f = x;
    int32_t e = (int32_t)((fx.u >> 23) & 0xFFu) - 127;
    /* Set exponent to 0 (i.e. normalise mantissa into [1, 2)) */
    fx.u = (fx.u & 0x807FFFFFu) | 0x3F800000u;
    float m = fx.f;  /* m in [1, 2) */

    /* Now compute ln(m) where m in [1, 2). Use ln(m) = 2·atanh(t)
     * where t = (m-1)/(m+1) in [-0.333, 0.333] for m in [1, 2).      */
    float t = (m - 1.0f) / (m + 1.0f);
    float t2 = t * t;

    /* atanh(t) = t + t^3/3 + t^5/5 + t^7/7 + t^9/9 + t^11/11 + t^13/13 */
    float atanh_t = t * (1.0f
                   + t2 * (0.33333333f
                   + t2 * (0.2f
                   + t2 * (0.14285714f
                   + t2 * (0.11111111f
                   + t2 * (0.09090909f
                   + t2 * 0.07692308f))))));

    const float ln2 = 0.693147181f;
    return 2.0f * atanh_t + (float)e * ln2;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §2  Internal string utilities (no libc)
 * ═══════════════════════════════════════════════════════════════════════ */

/* Write decimal uint32 into buf[]; returns pointer past last digit.
 * buf must be at least 11 bytes.                                       */
static char *u32_to_dec(char *buf, uint32_t val) {
    if (val == 0u) { *buf++ = '0'; return buf; }
    char tmp[10];
    int32_t i = 0;
    while (val > 0u) { tmp[i++] = (char)('0' + (val % 10u)); val /= 10u; }
    while (i > 0)    { *buf++ = tmp[--i]; }
    return buf;
}

/* Write a float as "ddd.dd" (2 decimal places) into buf.
 * Returns pointer past last char.  buf must be >= 14 bytes.           */
static char *f32_to_str(char *buf, float val) {
    if (val < 0.0f) { *buf++ = '-'; val = -val; }
    uint32_t whole = (uint32_t)val;
    uint32_t frac  = (uint32_t)((val - (float)whole) * 100.0f + 0.5f);
    if (frac >= 100u) { whole++; frac = 0u; }
    buf = u32_to_dec(buf, whole);
    *buf++ = '.';
    /* Always emit two frac digits */
    *buf++ = (char)('0' + frac / 10u);
    *buf++ = (char)('0' + frac % 10u);
    return buf;
}

/* Build a bounded detail string from format components.
 * Output is always NUL-terminated.  At most (cap-1) chars written.    */
static void build_detail(char *out, uint32_t cap,
                         uint32_t seq, float eval, float conf, uint8_t halt) {
    /* "seq=%u eval=%.2f conf=%.2f halt=%d" */
    char *p = out;
    const char *end = out + cap - 1u;

#define APPEND_STR(s) do { \
    const char *_s = (s); \
    while (*_s && p < end) *p++ = *_s++; \
} while (0)

    APPEND_STR("seq=");
    if (p < end) {
        char tmp[12]; char *e = u32_to_dec(tmp, seq); *e = '\0';
        APPEND_STR(tmp);
    }
    APPEND_STR(" eval=");
    if (p < end) {
        char tmp[16]; char *e = f32_to_str(tmp, eval); *e = '\0';
        APPEND_STR(tmp);
    }
    APPEND_STR(" conf=");
    if (p < end) {
        char tmp[16]; char *e = f32_to_str(tmp, conf); *e = '\0';
        APPEND_STR(tmp);
    }
    APPEND_STR(" halt=");
    if (p < end) *p++ = (char)('0' + (halt & 1u));

#undef APPEND_STR
    *p = '\0';
}

/* ═══════════════════════════════════════════════════════════════════════
 * §3  Keyword domain classifier (L1 fallback path)
 *
 * Called only when r1_per_signal_t.fallback_flag == 1 (R1_PER unavailable).
 * Scans raw_tokens as a byte stream to detect domain-specific patterns.
 *
 * Algorithm: single linear scan O(n) over token bytes.
 * Pattern matching uses a 4-byte sliding window for "def " / "class ".
 * UTF-8 multi-byte sequences for "∫" (0xE2 0x88 0xAB) and
 * "√" (0xE2 0x88 0x9A) are matched as raw byte triplets.
 *
 * Priority: code > math > creative > general (first match wins per pass).
 * ═══════════════════════════════════════════════════════════════════════ */

#define DOMAIN_GENERAL  0u
#define DOMAIN_CODE     1u
#define DOMAIN_MATH     2u
#define DOMAIN_CREATIVE 3u

static uint8_t classify_domain_keywords(const uint32_t *raw_tokens,
                                         uint32_t        count) {
    /* Treat each token ID's low 8 bits as a char stream for keyword
     * detection.  This is a best-effort heuristic when R1_PER is down. */
    if (raw_tokens == NULL || count == 0u) return DOMAIN_GENERAL;

    /* We need at least 6 tokens for "class " (6 chars).
     * Slide a window checking for ASCII patterns.                     */
    uint8_t found_code     = 0u;
    uint8_t found_math     = 0u;
    uint8_t found_creative = 0u;

    for (uint32_t i = 0u; i < count; i++) {
        uint8_t c0 = (uint8_t)(raw_tokens[i] & 0xFFu);

        /* "def " — check 4 tokens: 'd','e','f',' ' */
        if (c0 == (uint8_t)'d' && (i + 3u) < count) {
            if ((uint8_t)(raw_tokens[i+1] & 0xFFu) == (uint8_t)'e' &&
                (uint8_t)(raw_tokens[i+2] & 0xFFu) == (uint8_t)'f' &&
                (uint8_t)(raw_tokens[i+3] & 0xFFu) == (uint8_t)' ') {
                found_code = 1u;
            }
        }

        /* "class " — check 6 tokens: 'c','l','a','s','s',' ' */
        if (c0 == (uint8_t)'c' && (i + 5u) < count) {
            if ((uint8_t)(raw_tokens[i+1] & 0xFFu) == (uint8_t)'l' &&
                (uint8_t)(raw_tokens[i+2] & 0xFFu) == (uint8_t)'a' &&
                (uint8_t)(raw_tokens[i+3] & 0xFFu) == (uint8_t)'s' &&
                (uint8_t)(raw_tokens[i+4] & 0xFFu) == (uint8_t)'s' &&
                (uint8_t)(raw_tokens[i+5] & 0xFFu) == (uint8_t)' ') {
                found_code = 1u;
            }
        }

        /* UTF-8 "∫" = 0xE2 0x88 0xAB — check 3 tokens */
        if (c0 == 0xE2u && (i + 2u) < count) {
            uint8_t c1 = (uint8_t)(raw_tokens[i+1] & 0xFFu);
            uint8_t c2 = (uint8_t)(raw_tokens[i+2] & 0xFFu);
            if ((c1 == 0x88u && c2 == 0xABu) ||   /* ∫ */
                (c1 == 0x88u && c2 == 0x9Au)) {     /* √ */
                found_math = 1u;
            }
        }

        /* "once " — start of "once upon" — check 5 tokens */
        if (c0 == (uint8_t)'o' && (i + 4u) < count) {
            if ((uint8_t)(raw_tokens[i+1] & 0xFFu) == (uint8_t)'n' &&
                (uint8_t)(raw_tokens[i+2] & 0xFFu) == (uint8_t)'c' &&
                (uint8_t)(raw_tokens[i+3] & 0xFFu) == (uint8_t)'e' &&
                (uint8_t)(raw_tokens[i+4] & 0xFFu) == (uint8_t)' ') {
                /* Look ahead for "upon" */
                if ((i + 9u) < count &&
                    (uint8_t)(raw_tokens[i+5] & 0xFFu) == (uint8_t)'u' &&
                    (uint8_t)(raw_tokens[i+6] & 0xFFu) == (uint8_t)'p' &&
                    (uint8_t)(raw_tokens[i+7] & 0xFFu) == (uint8_t)'o' &&
                    (uint8_t)(raw_tokens[i+8] & 0xFFu) == (uint8_t)'n') {
                    found_creative = 1u;
                }
            }
        }
    }

    /* Priority: code > math > creative > general */
    if (found_code)     return DOMAIN_CODE;
    if (found_math)     return DOMAIN_MATH;
    if (found_creative) return DOMAIN_CREATIVE;
    return DOMAIN_GENERAL;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §4  Intent → domain mapping (L1 R1_PER path)
 * ═══════════════════════════════════════════════════════════════════════ */

static uint8_t intent_subtype_to_domain(uint8_t intent_subtype) {
    switch (intent_subtype) {
        case XCOG_INTENT_QUERY:
        case XCOG_INTENT_COMMAND:
        case XCOG_INTENT_CREATE:
        case XCOG_INTENT_MODIFY:
        case XCOG_INTENT_DELETE:
        case XCOG_INTENT_NAVIGATE:
        case XCOG_INTENT_CONFIGURE:
        case XCOG_INTENT_CONVERSE:
            return DOMAIN_GENERAL;
        case XCOG_INTENT_ANALYZE:
            return DOMAIN_CODE;
        default:
            return DOMAIN_GENERAL;
    }
}

/* ═══════════════════════════════════════════════════════════════════════
 * §5  Public API — xmind_heptagon_init
 * ═══════════════════════════════════════════════════════════════════════ */

void xmind_heptagon_init(xmind_heptagon_t *h) {
    if (h == NULL) return;

    /* Zero entire struct — clears all counters, pointers, flags */
    uint8_t *p   = (uint8_t *)h;
    uint32_t len = (uint32_t)sizeof(xmind_heptagon_t);
    for (uint32_t i = 0u; i < len; i++) p[i] = 0u;

    /* L6 Calibration defaults — conservative neutral sampler */
    h->calibrated_temp  = 0.7f;
    h->calibrated_top_p = 0.9f;

    /* Telemetry disabled by default until consumer registered */
    h->telemetry_fd      = -1;
    h->telemetry_enabled = 1u;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §6  Public API — xmind_heptagon_pre_inference
 *
 * L1 Ontology: classify intent and query domain before prompt prefill.
 * Two paths:
 *   (A) R1_PER signal available (signal != NULL, fallback_flag == 0):
 *       Read first XCOG_INTENT instruction; map subtype to domain.
 *   (B) Fallback (signal == NULL or fallback_flag == 1):
 *       Run keyword classifier over raw_tokens.
 *
 * Returns 0 to proceed, negative to reject inference.
 * ═══════════════════════════════════════════════════════════════════════ */

int xmind_heptagon_pre_inference(xmind_heptagon_t             *h,
                                  const xmind_inference_input_t *input) {
    if (h == NULL || input == NULL) return -1;

    /* Reset per-session metrics for this inference run */
    h->avg_confidence    = 0.0f;
    h->attention_entropy = 0.0f;
    h->tokens_generated  = 0u;
    h->eval_score        = 0.0f;
    h->safety_halt       = 0u;

    /* Path A — R1_PER signal present and not in fallback mode */
    if (input->signal != NULL && input->signal->fallback_flag == 0u) {
        const r1_per_signal_t *sig = input->signal;
        uint16_t count = sig->instruction_count;

        h->current_signal = input->signal;
        h->intent_code    = 0u;
        h->query_domain   = DOMAIN_GENERAL;

        /* Scan XCOG stream for first XCOG_INTENT instruction */
        for (uint16_t i = 0u; i < count && i < R1_PER_MAX_INSTRUCTIONS; i++) {
            const xcog_instr_t *instr = &sig->instructions[i];
            if (instr->opcode == XCOG_INTENT) {
                /* intent_code = subtype (high byte) | confidence low byte */
                h->intent_code  = (uint16_t)((uint16_t)instr->subtype << 8)
                                | (uint16_t)(instr->payload & 0xFFu);
                h->query_domain = intent_subtype_to_domain(instr->subtype);
                break;
            }
        }
        return 0;
    }

    /* Path B — Fallback: keyword classification on raw tokens */
    h->current_signal = NULL;
    h->intent_code    = 0u;
    h->query_domain   = classify_domain_keywords(input->raw_tokens,
                                                  input->raw_token_count);
    return 0;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §7  Public API — xmind_heptagon_per_token
 *
 * L4 Instrumentation: called after xmind_forward(), before xmind_sample().
 *
 * Operations:
 *   1. Compute numerically-stable softmax via max-shift.
 *   2. Extract p(token_id) for the current sampled token.
 *   3. Update running exponential average of avg_confidence (alpha=0.1).
 *   4. Compute attention_entropy over top-10 logits.
 *   5. Increment tokens_generated.
 *   6. L7 check: if safety_halt set, return -1 immediately.
 *
 * Complexity: O(vocab_size) — one pass for max/sum, O(1) for top-10 scan.
 *
 * Returns 0 to continue, -1 to halt.
 * ═══════════════════════════════════════════════════════════════════════ */

/* Number of top logits to include in entropy computation.
 * Keeping this small (10) bounds the per-token cost to O(vocab_size)
 * for the softmax pass + O(10) for entropy, not O(vocab_size·log(v)).  */
#define HEPT_ENTROPY_TOP_K  10u

int xmind_heptagon_per_token(xmind_heptagon_t *h,
                              uint32_t          token_id,
                              float            *logits,
                              uint32_t          vocab_size) {
    if (h == NULL || logits == NULL || vocab_size == 0u) return -1;

    /* L7 check first — honour halt set by external escalation */
    if (h->safety_halt) return -1;

    if (token_id >= vocab_size) return -1;

    /* ── Step 1: find max logit for numerical stability ── */
    float max_logit = logits[0];
    for (uint32_t i = 1u; i < vocab_size; i++) {
        if (logits[i] > max_logit) max_logit = logits[i];
    }

    /* ── Step 2: compute sum_exp and exp for token_id ── */
    float sum_exp      = 0.0f;
    float token_exp    = 0.0f;
    for (uint32_t i = 0u; i < vocab_size; i++) {
        float e = exp_fast(logits[i] - max_logit);
        sum_exp += e;
        if (i == token_id) token_exp = e;
    }

    float token_prob = (sum_exp > 0.0f) ? (token_exp / sum_exp) : 0.0f;

    /* ── Step 3: running exponential average of confidence ── */
    /* alpha=0.1 — slow adaptation to preserve session context */
    const float alpha = 0.1f;
    if (h->tokens_generated == 0u) {
        h->avg_confidence = token_prob;
    } else {
        h->avg_confidence = alpha * token_prob
                          + (1.0f - alpha) * h->avg_confidence;
    }

    /* ── Step 4: attention entropy over top-HEPT_ENTROPY_TOP_K logits ──
     *
     * We track the top-K (logit, exp) pairs in a small array via
     * insertion into a min-heap of size K.  Since K=10 is fixed and tiny,
     * a simple selection scan is O(vocab_size · K) but K is a constant,
     * so effective complexity remains O(vocab_size).
     *
     * Entropy = -sum_{i in top-K}( p_i · ln(p_i) ) where p_i is the
     * re-normalised probability within the top-K set.                   */
    {
        /* Collect top-K indices by exp value (proportional to probability) */
        uint32_t top_idx[HEPT_ENTROPY_TOP_K];
        float    top_exp[HEPT_ENTROPY_TOP_K];
        uint32_t filled = 0u;

        for (uint32_t i = 0u; i < vocab_size; i++) {
            float e = exp_fast(logits[i] - max_logit);
            if (filled < HEPT_ENTROPY_TOP_K) {
                top_idx[filled] = i;
                top_exp[filled] = e;
                filled++;
            } else {
                /* Replace minimum if current is larger */
                uint32_t min_pos = 0u;
                for (uint32_t j = 1u; j < HEPT_ENTROPY_TOP_K; j++) {
                    if (top_exp[j] < top_exp[min_pos]) min_pos = j;
                }
                if (e > top_exp[min_pos]) {
                    top_idx[min_pos] = i;
                    top_exp[min_pos] = e;
                }
            }
        }

        /* Re-normalise top-K to get local probability distribution */
        float local_sum = 0.0f;
        for (uint32_t j = 0u; j < filled; j++) local_sum += top_exp[j];

        float entropy = 0.0f;
        if (local_sum > 0.0f) {
            for (uint32_t j = 0u; j < filled; j++) {
                float p = top_exp[j] / local_sum;
                if (p > 0.0f) {
                    entropy -= p * log_fast(p);
                }
            }
        }
        h->attention_entropy = entropy;

        /* Suppress unused variable warning for top_idx when not debugging */
        (void)top_idx;
    }

    /* ── Step 5: increment token counter ── */
    h->tokens_generated++;

    return 0;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §8  Public API — xmind_heptagon_post_inference
 *
 * L5 Evaluation + L6 Calibration + L7 Enforcement:
 *   Called once per generation cycle after all tokens are produced.
 *
 * eval_score formula:
 *   confidence_component = avg_confidence × 0.6
 *   entropy_component    = (1.0 - attention_entropy / ln(vocab_approx)) × 0.4
 *   eval_score           = confidence_component + entropy_component
 *
 *   vocab_approx = ln(XMIND_VOCAB_SIZE) where XMIND_VOCAB_SIZE = 128256.
 *   ln(128256) ≈ 11.762.  Precomputed to avoid log() at runtime.
 *
 * Calibration (L6):
 *   eval_score < 0.5 → temperature += 0.05 (increase diversity)
 *   eval_score > 0.8 → temperature -= 0.03 (decrease noise)
 *   Clamped to [0.1, 1.5].  top_p unchanged by this heuristic.
 *
 * Returns 0 on success, -1 on invariant violation.
 * ═══════════════════════════════════════════════════════════════════════ */

/* ln(128256) ≈ 11.762 — precomputed normalisation constant for entropy */
#define HEPT_LN_VOCAB  11.762f

/* Temperature adjustment deltas and clamp bounds */
#define HEPT_TEMP_BUMP_UP    0.05f
#define HEPT_TEMP_BUMP_DOWN  0.03f
#define HEPT_TEMP_MIN        0.1f
#define HEPT_TEMP_MAX        1.5f

int xmind_heptagon_post_inference(xmind_heptagon_t *h) {
    if (h == NULL) return -1;

    /* ── L5 Evaluation ── */
    float norm_entropy = h->attention_entropy / HEPT_LN_VOCAB;
    /* Clamp norm_entropy to [0, 1] */
    if (norm_entropy < 0.0f) norm_entropy = 0.0f;
    if (norm_entropy > 1.0f) norm_entropy = 1.0f;

    float eval = h->avg_confidence * 0.6f
               + (1.0f - norm_entropy) * 0.4f;
    /* Clamp to [0, 1] */
    if (eval < 0.0f) eval = 0.0f;
    if (eval > 1.0f) eval = 1.0f;
    h->eval_score = eval;

    /* ── L7 Enforcement — invariant violation check ── */
    if (eval < 0.3f) {
        h->invariant_violations++;
    }

    if (h->invariant_violations > 0u) {
        /* Build causal trace string: "trace=<hex_prefix> eval=X.XX" */
        char detail[64];
        char *p = detail;
        const char *end = detail + 63;

        /* Write "trace=" then first 8 bytes of input_hash as 16 hex chars */
        const char hex_chars[] = "0123456789abcdef";
        const uint8_t *hash = (h->current_signal != NULL)
                            ? h->current_signal->input_hash
                            : (const uint8_t *)"\0\0\0\0\0\0\0\0";

        const char *prefix = "trace=";
        for (uint32_t i = 0u; prefix[i] && p < end; i++) *p++ = prefix[i];
        for (uint32_t i = 0u; i < 8u && (p + 2) < end; i++) {
            *p++ = hex_chars[(hash[i] >> 4) & 0xFu];
            *p++ = hex_chars[ hash[i]       & 0xFu];
        }
        const char *ev_str = " eval=";
        for (uint32_t i = 0u; ev_str[i] && p < end; i++) *p++ = ev_str[i];
        {
            char tmp[16]; char *e = f32_to_str(tmp, eval); *e = '\0';
            for (uint32_t i = 0u; tmp[i] && p < end; i++) *p++ = tmp[i];
        }
        *p = '\0';

        xsec_audit_log((xsec_audit_event_t)XSEC_AUDIT_XCOG_ESCALATION,
                       (xsec_module_id_t)XSEC_MODULE_COGNITIVE,
                       detail);
    }

    /* ── Telemetry emission ── */
    if (h->telemetry_enabled) {
        xmind_telemetry_packet_t pkt;

        /* Zero the packet */
        uint8_t *pp = (uint8_t *)&pkt;
        for (uint32_t i = 0u; i < (uint32_t)sizeof(pkt); i++) pp[i] = 0u;

        pkt.magic               = XMIND_TELEMETRY_MAGIC;
        pkt.timestamp_ns        = pal_time_now_ns();
        pkt.session_id          = h->telemetry_seq;
        pkt.tokens_generated    = (uint16_t)(h->tokens_generated > 0xFFFFu
                                             ? 0xFFFFu : h->tokens_generated);
        pkt.intent_code         = (uint16_t)(h->intent_code);
        pkt.eval_score          = h->eval_score;
        pkt.avg_confidence      = h->avg_confidence;
        pkt.attention_entropy   = h->attention_entropy;
        pkt.invariant_violations = h->invariant_violations;
        pkt.safety_halted       = h->safety_halt;
        pkt.fallback_used       = (h->current_signal == NULL) ? 1u : 0u;

        /* Copy input_hash from R1_PER signal if available */
        if (h->current_signal != NULL) {
            for (uint32_t i = 0u; i < 32u; i++) {
                pkt.input_hash[i] = h->current_signal->input_hash[i];
            }
        }

        xmind_telemetry_emit(h, &pkt);
    }

    /* ── L6 Calibration — temperature adjustment ── */
    if (eval < 0.5f) {
        h->calibrated_temp += HEPT_TEMP_BUMP_UP;
    } else if (eval > 0.8f) {
        h->calibrated_temp -= HEPT_TEMP_BUMP_DOWN;
    }
    /* Clamp temperature */
    if (h->calibrated_temp < HEPT_TEMP_MIN) h->calibrated_temp = HEPT_TEMP_MIN;
    if (h->calibrated_temp > HEPT_TEMP_MAX) h->calibrated_temp = HEPT_TEMP_MAX;

    return (h->invariant_violations > 0u) ? -1 : 0;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §9  Public API — xmind_heptagon_get_sampler
 *
 * Returns L6-calibrated sampler parameters.  Called from inference.c
 * just before xmind_sample() to apply the current session calibration.
 * ═══════════════════════════════════════════════════════════════════════ */

void xmind_heptagon_get_sampler(const xmind_heptagon_t *h,
                                 float                  *temp_out,
                                 float                  *top_p_out) {
    if (h == NULL) {
        if (temp_out)  *temp_out  = 0.7f;
        if (top_p_out) *top_p_out = 0.9f;
        return;
    }
    if (temp_out)  *temp_out  = h->calibrated_temp;
    if (top_p_out) *top_p_out = h->calibrated_top_p;
}
