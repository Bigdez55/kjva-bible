/*
 * xmind_easy.h — Simplified C convenience API for Python ctypes / FFI.
 *
 * The native xmind_* API takes complex structs (xmind_model_t, xmind_config_t,
 * xmind_session_t). For Python integration we expose a flat function set with
 * primitive arguments only — easy to map via ctypes.
 *
 * Per-process singleton: each council daemon is its own process. One
 * xmind_easy_init() call per process loads the model + creates the per-member
 * session. Federated architecture: each process has its own model_t + KV cache.
 */
#ifndef XMIND_EASY_H
#define XMIND_EASY_H

#ifdef __cplusplus
extern "C" {
#endif

/* §8.3 verify-before-materialize: declare the expected FIPS sha256 (lowercase or
 * uppercase hex; a leading-64-hex sidecar form like `shasum -a 256` output is also
 * accepted) of the model artifact BEFORE xmind_easy_init() loads it. If set non-empty
 * and the real hash of the GGUF differs, xmind_easy_init() REFUSES to materialize the
 * weights (returns -8) — no model artifact loads without hash verification.
 * Pass "" / NULL to clear. Backward-compatible: absent expectation = load proceeds.
 * Precedence at init: this setter (if non-empty) → `<model_path>.sha256` sidecar
 * (if present) → no expectation (fail-open, as today). */
int xmind_easy_set_expected_sha256(const char *hex);

/* Returns 0 on success, negative on error. -8 = declared-sha256 mismatch (REFUSED
 * before materialization; the weights were NOT loaded). */
int xmind_easy_init(const char *model_path, int max_seq_len);

/* Load a LoRA adapter (safetensors format) on top of the loaded base model.
 * Returns: 0 = OK, 1 = no adapter path (skip), <0 = error.
 * Subsequent xmind_easy_generate() calls will apply the delta at inference. */
int xmind_easy_load_adapter(const char *adapter_path);

/* True (1) if an adapter is currently loaded, 0 otherwise. */
int xmind_easy_adapter_loaded(void);

/* Generate up to max_out bytes into out_buf. Returns bytes written or negative on error. */
int xmind_easy_generate(const char *prompt, char *out_buf, int max_out,
                         float temperature, float top_p, int max_new_tokens);

/* Set sampler for subsequent calls. */
int xmind_easy_set_sampler(float temperature, float top_p, unsigned long long seed);

/* Reset session (clears KV cache) — call between independent prompts. */
int xmind_easy_reset(void);

/* True (1) if initialized + ready, 0 otherwise. */
int xmind_easy_ready(void);

/* Build identification — for logging. */
const char *xmind_easy_version(void);

/* Materialization Plane (ADR-0002 §8.2): write the materialized model's architecture facts
 * as JSON into `out`. Returns bytes written (>0), or <0 on error / not-initialized. */
int xmind_easy_model_info(char *out, int max_out);

/* Adapter IR descriptor (§11.1) as JSON — structural identity of the loaded adapter (family,
 * target_count, total_rank, param_count, ir_key, cached). <0 when no adapter is loaded. */
int xmind_easy_adapter_ir(char *out, int max_out);

void xmind_easy_shutdown(void);

#ifdef __cplusplus
}
#endif
#endif
