/*
 * interp_llama.c — Llama Family Artifact Interpreter
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Implements the artifact interpreter for the Llama model family
 *   (Llama 2, Llama 3, Llama 3.1, Llama 3.2).  Maps Llama-specific
 *   GGUF metadata keys and tensor names to XMIND canonical types.
 *
 *   detect():       Checks for "llama" arch or "llama.block_count" key
 *   build_config(): Extracts n_layers, n_heads, etc. from GGUF metadata
 *   map_tensor():   Maps "blk.N.attn_q.weight" -> XMIND_ROLE_ATTN_Q
 *   validate():     Verifies all required roles present for all layers
 *
 * No libc.  Freestanding C11.  PAL types only.
 *
 * S1  String helpers
 * S2  Llama GGUF metadata key constants
 * S3  detect() — family detection
 * S4  build_config() — config extraction from metadata
 * S5  map_tensor() — tensor name to role mapping
 * S6  validate() — completeness check
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

static uint32_t il_strlen(const char *s) {
    uint32_t n = 0u;
    while (s[n]) { n++; }
    return n;
}

static int32_t il_strncmp(const char *a, const char *b, uint32_t n) {
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
static int il_name_eq(const char *name, uint32_t nl, const char *s) {
    uint32_t i;
    for (i = 0u; i < nl; i++) {
        if (!s[i] || (uint8_t)s[i] != (uint8_t)name[i]) return 0;
    }
    return s[nl] == '\0';
}

/* ===================================================================
 * S2  LLAMA GGUF METADATA KEY CONSTANTS
 * =================================================================== */

#define LLAMA_KEY_BLOCK_COUNT     "llama.block_count"
#define LLAMA_KEY_HEAD_COUNT      "llama.attention.head_count"
#define LLAMA_KEY_HEAD_COUNT_KV   "llama.attention.head_count_kv"
#define LLAMA_KEY_CTX_LEN         "llama.context_length"
#define LLAMA_KEY_EMBEDDING_LEN   "llama.embedding_length"
#define LLAMA_KEY_FFN_LEN         "llama.feed_forward_length"
#define LLAMA_KEY_ROPE_FREQ_BASE  "llama.rope.freq_base"
#define LLAMA_KEY_VOCAB_SIZE      "tokenizer.ggml.tokens"
#define LLAMA_KEY_BOS_ID          "tokenizer.ggml.bos_token_id"
#define LLAMA_KEY_EOS_ID          "tokenizer.ggml.eos_token_id"

/* ===================================================================
 * S3  detect() — Llama family detection
 *
 * Returns 100 if catalog arch == "llama".
 * Returns  80 if "llama.block_count" is present in KV.
 * Returns   0 otherwise.
 * =================================================================== */

static uint32_t il_detect(const gguf_catalog_t *catalog) {
    if (!catalog) return 0u;

    /* Primary: check arch string */
    if (catalog->arch_len == 5u &&
        il_strncmp(catalog->arch, "llama", 5u) == 0) {
        return 100u;
    }

    /* Fallback: check for characteristic metadata key */
    const gguf_kv_t *kv = gguf_find_kv(catalog, LLAMA_KEY_BLOCK_COUNT);
    if (kv) return 80u;

    return 0u;
}

/* ===================================================================
 * S4  build_config() — Extract xmind_config_t from Llama metadata
 *
 * Reads actual metadata values.  Falls back to Llama 3.2 3B defaults
 * for any missing fields (backward compatible with Sprint 8 behavior).
 * =================================================================== */

/* Llama 3.2 3B preset defaults */
#define LLAMA_DEFAULT_LAYERS     28u
#define LLAMA_DEFAULT_HEADS      32u
#define LLAMA_DEFAULT_KV_HEADS    8u
#define LLAMA_DEFAULT_HIDDEN   3072u
#define LLAMA_DEFAULT_FFN      8192u
#define LLAMA_DEFAULT_VOCAB  128256u
#define LLAMA_DEFAULT_CTX      2048u
#define LLAMA_DEFAULT_ROPE  500000.0f

static int32_t il_build_config(const gguf_catalog_t *catalog,
                                 void *cfg_out) {
    if (!catalog || !cfg_out) return -1;
    xmind_config_t *cfg = (xmind_config_t *)cfg_out;

    /* Start from Llama 3.2 3B defaults */
    cfg->n_layers   = LLAMA_DEFAULT_LAYERS;
    cfg->n_heads    = LLAMA_DEFAULT_HEADS;
    cfg->n_kv_heads = LLAMA_DEFAULT_KV_HEADS;
    cfg->hidden_dim = LLAMA_DEFAULT_HIDDEN;
    cfg->ffn_dim    = LLAMA_DEFAULT_FFN;
    cfg->vocab_size = LLAMA_DEFAULT_VOCAB;
    cfg->ctx_len    = LLAMA_DEFAULT_CTX;
    cfg->rope_base  = LLAMA_DEFAULT_ROPE;
    cfg->bos_id     = 0u;   /* 0 = use compile-time default */
    cfg->eos_id     = 0u;
    cfg->eog_ids[0] = 0u;
    cfg->eog_ids[1] = 0u;
    cfg->eog_ids[2] = 0u;
    cfg->eog_ids[3] = 0u;

    /* Override from actual metadata */
    const gguf_kv_t *kv;

    kv = gguf_find_kv(catalog, LLAMA_KEY_BLOCK_COUNT);
    if (kv && kv->val.u64 > 0u && kv->val.u64 <= XMIND_MAX_LAYERS) {
        cfg->n_layers = (uint32_t)kv->val.u64;
    }

    kv = gguf_find_kv(catalog, LLAMA_KEY_HEAD_COUNT);
    if (kv && kv->val.u64 > 0u && kv->val.u64 <= XMIND_MAX_HEADS) {
        cfg->n_heads = (uint32_t)kv->val.u64;
    }

    kv = gguf_find_kv(catalog, LLAMA_KEY_HEAD_COUNT_KV);
    if (kv && kv->val.u64 > 0u) {
        cfg->n_kv_heads = (uint32_t)kv->val.u64;
    }

    kv = gguf_find_kv(catalog, LLAMA_KEY_CTX_LEN);
    if (kv && kv->val.u64 > 0u && kv->val.u64 <= XMIND_MAX_SEQ) {
        cfg->ctx_len = (uint32_t)kv->val.u64;
    }

    kv = gguf_find_kv(catalog, LLAMA_KEY_EMBEDDING_LEN);
    if (kv && kv->val.u64 > 0u) {
        cfg->hidden_dim = (uint32_t)kv->val.u64;
    }

    kv = gguf_find_kv(catalog, LLAMA_KEY_FFN_LEN);
    if (kv && kv->val.u64 > 0u) {
        cfg->ffn_dim = (uint32_t)kv->val.u64;
    }

    kv = gguf_find_kv(catalog, LLAMA_KEY_ROPE_FREQ_BASE);
    if (kv) {
        cfg->rope_base = kv->val.f32;
    }

    /* Vocab size from tokenizer array (count of elements) */
    kv = gguf_find_kv(catalog, LLAMA_KEY_VOCAB_SIZE);
    if (kv && (uint32_t)kv->vtype == GGUF_TYPE_ARRAY && kv->val.arr.arr_count > 0u) {
        cfg->vocab_size = (uint32_t)kv->val.arr.arr_count;
    }

    /* Special token IDs */
    kv = gguf_find_kv(catalog, LLAMA_KEY_BOS_ID);
    if (kv) { cfg->bos_id = (uint32_t)kv->val.u64; }

    kv = gguf_find_kv(catalog, LLAMA_KEY_EOS_ID);
    if (kv) { cfg->eos_id = (uint32_t)kv->val.u64; }

    /* Derive head_dim */
    if (cfg->n_heads > 0u) {
        cfg->head_dim = cfg->hidden_dim / cfg->n_heads;
    }

    /* FFN LAYOUT ASSUMPTION: XM_FFN_SWIGLU_3MAT
     * This interpreter assumes SwiGLU 3-matrix FFN layout throughout:
     *   ffn_gate.weight  (w1) — gating projection (activated)
     *   ffn_up.weight    (w3) — up projection (gated)
     *   ffn_down.weight  (w2) — down projection (output)
     * Allocation: per-layer scratch requires 2 * ffn_dim * sizeof(float).
     * Non-Llama families (Qwen2, some Phi variants) must use their own
     * interpreter and must NOT be loaded through this vtable. */

    pal_console_printf("[INTERP-LLAMA] config: layers=%u heads=%u kv=%u "
                       "hidden=%u ffn=%u vocab=%u ctx=%u rope=%.0f "
                       "ffn_layout=XM_FFN_SWIGLU_3MAT\n",
                       cfg->n_layers, cfg->n_heads, cfg->n_kv_heads,
                       cfg->hidden_dim, cfg->ffn_dim, cfg->vocab_size,
                       cfg->ctx_len, (double)cfg->rope_base);
    return 0;
}

/* ===================================================================
 * S5  map_tensor() — Map Llama tensor names to canonical roles
 *
 * Llama naming convention:
 *   token_emb.weight       -> XMIND_ROLE_TOKEN_EMB     (global)
 *   output_norm.weight     -> XMIND_ROLE_NORM_FINAL    (global)
 *   output.weight          -> XMIND_ROLE_OUTPUT         (global)
 *   blk.N.attn_q.weight    -> XMIND_ROLE_ATTN_Q        (layer N)
 *   blk.N.attn_k.weight    -> XMIND_ROLE_ATTN_K        (layer N)
 *   blk.N.attn_v.weight    -> XMIND_ROLE_ATTN_V        (layer N)
 *   blk.N.attn_output.weight -> XMIND_ROLE_ATTN_O      (layer N)
 *   blk.N.ffn_gate.weight  -> XMIND_ROLE_FFN_GATE      (layer N)
 *   blk.N.ffn_down.weight  -> XMIND_ROLE_FFN_DOWN      (layer N)
 *   blk.N.ffn_up.weight    -> XMIND_ROLE_FFN_UP        (layer N)
 *   blk.N.attn_norm.weight -> XMIND_ROLE_NORM_ATTN     (layer N)
 *   blk.N.ffn_norm.weight  -> XMIND_ROLE_NORM_FFN      (layer N)
 * =================================================================== */

/*
 * Parse "blk.N." prefix from tensor name.
 * Returns the byte offset of the suffix (after "blk.N."),
 * or -1 if name doesn't match the pattern.
 * Writes the layer number to *layer_out.
 */
static int32_t il_parse_blk_prefix(const char *name, uint32_t name_len,
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

static int32_t il_map_tensor(const gguf_catalog_t *catalog,
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

    /* Global tensors (no "blk." prefix) */
    if (il_name_eq(name, snl, "token_emb.weight")) {
        *role_out = XMIND_ROLE_TOKEN_EMB; *layer_out = 0u; return 0;
    }
    if (il_name_eq(name, snl, "output_norm.weight")) {
        *role_out = XMIND_ROLE_NORM_FINAL; *layer_out = 0u; return 0;
    }
    if (il_name_eq(name, snl, "output.weight")) {
        *role_out = XMIND_ROLE_OUTPUT; *layer_out = 0u; return 0;
    }

    /* Per-layer tensors: "blk.N.suffix.weight" */
    uint32_t layer = 0u;
    int32_t sfx_off = il_parse_blk_prefix(name, snl, &layer);
    if (sfx_off < 0) {
        *role_out = XMIND_ROLE_UNKNOWN; *layer_out = 0u; return -1;
    }

    const char *sfx = name + sfx_off;
    uint32_t sfx_len = snl - (uint32_t)sfx_off;
    *layer_out = layer;

    if      (il_name_eq(sfx, sfx_len, "attn_q.weight"))      { *role_out = XMIND_ROLE_ATTN_Q;    return 0; }
    else if (il_name_eq(sfx, sfx_len, "attn_k.weight"))      { *role_out = XMIND_ROLE_ATTN_K;    return 0; }
    else if (il_name_eq(sfx, sfx_len, "attn_v.weight"))      { *role_out = XMIND_ROLE_ATTN_V;    return 0; }
    else if (il_name_eq(sfx, sfx_len, "attn_output.weight")) { *role_out = XMIND_ROLE_ATTN_O;    return 0; }
    else if (il_name_eq(sfx, sfx_len, "ffn_gate.weight"))    { *role_out = XMIND_ROLE_FFN_GATE;  return 0; }
    else if (il_name_eq(sfx, sfx_len, "ffn_down.weight"))    { *role_out = XMIND_ROLE_FFN_DOWN;  return 0; }
    else if (il_name_eq(sfx, sfx_len, "ffn_up.weight"))      { *role_out = XMIND_ROLE_FFN_UP;    return 0; }
    else if (il_name_eq(sfx, sfx_len, "attn_norm.weight"))   { *role_out = XMIND_ROLE_NORM_ATTN; return 0; }
    else if (il_name_eq(sfx, sfx_len, "ffn_norm.weight"))    { *role_out = XMIND_ROLE_NORM_FFN;  return 0; }

    /* Unrecognized suffix */
    *role_out = XMIND_ROLE_UNKNOWN;
    return -1;
}

/* ===================================================================
 * S6  validate() — Verify weight plan completeness
 *
 * Checks that every required role is present for every layer.
 * Required per-layer roles: Q, K, V, O, GATE, DOWN, UP, NORM_ATTN, NORM_FFN
 * Required global roles: TOKEN_EMB, NORM_FINAL
 * =================================================================== */

static int32_t il_validate(const gguf_catalog_t *catalog,
                             const xmind_weight_plan_t *plan,
                             uint32_t n_layers) {
    (void)catalog;
    if (!plan) return -1;

    int32_t errors = 0;

    /* Check global roles */
    if (!xmind_plan_find(plan, XMIND_ROLE_TOKEN_EMB, 0u)) {
        pal_console_printf("[INTERP-LLAMA] WARN: missing token_emb\n");
        errors++;
    }
    if (!xmind_plan_find(plan, XMIND_ROLE_NORM_FINAL, 0u)) {
        pal_console_printf("[INTERP-LLAMA] WARN: missing output_norm\n");
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
                pal_console_printf("[INTERP-LLAMA] WARN: layer %u missing role %u\n",
                                   layer, (uint32_t)required_layer_roles[ri]);
                errors++;
            }
        }
    }

    if (errors == 0) {
        pal_console_printf("[INTERP-LLAMA] validation: %u layers, all roles present\n",
                           n_layers);
    } else {
        pal_console_printf("[INTERP-LLAMA] validation: %d missing roles\n", errors);
    }

    return -errors;
}

/* ===================================================================
 * S7  VTABLE DEFINITION
 * =================================================================== */

const xmind_artifact_interp_t xmind_interp_llama = {
    .family_name  = "llama",
    .detect       = il_detect,
    .build_config = il_build_config,
    .map_tensor   = il_map_tensor,
    .validate     = il_validate,
};
