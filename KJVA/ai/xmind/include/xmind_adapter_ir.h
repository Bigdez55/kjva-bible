/* xmind_adapter_ir.h — C-side AdapterIR descriptor (§11.1 Add).
 *
 * A lightweight, inspectable descriptor of an adapter's shape/provenance, mirroring
 * the Python AdapterIR (training/peft/v2/adapter_ir.py) for the C runtime. Used for
 * telemetry, validation, and cache keys. NEW header (does not modify contract headers).
 */
#ifndef XMIND_ADAPTER_IR_H
#define XMIND_ADAPTER_IR_H

#include <stdint.h>
#include "lora.h"

#ifdef __cplusplus
extern "C" {
#endif

#define XMIND_ADAPTER_FAMILY_MAX 24

typedef struct {
    char     family[XMIND_ADAPTER_FAMILY_MAX];  /* "WEIGHT_ADDITIVE", ... */
    uint32_t target_count;                       /* number of adapted tensors */
    uint32_t total_rank;                         /* sum of per-tensor ranks */
    uint64_t param_count;                        /* trainable element count */
} xmind_adapter_ir_t;

/* Summarize a loaded LoRA adapter into an IR descriptor. Returns 0 on success. */
int xmind_adapter_ir_describe(const xmind_lora_t *adapter, xmind_adapter_ir_t *out);

/* Stable 16-hex content key derived from the descriptor (for cache lookup). */
void xmind_adapter_ir_key(const xmind_adapter_ir_t *ir, char out_key[17]);

/* --- Adapter cache (§11.1 Add: adapter_cache.c) — bounded LRU of borrowed adapters. --- */
void                 xmind_adapter_cache_reset(void);
int                  xmind_adapter_cache_put(const char *key, const xmind_lora_t *adapter);
const xmind_lora_t  *xmind_adapter_cache_get(const char *key);
uint32_t             xmind_adapter_cache_count(void);

#ifdef __cplusplus
}
#endif
#endif /* XMIND_ADAPTER_IR_H */
