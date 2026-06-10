/*
 * xmind_easy.c — Python-friendly C API. Per-process singleton.
 *
 * Init flow (matches docs in include/xmind.h):
 *   1. xmind_init()           — validate config, zero-init model
 *   2. xmind_weights_load_file() — load GGUF (sets config from header)
 *   3. xmind_alloc_state()    — allocate KV cache + scratch
 *   4. xmind_rope_precompute()— RoPE table
 *   5. xmind_preflight_check()— verify pointers
 *   6. xmind_session_create() — per-process session
 */

#include "xmind_easy.h"
#include "xmind.h"
#include "lora.h"
#include "xmind_adapter_runtime.h"   /* §11.1 adapter runtime: bind loaded adapter to inference */
#include "xmind_adapter_ir.h"        /* §11.1 adapter IR descriptor + content cache */
#include "xsec.h"                    /* real SHA-256 (xsec) for the weight source_hash */
#include <string.h>
#include <time.h>
#include <stdio.h>

/* The XMIND C engine maintains a process-global model singleton in xmind.c
 * (s_xmind_model, returned by xmind_get_global()). xmind_session_create()
 * uses that global directly. Earlier revisions of this file used a private
 * static `s_model`, which caused session_create() to operate on a different
 * (uninitialized) model from xmind_easy_init(), failing preflight inside
 * session_create with rc=-7. We route all easy-API operations through the
 * global to match the engine's singleton contract. */
static xmind_session_t *s_session    = (xmind_session_t *)0;
static int              s_initialized = 0;
static float            s_temperature = 0.7f;
static float            s_top_p       = 0.9f;
static unsigned long long s_seed      = 0;
static uint32_t         s_max_seq_len = 0;   /* session context bound (tokens) */

/* LoRA adapter — at most one loaded per process. The federated runtime has
 * each council daemon in its own process, so each gets its own adapter. */
static xmind_lora_t     s_adapter;
static int              s_adapter_loaded = 0;
static xmind_adapter_ir_t s_adapter_ir;        /* IR descriptor of the loaded adapter */
static char             s_adapter_ir_key[17] = {0};  /* content key (§11.1) */
static char             s_weight_fingerprint[65] = {0};  /* §8.3 source_hash: real SHA-256 of the GGUF */
static unsigned long long s_materialized_at_ns = 0;       /* §8.3 materialized_at_ns */
static char             s_expected_sha256[65] = {0};       /* §8.3 verify-before-materialize: declared expected hash ("" = unset) */

/* §8.3 source_hash: the real SHA-256 of the materialized GGUF (xsec now links a FIPS SHA-256, no
 * longer an FNV fold) — matches `shasum -a 256`, so the engine reports the cryptographic source
 * hash directly (enables "no model artifact loads without hash verification"). */
static void easy_file_fingerprint(const char *path, char hex_out[65]) {
    hex_out[0] = '\0';
    FILE *f = fopen(path, "rb");
    if (!f) return;
    xsec_sha256_ctx_t ctx;
    xsec_sha256_init(&ctx);
    unsigned char buf[8192];
    size_t n;
    while ((n = fread(buf, 1u, sizeof(buf), f)) > 0u) {
        xsec_sha256_update(&ctx, buf, n);
    }
    fclose(f);
    uint8_t digest[32];
    xsec_sha256_final(&ctx, digest);
    static const char hx[] = "0123456789abcdef";
    for (int i = 0; i < 32; i++) {
        hex_out[i * 2]     = hx[(digest[i] >> 4) & 0x0F];
        hex_out[i * 2 + 1] = hx[digest[i] & 0x0F];
    }
    hex_out[64] = '\0';
}

/* §8.3 verify-before-materialize helpers.
 *
 * Normalize a caller- or sidecar-supplied expected hash into a lowercase 64-hex
 * string. A real `shasum -a 256 file.gguf` sidecar contains "<64hex>  file.gguf",
 * not a bare hash, so we take ONLY the leading 64 hex chars and lowercase them.
 * Returns 1 if a full 64-hex hash was extracted, 0 otherwise (out is cleared). */
static int easy_normalize_sha_hex(const char *in, char out[65]) {
    out[0] = '\0';
    if (!in) return 0;
    int n = 0;
    for (const char *p = in; *p && n < 64; p++) {
        char c = *p;
        if (c >= '0' && c <= '9') { out[n++] = c; }
        else if (c >= 'a' && c <= 'f') { out[n++] = c; }
        else if (c >= 'A' && c <= 'F') { out[n++] = (char)(c - 'A' + 'a'); }
        else break;  /* stop at first non-hex (whitespace before the filename) */
    }
    out[n] = '\0';
    return (n == 64) ? 1 : 0;
}

/* If a `<model_path>.sha256` sidecar exists, read its expected hash into out[65]
 * (normalized to leading-64-hex lowercase). Returns 1 if a full hash was read,
 * 0 if no sidecar or it did not contain a 64-hex hash. */
static int easy_read_sha_sidecar(const char *model_path, char out[65]) {
    out[0] = '\0';
    if (!model_path) return 0;
    char sidecar[1100];
    int n = snprintf(sidecar, sizeof(sidecar), "%s.sha256", model_path);
    if (n < 0 || (size_t)n >= sizeof(sidecar)) return 0;
    FILE *f = fopen(sidecar, "rb");
    if (!f) return 0;
    char buf[256];
    size_t got = fread(buf, 1u, sizeof(buf) - 1u, f);
    fclose(f);
    buf[got] = '\0';
    return easy_normalize_sha_hex(buf, out);
}

int xmind_easy_set_expected_sha256(const char *hex) {
    if (!hex || hex[0] == '\0') { s_expected_sha256[0] = '\0'; return 0; }
    /* Normalize so a bare hash, an uppercase hash, or a `shasum` sidecar line all
     * land as the same lowercase 64-hex string the engine compares against. */
    if (!easy_normalize_sha_hex(hex, s_expected_sha256)) {
        /* Not a usable 64-hex declaration — treat as unset rather than fail-closed
         * on garbage; the caller can re-set a valid one. */
        s_expected_sha256[0] = '\0';
        return -1;
    }
    return 0;
}

const char *xmind_easy_version(void) {
    return "xmind-easy/1.0 consumer-build";
}

int xmind_easy_model_info(char *out, int max_out) {
    /* Materialization Plane (ADR-0002 §8.2 "model artifact / weight materialization"): expose
     * the facts of the model the engine materialized from the GGUF, as JSON, so the Python
     * materialization path can CONSUME a model_artifact MaterializationRecord. The C side is the
     * one owner of the weight materialization; this is read-only reporting, never a second loop. */
    if (!out || max_out <= 0) return -1;
    if (!s_initialized) { out[0] = '\0'; return -1; }
    xmind_model_t *m = xmind_get_global();
    const xmind_config_t *c = &m->cfg;
    int n = snprintf(out, (size_t)max_out,
        "{\"n_layers\":%u,\"n_heads\":%u,\"n_kv_heads\":%u,\"head_dim\":%u,"
        "\"hidden_dim\":%u,\"ffn_dim\":%u,\"vocab_size\":%u,\"ctx_len\":%u,"
        "\"rope_base\":%.1f,\"quant\":\"q4_0\",\"adapter_loaded\":%d,"
        "\"weight_sha256\":\"%s\",\"materialized_at_ns\":%llu}",
        c->n_layers, c->n_heads, c->n_kv_heads, c->head_dim,
        c->hidden_dim, c->ffn_dim, c->vocab_size, c->ctx_len,
        (double)c->rope_base, s_adapter_loaded,
        s_weight_fingerprint, s_materialized_at_ns);
    if (n < 0 || n >= max_out) return -2;
    return n;
}

int xmind_easy_ready(void) { return s_initialized; }

int xmind_easy_init(const char *model_path, int max_seq_len) {
    if (s_initialized) return 0;
    if (!model_path) return -1;
    if (max_seq_len <= 0) max_seq_len = 2048;

    /* §8.3 VERIFY-BEFORE-MATERIALIZE — "no model artifact loads without hash
     * verification". Compute the real FIPS sha256 of the GGUF NOW, before the
     * loader maps/reads a single weight. The expected hash comes from (in order):
     *   1. xmind_easy_set_expected_sha256()  (explicit caller declaration)
     *   2. `<model_path>.sha256` sidecar      (zero-caller-change verification)
     *   3. neither                            (identity unknown → fail-OPEN, load)
     * On a DECLARED mismatch we REFUSE: return -8 WITHOUT touching the model
     * singleton, so the weights are never materialized. We reuse this computed
     * digest to populate s_weight_fingerprint below (no double-hash). */
    char real_sha[65];
    easy_file_fingerprint(model_path, real_sha);  /* "" if the file can't be opened */

    char expected_sha[65];
    int have_expected = 0;
    if (s_expected_sha256[0] != '\0') {
        strncpy(expected_sha, s_expected_sha256, sizeof(expected_sha) - 1);
        expected_sha[sizeof(expected_sha) - 1] = '\0';
        have_expected = 1;
    } else if (easy_read_sha_sidecar(model_path, expected_sha)) {
        have_expected = 1;
    }

    if (have_expected) {
        /* easy_file_fingerprint emits lowercase; expected_sha is already normalized
         * to lowercase 64-hex, so a plain strcmp is the case-correct comparison. */
        if (real_sha[0] == '\0' || strcmp(real_sha, expected_sha) != 0) {
            fprintf(stderr,
                "[xmind_easy] REFUSE materialize: sha256 mismatch path=%s "
                "expected=%s actual=%s\n",
                model_path, expected_sha,
                (real_sha[0] != '\0') ? real_sha : "(unreadable)");
            return -8;  /* declared-hash mismatch — weights NOT materialized */
        }
        fprintf(stderr,
            "[xmind_easy] sha256 verified path=%s sha256=%s\n",
            model_path, real_sha);
    }

    /* xmind_weights_load_file internally performs:
     *   - GGUF catalog parse
     *   - interpreter detect (slot 0 llama / slot 1 tokenless_lm)
     *   - build_config from actual metadata (populates n_layers/heads/dims)
     *   - xmind_init(m, &cfg) with the populated config
     *   - xmind_alloc_state(m)
     *   - tensor data load
     * So calling xmind_init() here with an empty cfg would (and previously did)
     * fail with XMIND_ERR_INVAL because dimension fields are zero. We rely on
     * weights_load_file to perform the init with the GGUF-derived config. */
    xmind_model_t *m = xmind_get_global();
    memset(m, 0, sizeof(*m));

    if (xmind_weights_load_file(m, model_path) != XMIND_OK) {
        xmind_shutdown(m);
        return -3;
    }

    if (xmind_rope_precompute(m) != XMIND_OK) {
        return -5;
    }

    if (xmind_preflight_check(m) != XMIND_OK) {
        return -6;
    }

    if (xmind_session_create(&s_session, (uint32_t)max_seq_len) != XMIND_OK) {
        return -7;
    }
    s_max_seq_len = (uint32_t)max_seq_len;   /* remember the context bound for prompt truncation */

    /* D10: explicitly initialize the adapter runtime once the session exists.
     * Without this, the adapter runtime's static state (active pointer, apply
     * counter, contribution telemetry) was never reset to a known-clean baseline
     * on a fresh process — it only happened to be zero-initialized by the loader.
     * Calling init() here makes the "no adapter active" baseline explicit and
     * resets adapter telemetry, so D36 admission decisions start from a clean
     * ledger. No-op-safe: it only clears state, never binds an adapter. */
    xmind_adapter_runtime_init();

    xmind_session_set_sampler(s_session, s_temperature, s_top_p, s_seed);

    /* §8.3 weight materialization tracking: record the source_hash of the GGUF the engine just
     * materialized + the materialization timestamp, so the Python model_artifact
     * MaterializationRecord carries a real source_hash + materialized_at_ns (Workstream 4:
     * "connect weights_loader … to materialization tracking"). Reuse the digest already
     * computed for verify-before-materialize (no second pass over the file). */
    strncpy(s_weight_fingerprint, real_sha, sizeof(s_weight_fingerprint) - 1);
    s_weight_fingerprint[sizeof(s_weight_fingerprint) - 1] = '\0';
    {
        struct timespec ts;
        if (clock_gettime(CLOCK_REALTIME, &ts) == 0) {
            s_materialized_at_ns = (unsigned long long)ts.tv_sec * 1000000000ULL
                                 + (unsigned long long)ts.tv_nsec;
        }
    }

    s_initialized = 1;
    return 0;
}

int xmind_easy_set_sampler(float temperature, float top_p, unsigned long long seed) {
    s_temperature = temperature;
    s_top_p       = top_p;
    s_seed        = seed;
    if (s_session) {
        return xmind_session_set_sampler(s_session, temperature, top_p, seed);
    }
    return 0;
}

int xmind_easy_reset(void) {
    if (!s_session) return -1;
    return xmind_session_reset(s_session);
}

int xmind_easy_generate(const char *prompt, char *out_buf, int max_out,
                         float temperature, float top_p, int max_new_tokens) {
    if (!s_initialized || !s_session || !prompt || !out_buf || max_out <= 1)
        return -1;

    /* Apply per-call sampler overrides (don't persist across calls) */
    xmind_session_set_sampler(s_session, temperature, top_p, s_seed);

    /* Byte-level tokenizer (master spec Part II §25.6):
     *   token = byte + 3
     *   vocab = 259  (PAD=0, BOS=1, EOS=2, then 256 raw bytes at +3)
     *
     * xmind_generate expects uint32_t* prompt tokens, not a char* string.
     * We allocate stack/static buffers for the tokenized prompt and output. */
    static uint32_t s_prompt_tokens[2048];
    static uint32_t s_output_tokens[2048];

    uint32_t prompt_chars = (uint32_t)strlen(prompt);

    /* Graceful long-prompt handling (was a hard rc=-3 error): if the prompt does not fit
     * the static buffer OR the model context, keep the TAIL (most recent context) that fits
     * and truncate the head, leaving room for generation. For a continuation model the recent
     * context matters most, so tail-truncation degrades gracefully instead of failing. */
    uint32_t buf_cap = (uint32_t)(sizeof(s_prompt_tokens) / sizeof(s_prompt_tokens[0]));
    /* reserve room within ctx for at least some generation */
    uint32_t gen_reserve = (max_new_tokens > 0) ? (uint32_t)max_new_tokens : 32u;
    if (gen_reserve > 256u) gen_reserve = 256u;   /* cap the reserve so the prompt isn't starved */
    uint32_t ctx_cap = (s_max_seq_len > gen_reserve + 1u) ? (s_max_seq_len - gen_reserve) : s_max_seq_len;
    uint32_t max_prompt_toks = buf_cap - 1u;       /* leave one slot */
    if (ctx_cap > 0u && ctx_cap - 1u < max_prompt_toks) max_prompt_toks = ctx_cap - 1u;
    if (max_prompt_toks < 1u) max_prompt_toks = 1u;
    /* max_prompt_toks includes BOS, so chars budget = max_prompt_toks - 1 */
    uint32_t max_prompt_chars = max_prompt_toks - 1u;
    const char *p = prompt;
    if (prompt_chars > max_prompt_chars) {
        p += (prompt_chars - max_prompt_chars);    /* keep the tail */
        prompt_chars = max_prompt_chars;
    }

    /* BOS + per-byte +3 encoding */
    uint32_t prompt_tok_count = 0;
    s_prompt_tokens[prompt_tok_count++] = 1u;   /* BOS */
    for (uint32_t i = 0u; i < prompt_chars; i++) {
        s_prompt_tokens[prompt_tok_count++] =
            (uint32_t)(unsigned char)p[i] + 3u;
    }

    /* Cap requested generation against the static output buffer */
    uint32_t max_new = (max_new_tokens > 0)
                       ? (uint32_t)max_new_tokens
                       : (uint32_t)(max_out - 1);
    uint32_t out_cap = (uint32_t)(sizeof(s_output_tokens) / sizeof(s_output_tokens[0]));
    if (max_new > out_cap) max_new = out_cap;
    if (max_new > (uint32_t)(max_out - 1)) max_new = (uint32_t)(max_out - 1);

    uint32_t n_out = 0;
    xmind_status_t rc = xmind_generate(
        s_session,
        s_prompt_tokens,
        prompt_tok_count,
        s_output_tokens,
        max_new,
        &n_out
    );
    if (rc != XMIND_OK) return -2;

    /* Decode output tokens back to bytes: byte = token - 3 (skip PAD/BOS/EOS) */
    int out_pos = 0;
    for (uint32_t i = 0u; i < n_out && out_pos + 1 < max_out; i++) {
        uint32_t t = s_output_tokens[i];
        if (t >= 3u && t < 259u) {
            out_buf[out_pos++] = (char)(t - 3u);
        }
        /* PAD(0)/BOS(1)/EOS(2) are skipped from the rendered text */
    }
    out_buf[out_pos] = '\0';

    /* Restore default sampler */
    xmind_session_set_sampler(s_session, s_temperature, s_top_p, s_seed);

    return out_pos;
}

int xmind_easy_load_adapter(const char *adapter_path) {
    if (!s_initialized) return -1;
    if (!adapter_path || adapter_path[0] == '\0') return 1;  /* no-op signal */

    /* Unload any prior adapter first */
    if (s_adapter_loaded) {
        xmind_adapter_runtime_deactivate();   /* unbind before freeing the payload */
        xmind_lora_free(&s_adapter);
        s_adapter_loaded = 0;
    }

    int rc = xmind_lora_load_safetensors(adapter_path, &s_adapter);
    if (rc != 0) {
        printf("[xmind_easy] adapter load failed rc=%d path=%s\n", rc, adapter_path);
        return -2;
    }
    xmind_lora_dump(&s_adapter);
    /* §11.1: bind s_adapter into the transformer hot path. adapter_runtime.c applies
     * the delta after each matmul (no-op when inactive); activation is all it takes.
     * D36: activation now runs admission governance and can REFUSE (returns < 0).
     * On refusal we must not report the adapter as loaded/active — free the payload
     * and surface the failure so a refused adapter cannot silently look applied. */
    /* §9.2: tell the runtime which base this engine is — gov_admit refuses an adapter whose
     * declared base_sha256 mismatches s_weight_fingerprint (the real GGUF sha256). */
    xmind_adapter_runtime_set_expected_base(s_weight_fingerprint);
    if (xmind_adapter_runtime_activate(&s_adapter, "easy-adapter") != 0) {
        printf("[xmind_easy] adapter refused by governance path=%s\n", adapter_path);
        xmind_lora_free(&s_adapter);
        s_adapter_loaded = 0;
        return -4;
    }
    s_adapter_loaded = 1;
    /* §11.1: describe the adapter's IR (structural identity) + cache it by content key, so the
     * adapter materialization has a real IR descriptor and a re-load can hit the cache. Additive
     * to the live path (the adapter is already loaded + active); failures here never unload it. */
    if (xmind_adapter_ir_describe(&s_adapter, &s_adapter_ir) == 0) {
        xmind_adapter_ir_key(&s_adapter_ir, s_adapter_ir_key);
        xmind_adapter_cache_put(s_adapter_ir_key, &s_adapter);
    } else {
        s_adapter_ir_key[0] = '\0';
    }
    return 0;
}

int xmind_easy_adapter_ir(char *out, int max_out) {
    /* Adapter IR descriptor (§11.1) as JSON — the loaded adapter's structural identity, for the
     * Python adapter materialization record. Empty/<0 when no adapter is loaded. */
    if (!out || max_out <= 0) return -1;
    if (!s_adapter_loaded || s_adapter_ir_key[0] == '\0') { out[0] = '\0'; return -1; }
    int n = snprintf(out, (size_t)max_out,
        "{\"family\":\"%s\",\"target_count\":%u,\"total_rank\":%u,\"param_count\":%llu,"
        "\"ir_key\":\"%s\",\"cached\":%u}",
        s_adapter_ir.family, s_adapter_ir.target_count, s_adapter_ir.total_rank,
        (unsigned long long)s_adapter_ir.param_count, s_adapter_ir_key,
        xmind_adapter_cache_count());
    if (n < 0 || n >= max_out) return -2;
    return n;
}

int xmind_easy_adapter_loaded(void) { return s_adapter_loaded; }

void xmind_easy_shutdown(void) {
    if (s_adapter_loaded) {
        xmind_adapter_runtime_deactivate();   /* unbind before freeing the payload */
        xmind_lora_free(&s_adapter);
        s_adapter_loaded = 0;
    }
    if (s_session) {
        xmind_session_destroy(s_session);
        s_session = (xmind_session_t *)0;
    }
    if (s_initialized) {
        xmind_model_t *m = xmind_get_global();
        xmind_weights_unload(m);
        xmind_shutdown(m);
        s_initialized = 0;
    }
}
