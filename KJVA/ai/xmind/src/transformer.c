/*
 * transformer.c -- XMIND Transformer Forward Pass (AVX2 optimized)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Sprint 41: AVX2 SIMD acceleration wired into attention dot products
 * and the logit projection.  The matmul_q4 calls (Q/K/V/O projections
 * and FFN w1/w2/w3) are accelerated via tensor.c's SIMD-dispatched
 * xmind_matmul_q4().  The attention score computation and logit
 * projection use xmind_dot() which routes to AVX2 when available.
 *
 * Functions (each <= 120 lines):
 *   xm_kv_store       -- write K,V into cache at position pos
 *   xm_attention_head -- compute attention for one head (AVX2 dot)
 *   xm_attention      -- full multi-head attention for one layer
 *   xm_ffn            -- SwiGLU FFN for one layer
 *   xmind_forward     -- complete forward pass (AVX2 logit projection)
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"

/* ====================================================================
 * S1  SCRATCH BUFFER SIZES
 *
 * Stack-allocated scratch used within attention / FFN helpers.
 * Sized for worst-case (XMIND_MAX_HEADS x head_dim and ctx_len).
 *
 * We avoid VLAs (not allowed in strict C11 freestanding) by using
 * a single flat float[XMIND_MAX_SEQ] scratch on the stack for attn
 * scores (one head at a time).
 * ==================================================================== */

/* Maximum head_dim we plan to support (512 bits = head_dim 64 typical) */
#define XM_MAX_HEAD_DIM  256u
/* Max attn buffer per head */
#define XM_ATTN_SCRATCH  XMIND_MAX_SEQ

/* ====================================================================
 * S2  INTERNAL HELPER -- store K, V at position pos in KV cache
 *
 * KV cache layout per layer:
 *   k[layer][pos * n_kv_heads * head_dim + h * head_dim + d]
 *
 * We copy the freshly computed K/V from m->state.k / m->state.v
 * into the persistent cache.
 * ==================================================================== */
static void xm_kv_store(xmind_model_t *m, uint32_t layer, uint32_t pos) {
    uint32_t head_dim   = m->cfg.head_dim;
    uint32_t n_kv_heads = m->cfg.n_kv_heads;
    uint32_t kv_stride  = n_kv_heads * head_dim; /* floats per token position */

    float *k_dst = m->kv.k[layer] + (uint64_t)pos * kv_stride;
    float *v_dst = m->kv.v[layer] + (uint64_t)pos * kv_stride;
    const float *k_src = m->state.k;
    const float *v_src = m->state.v;

    uint32_t i;
    for (i = 0u; i < kv_stride; i++) {
        k_dst[i] = k_src[i];
        v_dst[i] = v_src[i];
    }
}

/* ====================================================================
 * S3  INTERNAL HELPER -- attention for one query head (AVX2 dot)
 *
 * @param m         model
 * @param layer     current layer index
 * @param pos       current position (0-based)
 * @param h         query head index
 * @param attn_out  output buffer: head_dim floats (the weighted V sum)
 *
 * Steps:
 *   1. score[t] = dot(q_head, k_cache[t][kv_head]) / sqrt(head_dim)
 *   2. softmax(score[0..pos])
 *   3. attn_out = sum_t( score[t] * v_cache[t][kv_head] )
 *
 * GQA: kv_head = h * n_kv_heads / n_heads  (integer division)
 *
 * The dot product in step 1 now uses xmind_dot() which dispatches
 * to AVX2+FMA3 when available (8-wide VFMADD231PS), giving ~8x
 * throughput over scalar on the i5-8250U's 256-bit execution units.
 * ==================================================================== */
static void xm_attention_head(xmind_model_t *m, uint32_t layer,
                               uint32_t pos, uint32_t h,
                               float *attn_out) {
    uint32_t head_dim   = m->cfg.head_dim;
    uint32_t n_heads    = m->cfg.n_heads;
    uint32_t n_kv_heads = m->cfg.n_kv_heads;
    uint32_t kv_stride  = n_kv_heads * head_dim;

    /* GQA: map query head h -> key-value head */
    uint32_t kv_head = h * n_kv_heads / n_heads;

    const float *q_head = m->state.q + h * head_dim;

    /* Scale factor 1/sqrt(head_dim) -- precompute reciprocal */
    float scale = 1.0f;
    {
        /* Simple integer sqrt via float reciprocal; head_dim is small. */
        float hd_f = (float)head_dim;
        /* Newton-Raphson single step for 1/sqrt -- sufficient for small ints */
        union { float f; uint32_t u; } est;
        est.f = hd_f;
        est.u = 0x5F3759DFu - (est.u >> 1u);
        est.f *= 1.5f - (hd_f * 0.5f * est.f * est.f);
        scale = est.f;
    }

    /* Compute attention scores score[t] for t in [0, pos]
     * Using xmind_dot() which dispatches to AVX2 when available. */
    float scores[XM_ATTN_SCRATCH];
    uint32_t t;
    for (t = 0u; t <= pos; t++) {
        const float *k_t = m->kv.k[layer]
                         + (uint64_t)t * kv_stride
                         + kv_head * head_dim;
        scores[t] = xmind_dot(q_head, k_t, head_dim) * scale;
    }

    /* Softmax over [0, pos] */
    float mx = scores[0];
    for (t = 1u; t <= pos; t++) {
        if (scores[t] > mx) { mx = scores[t]; }
    }
    float sum = 0.0f;
    for (t = 0u; t <= pos; t++) {
        /* Inline xm_expf -- avoid function call overhead in inner loop */
        float x  = scores[t] - mx;
        if (x < -87.0f) { x = -87.0f; }
        float y  = x * 1.4426950408889634f;
        int32_t n = (int32_t)y;
        if ((float)n > y) { n -= 1; }
        float f  = y - (float)n;
        float p  = 1.0f + f * (0.6931471806f
                       + f * (0.2402265069f
                       + f * (0.0555041086f
                       + f * (0.0096181292f
                       + f *  0.0013333558f))));
        union { float fv; uint32_t uv; } bits;
        bits.uv = (uint32_t)((n + 127) << 23);
        scores[t] = p * bits.fv;
        sum += scores[t];
    }
    float inv_sum = 1.0f / sum;
    for (t = 0u; t <= pos; t++) {
        scores[t] *= inv_sum;
    }

    /* Weighted sum of value vectors */
    uint32_t d;
    for (d = 0u; d < head_dim; d++) {
        attn_out[d] = 0.0f;
    }
    for (t = 0u; t <= pos; t++) {
        const float *v_t = m->kv.v[layer]
                         + (uint64_t)t * kv_stride
                         + kv_head * head_dim;
        float w = scores[t];
        for (d = 0u; d < head_dim; d++) {
            attn_out[d] += w * v_t[d];
        }
    }
}

/* ====================================================================
 * S4  MULTI-HEAD ATTENTION  (one transformer layer)
 *
 * Input:  m->state.xb  (RMSNorm output for this layer, hidden_dim floats)
 * Output: m->state.xb  (overwritten with attention output projection)
 *
 * Steps:
 *   1. Q = wq[layer] x xb  (Q4 matmul -- AVX2 accelerated)
 *   2. K = wk[layer] x xb
 *   3. V = wv[layer] x xb
 *   4. RoPE applied to Q and K
 *   5. KV stored in cache at position pos
 *   6. Per-head attention -> assembles full attn vector in state.attn
 *   7. xb = wo[layer] x attn  (Q4 matmul)
 * ==================================================================== */
static void xm_attention(xmind_model_t *m, uint32_t layer, uint32_t pos) {
    uint32_t head_dim   = m->cfg.head_dim;
    uint32_t n_heads    = m->cfg.n_heads;
    uint32_t n_kv_heads = m->cfg.n_kv_heads;
    uint32_t hidden_dim = m->cfg.hidden_dim;

    /* Project Q, K, V (AVX2-accelerated Q4_0 matmul via tensor.c) */
    xmind_matmul_q4(m->state.q, m->state.xb, m->wq[layer],
                    n_heads * head_dim, hidden_dim);
    xmind_matmul_q4(m->state.k, m->state.xb, m->wk[layer],
                    n_kv_heads * head_dim, hidden_dim);
    xmind_matmul_q4(m->state.v, m->state.xb, m->wv[layer],
                    n_kv_heads * head_dim, hidden_dim);

    /* Apply RoPE */
    xmind_rope(m->state.q, m->state.k,
               m->rope_cos, m->rope_sin,
               pos, head_dim, n_heads, n_kv_heads);

    /* Store K, V into cache */
    xm_kv_store(m, layer, pos);
    m->kv.n_cached = pos + 1u;

    /* Per-head attention; assemble output into state.attn */
    float head_out[XM_MAX_HEAD_DIM];
    uint32_t h;
    for (h = 0u; h < n_heads; h++) {
        xm_attention_head(m, layer, pos, h, head_out);
        /* Copy head output into state.attn at head offset */
        uint32_t d;
        for (d = 0u; d < head_dim; d++) {
            m->state.attn[h * head_dim + d] = head_out[d];
        }
    }

    /* Output projection: xb = wo[layer] x attn */
    xmind_matmul_q4(m->state.xb, m->state.attn, m->wo[layer],
                    hidden_dim, n_heads * head_dim);
}

/* ====================================================================
 * S5  SwiGLU FEED-FORWARD NETWORK  (one transformer layer)
 *
 * Input:  m->state.xb  (RMSNorm output for FFN, hidden_dim floats)
 * Output: m->state.xb  (overwritten with FFN output)
 *
 * SwiGLU:
 *   gate   = w1[layer] x xb       (ffn_dim floats)
 *   up     = w3[layer] x xb       (ffn_dim floats)
 *   hidden = SiLU(gate) * up      (element-wise SwiGLU)
 *   xb     = w2[layer] x hidden   (hidden_dim floats)
 *
 * Stack overflow fix (P0): XM_FFN_SCRATCH = 8192 floats = 32KB per
 * buffer.  Two stack-local arrays (gate + up) totalled 64KB -- an
 * immediate silent kernel stack overflow on the first inference call.
 * Both are promoted to module-level static storage.  This is safe
 * because XMIND runs single-threaded at boot; xm_ffn() is not
 * re-entered.
 * ==================================================================== */
#define XM_FFN_SCRATCH (XMIND_MAX_HEADS * XM_MAX_HEAD_DIM)

/* Static FFN scratch buffers -- safe because XMIND runs single-threaded at boot.
 * Converting from stack allocation prevents 64KB kernel stack overflow (P0). */
static float s_xm_ffn_gate[XM_FFN_SCRATCH];
static float s_xm_ffn_up[XM_FFN_SCRATCH];

static void xm_ffn(xmind_model_t *m, uint32_t layer) {
    uint32_t hidden_dim = m->cfg.hidden_dim;
    uint32_t ffn_dim    = m->cfg.ffn_dim;

    XM_ASSERT(ffn_dim <= XM_FFN_SCRATCH);

    /* Gate and up projections (AVX2-accelerated) */
    xmind_matmul_q4(s_xm_ffn_gate, m->state.xb, m->w1[layer], ffn_dim, hidden_dim);
    xmind_matmul_q4(s_xm_ffn_up,   m->state.xb, m->w3[layer], ffn_dim, hidden_dim);

    /* SiLU activation fused with element-wise multiply */
    xmind_silu(s_xm_ffn_gate, s_xm_ffn_gate, s_xm_ffn_up, ffn_dim);

    /* Down projection back to hidden_dim */
    xmind_matmul_q4(m->state.xb, s_xm_ffn_gate, m->w2[layer], hidden_dim, ffn_dim);
}

/* ====================================================================
 * S6  FULL FORWARD PASS (AVX2 logit projection)
 *
 * Executes the complete transformer for one token at one position.
 * After return, m->state.logits contains unnormalized log-probs
 * over the vocabulary.
 *
 * Pass structure (LLaMA 2 / 3 style):
 *   x = token_emb[token * hidden_dim]
 *   for each layer l:
 *     xb = RMSNorm(x, rms_att[l])
 *     xb = attention(xb)            -- writes result back into xb
 *     x  = x + xb                   -- residual
 *     xb = RMSNorm(x, rms_ffn[l])
 *     xb = ffn(xb)
 *     x  = x + xb                   -- residual
 *   x = RMSNorm(x, rms_final)
 *   logits = token_emb^T x x        -- weight tying (AVX2 dot)
 *
 * The logit projection step uses xmind_dot() which dispatches to
 * AVX2+FMA3 when available.  For Llama 3B (32000 x 3072 = 98M MADs),
 * this step drops from ~34ms (scalar) to ~4ms (AVX2) on i5-8250U.
 * ==================================================================== */
void xmind_forward(xmind_model_t *m, uint32_t token, uint32_t pos) {
    XM_ASSERT(m != (void *)0);
    XM_ASSERT(m->initialized != 0u);
    XM_ASSERT(token < m->cfg.vocab_size);
    XM_ASSERT(pos   < m->cfg.ctx_len);

    uint32_t hidden_dim = m->cfg.hidden_dim;
    uint32_t n_layers   = m->cfg.n_layers;
    uint32_t vocab_size = m->cfg.vocab_size;

    /* Load token embedding: x = token_emb[token * hidden_dim] */
    const float *emb = m->token_emb + (uint64_t)token * hidden_dim;
    float *x  = m->state.x;
    float *xb = m->state.xb;
    uint32_t i;
    for (i = 0u; i < hidden_dim; i++) {
        x[i] = emb[i];
    }

    /* Update current position in state */
    m->state.pos = pos;

    /* Transformer layers */
    uint32_t l;
    for (l = 0u; l < n_layers; l++) {
        /* --- Attention sub-layer --- */
        xmind_rmsnorm(xb, x, m->rms_att[l], hidden_dim);
        xm_attention(m, l, pos);
        /* Residual: x += xb */
        for (i = 0u; i < hidden_dim; i++) {
            x[i] += xb[i];
        }

        /* --- FFN sub-layer --- */
        xmind_rmsnorm(xb, x, m->rms_ffn[l], hidden_dim);
        xm_ffn(m, l);
        /* Residual: x += xb */
        for (i = 0u; i < hidden_dim; i++) {
            x[i] += xb[i];
        }
    }

    /* Final RMSNorm (in-place: out == x) */
    xmind_rmsnorm(x, x, m->rms_final, hidden_dim);

    /*
     * Logit computation via weight tying (AVX2 accelerated):
     * logits = token_emb^T x x
     * token_emb is (vocab_size x hidden_dim), so:
     *   logits[v] = dot(token_emb[v * hidden_dim .. (v+1)*hidden_dim - 1], x)
     *
     * Complexity: O(vocab_size x hidden_dim) -- the bottleneck step.
     * For Llama 3B: 32000 x 3072 = 98M multiply-adds.
     *
     * xmind_dot() dispatches to xjit_dot_f32_avx2 when available,
     * processing 8 floats per VFMADD231PS cycle.
     */
    float *logits = m->state.logits;
    uint32_t v;
    for (v = 0u; v < vocab_size; v++) {
        const float *row = m->token_emb + (uint64_t)v * hidden_dim;
        logits[v] = xmind_dot(row, x, hidden_dim);
    }
}
