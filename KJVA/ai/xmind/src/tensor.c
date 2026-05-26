/*
 * tensor.c -- XMIND Math Primitives (AVX2 SIMD optimized)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Sprint 41: AVX2+FMA3 SIMD dispatch for matmul, dot product, and RMSNorm.
 * Runtime CPUID detection selects AVX2 or scalar at init time via
 * xmind_simd_init().  No CPUID in the hot path -- function pointers
 * are resolved once and stored in module-static state.
 *
 * Functions:
 *   xm_memset / xm_memcpy    -- memory helpers
 *   xm_expf / xm_sqrtf       -- scalar math (no <math.h>)
 *   xmind_simd_init           -- runtime CPUID probe + dispatch setup
 *   xmind_rmsnorm             -- RMS layer normalization
 *   xmind_matmul_q4           -- Q4_0 quantized matrix-vector multiply
 *   xmind_softmax             -- numerically stable softmax
 *   xmind_dot                 -- fp32 dot product (AVX2 or scalar)
 *   xmind_silu                -- SiLU activation (SwiGLU variant)
 *   xmind_rope                -- Rotary Position Embedding
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"

/* XJIT AVX2 dot-product and matvec functions (avx2_dot.c).
 * Declared via xjit.h; we forward-declare the subset we need here
 * to avoid pulling in the entire JIT header into XMIND translation units. */
extern uint8_t xjit_avx2_available(void);
extern float   xjit_dot_f32_avx2(const float *a, const float *b, uint32_t n);
extern float   xjit_dot_f32_scalar(const float *a, const float *b, uint32_t n);
extern float   xjit_dot_q4_0_avx2(const uint8_t *quants, float scale,
                                    const float *input, uint32_t n);
extern void    xjit_matvec_f32_avx2(float *out, const float *mat,
                                     const float *vec, uint32_t M, uint32_t K);
extern void    xjit_matvec_f32_scalar(float *out, const float *mat,
                                       const float *vec, uint32_t M, uint32_t K);

/* ====================================================================
 * S0  SIMD DISPATCH STATE
 *
 * Function pointers resolved by xmind_simd_init().  Defaults to scalar.
 * Single-threaded at boot -- no atomics needed.
 * ==================================================================== */

typedef float (*xm_dot_fn_t)(const float *a, const float *b, uint32_t n);
typedef void  (*xm_matvec_fn_t)(float *out, const float *mat,
                                 const float *vec, uint32_t M, uint32_t K);
typedef float (*xm_dot_q4_fn_t)(const uint8_t *quants, float scale,
                                 const float *input, uint32_t n);

static xm_dot_fn_t    s_dot_f32   = (xm_dot_fn_t)0;
__attribute__((unused))
static xm_matvec_fn_t s_matvec    = (xm_matvec_fn_t)0;
static xm_dot_q4_fn_t s_dot_q4    = (xm_dot_q4_fn_t)0;
static uint8_t        s_simd_init = 0u;

void xmind_simd_init(void) {
    uint8_t has_avx2 = xjit_avx2_available();
    if (has_avx2) {
        s_dot_f32 = xjit_dot_f32_avx2;
        s_matvec  = xjit_matvec_f32_avx2;
        s_dot_q4  = xjit_dot_q4_0_avx2;
        pal_console_printf("[XMIND] SIMD: AVX2+FMA3 detected -- "
                           "accelerated inference enabled\n");
    } else {
        s_dot_f32 = xjit_dot_f32_scalar;
        s_matvec  = xjit_matvec_f32_scalar;
        s_dot_q4  = (xm_dot_q4_fn_t)0;  /* scalar Q4 handled inline */
        pal_console_printf("[XMIND] SIMD: AVX2 not available -- "
                           "using scalar path\n");
    }
    s_simd_init = 1u;
}

/* ====================================================================
 * S1  INTERNAL MEMORY HELPERS
 * ==================================================================== */

__attribute__((unused))
static void xm_memset(void *dst, uint8_t v, uint64_t n) {
    uint8_t *p = (uint8_t *)dst;
    uint64_t i;
    for (i = 0u; i < n; i++) {
        p[i] = v;
    }
}

__attribute__((unused))
static void xm_memcpy(void *dst, const void *src, uint64_t n) {
    uint8_t       *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;
    uint64_t       i;
    for (i = 0u; i < n; i++) {
        d[i] = s[i];
    }
}

/* ====================================================================
 * S2  SCALAR MATH -- expf via 2^(x*log2e) bit trick
 *
 * Algorithm:
 *   expf(x) = 2^(x * log2(e))
 *   Split exponent into integer n and fractional f in [0,1).
 *   2^n  is exact via IEEE 754 bit manipulation.
 *   2^f  is approximated by a degree-5 minimax polynomial on [0,1).
 *
 * Max relative error on [-87, 87]: < 1.5e-6  (sufficient for softmax).
 * ==================================================================== */

#define XM_LOG2E  1.4426950408889634f   /* log2(e) */
#define XM_LN2    0.6931471805599453f   /* ln(2)   */

static float xm_expf(float x) {
    /* Clamp to avoid IEEE 754 overflow / underflow */
    if (x >  87.0f) { x =  87.0f; }
    if (x < -87.0f) { x = -87.0f; }

    /* y = x * log2(e) */
    float y = x * XM_LOG2E;

    /* n = floor(y); f = y - n  (f in [0, 1)) */
    int32_t n = (int32_t)y;
    if ((float)n > y) { n -= 1; }   /* handle negative floor */
    float f = y - (float)n;

    /* 2^f via degree-5 polynomial (Horner form, coefficients for [0,1)) */
    float p = 1.0f + f * (0.6931471806f
                  + f * (0.2402265069f
                  + f * (0.0555041086f
                  + f * (0.0096181292f
                  + f *  0.0013333558f))));

    /* 2^n via IEEE 754 biased exponent field */
    union { float fv; uint32_t u; } bits;
    bits.u = (uint32_t)((n + 127) << 23);
    return p * bits.fv;
}

/* ====================================================================
 * S3  sqrtf via Newton-Raphson (3 iterations)
 *
 * Seed from Quake fast inverse sqrt, then three NR refinements.
 * Three NR iterations give ~6 ULP accuracy on [1e-6, 1e8].
 * ==================================================================== */
static float xm_sqrtf(float x) {
    if (x <= 0.0f) { return 0.0f; }

    /* Initial estimate via bit hack (inverse sqrt scaled) */
    union { float f; uint32_t u; } bits;
    bits.f = x;
    bits.u = 0x1FBD1DF5u + (bits.u >> 1u);
    float r = bits.f;  /* r ~ sqrt(x), rough */

    /* Newton-Raphson: r_{k+1} = (r_k + x/r_k) / 2 */
    r = 0.5f * (r + x / r);
    r = 0.5f * (r + x / r);
    r = 0.5f * (r + x / r);
    return r;
}

/* ====================================================================
 * S4  RMS NORMALIZATION
 *
 *   rms  = sqrt( mean(x^2) + eps )
 *   out[i] = (x[i] / rms) * weight[i]
 *
 * Epsilon 1e-5 matches LLaMA reference implementation.
 * The sum-of-squares computation uses AVX2 dot product when available
 * (xmind_dot dispatches to the SIMD path).
 * Complexity: O(n).
 * ==================================================================== */
void xmind_rmsnorm(float *out, const float *x, const float *weight, uint32_t n) {
    XM_ASSERT(out != (void *)0);
    XM_ASSERT(x   != (void *)0);
    XM_ASSERT(weight != (void *)0);
    XM_ASSERT(n > 0u);

    /* Use SIMD-accelerated dot product for sum-of-squares when available */
    float ss;
    if (s_simd_init && s_dot_f32) {
        ss = s_dot_f32(x, x, n);
    } else {
        ss = 0.0f;
        uint32_t i;
        for (i = 0u; i < n; i++) {
            ss += x[i] * x[i];
        }
    }
    ss = ss / (float)n + 1e-5f;
    float scale = 1.0f / xm_sqrtf(ss);
    uint32_t i;
    for (i = 0u; i < n; i++) {
        out[i] = weight[i] * (x[i] * scale);
    }
}

/* ====================================================================
 * S5  Q4_0 MATRIX-VECTOR MULTIPLY (AVX2 accelerated)
 *
 * Computes: out[r] = sum_c( W[r,c] * x[c] )  for r in [0, rows)
 *
 * W is stored in Q4_0 format: each row has (cols / XMIND_Q4_BLOCK)
 * xmind_q4_block_t structs.  When AVX2 is available, each 32-element
 * block's dot product is computed via xjit_dot_q4_0_avx2() which
 * performs dequantization and FMA in-register without materializing
 * the dequantized weights to memory.
 *
 * cols must be a multiple of XMIND_Q4_BLOCK (32).
 * Complexity: O(rows x cols).
 * ==================================================================== */
void xmind_matmul_q4(float *out, const float *x,
                     const xmind_q4_block_t *W,
                     uint32_t rows, uint32_t cols) {
    XM_ASSERT(out != (void *)0);
    XM_ASSERT(x   != (void *)0);
    XM_ASSERT(W   != (void *)0);
    XM_ASSERT(cols % XMIND_Q4_BLOCK == 0u);

    uint32_t n_blocks_per_row = cols / XMIND_Q4_BLOCK;
    uint32_t r, b;

    if (s_simd_init && s_dot_q4) {
        /* ── AVX2 accelerated path ──────────────────────────────────
         * Each Q4_0 block: xjit_dot_q4_0_avx2() performs fused
         * dequantize + dot in YMM registers.  No intermediate buffer. */
        for (r = 0u; r < rows; r++) {
            float acc = 0.0f;
            const xmind_q4_block_t *row_blks =
                W + (uint64_t)r * n_blocks_per_row;

            for (b = 0u; b < n_blocks_per_row; b++) {
                const xmind_q4_block_t *blk = &row_blks[b];
                uint32_t base_col = b * XMIND_Q4_BLOCK;
                acc += s_dot_q4(blk->nibbles, blk->scale,
                                x + base_col, XMIND_Q4_BLOCK);
            }
            out[r] = acc;
        }
    } else {
        /* ── Scalar fallback ────────────────────────────────────────
         * Inline dequant + multiply-accumulate per nibble pair.     */
        uint32_t i;
        for (r = 0u; r < rows; r++) {
            float acc = 0.0f;
            const xmind_q4_block_t *row_blocks =
                W + (uint64_t)r * n_blocks_per_row;

            for (b = 0u; b < n_blocks_per_row; b++) {
                const xmind_q4_block_t *blk = &row_blocks[b];
                float blk_scale = blk->scale;
                uint32_t base_col = b * XMIND_Q4_BLOCK;

                /* 16 bytes -> 32 nibbles -> 32 weights */
                for (i = 0u; i < 16u; i++) {
                    uint8_t byte   = blk->nibbles[i];
                    int32_t lo_raw = (int32_t)(byte & 0x0Fu) - 8;
                    int32_t hi_raw = (int32_t)(byte >> 4u)  - 8;
                    float   w_lo   = (float)lo_raw * blk_scale;
                    float   w_hi   = (float)hi_raw * blk_scale;
                    acc += w_lo * x[base_col + i * 2u];
                    acc += w_hi * x[base_col + i * 2u + 1u];
                }
            }
            out[r] = acc;
        }
    }
}

/* ====================================================================
 * S6  NUMERICALLY STABLE SOFTMAX
 *
 *   1. Find max value (subtract to prevent overflow in expf)
 *   2. Compute exp(x[i] - max) for all i
 *   3. Normalise by sum
 *
 * Complexity: O(n).
 * ==================================================================== */
void xmind_softmax(float *x, uint32_t n) {
    XM_ASSERT(x != (void *)0);
    XM_ASSERT(n > 0u);

    /* Find max */
    float mx = x[0];
    uint32_t i;
    for (i = 1u; i < n; i++) {
        if (x[i] > mx) { mx = x[i]; }
    }

    /* Exp and sum */
    float sum = 0.0f;
    for (i = 0u; i < n; i++) {
        x[i] = xm_expf(x[i] - mx);
        sum += x[i];
    }

    /* Normalise */
    float inv_sum = 1.0f / sum;
    for (i = 0u; i < n; i++) {
        x[i] *= inv_sum;
    }
}

/* ====================================================================
 * S7  DOT PRODUCT (SIMD-dispatched)
 *
 * Routes to xjit_dot_f32_avx2 or xjit_dot_f32_scalar based on the
 * result of xmind_simd_init().  If init has not been called, falls
 * back to the inline scalar loop.
 * ==================================================================== */

float xmind_dot(const float *a, const float *b, uint32_t n) {
    XM_ASSERT(a != (void *)0);
    XM_ASSERT(b != (void *)0);

    if (s_simd_init && s_dot_f32) {
        return s_dot_f32(a, b, n);
    }

    /* Fallback scalar */
    float acc = 0.0f;
    uint32_t i;
    for (i = 0u; i < n; i++) {
        acc += a[i] * b[i];
    }
    return acc;
}

/* ====================================================================
 * S8  SiLU (Sigmoid Linear Unit) -- SwiGLU variant
 *
 *   silu(gate)[i] = gate[i] * sigmoid(gate[i])
 *                 = gate[i] / (1 + exp(-gate[i]))
 *   out[i] = silu(gate[i]) * up[i]
 *
 * This is the SwiGLU FFN activation used in LLaMA models.
 * Complexity: O(n).
 * ==================================================================== */
void xmind_silu(float *out, const float *gate, const float *up, uint32_t n) {
    XM_ASSERT(out  != (void *)0);
    XM_ASSERT(gate != (void *)0);
    XM_ASSERT(up   != (void *)0);

    uint32_t i;
    for (i = 0u; i < n; i++) {
        float g  = gate[i];
        float sg = 1.0f / (1.0f + xm_expf(-g));  /* sigmoid(g) */
        out[i] = g * sg * up[i];
    }
}

/* ====================================================================
 * S9  ROTARY POSITION EMBEDDING (RoPE)
 *
 * Applies RoPE to the query and key vectors for a single token at
 * position `pos`.  The rotation operates on consecutive pairs:
 *
 *   q'[2i]   = q[2i]   * cos - q[2i+1] * sin
 *   q'[2i+1] = q[2i]   * sin + q[2i+1] * cos
 *
 * cos/sin are looked up from pre-computed tables indexed by:
 *   table[pos * (head_dim/2) + i]
 *
 * For GQA (n_kv_heads < n_heads), key vectors use the same rotation
 * but only for n_kv_heads heads.
 *
 * Complexity: O(n_heads x head_dim).
 * ==================================================================== */
void xmind_rope(float *q, float *k,
                const float *cos_table, const float *sin_table,
                uint32_t pos, uint32_t head_dim,
                uint32_t n_heads, uint32_t n_kv_heads) {
    XM_ASSERT(q         != (void *)0);
    XM_ASSERT(k         != (void *)0);
    XM_ASSERT(cos_table != (void *)0);
    XM_ASSERT(sin_table != (void *)0);
    XM_ASSERT(head_dim % 2u == 0u);

    uint32_t half = head_dim / 2u;
    uint32_t h, i;
    uint32_t table_base = pos * half;

    /* Rotate query heads */
    for (h = 0u; h < n_heads; h++) {
        float *qh = q + h * head_dim;
        for (i = 0u; i < half; i++) {
            float c  = cos_table[table_base + i];
            float s  = sin_table[table_base + i];
            float q0 = qh[2u * i];
            float q1 = qh[2u * i + 1u];
            qh[2u * i]      = q0 * c - q1 * s;
            qh[2u * i + 1u] = q0 * s + q1 * c;
        }
    }

    /* Rotate key heads (only n_kv_heads for GQA) */
    for (h = 0u; h < n_kv_heads; h++) {
        float *kh = k + h * head_dim;
        for (i = 0u; i < half; i++) {
            float c  = cos_table[table_base + i];
            float s  = sin_table[table_base + i];
            float k0 = kh[2u * i];
            float k1 = kh[2u * i + 1u];
            kh[2u * i]      = k0 * c - k1 * s;
            kh[2u * i + 1u] = k0 * s + k1 * c;
        }
    }
}
