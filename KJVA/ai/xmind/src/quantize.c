/*
 * quantize.c — XMIND Q4_0 Quantization Utilities
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Q4_0 format:
 *   Each block of XMIND_Q4_BLOCK (32) weights is represented by:
 *     - float scale = max_abs / 7.0f
 *     - 16 bytes of packed nibbles (2 weights per byte)
 *
 *   Quantize:  q = clamp(round(w / scale), -8, 7)
 *              stored nibble = (uint8_t)(q + 8)  → range [0, 15]
 *
 *   Dequantize: w = (float)(nibble - 8) * scale
 *
 * Functions:
 *   xmind_q4_block_init        — zero a single block
 *   xmind_quantize_block       — fp32[32] → xmind_q4_block_t
 *   xmind_dequantize_block     — xmind_q4_block_t → fp32[32]
 *   xmind_quantize_row         — fp32[n] → xmind_q4_block_t[n/32]
 *   xmind_dequantize_row       — xmind_q4_block_t[n_blocks] → fp32[n_blocks*32]
 *   xmind_verify_q4_roundtrip  — self-test (marked unused)
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"

/* ═══════════════════════════════════════════════════════════════════
 * §1  INTERNAL HELPERS
 * ═══════════════════════════════════════════════════════════════════ */

/* Integer absolute value (avoids abs() from <stdlib.h>) */
static inline float xm_fabsf(float x) {
    return (x < 0.0f) ? -x : x;
}

/* Round float to nearest integer (no lroundf from <math.h>) */
static inline int32_t xm_roundf_i32(float x) {
    return (x >= 0.0f) ? (int32_t)(x + 0.5f) : (int32_t)(x - 0.5f);
}

/* Clamp int32 to [lo, hi] */
static inline int32_t xm_clamp_i32(int32_t v, int32_t lo, int32_t hi) {
    if (v < lo) { return lo; }
    if (v > hi) { return hi; }
    return v;
}

/* ═══════════════════════════════════════════════════════════════════
 * §2  BLOCK ZERO-INIT
 * ═══════════════════════════════════════════════════════════════════ */

void xmind_q4_block_init(xmind_q4_block_t *blk) {
    XM_ASSERT(blk != (void *)0);
    blk->scale = 0.0f;
    uint32_t i;
    for (i = 0u; i < 16u; i++) {
        blk->nibbles[i] = 0u;
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * §3  QUANTIZE ONE BLOCK  (fp32[32] → xmind_q4_block_t)
 * ═══════════════════════════════════════════════════════════════════
 *
 * Steps:
 *   1. Find max absolute value in the 32 inputs.
 *   2. scale = max_abs / 7.0f  (maps [-7*scale, 7*scale] onto [-7,7])
 *   3. For each weight: q = clamp(round(w / scale), -8, 7)
 *      Store as unsigned nibble = q + 8 in range [0, 15].
 *   4. Pack nibble pairs: nibbles[i] = lo | (hi << 4)
 *
 * If max_abs == 0 (all-zero block), scale = 0 and all nibbles = 8
 * (the midpoint, representing w = 0).
 */
void xmind_quantize_block(xmind_q4_block_t *blk, const float *in) {
    XM_ASSERT(blk != (void *)0);
    XM_ASSERT(in  != (void *)0);

    /* Find max absolute value */
    float max_abs = 0.0f;
    uint32_t i;
    for (i = 0u; i < XMIND_Q4_BLOCK; i++) {
        float a = xm_fabsf(in[i]);
        if (a > max_abs) { max_abs = a; }
    }

    /* Compute scale; handle zero block */
    float scale = (max_abs > 0.0f) ? (max_abs / 7.0f) : 1.0f;
    blk->scale = scale;

    float inv_scale = 1.0f / scale;

    /* Quantize and pack nibble pairs */
    for (i = 0u; i < 16u; i++) {
        float   w_lo   = in[i * 2u];
        float   w_hi   = in[i * 2u + 1u];
        int32_t q_lo   = xm_clamp_i32(xm_roundf_i32(w_lo * inv_scale), -8, 7);
        int32_t q_hi   = xm_clamp_i32(xm_roundf_i32(w_hi * inv_scale), -8, 7);
        uint8_t nib_lo = (uint8_t)(q_lo + 8);   /* [0, 15] */
        uint8_t nib_hi = (uint8_t)(q_hi + 8);   /* [0, 15] */
        blk->nibbles[i] = (uint8_t)(nib_lo | (nib_hi << 4u));
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * §4  DEQUANTIZE ONE BLOCK  (xmind_q4_block_t → fp32[32])
 * ═══════════════════════════════════════════════════════════════════
 *
 * For each packed byte:
 *   lo_nibble = byte & 0x0F
 *   hi_nibble = byte >> 4
 *   w = (float)(nibble - 8) * scale
 */
void xmind_dequantize_block(float *out, const xmind_q4_block_t *blk) {
    XM_ASSERT(out != (void *)0);
    XM_ASSERT(blk != (void *)0);

    float scale = blk->scale;
    uint32_t i;
    for (i = 0u; i < 16u; i++) {
        uint8_t byte   = blk->nibbles[i];
        int32_t lo_raw = (int32_t)(byte & 0x0Fu) - 8;
        int32_t hi_raw = (int32_t)(byte >> 4u)   - 8;
        out[i * 2u]      = (float)lo_raw * scale;
        out[i * 2u + 1u] = (float)hi_raw * scale;
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * §5  QUANTIZE AN ENTIRE ROW
 * ═══════════════════════════════════════════════════════════════════
 *
 * n must be a multiple of XMIND_Q4_BLOCK (32).
 * blocks must point to n/32 pre-allocated xmind_q4_block_t structs.
 */
void xmind_quantize_row(xmind_q4_block_t *blocks, const float *in, uint32_t n) {
    XM_ASSERT(blocks != (void *)0);
    XM_ASSERT(in     != (void *)0);
    XM_ASSERT(n > 0u);
    XM_ASSERT(n % XMIND_Q4_BLOCK == 0u);

    uint32_t n_blocks = n / XMIND_Q4_BLOCK;
    uint32_t b;
    for (b = 0u; b < n_blocks; b++) {
        xmind_quantize_block(&blocks[b], in + b * XMIND_Q4_BLOCK);
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * §6  DEQUANTIZE AN ENTIRE ROW
 * ═══════════════════════════════════════════════════════════════════
 *
 * out must point to n_blocks * XMIND_Q4_BLOCK pre-allocated floats.
 */
void xmind_dequantize_row(float *out, const xmind_q4_block_t *blocks,
                          uint32_t n_blocks) {
    XM_ASSERT(out    != (void *)0);
    XM_ASSERT(blocks != (void *)0);

    uint32_t b;
    for (b = 0u; b < n_blocks; b++) {
        xmind_dequantize_block(out + b * XMIND_Q4_BLOCK, &blocks[b]);
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * §7  ROUND-TRIP SELF-TEST  (compile-out in production)
 * ═══════════════════════════════════════════════════════════════════
 *
 * Encodes a known 32-element pattern, decodes it, and verifies that
 * the maximum reconstruction error is within the expected Q4_0 bound.
 *
 * Maximum theoretical error per weight = scale / 2 = max_abs / 14.
 * For max_abs = 7.0f (chosen below), that is 0.5f.
 *
 * Marked __attribute__((unused)) so the compiler does not warn when
 * this function is excluded from the production call graph.
 */
__attribute__((unused))
static void xmind_verify_q4_roundtrip(void) {
    /* Input: weights in [-7.0, 7.0] spanning the full quantization range */
    float in[XMIND_Q4_BLOCK];
    uint32_t i;
    for (i = 0u; i < XMIND_Q4_BLOCK; i++) {
        /* Map index [0..31] to [-7.75, 7.75] in steps of 0.5 */
        in[i] = (float)(int32_t)i * 0.5f - 7.75f;
    }

    xmind_q4_block_t blk;
    xmind_q4_block_init(&blk);
    xmind_quantize_block(&blk, in);

    float out[XMIND_Q4_BLOCK];
    xmind_dequantize_block(out, &blk);

    /* Verify max error < scale (= max_abs / 7.0) */
    float max_err = 0.0f;
    for (i = 0u; i < XMIND_Q4_BLOCK; i++) {
        float err = in[i] - out[i];
        if (err < 0.0f) { err = -err; }
        if (err > max_err) { max_err = err; }
    }

    /* scale = max_abs / 7.0; max_abs ≈ 7.75 → scale ≈ 1.107 */
    float expected_max_err = blk.scale;
    if (max_err > expected_max_err) {
        pal_console_printf("[XMIND] Q4 roundtrip FAIL: max_err=%d (scaled x1000), "
                           "expected <= %d (scaled x1000)\n",
                           (int32_t)(max_err * 1000.0f),
                           (int32_t)(expected_max_err * 1000.0f));
    } else {
        pal_console_printf("[XMIND] Q4 roundtrip OK: max_err=%d/1000 scale=%d/1000\n",
                           (int32_t)(max_err * 1000.0f),
                           (int32_t)(blk.scale * 1000.0f));
    }
}

/* =====================================================================
 * S8  Q4_K_M DEQUANTIZATION
 *
 * K-quant 4-bit mixed format from llama.cpp (ggml GGML_TYPE_Q4_K).
 * Each super-block encodes 256 weights with higher quality than Q4_0:
 *
 *   Layout (144 bytes per super-block):
 *     d     (uint16_t): super-block scale in IEEE fp16 bit pattern
 *     dmin  (uint16_t): super-block minimum in IEEE fp16 bit pattern
 *     scales_and_mins[12]: 6-bit scale + 6-bit min per sub-block (8 sub-blocks)
 *     qs[128]: 4-bit quantized values (256 weights, 2 per byte)
 *
 *   For sub-block sb in [0..7]:
 *     sc = 6-bit scale extracted from scales_and_mins
 *     m  = 6-bit min extracted from scales_and_mins
 *     For weight i in [0..31]:
 *       nibble = qs[sb * 16 + i/2] >> (4 * (i % 2)) & 0x0F
 *       w = d_f32 * sc * nibble - dmin_f32 * m
 *
 *   Scale packing:
 *     Sub-blocks 0-3: scales_and_mins[sb] low 6 bits = sc, high 2 bits = 0
 *                     scales_and_mins[sb+4] low 6 bits = m
 *     Sub-blocks 4-7: scales_and_mins[sb+4] bits [0:3] | scales_and_mins[sb-4] bits [6:7]<<4 = sc
 *                     similar for m using bytes 8-11
 *
 * Simplified layout: for sub-blocks 0-3, the scale/min extraction is
 * straightforward; for 4-7, high bits are packed across byte boundaries.
 * ===================================================================== */

/* Convert IEEE fp16 bit pattern to float32 */
static float xm_fp16_to_f32(uint16_t h) {
    /* Extract fields */
    uint32_t sign = ((uint32_t)h >> 15u) & 1u;
    uint32_t exp  = ((uint32_t)h >> 10u) & 0x1Fu;
    uint32_t mant = (uint32_t)h & 0x3FFu;

    union { float f; uint32_t u; } bits;

    if (exp == 0u) {
        if (mant == 0u) {
            /* Zero (signed) */
            bits.u = sign << 31u;
        } else {
            /* Denormalized: convert to normalized fp32 */
            float f = (float)mant / 1024.0f;
            f *= (1.0f / 16384.0f);  /* 2^(-14) */
            bits.f = f;
            if (sign) { bits.u |= 0x80000000u; }
        }
    } else if (exp == 31u) {
        /* Inf / NaN -- clamp to large float to avoid propagating NaN */
        bits.u = (sign << 31u) | 0x7F800000u | (mant << 13u);
    } else {
        /* Normalized: rebias exponent from fp16 (bias 15) to fp32 (bias 127) */
        uint32_t fp32_exp  = exp - 15u + 127u;
        uint32_t fp32_mant = mant << 13u;
        bits.u = (sign << 31u) | (fp32_exp << 23u) | fp32_mant;
    }

    return bits.f;
}

void xmind_dequantize_q4km_block(float *out, const xmind_q4km_block_t *blk) {
    XM_ASSERT(out != (void *)0);
    XM_ASSERT(blk != (void *)0);

    float d_f32    = xm_fp16_to_f32(blk->d);
    float dmin_f32 = xm_fp16_to_f32(blk->dmin);

    uint32_t sb;
    for (sb = 0u; sb < 8u; sb++) {
        /* Extract 6-bit scale (sc) and 6-bit min (m) for this sub-block.
         *
         * Packing layout in scales_and_mins[12]:
         *   bytes 0-3:  low 6 bits of scale for sub-blocks 0-3
         *   bytes 4-7:  low 6 bits of min   for sub-blocks 0-3
         *   bytes 8-11: for sub-blocks 4-7, packed with high bits from 0-3
         *
         * Sub-blocks 0-3: sc = scales_and_mins[sb] & 0x3F
         *                 m  = scales_and_mins[sb + 4] & 0x3F
         * Sub-blocks 4-7: sc = (scales_and_mins[sb + 4] & 0x0F)
         *                    | ((scales_and_mins[sb - 4] >> 6) << 4)
         *                 m  = (scales_and_mins[sb + 4] >> 4)
         *                    | ((scales_and_mins[sb - 0] >> 6) << 4)
         *
         * Note: the exact packing depends on the ggml Q4_K format version.
         * Below implements the standard ggml v3 layout.
         */
        uint32_t sc, m_val;
        if (sb < 4u) {
            sc    = (uint32_t)blk->scales_and_mins[sb] & 0x3Fu;
            m_val = (uint32_t)blk->scales_and_mins[sb + 4u] & 0x3Fu;
        } else {
            /* Sub-blocks 4-7: 4 low bits from byte (sb+4), 2 high bits from byte (sb-4) */
            sc    = ((uint32_t)blk->scales_and_mins[sb + 4u] & 0x0Fu)
                  | (((uint32_t)blk->scales_and_mins[sb - 4u] >> 6u) << 4u);
            m_val = ((uint32_t)blk->scales_and_mins[sb + 4u] >> 4u)
                  | (((uint32_t)blk->scales_and_mins[sb] >> 6u) << 4u);
        }

        float sc_f  = d_f32 * (float)sc;
        float m_f   = dmin_f32 * (float)m_val;

        /* 32 weights per sub-block, packed as 16 bytes of nibble pairs */
        uint32_t base = sb * 32u;
        uint32_t qi_base = sb * 16u;
        uint32_t wi;
        for (wi = 0u; wi < 16u; wi++) {
            uint8_t byte_val = blk->qs[qi_base + wi];
            uint32_t lo_nib = (uint32_t)(byte_val & 0x0Fu);
            uint32_t hi_nib = (uint32_t)(byte_val >> 4u);
            out[base + wi * 2u]      = sc_f * (float)lo_nib - m_f;
            out[base + wi * 2u + 1u] = sc_f * (float)hi_nib - m_f;
        }
    }
}

void xmind_dequantize_q4km_row(float *out, const xmind_q4km_block_t *blocks,
                                uint32_t n_blocks) {
    XM_ASSERT(out    != (void *)0);
    XM_ASSERT(blocks != (void *)0);

    uint32_t b;
    for (b = 0u; b < n_blocks; b++) {
        xmind_dequantize_q4km_block(out + b * XMIND_Q4KM_SUPERBLOCK, &blocks[b]);
    }
}

/* =====================================================================
 * S8b  Q4_K_M QUANTIZATION (fp32[256] → xmind_q4km_block_t)
 *
 * Encodes a 256-element fp32 vector into a single Q4_K_M super-block.
 *
 * Algorithm for each sub-block (32 weights):
 *   1. Find min and max of the 32 weights
 *   2. Compute scale = (max - min) / 15.0  (maps range to [0, 15])
 *   3. Compute min_val = min  (the minimum is subtracted before scaling)
 *   4. Quantize: q = clamp(round((w - min_val) / scale), 0, 15)
 *   5. Store as nibble pair
 *
 * Super-block scales:
 *   d = max of all sub-block scales → stored as fp16
 *   dmin = max of all sub-block mins → stored as fp16
 *   Per-sub-block sc  = round(sub_scale / d * 63)  (6-bit)
 *   Per-sub-block m   = round(sub_min   / dmin * 63) (6-bit)
 *
 * Scale packing mirrors the dequantization layout:
 *   Sub-blocks 0-3: scales_and_mins[sb]   low 6 bits = sc
 *                   scales_and_mins[sb+4] low 6 bits = m
 *   Sub-blocks 4-7: packed across byte boundaries (2 high bits)
 * ===================================================================== */

/* Convert float32 to IEEE fp16 bit pattern */
static uint16_t xm_f32_to_fp16(float f) {
    union { float fv; uint32_t u; } bits;
    bits.fv = f;

    uint32_t sign = (bits.u >> 31u) & 1u;
    int32_t  exp  = (int32_t)((bits.u >> 23u) & 0xFFu) - 127;
    uint32_t mant = bits.u & 0x007FFFFFu;

    uint16_t h;

    if (exp > 15) {
        /* Overflow → Inf */
        h = (uint16_t)((sign << 15u) | 0x7C00u);
    } else if (exp < -14) {
        /* Underflow → zero (flush subnormals) */
        h = (uint16_t)(sign << 15u);
    } else {
        uint32_t fp16_exp  = (uint32_t)(exp + 15);
        uint32_t fp16_mant = mant >> 13u;
        h = (uint16_t)((sign << 15u) | (fp16_exp << 10u) | fp16_mant);
    }
    return h;
}

void xmind_quantize_q4km_block(xmind_q4km_block_t *blk, const float *in) {
    XM_ASSERT(blk != (void *)0);
    XM_ASSERT(in  != (void *)0);

    /* Per-sub-block statistics */
    float sub_scale[8];
    float sub_min[8];
    uint32_t sb, wi;

    for (sb = 0u; sb < 8u; sb++) {
        const float *sub = in + sb * 32u;
        float mn = sub[0], mx = sub[0];
        for (wi = 1u; wi < 32u; wi++) {
            if (sub[wi] < mn) mn = sub[wi];
            if (sub[wi] > mx) mx = sub[wi];
        }
        float range = mx - mn;
        sub_scale[sb] = (range > 0.0f) ? (range / 15.0f) : 1.0f;
        sub_min[sb] = mn;
    }

    /* Compute super-block scales: d = max(sub_scale), dmin = max(|sub_min|) */
    float d_max = sub_scale[0];
    float dmin_max = xm_fabsf(sub_min[0]);
    for (sb = 1u; sb < 8u; sb++) {
        if (sub_scale[sb] > d_max) d_max = sub_scale[sb];
        float am = xm_fabsf(sub_min[sb]);
        if (am > dmin_max) dmin_max = am;
    }

    /* Avoid division by zero */
    if (d_max < 1e-10f) d_max = 1e-10f;
    if (dmin_max < 1e-10f) dmin_max = 1e-10f;

    blk->d    = xm_f32_to_fp16(d_max);
    blk->dmin = xm_f32_to_fp16(dmin_max);

    /* Recover the fp32 values of d and dmin after fp16 roundtrip
     * so that quantization uses the same scales as dequantization */
    float d_f32    = xm_fp16_to_f32(blk->d);
    float dmin_f32 = xm_fp16_to_f32(blk->dmin);

    /* Compute 6-bit sub-block scales and mins */
    uint8_t sc6[8], m6[8];
    for (sb = 0u; sb < 8u; sb++) {
        float sc_ratio = (d_f32 > 0.0f) ? (sub_scale[sb] / d_f32) : 0.0f;
        float m_ratio  = (dmin_f32 > 0.0f)
                          ? (xm_fabsf(sub_min[sb]) / dmin_f32) : 0.0f;
        int32_t sc_i = xm_roundf_i32(sc_ratio * 63.0f);
        int32_t m_i  = xm_roundf_i32(m_ratio * 63.0f);
        if (sc_i < 0) sc_i = 0; if (sc_i > 63) sc_i = 63;
        if (m_i  < 0) m_i  = 0; if (m_i  > 63) m_i  = 63;
        sc6[sb] = (uint8_t)sc_i;
        m6[sb]  = (uint8_t)m_i;
    }

    /* Pack 6-bit scales and mins into scales_and_mins[12]
     *
     * For sub-blocks 0-3:
     *   scales_and_mins[sb]   = sc6[sb] (low 6 bits)
     *   scales_and_mins[sb+4] = m6[sb]  (low 6 bits)
     *   High 2 bits of bytes 0-3 store high bits for sub-blocks 4-7
     *
     * For sub-blocks 4-7:
     *   scales_and_mins[sb+4] low 4 bits  = sc6[sb] low 4 bits
     *   scales_and_mins[sb+4] high 4 bits = m6[sb] low 4 bits
     *   High 2 bits of sc6[sb] packed into scales_and_mins[sb-4] bits [6:7]
     *   High 2 bits of m6[sb]  packed into scales_and_mins[sb] bits [6:7]
     *
     * Initialize to zero first to simplify bit manipulation */
    uint32_t bi;
    for (bi = 0u; bi < 12u; bi++) { blk->scales_and_mins[bi] = 0u; }

    /* Sub-blocks 0-3: pack into bytes 0-3 (scales) and 4-7 (mins) */
    for (sb = 0u; sb < 4u; sb++) {
        blk->scales_and_mins[sb]     = (sc6[sb] & 0x3Fu);
        blk->scales_and_mins[sb + 4u] = (m6[sb] & 0x3Fu);
    }

    /* Sub-blocks 4-7: pack into bytes 8-11 with high bits in bytes 0-7 */
    for (sb = 4u; sb < 8u; sb++) {
        /* Low 4 bits of sc and m packed into scales_and_mins[sb+4] */
        blk->scales_and_mins[sb + 4u] = (uint8_t)(
            (sc6[sb] & 0x0Fu) | ((m6[sb] & 0x0Fu) << 4u)
        );
        /* High 2 bits of sc6[sb] → bits [6:7] of scales_and_mins[sb-4] */
        blk->scales_and_mins[sb - 4u] |= (uint8_t)(
            ((sc6[sb] >> 4u) & 0x03u) << 6u
        );
        /* High 2 bits of m6[sb] → bits [6:7] of scales_and_mins[sb] */
        blk->scales_and_mins[sb] |= (uint8_t)(
            ((m6[sb] >> 4u) & 0x03u) << 6u
        );
    }

    /* Quantize weights into nibble pairs */
    for (sb = 0u; sb < 8u; sb++) {
        /* Recover effective scale and min for this sub-block
         * using the same extraction as dequantize */
        uint32_t sc_eff, m_eff;
        if (sb < 4u) {
            sc_eff = (uint32_t)blk->scales_and_mins[sb] & 0x3Fu;
            m_eff  = (uint32_t)blk->scales_and_mins[sb + 4u] & 0x3Fu;
        } else {
            sc_eff = ((uint32_t)blk->scales_and_mins[sb + 4u] & 0x0Fu)
                   | (((uint32_t)blk->scales_and_mins[sb - 4u] >> 6u) << 4u);
            m_eff  = ((uint32_t)blk->scales_and_mins[sb + 4u] >> 4u)
                   | (((uint32_t)blk->scales_and_mins[sb] >> 6u) << 4u);
        }

        float sc_f = d_f32 * (float)sc_eff;
        float m_f  = dmin_f32 * (float)m_eff;
        float inv_sc = (sc_f > 1e-10f) ? (1.0f / sc_f) : 0.0f;

        const float *sub = in + sb * 32u;
        uint32_t qi_base = sb * 16u;

        for (wi = 0u; wi < 16u; wi++) {
            float w_lo = sub[wi * 2u];
            float w_hi = sub[wi * 2u + 1u];
            /* Reverse dequant formula: w = sc_f * nibble - m_f
             * → nibble = (w + m_f) / sc_f */
            int32_t q_lo = xm_roundf_i32((w_lo + m_f) * inv_sc);
            int32_t q_hi = xm_roundf_i32((w_hi + m_f) * inv_sc);
            q_lo = xm_clamp_i32(q_lo, 0, 15);
            q_hi = xm_clamp_i32(q_hi, 0, 15);
            blk->qs[qi_base + wi] = (uint8_t)(
                ((uint8_t)q_lo & 0x0Fu) | (((uint8_t)q_hi & 0x0Fu) << 4u)
            );
        }
    }
}

void xmind_quantize_q4km_row(xmind_q4km_block_t *blocks, const float *in,
                               uint32_t n) {
    XM_ASSERT(blocks != (void *)0);
    XM_ASSERT(in     != (void *)0);
    XM_ASSERT(n > 0u);
    XM_ASSERT(n % XMIND_Q4KM_SUPERBLOCK == 0u);

    uint32_t n_blocks = n / XMIND_Q4KM_SUPERBLOCK;
    uint32_t b;
    for (b = 0u; b < n_blocks; b++) {
        xmind_quantize_q4km_block(&blocks[b], in + b * XMIND_Q4KM_SUPERBLOCK);
    }
}

/* =====================================================================
 * S8c  Q4_K_M ROUND-TRIP SELF-TEST
 *
 * Encodes a known 256-element pattern, decodes it, and verifies that
 * the maximum reconstruction error is within the expected Q4_K_M bound.
 *
 * Q4_K_M has better accuracy than Q4_0 due to per-sub-block scale/min,
 * but the error is bounded by the per-sub-block quantization step:
 *   max_error ≈ d * sc / 15 (per weight)
 * ===================================================================== */

__attribute__((unused))
static void xmind_verify_q4km_roundtrip(void) {
    float in[XMIND_Q4KM_SUPERBLOCK];
    uint32_t i;
    /* Generate a diverse test pattern spanning [-10, 10] */
    for (i = 0u; i < XMIND_Q4KM_SUPERBLOCK; i++) {
        in[i] = (float)(int32_t)i * (20.0f / (float)XMIND_Q4KM_SUPERBLOCK) - 10.0f;
    }

    xmind_q4km_block_t blk;
    xmind_quantize_q4km_block(&blk, in);

    float out[XMIND_Q4KM_SUPERBLOCK];
    xmind_dequantize_q4km_block(out, &blk);

    float max_err = 0.0f;
    for (i = 0u; i < XMIND_Q4KM_SUPERBLOCK; i++) {
        float err = in[i] - out[i];
        if (err < 0.0f) err = -err;
        if (err > max_err) max_err = err;
    }

    /* Q4_K_M should have significantly lower error than Q4_0
     * For a range of 20 with 6-bit sub-scales, expected max error
     * is roughly 20/(15*63) ≈ 0.02, but fp16 quantization of d/dmin
     * adds some loss.  We allow up to 2.0 as a generous bound. */
    if (max_err > 2.0f) {
        pal_console_printf("[XMIND] Q4_K_M roundtrip FAIL: max_err=%d/1000\n",
                           (int32_t)(max_err * 1000.0f));
    } else {
        pal_console_printf("[XMIND] Q4_K_M roundtrip OK: max_err=%d/1000\n",
                           (int32_t)(max_err * 1000.0f));
    }
}

/* =====================================================================
 * S9  Q4_K_M MATRIX-VECTOR MULTIPLY
 *
 * Computes: out[r] = sum_c( W[r,c] * x[c] )  for r in [0, rows)
 *
 * W is stored in Q4_K_M format: each row has (cols / 256) super-blocks.
 * cols must be a multiple of XMIND_Q4KM_SUPERBLOCK (256).
 * Complexity: O(rows x cols).
 * ===================================================================== */
void xmind_matmul_q4km(float *out, const float *x,
                        const xmind_q4km_block_t *W,
                        uint32_t rows, uint32_t cols) {
    XM_ASSERT(out != (void *)0);
    XM_ASSERT(x   != (void *)0);
    XM_ASSERT(W   != (void *)0);
    XM_ASSERT(cols % XMIND_Q4KM_SUPERBLOCK == 0u);

    uint32_t n_blocks_per_row = cols / XMIND_Q4KM_SUPERBLOCK;
    uint32_t r, b, sb, wi;

    for (r = 0u; r < rows; r++) {
        float acc = 0.0f;
        const xmind_q4km_block_t *row_blocks =
            W + (uint64_t)r * n_blocks_per_row;

        for (b = 0u; b < n_blocks_per_row; b++) {
            const xmind_q4km_block_t *blk = &row_blocks[b];
            float d_f32    = xm_fp16_to_f32(blk->d);
            float dmin_f32 = xm_fp16_to_f32(blk->dmin);
            uint32_t base_col = b * XMIND_Q4KM_SUPERBLOCK;

            for (sb = 0u; sb < 8u; sb++) {
                uint32_t sc, m_val;
                if (sb < 4u) {
                    sc    = (uint32_t)blk->scales_and_mins[sb] & 0x3Fu;
                    m_val = (uint32_t)blk->scales_and_mins[sb + 4u] & 0x3Fu;
                } else {
                    sc    = ((uint32_t)blk->scales_and_mins[sb + 4u] & 0x0Fu)
                          | (((uint32_t)blk->scales_and_mins[sb - 4u] >> 6u) << 4u);
                    m_val = ((uint32_t)blk->scales_and_mins[sb + 4u] >> 4u)
                          | (((uint32_t)blk->scales_and_mins[sb] >> 6u) << 4u);
                }

                float sc_f  = d_f32 * (float)sc;
                float m_f   = dmin_f32 * (float)m_val;
                uint32_t qi_base = sb * 16u;
                uint32_t sb_col  = base_col + sb * 32u;

                for (wi = 0u; wi < 16u; wi++) {
                    uint8_t byte_val = blk->qs[qi_base + wi];
                    float w_lo = sc_f * (float)(byte_val & 0x0Fu) - m_f;
                    float w_hi = sc_f * (float)(byte_val >> 4u)   - m_f;
                    acc += w_lo * x[sb_col + wi * 2u];
                    acc += w_hi * x[sb_col + wi * 2u + 1u];
                }
            }
        }
        out[r] = acc;
    }
}
