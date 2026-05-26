/*
 * neon_matmul.c -- XMIND NEON SIMD Matrix Multiplication (AArch64)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * ARM NEON/ASIMD accelerated matrix multiplication for XMIND inference
 * on AArch64 targets.  This is the ARM64 counterpart to the AVX2
 * JIT-emitted matmul in avx2_matmul.c.
 *
 * Strategy:
 *   4x4 tiled matmul using NEON FMLA.  The outer loops tile over M and N
 *   in blocks of 4, and the inner loop accumulates the K dimension using
 *   4-wide FMLA (vfmaq_laneq_f32).
 *
 * Performance target (Cortex-A76 class):
 *   ~12 GFLOPS single-core at 2.4 GHz (4 FMA/cycle * 2 * 2.4G / 4)
 *   Memory-bandwidth limited for large matrices (~25 GB/s LPDDR4x)
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
 * S1  4x4 MICRO-KERNEL
 *
 * Computes a 4x4 tile of C += A * B^T using NEON FMLA.
 * A is [4 x K], B is [4 x K] (B is accessed as rows, not columns).
 * C is [4 x 4], accumulated in 4 float32x4 registers.
 *
 * This micro-kernel processes 4 elements of K per iteration using
 * vfmaq_laneq_f32 for broadcast-multiply-accumulate.
 * =================================================================== */

static void neon_micro_4x4(const float *A, uint32_t lda,
                            const float *B, uint32_t ldb,
                            float *C,       uint32_t ldc,
                            uint32_t K) {
    /* Accumulators for 4 rows of C, each 4 columns */
    float32x4_t c0 = vld1q_f32(C + 0u * ldc);
    float32x4_t c1 = vld1q_f32(C + 1u * ldc);
    float32x4_t c2 = vld1q_f32(C + 2u * ldc);
    float32x4_t c3 = vld1q_f32(C + 3u * ldc);

    uint32_t k;
    for (k = 0u; k + 4u <= K; k += 4u) {
        /* Load 4 elements from each of the 4 rows of A */
        float32x4_t a0 = vld1q_f32(A + 0u * lda + k);
        float32x4_t a1 = vld1q_f32(A + 1u * lda + k);
        float32x4_t a2 = vld1q_f32(A + 2u * lda + k);
        float32x4_t a3 = vld1q_f32(A + 3u * lda + k);

        /* Load 4 elements from each of the 4 rows of B */
        float32x4_t b0 = vld1q_f32(B + 0u * ldb + k);
        float32x4_t b1 = vld1q_f32(B + 1u * ldb + k);
        float32x4_t b2 = vld1q_f32(B + 2u * ldb + k);
        float32x4_t b3 = vld1q_f32(B + 3u * ldb + k);

        /* Accumulate: C[i][j] += sum_k(A[i][k] * B[j][k]) */
        /* Row 0 of C */
        c0 = vfmaq_laneq_f32(c0, b0, a0, 0);
        c0 = vfmaq_laneq_f32(c0, b1, a0, 1);
        c0 = vfmaq_laneq_f32(c0, b2, a0, 2);
        c0 = vfmaq_laneq_f32(c0, b3, a0, 3);

        /* Row 1 of C */
        c1 = vfmaq_laneq_f32(c1, b0, a1, 0);
        c1 = vfmaq_laneq_f32(c1, b1, a1, 1);
        c1 = vfmaq_laneq_f32(c1, b2, a1, 2);
        c1 = vfmaq_laneq_f32(c1, b3, a1, 3);

        /* Row 2 of C */
        c2 = vfmaq_laneq_f32(c2, b0, a2, 0);
        c2 = vfmaq_laneq_f32(c2, b1, a2, 1);
        c2 = vfmaq_laneq_f32(c2, b2, a2, 2);
        c2 = vfmaq_laneq_f32(c2, b3, a2, 3);

        /* Row 3 of C */
        c3 = vfmaq_laneq_f32(c3, b0, a3, 0);
        c3 = vfmaq_laneq_f32(c3, b1, a3, 1);
        c3 = vfmaq_laneq_f32(c3, b2, a3, 2);
        c3 = vfmaq_laneq_f32(c3, b3, a3, 3);
    }

    /* Scalar tail for K not divisible by 4 */
    for (; k < K; k++) {
        float a0k = A[0u * lda + k];
        float a1k = A[1u * lda + k];
        float a2k = A[2u * lda + k];
        float a3k = A[3u * lda + k];

        float b0k = B[0u * ldb + k];
        float b1k = B[1u * ldb + k];
        float b2k = B[2u * ldb + k];
        float b3k = B[3u * ldb + k];

        /* Manually update each lane */
        float c0v[4], c1v[4], c2v[4], c3v[4];
        vst1q_f32(c0v, c0); vst1q_f32(c1v, c1);
        vst1q_f32(c2v, c2); vst1q_f32(c3v, c3);

        c0v[0] += a0k * b0k; c0v[1] += a0k * b1k;
        c0v[2] += a0k * b2k; c0v[3] += a0k * b3k;
        c1v[0] += a1k * b0k; c1v[1] += a1k * b1k;
        c1v[2] += a1k * b2k; c1v[3] += a1k * b3k;
        c2v[0] += a2k * b0k; c2v[1] += a2k * b1k;
        c2v[2] += a2k * b2k; c2v[3] += a2k * b3k;
        c3v[0] += a3k * b0k; c3v[1] += a3k * b1k;
        c3v[2] += a3k * b2k; c3v[3] += a3k * b3k;

        c0 = vld1q_f32(c0v); c1 = vld1q_f32(c1v);
        c2 = vld1q_f32(c2v); c3 = vld1q_f32(c3v);
    }

    /* Store back to C */
    vst1q_f32(C + 0u * ldc, c0);
    vst1q_f32(C + 1u * ldc, c1);
    vst1q_f32(C + 2u * ldc, c2);
    vst1q_f32(C + 3u * ldc, c3);
}

/* ===================================================================
 * S2  SCALAR EDGE HANDLERS
 *
 * Handle the edge tiles when M or N is not a multiple of 4.
 * =================================================================== */

static void scalar_matmul_tile(const float *A, uint32_t lda,
                                const float *B, uint32_t ldb,
                                float *C,       uint32_t ldc,
                                uint32_t mr, uint32_t nr, uint32_t K) {
    uint32_t i, j, k;
    for (i = 0u; i < mr; i++) {
        for (j = 0u; j < nr; j++) {
            float acc = C[i * ldc + j];
            for (k = 0u; k < K; k++) {
                acc += A[i * lda + k] * B[j * ldb + k];
            }
            C[i * ldc + j] = acc;
        }
    }
}

/* ===================================================================
 * S3  PUBLIC API: TILED MATMUL
 *
 * Computes: C[M x N] += A[M x K] * B[N x K]^T
 *
 * NOTE: B is stored in ROW-MAJOR ORDER with N rows of K elements.
 * This layout is natural for weight matrices in transformers where
 * each output neuron's weights are stored contiguously.
 *
 * The caller must zero-initialize C before calling if a fresh
 * multiplication is desired (this function accumulates into C).
 *
 * Parameters:
 *   A:  input matrix [M x K], row-major
 *   B:  weight matrix [N x K], row-major (transposed multiply)
 *   C:  output matrix [M x N], row-major
 *   M:  number of rows of A (and C)
 *   N:  number of rows of B (and columns of C)
 *   K:  inner dimension (columns of A, columns of B)
 * =================================================================== */

void xmind_neon_matmul_f32(const float *A, const float *B, float *C,
                             uint32_t M, uint32_t N, uint32_t K) {
    uint32_t i, j;

    /* Tile over M in blocks of 4 */
    for (i = 0u; i + 4u <= M; i += 4u) {
        /* Tile over N in blocks of 4 */
        for (j = 0u; j + 4u <= N; j += 4u) {
            neon_micro_4x4(A + i * K, K,
                           B + j * K, K,
                           C + i * N + j, N,
                           K);
        }
        /* N edge tile */
        if (j < N) {
            scalar_matmul_tile(A + i * K, K,
                               B + j * K, K,
                               C + i * N + j, N,
                               4u, N - j, K);
        }
    }

    /* M edge tile */
    if (i < M) {
        for (j = 0u; j < N; j++) {
            uint32_t ii;
            for (ii = i; ii < M; ii++) {
                float acc = C[ii * N + j];
                uint32_t k;
                for (k = 0u; k < K; k++) {
                    acc += A[ii * K + k] * B[j * K + k];
                }
                C[ii * N + j] = acc;
            }
        }
    }
}

#else /* !__aarch64__ */

/* Scalar fallback for non-ARM64 builds */

/* Forward declare the NEON dot for the scalar matvec to reuse */
extern float xmind_neon_dot_f32(const float *a, const float *b, uint32_t n);

void xmind_neon_matmul_f32(const float *A, const float *B, float *C,
                             uint32_t M, uint32_t N, uint32_t K) {
    uint32_t i, j, k;
    for (i = 0u; i < M; i++) {
        for (j = 0u; j < N; j++) {
            float acc = C[i * N + j];
            for (k = 0u; k < K; k++) {
                acc += A[i * K + k] * B[j * K + k];
            }
            C[i * N + j] = acc;
        }
    }
}

#endif /* __aarch64__ */
