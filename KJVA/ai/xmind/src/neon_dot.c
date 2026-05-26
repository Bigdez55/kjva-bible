/*
 * neon_dot.c -- XMIND NEON SIMD Dot Product & Matvec (AArch64)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * ARM NEON/ASIMD accelerated math primitives for XMIND inference
 * on AArch64 targets.  This is the ARM64 counterpart to the AVX2
 * path in avx2_dot.c / tensor.c.
 *
 * Functions:
 *   xmind_neon_dot_f32   -- fp32 dot product (NEON FMLA, 4-wide)
 *   xmind_neon_matvec_f32 -- fp32 matrix-vector multiply
 *   xmind_neon_dot_q4_0  -- Q4_0 dequant + dot product
 *
 * All functions are guarded by #ifdef __aarch64__ and compile to
 * empty stubs on non-ARM64 targets.
 *
 * Freestanding C. No libc.
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"

#ifdef __aarch64__
#include <arm_neon.h>

/* ===================================================================
 * S1  FP32 DOT PRODUCT (NEON 4-wide FMLA)
 *
 * Process 16 floats per iteration (4x unrolled), then 4-wide cleanup,
 * then scalar tail.  Uses vfmaq_f32 (fused multiply-accumulate) for
 * maximum throughput.
 *
 * On Cortex-A76/A78 class cores:
 *   - vfmaq_f32: 1 cycle throughput, 4 cycle latency
 *   - 4x unroll hides FMA latency behind throughput
 *   - Expected ~16 FLOP/cycle per core
 *
 * Parameters:
 *   a, b:  float32 vectors, at least n elements
 *   n:     number of elements (need not be aligned)
 *
 * Returns: sum(a[i] * b[i]) for i in [0, n)
 * =================================================================== */

float xmind_neon_dot_f32(const float *a, const float *b, uint32_t n) {
    float32x4_t sum0 = vdupq_n_f32(0.0f);
    float32x4_t sum1 = vdupq_n_f32(0.0f);
    float32x4_t sum2 = vdupq_n_f32(0.0f);
    float32x4_t sum3 = vdupq_n_f32(0.0f);

    uint32_t i = 0u;

    /* 16-wide main loop (4x4 unroll) */
    for (; i + 16u <= n; i += 16u) {
        float32x4_t va0 = vld1q_f32(a + i);
        float32x4_t vb0 = vld1q_f32(b + i);
        sum0 = vfmaq_f32(sum0, va0, vb0);

        float32x4_t va1 = vld1q_f32(a + i + 4u);
        float32x4_t vb1 = vld1q_f32(b + i + 4u);
        sum1 = vfmaq_f32(sum1, va1, vb1);

        float32x4_t va2 = vld1q_f32(a + i + 8u);
        float32x4_t vb2 = vld1q_f32(b + i + 8u);
        sum2 = vfmaq_f32(sum2, va2, vb2);

        float32x4_t va3 = vld1q_f32(a + i + 12u);
        float32x4_t vb3 = vld1q_f32(b + i + 12u);
        sum3 = vfmaq_f32(sum3, va3, vb3);
    }

    /* Merge accumulators */
    sum0 = vaddq_f32(sum0, sum1);
    sum2 = vaddq_f32(sum2, sum3);
    sum0 = vaddq_f32(sum0, sum2);

    /* 4-wide cleanup */
    for (; i + 4u <= n; i += 4u) {
        float32x4_t va = vld1q_f32(a + i);
        float32x4_t vb = vld1q_f32(b + i);
        sum0 = vfmaq_f32(sum0, va, vb);
    }

    /* Horizontal reduction: add all 4 lanes */
    float result = vaddvq_f32(sum0);

    /* Scalar tail */
    for (; i < n; i++) {
        result += a[i] * b[i];
    }

    return result;
}

/* ===================================================================
 * S2  FP32 MATRIX-VECTOR MULTIPLY (NEON)
 *
 * Computes: out[r] = dot(mat[r,:], vec) for r in [0, rows)
 *
 * Each row is a dot product of length `cols`.  We reuse the
 * NEON dot product for each row.
 *
 * Parameters:
 *   mat:   row-major matrix [rows x cols]
 *   vec:   vector [cols]
 *   out:   output vector [rows]
 *   rows:  number of rows
 *   cols:  number of columns
 * =================================================================== */

void xmind_neon_matvec_f32(const float *mat, const float *vec,
                            float *out, uint32_t rows, uint32_t cols) {
    uint32_t r;
    for (r = 0u; r < rows; r++) {
        out[r] = xmind_neon_dot_f32(mat + (uint64_t)r * cols, vec, cols);
    }
}

/* ===================================================================
 * S3  Q4_0 DEQUANTIZE + DOT PRODUCT (NEON)
 *
 * Computes the dot product of a Q4_0-quantized weight block with
 * a float32 activation vector.
 *
 * Q4_0 format (32 elements per block):
 *   - scale: float32 (or float16, caller converts to float32)
 *   - nibbles[16]: 16 bytes = 32 x 4-bit weights packed lo/hi
 *   - Each nibble: unsigned [0,15], dequant as (val - 8) * scale
 *
 * Parameters:
 *   a_q4:  16 bytes of packed nibble data
 *   scale: float32 scale factor for the block
 *   b:     float32 activation vector, 32 elements
 *   n:     must be 32 (block size)
 *
 * Returns: sum( dequant(a_q4[i]) * b[i] ) for i in [0, 32)
 * =================================================================== */

float xmind_neon_dot_q4_0(const uint8_t *a_q4, float scale,
                            const float *b, uint32_t n) {
    (void)n;  /* always 32 */

    float32x4_t vscale = vdupq_n_f32(scale);
    float32x4_t sum0   = vdupq_n_f32(0.0f);
    float32x4_t sum1   = vdupq_n_f32(0.0f);
    int32x4_t   v8     = vdupq_n_s32(8);

    uint32_t i;
    for (i = 0u; i < 16u; i += 4u) {
        /* Load 4 bytes = 8 nibbles = 8 weights */
        uint8_t b0 = a_q4[i];
        uint8_t b1 = a_q4[i + 1u];
        uint8_t b2 = a_q4[i + 2u];
        uint8_t b3 = a_q4[i + 3u];

        /* Extract low nibbles (even indices) */
        int32x4_t lo = {
            (int32_t)(b0 & 0x0Fu),
            (int32_t)(b1 & 0x0Fu),
            (int32_t)(b2 & 0x0Fu),
            (int32_t)(b3 & 0x0Fu)
        };
        lo = vsubq_s32(lo, v8);  /* center at zero */

        /* Extract high nibbles (odd indices) */
        int32x4_t hi = {
            (int32_t)(b0 >> 4u),
            (int32_t)(b1 >> 4u),
            (int32_t)(b2 >> 4u),
            (int32_t)(b3 >> 4u)
        };
        hi = vsubq_s32(hi, v8);

        /* Dequantize: weight = (nibble - 8) * scale */
        float32x4_t w_lo = vmulq_f32(vcvtq_f32_s32(lo), vscale);
        float32x4_t w_hi = vmulq_f32(vcvtq_f32_s32(hi), vscale);

        /* Multiply with activation and accumulate */
        uint32_t base = i * 2u;
        float32x4_t act_lo = vld1q_f32(b + base);
        float32x4_t act_hi = vld1q_f32(b + base + 4u);

        sum0 = vfmaq_f32(sum0, w_lo, act_lo);
        sum1 = vfmaq_f32(sum1, w_hi, act_hi);
    }

    sum0 = vaddq_f32(sum0, sum1);
    return vaddvq_f32(sum0);
}

#else /* !__aarch64__ */

/* Stub implementations for non-ARM64 builds (syntax-check only) */

float xmind_neon_dot_f32(const float *a, const float *b, uint32_t n) {
    float acc = 0.0f;
    uint32_t i;
    for (i = 0u; i < n; i++) {
        acc += a[i] * b[i];
    }
    return acc;
}

void xmind_neon_matvec_f32(const float *mat, const float *vec,
                            float *out, uint32_t rows, uint32_t cols) {
    uint32_t r;
    for (r = 0u; r < rows; r++) {
        out[r] = xmind_neon_dot_f32(mat + (uint64_t)r * cols, vec, cols);
    }
}

float xmind_neon_dot_q4_0(const uint8_t *a_q4, float scale,
                            const float *b, uint32_t n) {
    (void)n;
    float acc = 0.0f;
    uint32_t i;
    for (i = 0u; i < 16u; i++) {
        int32_t lo = (int32_t)(a_q4[i] & 0x0Fu) - 8;
        int32_t hi = (int32_t)(a_q4[i] >> 4u) - 8;
        acc += (float)lo * scale * b[i * 2u];
        acc += (float)hi * scale * b[i * 2u + 1u];
    }
    return acc;
}

#endif /* __aarch64__ */
