/* xmind_adapter_runtime.h — XMIND-native adapter runtime dispatch (§11.1 Add).
 *
 * Binds a loaded LoRA-family adapter (lora.h) into the transformer hot path so its
 * delta applies at inference. The apply hook is a NO-OP when no adapter is active,
 * so a model running without an adapter is byte-identical to the pre-adapter engine.
 *
 * This is a NEW header (spec §11.1 "Add"); it does not modify any existing contract
 * header. It builds on the existing lora.c primitives (load/find/apply_delta).
 */
#ifndef XMIND_ADAPTER_RUNTIME_H
#define XMIND_ADAPTER_RUNTIME_H

#include <stdint.h>
#include "lora.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Reset the runtime to "no adapter active". */
void xmind_adapter_runtime_init(void);

/* §9.2: set the running model's base sha256 so gov_admit can refuse an adapter whose declared
 * base_sha256 mismatches. Pass "" / NULL to clear (no base-hash check). */
void xmind_adapter_runtime_set_expected_base(const char *sha256);

/* Activate a loaded adapter (borrowed pointer; owned by the caller). id is a short
 * label for telemetry/provenance. Returns 0 on success, -1 on null adapter. */
int xmind_adapter_runtime_activate(const xmind_lora_t *adapter, const char *id);

/* Deactivate the active adapter (the borrowed pointer is not freed here). */
void xmind_adapter_runtime_deactivate(void);

int         xmind_adapter_runtime_active(void);
const char *xmind_adapter_runtime_id(void);

/* Hot-path hook: after out = W * x for tensor `role` (e.g. "attn_q", "ffn_down")
 * at transformer `layer`, apply the active adapter's delta to `out` in place.
 * No-op when no adapter is active or no entry matches the tensor name. */
void xmind_adapter_runtime_apply(uint32_t layer, const char *role,
                                 const float *x, float *out);

/* Total successful delta applications since init (telemetry). */
uint64_t xmind_adapter_runtime_apply_count(void);

#ifdef __cplusplus
}
#endif
#endif /* XMIND_ADAPTER_RUNTIME_H */
