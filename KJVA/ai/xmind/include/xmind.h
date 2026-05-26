/*
 * xmind.h — XMIND Freestanding Inference Runtime
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * XMIND is the original Tokenless Models inference engine that replaces Ollama.
 * Version: sprint38 — SHA-384 transcript, BPE merge rules, weight validation.
 * It runs Llama-style transformer models quantized to Q4_0 format,
 * entirely within the Tokenless Models freestanding environment — no libc,
 * no Linux, no third-party dependencies.
 *
 * Architecture:
 *   xmind.c        — init / alloc / shutdown / global singleton
 *   tensor.c       — math primitives (matmul, softmax, rmsnorm, rope)
 *   quantize.c     — Q4_0 pack/unpack
 *   transformer.c  — forward pass (attention + FFN + residuals)
 *   sampler.c      — temperature / top-p sampling, xorshift64 PRNG
 *   tokenizer.c    — byte-level BPE tokenizer
 *   inference.c    — session management, generation pipeline (Sprint 15)
 */

#ifndef XMIND_H
#define XMIND_H

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "../../../pal/include/pal.h"

/* ═══════════════════════════════════════════════════════════════════
 * §1  VERSION & COMPILE-TIME CONSTANTS
 * ═══════════════════════════════════════════════════════════════════ */

#define XMIND_VERSION      "2.0.0-sprint41"
#define XMIND_MAX_LAYERS   32u
#define XMIND_MAX_HEADS    32u
#define XMIND_MAX_SEQ      8192u
#ifndef XMIND_VOCAB_SIZE
#define XMIND_VOCAB_SIZE   128256u
#endif
#define XMIND_Q4_BLOCK     32u   /* weights per quantization block */

/* ═══════════════════════════════════════════════════════════════════
 * §2  STATUS CODES
 * ═══════════════════════════════════════════════════════════════════ */

typedef int32_t xmind_status_t;

#define XMIND_OK           ((xmind_status_t)  0)
#define XMIND_ERR_INVAL    ((xmind_status_t) -1)
#define XMIND_ERR_NOMEM    ((xmind_status_t) -2)
#define XMIND_ERR_CORRUPT  ((xmind_status_t) -3)
#define XMIND_ERR_OVERFLOW ((xmind_status_t) -4)
#define XMIND_ERR_IO       ((xmind_status_t) -5)  /* file / storage I/O error */

/* ═══════════════════════════════════════════════════════════════════
 * §3  INTERNAL MEMORY / PANIC SHIMS
 *
 * pal.h does not expose pal_heap_alloc / pal_heap_free / pal_panic.
 * XMIND provides thin wrappers over pal_pages_alloc / pal_pages_free
 * plus a halt-loop panic macro so every .c can use a consistent API.
 * ═══════════════════════════════════════════════════════════════════ */

/*
 * XM_ASSERT — triggers a panic if condition is false.
 * Uses pal_console_puts to emit the message then spins forever.
 * In freestanding, there is no exit() — spinning is the correct
 * behavior until GENSD's watchdog resets the service.
 */
#define XM_ASSERT(cond) \
    do { \
        if (!(cond)) { \
            pal_console_puts("[XMIND ASSERT FAIL] " #cond "\n"); \
            for(;;) { __asm__ volatile("hlt"); } \
        } \
    } while (0)

/*
 * xm_heap_alloc / xm_heap_free — allocate from PAL page pool with
 * handle tracking.
 *
 * Sprint 10 (RA-XMIND-02 fix): implementations live in xmind.c where a
 * module-level slab tracks (va → ph, mh) mappings so xm_heap_free() can
 * locate and release the correct PAL handles.  Declared here as non-inline
 * extern so all translation units share the same slab state.
 *
 * Previous Sprint 6 behaviour (static inline no-op free) is replaced.
 */
void *xm_heap_alloc(uint64_t sz);
void  xm_heap_free(void *ptr);

/* ═══════════════════════════════════════════════════════════════════
 * §4  Q4_0 QUANTIZED BLOCK
 * ═══════════════════════════════════════════════════════════════════ */

/*
 * One Q4_0 block represents XMIND_Q4_BLOCK (32) weights.
 * Each weight is a 4-bit signed integer in the range [-8, 7],
 * stored as an unsigned nibble with an offset of 8 applied during
 * dequantization: weight = (nibble - 8) * scale.
 *
 * Memory layout:
 *   bytes 0-3:  scale (IEEE 754 float32, big-endian — same as host on x86)
 *   bytes 4-19: nibbles[16] — 32 nibbles packed as 16 bytes
 *               nibble[2i]   = byte[i] & 0x0F  (low  nibble → weight 2i  )
 *               nibble[2i+1] = byte[i] >> 4     (high nibble → weight 2i+1)
 *
 * Total: 4 + 16 = 20 bytes.
 */
typedef struct {
    float   scale;       /* block scale: max_abs / 7.0f                    */
    uint8_t nibbles[16]; /* 32 4-bit weights packed as 16 bytes            */
} xmind_q4_block_t;

_Static_assert(sizeof(xmind_q4_block_t) == 20u, "q4 block size must be 20 bytes");

/* ─── Q4_K_M quantization block ────────────────────────────────────────
 *
 * K-quant 4-bit format used by llama.cpp for improved quality:
 *   - Super-block of 256 weights (8 sub-blocks of 32 weights each)
 *   - 2 fp16 scales (d, dmin) stored as uint16_t bit pattern
 *   - Per-sub-block 6-bit scale + 6-bit min packed in 12 bytes
 *   - 128 bytes of 4-bit weight nibbles (256 weights / 2)
 *
 * Total: 2 + 2 + 12 + 128 = 144 bytes per super-block.
 *
 * Dequantization:
 *   For sub-block sb (0..7), weight index i (0..31):
 *     sc = scales_and_mins decoded for sub-block sb
 *     m  = mins decoded for sub-block sb
 *     w  = d * sc * nibble - dmin * m
 */
#define XMIND_Q4KM_SUPERBLOCK 256u  /* weights per Q4_K_M super-block */

typedef struct {
    uint16_t d;                 /* super-block scale (fp16 bits)         */
    uint16_t dmin;              /* super-block minimum (fp16 bits)       */
    uint8_t  scales_and_mins[12]; /* 6-bit scale + 6-bit min per sub-blk */
    uint8_t  qs[128];           /* 4-bit quantized values (256 nibbles)  */
} xmind_q4km_block_t;

_Static_assert(sizeof(xmind_q4km_block_t) == 144u,
               "q4km block size must be 144 bytes");

/* ═══════════════════════════════════════════════════════════════════
 * §5  MODEL CONFIGURATION
 * ═══════════════════════════════════════════════════════════════════ */

/* ── Special token IDs — decoupled from Llama 3.2 (B-PHASE1) ───────────
 * Default values match Llama 3.2.  Override via xmind_config_t fields at
 * runtime, or at compile-time via -DXMIND_DEFAULT_BOT_ID=N etc.
 * The XMIND_IS_EOG() macro uses the compile-time defaults for fast,
 * branchless checks in the generation hot path.  For full runtime
 * decoupling (e.g. running a non-Llama model), use xmind_is_eog_cfg()
 * which checks against config fields instead. */
#ifndef XMIND_DEFAULT_BOS_ID
#define XMIND_DEFAULT_BOS_ID     1u
#endif
#ifndef XMIND_DEFAULT_EOS_ID
#define XMIND_DEFAULT_EOS_ID     2u
#endif
#ifndef XMIND_DEFAULT_BOT_ID
#define XMIND_DEFAULT_BOT_ID     128000u  /* <|begin_of_text|> */
#endif
#ifndef XMIND_DEFAULT_EOT_ID
#define XMIND_DEFAULT_EOT_ID     128001u  /* <|end_of_text|>   */
#endif
#ifndef XMIND_DEFAULT_EOM_ID
#define XMIND_DEFAULT_EOM_ID     128008u  /* <|eom_id|>        */
#endif
#ifndef XMIND_DEFAULT_EOTURN_ID
#define XMIND_DEFAULT_EOTURN_ID  128009u  /* <|eot_id|>        */
#endif

typedef struct {
    uint32_t n_layers;    /* transformer depth                             */
    uint32_t n_heads;     /* number of query attention heads               */
    uint32_t n_kv_heads;  /* number of key/value heads (GQA support)       */
    uint32_t head_dim;    /* dimension per head (hidden_dim / n_heads)     */
    uint32_t hidden_dim;  /* model hidden dimension                        */
    uint32_t ffn_dim;     /* FFN intermediate dimension                    */
    uint32_t vocab_size;  /* vocabulary size                               */
    uint32_t ctx_len;     /* maximum context length in tokens              */
    float    rope_base;   /* RoPE base frequency (500000.0 for Llama 3.2) */
    /* ── Special token IDs (B-PHASE1: runtime-configurable) ─────────
     * Zero means "use compile-time default" (XMIND_DEFAULT_*_ID).
     * Set these before calling xmind_init() to run non-Llama models. */
    uint32_t bos_id;      /* begin-of-sequence token (default: 1)         */
    uint32_t eos_id;      /* end-of-sequence token (default: 2)           */
    uint32_t eog_ids[4];  /* end-of-generation tokens, 0 = unused slot    */
                          /* [0]=<|end_of_text|> [1]=<|eom_id|>           */
                          /* [2]=<|eot_id|>      [3]=reserved             */
} xmind_config_t;

/* ═══════════════════════════════════════════════════════════════════
 * §6  TENSOR (fp32, pointer into external buffer — no owned alloc)
 * ═══════════════════════════════════════════════════════════════════ */

typedef struct {
    float    *data;   /* pointer to row-major float32 data                 */
    uint32_t  n_rows; /* number of rows                                    */
    uint32_t  n_cols; /* number of columns                                 */
} xmind_tensor_t;

/* ═══════════════════════════════════════════════════════════════════
 * §7  KV CACHE
 * ═══════════════════════════════════════════════════════════════════ */

/*
 * Key and value caches for all layers.
 * k[l] points to a buffer of size: ctx_len × n_kv_heads × head_dim floats.
 * v[l] is the same shape.
 * n_cached tracks how many token positions have been filled so far.
 */
typedef struct {
    float   *k[XMIND_MAX_LAYERS]; /* key   cache per layer */
    float   *v[XMIND_MAX_LAYERS]; /* value cache per layer */
    uint32_t n_cached;            /* tokens processed so far */
} xmind_kv_cache_t;

/* ═══════════════════════════════════════════════════════════════════
 * §8  INFERENCE STATE  (scratch buffers — owned by xmind_alloc_state)
 * ═══════════════════════════════════════════════════════════════════ */

typedef struct {
    float   *logits; /* vocab_size floats — output distribution            */
    float   *x;      /* current hidden state (hidden_dim floats)           */
    float   *xb;     /* scratch buffer (hidden_dim floats)                 */
    float   *q;      /* query  (n_heads × head_dim floats)                 */
    float   *k;      /* key    (n_kv_heads × head_dim floats)              */
    float   *v;      /* value  (n_kv_heads × head_dim floats)              */
    float   *attn;   /* attention scores (n_heads × ctx_len floats)        */
    uint32_t pos;    /* current sequence position (token index)            */
    uint8_t  _pad[4];
} xmind_state_t;

/* ═══════════════════════════════════════════════════════════════════
 * §9  MODEL  (aggregates config, weights, KV cache, state)
 * ═══════════════════════════════════════════════════════════════════ */

/*
 * Weight pointers into a memory-mapped model file.
 * XMIND does not own the weight data — the caller maps the file
 * and assigns each pointer before calling xmind_forward().
 */
typedef struct {
    xmind_config_t   cfg;
    xmind_kv_cache_t kv;
    xmind_state_t    state;

    /* --- Q4_0 weight tables per layer --- */
    xmind_q4_block_t *wq[XMIND_MAX_LAYERS]; /* query projection      */
    xmind_q4_block_t *wk[XMIND_MAX_LAYERS]; /* key projection        */
    xmind_q4_block_t *wv[XMIND_MAX_LAYERS]; /* value projection      */
    xmind_q4_block_t *wo[XMIND_MAX_LAYERS]; /* output projection     */
    xmind_q4_block_t *w1[XMIND_MAX_LAYERS]; /* FFN gate (SwiGLU w1)  */
    xmind_q4_block_t *w2[XMIND_MAX_LAYERS]; /* FFN down proj (w2)    */
    xmind_q4_block_t *w3[XMIND_MAX_LAYERS]; /* FFN up   proj (w3)    */

    /* --- Non-quantized weights --- */
    float *token_emb;                        /* vocab_size × hidden_dim (fp32) */
    float *rms_att[XMIND_MAX_LAYERS];        /* RMSNorm weights for attention  */
    float *rms_ffn[XMIND_MAX_LAYERS];        /* RMSNorm weights for FFN        */
    float *rms_final;                        /* final RMSNorm weights          */
    float *rope_cos;                         /* ctx_len × head_dim/2 cosines   */
    float *rope_sin;                         /* ctx_len × head_dim/2 sines     */

    uint8_t initialized; /* non-zero after xmind_init() succeeds           */
    uint8_t _pad[7];
} xmind_model_t;

/* ═══════════════════════════════════════════════════════════════════
 * §10  SAMPLER
 * ═══════════════════════════════════════════════════════════════════ */

typedef struct {
    float    temperature; /* sampling temperature (0.0 = greedy)           */
    float    top_p;       /* nucleus sampling probability threshold         */
    uint64_t rng_state;   /* xorshift64 PRNG state (non-zero required)     */
} xmind_sampler_t;

/* ═══════════════════════════════════════════════════════════════════
 * §11  PUBLIC API
 * ═══════════════════════════════════════════════════════════════════ */

/*
 * xmind_init — validate config, zero-initialise model, store config.
 * Must be called before any other xmind_* function.
 * Returns XMIND_ERR_INVAL if cfg is NULL or any dimension is 0 or
 * exceeds XMIND_MAX_* constants.
 */
xmind_status_t xmind_init(xmind_model_t *m, const xmind_config_t *cfg);

/*
 * xmind_shutdown — release all state buffers allocated by xmind_alloc_state.
 * Weight pointers (wq, wk, … token_emb, rope_*) are owned by the caller
 * and are NOT freed here.
 */
void xmind_shutdown(xmind_model_t *m);

/*
 * xmind_alloc_state — allocate inference scratch buffers and KV cache.
 * Must be called after xmind_init() and after weight pointers are assigned.
 * Returns XMIND_ERR_NOMEM if any allocation fails (partial state is freed).
 */
xmind_status_t xmind_alloc_state(xmind_model_t *m);

/*
 * xmind_forward — run one full transformer forward pass.
 * @token  token ID to process (must be < cfg.vocab_size)
 * @pos    position in the sequence (must be < cfg.ctx_len)
 * After return, m->state.logits holds unnormalized log-probabilities.
 */
void xmind_forward(xmind_model_t *m, uint32_t token, uint32_t pos);

/*
 * xmind_sample — select the next token from m->state.logits using
 * the sampler's temperature and top-p settings.
 * Returns a token ID in [0, vocab_size).
 */
uint32_t xmind_sample(xmind_model_t *m, xmind_sampler_t *s);

/*
 * xmind_tokenize — encode a UTF-8 string into token IDs.
 * Prepends BOS (token 1).  Returns XMIND_ERR_OVERFLOW if the token
 * count would exceed max_tokens.
 * @out_len  receives the number of tokens written.
 */
xmind_status_t xmind_tokenize(const char *text, uint32_t *out_tokens,
                               uint32_t *out_len, uint32_t max_tokens);

/*
 * xmind_detokenize — decode a single token ID to a null-terminated string.
 * Writes at most bufsz-1 characters into buf and always null-terminates.
 */
void xmind_detokenize(uint32_t token, char *buf, uint32_t bufsz);

/*
 * xmind_sampler_init — initialise sampler with temperature, top-p, and seed.
 * If seed == 0, a default non-zero seed (0xDEADBEEFCAFEBABEull) is used.
 */
void xmind_sampler_init(xmind_sampler_t *s, float temperature,
                        float top_p, uint64_t seed);

/*
 * xmind_get_global — return pointer to the process-wide singleton model.
 * Declared here; defined in xmind.c.
 */
xmind_model_t *xmind_get_global(void);

/* ═══════════════════════════════════════════════════════════════════
 * §12  MATH PRIMITIVES (declared here; implemented in tensor.c)
 * ═══════════════════════════════════════════════════════════════════ */

void  xmind_rmsnorm(float *out, const float *x, const float *weight, uint32_t n);
void  xmind_matmul_q4(float *out, const float *x,
                      const xmind_q4_block_t *W, uint32_t rows, uint32_t cols);
void  xmind_softmax(float *x, uint32_t n);
float xmind_dot(const float *a, const float *b, uint32_t n);
void  xmind_silu(float *out, const float *gate, const float *up, uint32_t n);
void  xmind_rope(float *q, float *k,
                 const float *cos_table, const float *sin_table,
                 uint32_t pos, uint32_t head_dim,
                 uint32_t n_heads, uint32_t n_kv_heads);

/* ═══════════════════════════════════════════════════════════════════
 * §12b  SIMD DISPATCH  (runtime AVX2/scalar selection)
 *
 * xmind_simd_init() probes CPUID and sets function pointers for the
 * fastest available code path.  Must be called once before any forward
 * pass.  After init, xmind_matmul_q4() and xmind_dot() automatically
 * use AVX2 when available.
 *
 * The dispatch state is module-static in tensor.c and safe for the
 * single-threaded Sprint 15 inference pipeline.
 * ═══════════════════════════════════════════════════════════════════ */

void xmind_simd_init(void);

/* ═══════════════════════════════════════════════════════════════════
 * §13  QUANTIZE PRIMITIVES (declared here; implemented in quantize.c)
 * ═══════════════════════════════════════════════════════════════════ */

void xmind_dequantize_block(float *out, const xmind_q4_block_t *blk);
void xmind_quantize_block(xmind_q4_block_t *blk, const float *in);
void xmind_dequantize_row(float *out, const xmind_q4_block_t *blocks, uint32_t n_blocks);
void xmind_quantize_row(xmind_q4_block_t *blocks, const float *in, uint32_t n);
void xmind_q4_block_init(xmind_q4_block_t *blk);

/* Q4_K_M quantization / dequantization (implemented in quantize.c) */
void xmind_quantize_q4km_block(xmind_q4km_block_t *blk, const float *in);
void xmind_quantize_q4km_row(xmind_q4km_block_t *blocks, const float *in,
                               uint32_t n);
void xmind_dequantize_q4km_block(float *out, const xmind_q4km_block_t *blk);
void xmind_dequantize_q4km_row(float *out, const xmind_q4km_block_t *blocks,
                                uint32_t n_blocks);
void xmind_matmul_q4km(float *out, const float *x,
                        const xmind_q4km_block_t *W,
                        uint32_t rows, uint32_t cols);

/* ═══════════════════════════════════════════════════════════════════
 * §14  TOKENIZER CONSTANTS & VOCAB QUERY
 * ═══════════════════════════════════════════════════════════════════ */

/* ── Compile-time token ID aliases (use XMIND_DEFAULT_* as backing values)
 * These are kept for source compatibility; new code should prefer the
 * xmind_config_t fields or xmind_is_eog_cfg() for runtime portability. */
#define XMIND_TOK_PAD     0u
#define XMIND_TOK_BOS     XMIND_DEFAULT_BOS_ID
#define XMIND_TOK_EOS     XMIND_DEFAULT_EOS_ID
#define XMIND_TOK_BOT     XMIND_DEFAULT_BOT_ID    /* <|begin_of_text|>    */
#define XMIND_TOK_EOT     XMIND_DEFAULT_EOT_ID    /* <|end_of_text|>      */
#define XMIND_TOK_SHD     128006u                  /* <|start_header_id|> */
#define XMIND_TOK_EHD     128007u                  /* <|end_header_id|>   */
#define XMIND_TOK_EOM     XMIND_DEFAULT_EOM_ID    /* <|eom_id|>           */
#define XMIND_TOK_EOTURN  XMIND_DEFAULT_EOTURN_ID /* <|eot_id|>           */

/* XMIND_IS_EOG — compile-time EOG check using default Llama 3.2 token IDs.
 * For runtime-configurable EOG checking with a loaded config, use
 * xmind_is_eog_cfg(tok, cfg) which reads eog_ids[] from xmind_config_t. */
#define XMIND_IS_EOG(tok) \
    ((tok) == XMIND_TOK_EOS    || (tok) == XMIND_TOK_EOT || \
     (tok) == XMIND_TOK_EOM    || (tok) == XMIND_TOK_EOTURN)

/*
 * xmind_is_eog_cfg — runtime EOG check against loaded model config.
 * Uses cfg->eog_ids[] if any slot is non-zero, otherwise falls back to
 * cfg->eos_id (or XMIND_TOK_EOS if that is also zero).
 * This is the correct check to use when running non-Llama models where
 * EOG token IDs differ from the Llama 3.2 defaults.
 */
static inline int xmind_is_eog_cfg(uint32_t tok, const xmind_config_t *cfg) {
    uint32_t eos = cfg->eos_id ? cfg->eos_id : XMIND_TOK_EOS;
    if (tok == eos) return 1;
    /* Check each runtime EOG slot */
    for (uint32_t i = 0u; i < 4u; i++) {
        if (cfg->eog_ids[i] && tok == cfg->eog_ids[i]) return 1;
    }
    return 0;
}

uint32_t xmind_vocab_size(void);

/*
 * xmind_tokenizer_load — load BPE merge rules + vocab from XSTORE.
 * @xstore_ctx  opaque pointer to an xstore_ctx_t (void* to avoid
 *              requiring xstore.h — compiled with XMIND_HAS_XSTORE only)
 * Returns XMIND_OK on success; XMIND_ERR_INVAL if XSTORE unavailable.
 * Falls back to byte-level mode on failure.
 */
xmind_status_t xmind_tokenizer_load(void *xstore_ctx,
                                     const char *rules_key,
                                     const char *vocab_key);

/*
 * xmind_tokenizer_reset — unload BPE data, revert to byte-level mode.
 * Idempotent; safe to call multiple times.
 */
void xmind_tokenizer_reset(void);

/*
 * xmind_tokenizer_load_direct — load BPE vocab directly from a GGUF
 * vocabulary array captured by weights_loader.c §8b.
 * @vocab_raw  pointer to an array of { uint32_t id; float score;
 *             char str[60]; } entries (compatible with wl_tok_entry_t).
 * @n_vocab    number of entries in vocab_raw.
 * Called automatically by xmind_weights_load_file() when
 * tokenizer.ggml.tokens is present in the GGUF metadata.
 * Returns XMIND_OK on success.
 */
xmind_status_t xmind_tokenizer_load_direct(const void *vocab_raw,
                                             uint32_t n_vocab);

/* Dump config to debug console (defined in xmind.c) */
void xmind_dump_config(const xmind_model_t *m);

/* ═══════════════════════════════════════════════════════════════════
 * §14c  PRE-TOKENIZER API  (implemented in pretokenizer.c)
 *
 * Splits text into spans before BPE processing using the GPT-4
 * regex pattern.  Each span is BPE-tokenized independently.
 * ═══════════════════════════════════════════════════════════════════ */

/* Span describing a contiguous byte range in the input text */
typedef struct {
    uint32_t start;   /* byte offset into input text */
    uint32_t len;     /* byte length of this span    */
} xmind_span_t;

/*
 * xmind_pretokenize — split text into spans for BPE processing.
 * @text       Input UTF-8 text (null-terminated)
 * @out_spans  Output array of spans (caller-provided)
 * @max_spans  Maximum number of spans to emit
 * @out_count  Receives the number of spans emitted
 * Returns XMIND_OK on success; XMIND_ERR_OVERFLOW if max_spans exhausted.
 */
xmind_status_t xmind_pretokenize(const char *text,
                                   xmind_span_t *out_spans,
                                   uint32_t max_spans,
                                   uint32_t *out_count);

/* Copy span text into a null-terminated buffer */
uint32_t xmind_span_copy(const char *text, const xmind_span_t *span,
                           char *buf, uint32_t bufsz);

/* ═══════════════════════════════════════════════════════════════════
 * §14b  WEIGHTS LOADER API  (implemented in weights_loader.c)
 *
 * xmind_weights_load_file — Load model weights from a GGUF file path.
 * Opens the file via PAL file I/O, verifies GGUF magic, scans metadata,
 * allocates weight pages via wl_alloc_pages, and calls xmind_init() +
 * xmind_alloc_state().  On success all weight pointers in m are valid.
 * Returns XMIND_ERR_INVAL if path is NULL or file not found;
 * XMIND_ERR_IO on read failure; XMIND_ERR_NOMEM if weight alloc fails.
 *
 * xmind_weights_load — Convenience wrapper; calls xmind_weights_load_file.
 *
 * xmind_weights_unload — Release all weight tensor PAL pages and zero
 * weight pointers.  Calls xmind_shutdown() to free inference state buffers
 * (via xm_heap_free slab) and wl_free_all_pages() to release weight pages
 * (via wl slab, pal_unmap + pal_pages_free per entry).  After return the
 * model struct is fully zero-initialised and no memory is leaked.
 * Safe to call multiple times (idempotent on NULL m).
 * ═══════════════════════════════════════════════════════════════════ */

xmind_status_t xmind_weights_load_file(xmind_model_t *m,
                                        const char *gguf_path);

xmind_status_t xmind_weights_load(xmind_model_t *m,
                                   const char *gguf_path);

void xmind_weights_unload(xmind_model_t *m);

/*
 * xmind_weights_map_phys — zero-copy weight loading from physical memory.
 * Maps model weights from a GGUF file already resident in physical memory
 * (e.g., loaded by bootloader or present in initrd) via the HHDM.
 *
 * F32 tensors (embeddings, norms) are zero-copy — weight pointers aim
 * directly into the HHDM-mapped GGUF data.  Q4_0 tensors require a
 * one-time fp16 to fp32 scale conversion into pre-allocated buffers.
 *
 * @m          Model struct to populate (must not be initialized)
 * @phys_base  Physical address of the GGUF file (must be page-aligned)
 * @file_size  Size of the GGUF file in bytes
 *
 * Returns XMIND_OK on success; XMIND_ERR_INVAL if alignment is wrong;
 * XMIND_ERR_CORRUPT if GGUF magic/version fails; XMIND_ERR_NOMEM if
 * Q4_0 buffer allocation fails.
 */
xmind_status_t xmind_weights_map_phys(xmind_model_t *m,
                                        uint64_t phys_base,
                                        uint64_t file_size);

/* ═══════════════════════════════════════════════════════════════════
 * §15  INFERENCE SESSION API  (Sprint 15 — implemented in inference.c)
 *
 * High-level generation pipeline that bridges:
 *   tokenizer -> forward pass -> sampler -> output token
 *
 * Usage:
 *   1. Load model (xmind_weights_load or manual weight assignment)
 *   2. xmind_rope_precompute(model)     -- populate RoPE tables
 *   3. xmind_preflight_check(model)     -- verify all pointers valid
 *   4. xmind_session_create(&session, max_tokens)
 *   5. xmind_generate(session, prompt, len, output, max, &n)
 *   6. xmind_session_destroy(session)
 * ═══════════════════════════════════════════════════════════════════ */

/* Opaque session handle */
typedef struct xmind_session xmind_session_t;

/*
 * xmind_session_create — allocate a new inference session.
 * Performs preflight check on the global model.
 * @out         receives the session pointer on success.
 * @max_tokens  maximum context length for this session (<= cfg.ctx_len).
 */
xmind_status_t xmind_session_create(xmind_session_t **out,
                                     uint32_t max_tokens);

/*
 * xmind_session_destroy — free session resources.
 * Does not affect model state or KV cache.
 */
xmind_status_t xmind_session_destroy(xmind_session_t *s);

/*
 * xmind_session_set_sampler — configure sampler parameters.
 * @temperature  0.0 = greedy, 0.7 = balanced, 1.0+ = creative
 * @top_p        nucleus sampling threshold (0.0-1.0, typically 0.9)
 * @seed         PRNG seed (0 = use default seed)
 */
xmind_status_t xmind_session_set_sampler(xmind_session_t *s,
                                          float temperature,
                                          float top_p,
                                          uint64_t seed);

/*
 * xmind_session_reset — reset position to 0 for a new conversation.
 * Logically invalidates KV cache (will be overwritten on next forward).
 */
xmind_status_t xmind_session_reset(xmind_session_t *s);

/*
 * xmind_infer_step — run one forward pass + sample.
 * @input_token   token to feed into the transformer
 * @output_token  receives the sampled next-token
 * Advances internal position counter by 1.
 * Returns XMIND_ERR_OVERFLOW if context is full.
 */
xmind_status_t xmind_infer_step(xmind_session_t *s,
                                 uint32_t input_token,
                                 uint32_t *output_token);

/*
 * xmind_generate — full prompt-to-completion generation.
 * Phase 1: ingests prompt tokens into KV cache (prefill).
 * Phase 2: autoregressively generates up to max_new_tokens.
 * Stops early on EOS token or context overflow.
 *
 * @prompt         array of input token IDs (must include BOS if desired)
 * @prompt_len     number of tokens in prompt (must be >= 1)
 * @output         output buffer for generated token IDs
 * @max_new_tokens maximum tokens to generate
 * @n_generated    receives actual number of tokens generated
 */
xmind_status_t xmind_generate(xmind_session_t *s,
                               const uint32_t *prompt,
                               uint32_t prompt_len,
                               uint32_t *output,
                               uint32_t max_new_tokens,
                               uint32_t *n_generated);

/* Session state queries (for UX progress display) */
uint32_t xmind_session_pos(const xmind_session_t *s);
uint32_t xmind_session_remaining(const xmind_session_t *s);

/*
 * xmind_rope_precompute — populate RoPE cos/sin tables.
 * Must be called after xmind_init() + xmind_alloc_state() and before
 * any forward pass.  Computes standard LLaMA RoPE with base=10000.
 * This is a P0 prerequisite: zero-filled RoPE tables destroy position
 * encoding and make attention output meaningless.
 * Default base is 500000.0 (Llama 3.2); overridden by cfg.rope_base if > 0.
 */
xmind_status_t xmind_rope_precompute(xmind_model_t *m);

/*
 * xmind_preflight_check — validate model is ready for inference.
 * Checks: initialized flag, state buffers, weight pointers (layer 0),
 * KV cache, RoPE tables, RMSNorm weights.
 * Returns XMIND_OK if all checks pass; XMIND_ERR_INVAL otherwise.
 */
xmind_status_t xmind_preflight_check(xmind_model_t *m);

#endif /* XMIND_H */
