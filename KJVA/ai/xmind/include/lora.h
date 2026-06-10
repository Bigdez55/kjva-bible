/*
 * lora.h — LoRA adapter loading + delta-apply for XMIND inference.
 *
 * Reads safetensors-formatted adapter files (industry-standard binary format
 * shared by HuggingFace and exportable from MLX). Applies low-rank delta
 * during matmul:  y = W*x  +  (alpha/r) * B * (A * x)
 *
 * Designed to be EXTENDED for the Omni-PEFT experimental composition path:
 * the xmind_lora_t structure supports MULTIPLE delta operators per tensor
 * (sum or routed composition). For now, only plain LoRA (single A/B) is
 * implemented in the scalar path. DoRA / IA3 / Omni composition can layer
 * on top by adding new xmind_lora_op_kind_t variants.
 *
 * Drift policy: XMIND consumes safetensors (open standard). No MLX or HF
 * dependency at runtime. The training stack writes safetensors; XMIND reads
 * safetensors.
 */
#ifndef XMIND_LORA_H
#define XMIND_LORA_H

#include "pal.h"

#ifdef __cplusplus
extern "C" {
#endif

#define XMIND_LORA_MAX_TENSORS  256u
#define XMIND_LORA_MAX_NAMELEN  128u

typedef enum {
    XMIND_LORA_OP_NONE     = 0,
    XMIND_LORA_OP_LORA     = 1,   /* W' = W + (alpha/r) * B * A             */
    XMIND_LORA_OP_DORA     = 2,   /* LoRA + magnitude rescaling (future)     */
    XMIND_LORA_OP_IA3      = 3,   /* element-wise scaling (future)           */
    XMIND_LORA_OP_OMNI     = 4,   /* composed/routed multi-operator (future) */
} xmind_lora_op_kind_t;

typedef struct {
    char                name[XMIND_LORA_MAX_NAMELEN];   /* target tensor (e.g. "layers.0.attn.wq") */
    xmind_lora_op_kind_t kind;
    uint32_t            rank;          /* r (LoRA rank, typically 8-32)         */
    float               alpha;         /* LoRA scaling factor                    */
    /* A: [rank × d_in]   B: [d_out × rank] — fp32 contiguous */
    const float        *A;             /* down-projection (rank rows × d_in cols) */
    const float        *B;             /* up-projection (d_out rows × rank cols)  */
    uint32_t            d_in;
    uint32_t            d_out;
} xmind_lora_entry_t;

typedef struct {
    xmind_lora_entry_t  entries[XMIND_LORA_MAX_TENSORS];
    uint32_t            n_entries;
    void               *raw_data;      /* mmap'd payload — keep alive until free */
    uint64_t            raw_size;
    pal_handle_t        raw_handle;
    char                base_sha256[80]; /* §9.2: base-model sha from __metadata__ ("" = unset) */
    char                scope[256];      /* §9.2 authority-scope: comma/space-separated permitted
                                          * tensor-name prefixes from __metadata__ ("" = unset =
                                          * unverifiable = admitted). gov_admit refuses any entry
                                          * targeting a tensor outside this declared scope. */
} xmind_lora_t;

/* Load a safetensors-format adapter. Sets *out on success.
 * Returns 0 on success, negative on error.
 * The adapter holds a reference to the mmap'd file payload until xmind_lora_free(). */
int xmind_lora_load_safetensors(const char *path, xmind_lora_t *out);

/* Find an entry by target-tensor name. Returns NULL if not adapted. */
const xmind_lora_entry_t *xmind_lora_find(const xmind_lora_t *lora, const char *name);

/* Apply the LoRA delta in place: out[d_out] += (alpha/r) * B * (A * x)
 * Used after a standard matmul out = W * x. Returns 0 on success. */
int xmind_lora_apply_delta(const xmind_lora_entry_t *entry,
                            const float *x,
                            float *out);

/* Release the adapter. Idempotent. */
void xmind_lora_free(xmind_lora_t *lora);

/* Diagnostics — prints entry inventory to console. */
void xmind_lora_dump(const xmind_lora_t *lora);

#ifdef __cplusplus
}
#endif
#endif
