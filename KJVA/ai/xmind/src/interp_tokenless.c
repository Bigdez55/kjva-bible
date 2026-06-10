/*
 * interp_tokenless.c — Tokenless LM Family Artifact Interpreter
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Implements the artifact interpreter for the Tokenless LM family
 *   (UTF-8 byte-level language models produced by ml-training/scripts/
 *   train_byte.py + convert_to_gguf.py).  Per UNIFIED_MASTER_TECH_PACK.md
 *   Part II §25.2, this is registry slot 1 (slot 0 is interp_llama).
 *
 *   detect():       arch == "tokenless_lm"                (conf 100)
 *                   "tokenless_lm.block_count" key present  (conf 80)
 *   build_config(): reads tokenless_lm.* metadata
 *   map_tensor():   maps token_emb / output_norm / blk.N.* tensors
 *                   (tied embeddings — no output.weight)
 *   validate():     verifies token_emb + output_norm + per-layer roles
 *   tokenizer:      UTF-8 byte-level, token = byte + 3, vocab = 259
 *                   (PAD=0, BOS=1, EOS=2, then 256 raw bytes at +3 offset)
 *
 * Master spec evidence (UNIFIED_MASTER_TECH_PACK.md Part II §25.2/§25.6):
 *   - 18M-param KJVA base substrate (val_ppl=3.21)
 *   - layers=8, heads=6, kv=6, hidden=384, ffn=1536, vocab=259, ctx=1024
 *   - rope_base=10000.0, rms_eps=1e-5, tie_embeddings=true
 *   - SwiGLU 3-matrix FFN (matches interp_llama vtable contract)
 *
 * No libc.  Freestanding C11.  PAL types only.
 *
 * S1  String helpers
 * S2  Tokenless GGUF metadata key constants
 * S3  detect() — family detection
 * S4  build_config() — config extraction from metadata
 * S5  map_tensor() — tensor name to role mapping
 * S6  validate() — completeness check (no output.weight; tied embeddings)
 * S7  Vtable definition
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"
#include "../include/xmind_artifact_interp.h"

/* ===================================================================
 * S1  STRING HELPERS
 * =================================================================== */

static uint32_t it_strlen(const char *s) {
    uint32_t n = 0u;
    while (s[n]) { n++; }
    return n;
}

static int32_t it_strncmp(const char *a, const char *b, uint32_t n) {
    uint32_t i;
    for (i = 0u; i < n; i++) {
        if ((uint8_t)a[i] != (uint8_t)b[i]) {
            return (int32_t)(uint8_t)a[i] - (int32_t)(uint8_t)b[i];
        }
        if (!a[i]) { return 0; }
    }
    return 0;
}

/* Compare name (may not be null-terminated, given length nl) against
 * null-terminated literal s.  Returns 1 if equal, 0 otherwise. */
static int it_name_eq(const char *name, uint32_t nl, const char *s) {
    uint32_t i;
    for (i = 0u; i < nl; i++) {
        if (!s[i] || (uint8_t)s[i] != (uint8_t)name[i]) return 0;
    }
    return s[nl] == '\0';
}

/* ===================================================================
 * S2  TOKENLESS LM GGUF METADATA KEY CONSTANTS
 *
 * Match the keys actually written by training/scripts/convert_to_gguf.py
 * (lines 391-411) and safetensors_to_gguf.py.
 * =================================================================== */

#define TOKENLESS_KEY_BLOCK_COUNT     "tokenless_lm.block_count"
#define TOKENLESS_KEY_HEAD_COUNT      "tokenless_lm.attention.head_count"
#define TOKENLESS_KEY_HEAD_COUNT_KV   "tokenless_lm.attention.head_count_kv"
#define TOKENLESS_KEY_CTX_LEN         "tokenless_lm.context_length"
#define TOKENLESS_KEY_EMBEDDING_LEN   "tokenless_lm.embedding_length"
#define TOKENLESS_KEY_FFN_LEN         "tokenless_lm.feed_forward_length"
#define TOKENLESS_KEY_ROPE_FREQ_BASE  "tokenless_lm.rope.freq_base"
#define TOKENLESS_KEY_VOCAB_SIZE      "tokenless_lm.vocab_size"
#define TOKENLESS_KEY_RMS_EPS         "tokenless_lm.attention.layer_norm_rms_epsilon"
#define TOKENLESS_KEY_BOS_ID          "tokenizer.ggml.bos_token_id"
#define TOKENLESS_KEY_EOS_ID          "tokenizer.ggml.eos_token_id"

/* ===================================================================
 * S3  detect() — Tokenless LM family detection
 *
 * Returns 100 if catalog arch == "tokenless_lm".
 * Returns  80 if "tokenless_lm.block_count" is present in KV.
 * Returns   0 otherwise.
 * =================================================================== */

static uint32_t it_detect(const gguf_catalog_t *catalog) {
    if (!catalog) return 0u;

    /* Primary: check arch string ("tokenless_lm" is 12 chars) */
    if (catalog->arch_len == 12u &&
        it_strncmp(catalog->arch, "tokenless_lm", 12u) == 0) {
        return 100u;
    }

    /* Fallback: check for characteristic metadata key */
    const gguf_kv_t *kv = gguf_find_kv(catalog, TOKENLESS_KEY_BLOCK_COUNT);
    if (kv) return 80u;

    return 0u;
}

/* ===================================================================
 * S4  build_config() — Extract xmind_config_t from Tokenless metadata
 *
 * Defaults match the KJVA 18M-param byte substrate per
 * UNIFIED_MASTER_TECH_PACK.md Part II §25.6 and the kjva-bible
 * model_config.json ground truth.
 * =================================================================== */

/* KJVA 18M byte substrate preset defaults */
#define TOKENLESS_DEFAULT_LAYERS      8u
#define TOKENLESS_DEFAULT_HEADS       6u
#define TOKENLESS_DEFAULT_KV_HEADS    6u
#define TOKENLESS_DEFAULT_HIDDEN    384u
#define TOKENLESS_DEFAULT_FFN      1536u
#define TOKENLESS_DEFAULT_VOCAB     259u   /* 256 bytes + PAD/BOS/EOS */
#define TOKENLESS_DEFAULT_CTX      1024u
#define TOKENLESS_DEFAULT_ROPE   10000.0f
#define TOKENLESS_DEFAULT_BOS_ID      1u
#define TOKENLESS_DEFAULT_EOS_ID      2u

static int32_t it_build_config(const gguf_catalog_t *catalog,
                                 void *cfg_out) {
    if (!catalog || !cfg_out) return -1;
    xmind_config_t *cfg = (xmind_config_t *)cfg_out;

    /* Start from KJVA 18M defaults */
    cfg->n_layers   = TOKENLESS_DEFAULT_LAYERS;
    cfg->n_heads    = TOKENLESS_DEFAULT_HEADS;
    cfg->n_kv_heads = TOKENLESS_DEFAULT_KV_HEADS;
    cfg->hidden_dim = TOKENLESS_DEFAULT_HIDDEN;
    cfg->ffn_dim    = TOKENLESS_DEFAULT_FFN;
    cfg->vocab_size = TOKENLESS_DEFAULT_VOCAB;
    cfg->ctx_len    = TOKENLESS_DEFAULT_CTX;
    cfg->rope_base  = TOKENLESS_DEFAULT_ROPE;
    cfg->bos_id     = TOKENLESS_DEFAULT_BOS_ID;
    cfg->eos_id     = TOKENLESS_DEFAULT_EOS_ID;
    cfg->eog_ids[0] = TOKENLESS_DEFAULT_EOS_ID;
    cfg->eog_ids[1] = 0u;
    cfg->eog_ids[2] = 0u;
    cfg->eog_ids[3] = 0u;

    /* Override from actual metadata */
    const gguf_kv_t *kv;

    kv = gguf_find_kv(catalog, TOKENLESS_KEY_BLOCK_COUNT);
    if (kv && kv->val.u64 > 0u && kv->val.u64 <= XMIND_MAX_LAYERS) {
        cfg->n_layers = (uint32_t)kv->val.u64;
    }

    kv = gguf_find_kv(catalog, TOKENLESS_KEY_HEAD_COUNT);
    if (kv && kv->val.u64 > 0u && kv->val.u64 <= XMIND_MAX_HEADS) {
        cfg->n_heads = (uint32_t)kv->val.u64;
    }

    kv = gguf_find_kv(catalog, TOKENLESS_KEY_HEAD_COUNT_KV);
    if (kv && kv->val.u64 > 0u) {
        cfg->n_kv_heads = (uint32_t)kv->val.u64;
    }

    kv = gguf_find_kv(catalog, TOKENLESS_KEY_CTX_LEN);
    if (kv && kv->val.u64 > 0u && kv->val.u64 <= XMIND_MAX_SEQ) {
        cfg->ctx_len = (uint32_t)kv->val.u64;
    }

    kv = gguf_find_kv(catalog, TOKENLESS_KEY_EMBEDDING_LEN);
    if (kv && kv->val.u64 > 0u) {
        cfg->hidden_dim = (uint32_t)kv->val.u64;
    }

    kv = gguf_find_kv(catalog, TOKENLESS_KEY_FFN_LEN);
    if (kv && kv->val.u64 > 0u) {
        cfg->ffn_dim = (uint32_t)kv->val.u64;
    }

    kv = gguf_find_kv(catalog, TOKENLESS_KEY_ROPE_FREQ_BASE);
    if (kv) {
        cfg->rope_base = kv->val.f32;
    }

    /* Vocab size: direct uint metadata key (NOT tokenizer array count).
     * convert_to_gguf.py writes a uint32 at tokenless_lm.vocab_size. */
    kv = gguf_find_kv(catalog, TOKENLESS_KEY_VOCAB_SIZE);
    if (kv && kv->val.u64 > 0u) {
        cfg->vocab_size = (uint32_t)kv->val.u64;
    }

    /* Special token IDs (PAD=0 implicit; BOS=1, EOS=2 per master spec) */
    kv = gguf_find_kv(catalog, TOKENLESS_KEY_BOS_ID);
    if (kv) { cfg->bos_id = (uint32_t)kv->val.u64; }

    kv = gguf_find_kv(catalog, TOKENLESS_KEY_EOS_ID);
    if (kv) {
        cfg->eos_id     = (uint32_t)kv->val.u64;
        cfg->eog_ids[0] = (uint32_t)kv->val.u64;
    }

    /* Derive head_dim */
    if (cfg->n_heads > 0u) {
        cfg->head_dim = cfg->hidden_dim / cfg->n_heads;
    }

    /* FFN LAYOUT: SwiGLU 3-matrix (matches interp_llama):
     *   ffn_gate.weight  (w1) — gating projection (activated)
     *   ffn_up.weight    (w3) — up projection (gated)
     *   ffn_down.weight  (w2) — down projection (output)
     * TIED EMBEDDINGS: no output.weight; token_emb is reused for output
     * projection (handled by the inference path).
     */

    pal_console_printf("[INTERP-TOKENLESS] config: layers=%u heads=%u kv=%u "
                       "hidden=%u ffn=%u vocab=%u ctx=%u rope=%.0f "
                       "ffn_layout=XM_FFN_SWIGLU_3MAT tied_emb=1 "
                       "tokenizer=utf8_byte+3 (PAD=0 BOS=%u EOS=%u)\n",
                       cfg->n_layers, cfg->n_heads, cfg->n_kv_heads,
                       cfg->hidden_dim, cfg->ffn_dim, cfg->vocab_size,
                       cfg->ctx_len, (double)cfg->rope_base,
                       cfg->bos_id, cfg->eos_id);
    return 0;
}

/* ===================================================================
 * S5  map_tensor() — Map Tokenless tensor names to canonical roles
 *
 * Tokenless naming convention (identical to Llama for the shared roles;
 * convert_to_gguf.py writes these exact names):
 *   token_emb.weight       -> XMIND_ROLE_TOKEN_EMB     (global)
 *   output_norm.weight     -> XMIND_ROLE_NORM_FINAL    (global)
 *   blk.N.attn_q.weight    -> XMIND_ROLE_ATTN_Q        (layer N)
 *   blk.N.attn_k.weight    -> XMIND_ROLE_ATTN_K        (layer N)
 *   blk.N.attn_v.weight    -> XMIND_ROLE_ATTN_V        (layer N)
 *   blk.N.attn_output.weight -> XMIND_ROLE_ATTN_O      (layer N)
 *   blk.N.ffn_gate.weight  -> XMIND_ROLE_FFN_GATE      (layer N)
 *   blk.N.ffn_down.weight  -> XMIND_ROLE_FFN_DOWN      (layer N)
 *   blk.N.ffn_up.weight    -> XMIND_ROLE_FFN_UP        (layer N)
 *   blk.N.attn_norm.weight -> XMIND_ROLE_NORM_ATTN     (layer N)
 *   blk.N.ffn_norm.weight  -> XMIND_ROLE_NORM_FFN      (layer N)
 *
 * NOTE: No "output.weight" — tokenless models use TIED EMBEDDINGS.
 * =================================================================== */

/*
 * Parse "blk.N." prefix from tensor name.
 * Returns the byte offset of the suffix (after "blk.N."),
 * or -1 if name doesn't match the pattern.
 * Writes the layer number to *layer_out.
 */
static int32_t it_parse_blk_prefix(const char *name, uint32_t name_len,
                                     uint32_t *layer_out) {
    if (name_len < 6u) return -1;
    if (name[0] != 'b' || name[1] != 'l' || name[2] != 'k' || name[3] != '.')
        return -1;

    uint32_t p = 4u;
    uint32_t layer = 0u;
    if (p >= name_len || name[p] < '0' || name[p] > '9') return -1;

    while (p < name_len && name[p] >= '0' && name[p] <= '9') {
        layer = layer * 10u + (uint32_t)(name[p] - '0');
        p++;
    }
    if (p >= name_len || name[p] != '.') return -1;
    if (layer >= XMIND_MAX_LAYERS) return -1;

    *layer_out = layer;
    return (int32_t)(p + 1u);  /* offset past "blk.N." */
}

static int32_t it_map_tensor(const gguf_catalog_t *catalog,
                               uint32_t tensor_index,
                               xmind_tensor_role_t *role_out,
                               uint32_t *layer_out) {
    if (!catalog || tensor_index >= catalog->tensors_stored ||
        !role_out || !layer_out) {
        return -1;
    }

    const gguf_tensor_desc_t *td = &catalog->tensors[tensor_index];
    const char *name = td->name;
    uint32_t nl = td->name_len;
    /* Use stored length (may be truncated) */
    uint32_t snl = (nl < (GGUF_TENSOR_NAME_MAX - 1u)) ? nl : (GGUF_TENSOR_NAME_MAX - 1u);

    /* Global tensors (no "blk." prefix) — tokenless has NO output.weight */
    if (it_name_eq(name, snl, "token_emb.weight")) {
        *role_out = XMIND_ROLE_TOKEN_EMB; *layer_out = 0u; return 0;
    }
    if (it_name_eq(name, snl, "output_norm.weight")) {
        *role_out = XMIND_ROLE_NORM_FINAL; *layer_out = 0u; return 0;
    }

    /* Per-layer tensors: "blk.N.suffix.weight" */
    uint32_t layer = 0u;
    int32_t sfx_off = it_parse_blk_prefix(name, snl, &layer);
    if (sfx_off < 0) {
        *role_out = XMIND_ROLE_UNKNOWN; *layer_out = 0u; return -1;
    }

    const char *sfx = name + sfx_off;
    uint32_t sfx_len = snl - (uint32_t)sfx_off;
    *layer_out = layer;

    if      (it_name_eq(sfx, sfx_len, "attn_q.weight"))      { *role_out = XMIND_ROLE_ATTN_Q;    return 0; }
    else if (it_name_eq(sfx, sfx_len, "attn_k.weight"))      { *role_out = XMIND_ROLE_ATTN_K;    return 0; }
    else if (it_name_eq(sfx, sfx_len, "attn_v.weight"))      { *role_out = XMIND_ROLE_ATTN_V;    return 0; }
    else if (it_name_eq(sfx, sfx_len, "attn_output.weight")) { *role_out = XMIND_ROLE_ATTN_O;    return 0; }
    else if (it_name_eq(sfx, sfx_len, "ffn_gate.weight"))    { *role_out = XMIND_ROLE_FFN_GATE;  return 0; }
    else if (it_name_eq(sfx, sfx_len, "ffn_down.weight"))    { *role_out = XMIND_ROLE_FFN_DOWN;  return 0; }
    else if (it_name_eq(sfx, sfx_len, "ffn_up.weight"))      { *role_out = XMIND_ROLE_FFN_UP;    return 0; }
    else if (it_name_eq(sfx, sfx_len, "attn_norm.weight"))   { *role_out = XMIND_ROLE_NORM_ATTN; return 0; }
    else if (it_name_eq(sfx, sfx_len, "ffn_norm.weight"))    { *role_out = XMIND_ROLE_NORM_FFN;  return 0; }

    /* Unrecognized suffix */
    *role_out = XMIND_ROLE_UNKNOWN;
    return -1;
}

/* ===================================================================
 * S6  validate() — Verify weight plan completeness
 *
 * Required global roles: TOKEN_EMB, NORM_FINAL  (NO OUTPUT — tied)
 * Required per-layer roles: Q, K, V, O, GATE, DOWN, UP, NORM_ATTN, NORM_FFN
 * =================================================================== */

static int32_t it_validate(const gguf_catalog_t *catalog,
                             const xmind_weight_plan_t *plan,
                             uint32_t n_layers) {
    (void)catalog;
    if (!plan) return -1;

    int32_t errors = 0;

    /* Check global roles (no XMIND_ROLE_OUTPUT — tied embeddings) */
    if (!xmind_plan_find(plan, XMIND_ROLE_TOKEN_EMB, 0u)) {
        pal_console_printf("[INTERP-TOKENLESS] WARN: missing token_emb\n");
        errors++;
    }
    if (!xmind_plan_find(plan, XMIND_ROLE_NORM_FINAL, 0u)) {
        pal_console_printf("[INTERP-TOKENLESS] WARN: missing output_norm\n");
        errors++;
    }

    /* Check per-layer roles */
    static const xmind_tensor_role_t required_layer_roles[] = {
        XMIND_ROLE_ATTN_Q, XMIND_ROLE_ATTN_K, XMIND_ROLE_ATTN_V,
        XMIND_ROLE_ATTN_O, XMIND_ROLE_FFN_GATE, XMIND_ROLE_FFN_DOWN,
        XMIND_ROLE_FFN_UP, XMIND_ROLE_NORM_ATTN, XMIND_ROLE_NORM_FFN,
    };
    uint32_t n_required = sizeof(required_layer_roles) / sizeof(required_layer_roles[0]);

    uint32_t layer;
    for (layer = 0u; layer < n_layers; layer++) {
        uint32_t ri;
        for (ri = 0u; ri < n_required; ri++) {
            if (!xmind_plan_find(plan, required_layer_roles[ri], layer)) {
                pal_console_printf("[INTERP-TOKENLESS] WARN: layer %u missing role %u\n",
                                   layer, (uint32_t)required_layer_roles[ri]);
                errors++;
            }
        }
    }

    if (errors == 0) {
        pal_console_printf("[INTERP-TOKENLESS] validation: %u layers, all roles present "
                           "(tied embeddings — no output.weight)\n", n_layers);
    } else {
        pal_console_printf("[INTERP-TOKENLESS] validation: %d missing roles\n", errors);
    }

    return -errors;
}

/* ===================================================================
 * S7  VTABLE DEFINITION
 *
 * Registered at slot 1 by interp_registry.c (slot 0 = interp_llama).
 * =================================================================== */

const xmind_artifact_interp_t xmind_interp_tokenless = {
    .family_name  = "tokenless_lm",
    .detect       = it_detect,
    .build_config = it_build_config,
    .map_tensor   = it_map_tensor,
    .validate     = it_validate,
};
