/* adapter_ir.c — C-side AdapterIR descriptor (§11.1 Add). */
#include "xmind_adapter_ir.h"

#include <stdio.h>
#include <string.h>

int xmind_adapter_ir_describe(const xmind_lora_t *adapter, xmind_adapter_ir_t *out) {
    uint32_t i;
    const char *family = "WEIGHT_ADDITIVE";

    if ((adapter == (const xmind_lora_t *)0) || (out == (xmind_adapter_ir_t *)0)) {
        return -1;
    }
    memset(out, 0, sizeof(*out));
    out->target_count = adapter->n_entries;
    for (i = 0u; i < adapter->n_entries; i++) {
        const xmind_lora_entry_t *e = &adapter->entries[i];
        out->total_rank += e->rank;
        out->param_count += (uint64_t)e->rank * (uint64_t)e->d_in
                          + (uint64_t)e->d_out * (uint64_t)e->rank;
        if (e->kind == XMIND_LORA_OP_IA3) {
            family = "ACTIVATION";
        } else if (e->kind == XMIND_LORA_OP_DORA) {
            family = "WEIGHT_ADDITIVE";
        }
    }
    strncpy(out->family, family, sizeof(out->family) - 1u);
    out->family[sizeof(out->family) - 1u] = '\0';
    return 0;
}

void xmind_adapter_ir_key(const xmind_adapter_ir_t *ir, char out_key[17]) {
    /* FNV-1a 64 over the descriptor bytes → 16-hex key. */
    uint64_t h = 1469598103934665603ULL;
    const unsigned char *p = (const unsigned char *)ir;
    size_t i;
    for (i = 0u; i < sizeof(*ir); i++) {
        h ^= (uint64_t)p[i];
        h *= 1099511628211ULL;
    }
    (void)snprintf(out_key, 17u, "%016llx", (unsigned long long)h);
}
