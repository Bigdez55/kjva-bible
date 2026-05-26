/*
 * ai/xmind/loader/weights_loader_mmap.c — XMIND mmap-based weight loader
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Provides mmap-backed weight loading for XMIND with GGUF header probing.
 * Falls back to sequential PAL file I/O when mmap is unavailable.
 *
 * PAL file I/O types and pal_mmap/pal_munmap extensions are declared locally
 * following the convention established in ai/xmind/src/weights_loader.c.
 *
 * Build:
 *   clang -fsyntax-only -ffreestanding \
 *         -Ipal/include -Iai/xmind/include \
 *         ai/xmind/loader/weights_loader_mmap.c
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif

#include "../../../pal/include/pal.h"
#include "../include/xmind.h"

/* ═══════════════════════════════════════════════════════════════════════════
 * §1  PAL FILE I/O EXTENSION TYPES
 *
 * pal.h does not expose file I/O — XMIND modules declare these locally
 * following the convention in ai/xmind/src/weights_loader.c §1.
 * ═══════════════════════════════════════════════════════════════════════════ */

#ifndef PAL_FILE_IO_DEFINED
#define PAL_FILE_IO_DEFINED

/* EOF sentinel — returned when end of file is reached */
#define PAL_ERR_EOF     ((pal_status_t)0x7FFF0001u)

/* Opaque file handle — wraps a PAL handle with a byte-position cursor */
typedef struct { pal_handle_t _h; uint64_t _pos; } pal_file_t;

/* File metadata */
typedef struct {
    uint64_t size;       /* file size in bytes                  */
    uint64_t mtime_ns;   /* last-modified time (ns since epoch) */
} pal_file_stat_t;

/* Seek whence */
typedef enum {
    PAL_SEEK_SET = 0,
    PAL_SEEK_CUR = 1,
    PAL_SEEK_END = 2,
} pal_seek_whence_t;

/* Open mode flags (subset used by XMIND) */
#define PAL_FILE_READ   0x01u
#define PAL_FILE_WRITE  0x02u

#endif /* PAL_FILE_IO_DEFINED */

/* PAL file I/O function declarations — implemented in pal_linux.c / pal_aether.c */
pal_status_t pal_file_open(pal_file_t *out_fh, const char *path, uint32_t mode);
pal_status_t pal_file_read(pal_file_t *fh, void *buf, uint64_t len,
                             uint64_t *out_read);
pal_status_t pal_file_close(pal_file_t *fh);
pal_status_t pal_file_seek(pal_file_t *fh, int64_t offset,
                             pal_seek_whence_t whence);
pal_status_t pal_file_stat(const char *path, pal_file_stat_t *out_stat);

/* ═══════════════════════════════════════════════════════════════════════════
 * §2  PAL MMAP EXTENSIONS
 *
 * These are new PAL extensions not yet present in pal.h.  Declared here with
 * a #ifndef guard to prevent conflicts when pal.h is eventually extended.
 * ═══════════════════════════════════════════════════════════════════════════ */

#ifndef PAL_MMAP_DEFINED
#define PAL_MMAP_DEFINED

/* Protection flags */
#define PAL_MMAP_PROT_READ   0x01u
#define PAL_MMAP_PROT_WRITE  0x02u
#define PAL_MMAP_PROT_EXEC   0x04u

/* Mapping flags */
#define PAL_MMAP_SHARED      0x01u
#define PAL_MMAP_PRIVATE     0x02u

/* Failure sentinel — mirrors POSIX MAP_FAILED */
#define PAL_MMAP_FAILED      ((void *)((uintptr_t)-1))

/**
 * pal_mmap — map file content into virtual address space.
 *
 * @param fh       open file handle (from pal_file_open)
 * @param offset   byte offset within the file (page-aligned)
 * @param length   number of bytes to map
 * @param prot     protection flags (PAL_MMAP_PROT_*)
 * @param flags    mapping flags (PAL_MMAP_PRIVATE recommended for read-only)
 * @param out_mh   receives PAL mapping handle (needed for pal_mmap_unmap)
 * @param out_va   receives the mapped virtual address
 * @return         PAL_OK on success, negative error code on failure
 */
pal_status_t pal_mmap(pal_file_t *fh, uint64_t offset, uint64_t length,
                       uint32_t prot, uint32_t flags,
                       pal_handle_t *out_mh, void **out_va);

/**
 * pal_mmap_unmap — release a mapping created by pal_mmap.
 *
 * @param mh       mapping handle returned by pal_mmap via out_mh
 * @param va       virtual address returned by pal_mmap via out_va
 * @param length   same length as passed to pal_mmap
 * @return         PAL_OK on success, negative on error
 */
pal_status_t pal_mmap_unmap(pal_handle_t mh, void *va, uint64_t length);

#endif /* PAL_MMAP_DEFINED */

/* ═══════════════════════════════════════════════════════════════════════════
 * §3  MMAP CONTEXT
 * ═══════════════════════════════════════════════════════════════════════════ */

/* Magic value: ASCII "XMINDMAP" packed as two 32-bit words — avoids UINT64_C */
#define XMIND_MMAP_MAGIC_HI  0x584D494Eu   /* "XMIN" */
#define XMIND_MMAP_MAGIC_LO  0x444D4150u   /* "DMAP" */

/**
 * xmind_mmap_ctx_t — caller-owned context for a loaded weight file.
 *
 * Do not modify any field directly — treat as opaque after creation.
 */
typedef struct {
    uint32_t     magic_hi;    /* XMIND_MMAP_MAGIC_HI — sanity check           */
    uint32_t     magic_lo;    /* XMIND_MMAP_MAGIC_LO — sanity check           */
    pal_handle_t map_handle;  /* PAL mapping handle for pal_mmap_unmap         */
    void        *base;        /* base virtual address of the weight data        */
    uint64_t     size;        /* byte length of the mapped / loaded region      */
    int          is_mmap;     /* 1 = backed by pal_mmap; 0 = heap copy fallback */
    pal_file_t   file;        /* PAL file handle (open for the loader lifetime) */
    int          file_open;   /* 1 = file handle is valid and open              */
} xmind_mmap_ctx_t;

/* ═══════════════════════════════════════════════════════════════════════════
 * §4  GGUF HEADER CONSTANTS + CATALOG/INTERPRETER INCLUDES
 *
 * Full GGUF parsing uses gguf_reader.c (gguf_catalog_parse_mem).
 * Tensor-to-role mapping uses the artifact interpreter system.
 * ═══════════════════════════════════════════════════════════════════════════ */

#include "../include/xmind_gguf.h"
#include "../include/xmind_tensor_roles.h"
#include "../include/xmind_artifact_interp.h"

#define GGUF_HEADER_BYTES   24u            /* magic(4)+ver(4)+n_tensors(8)+n_kv(8) */

typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint32_t version;
    uint64_t n_tensors;
    uint64_t n_kv;
} xm_gguf_hdr_t;

/* ═══════════════════════════════════════════════════════════════════════════
 * §5  INTERNAL HELPERS
 * ═══════════════════════════════════════════════════════════════════════════ */

static int _ctx_valid(const xmind_mmap_ctx_t *ctx)
{
    return ctx != (void *)0
        && ctx->magic_hi == XMIND_MMAP_MAGIC_HI
        && ctx->magic_lo == XMIND_MMAP_MAGIC_LO;
}

/**
 * _probe_gguf — read and validate the 24-byte GGUF header.
 *
 * @param fh      open file handle positioned at byte 0
 * @param fsize   total file size (must be >= GGUF_HEADER_BYTES)
 * @param hdr     output — receives the decoded header
 * @return        XMIND_OK, XMIND_ERR_IO, or XMIND_ERR_CORRUPT
 */
static xmind_status_t _probe_gguf(pal_file_t *fh, uint64_t fsize,
                                   xm_gguf_hdr_t *hdr)
{
    if (fsize < GGUF_HEADER_BYTES) {
        return XMIND_ERR_CORRUPT;
    }

    /* Seek to beginning before reading */
    if (pal_file_seek(fh, 0, PAL_SEEK_SET) != PAL_OK) {
        return XMIND_ERR_IO;
    }

    uint8_t buf[GGUF_HEADER_BYTES];
    uint64_t n_read = 0;
    if (pal_file_read(fh, buf, GGUF_HEADER_BYTES, &n_read) != PAL_OK
            || n_read != GGUF_HEADER_BYTES) {
        return XMIND_ERR_IO;
    }

    /* Decode little-endian fields without memcpy (avoids alignment UB) */
    uint32_t magic =
        (uint32_t)buf[0]        |
        ((uint32_t)buf[1] << 8) |
        ((uint32_t)buf[2] << 16)|
        ((uint32_t)buf[3] << 24);

    if (magic != (uint32_t)GGUF_MAGIC) {
        return XMIND_ERR_CORRUPT;
    }

    uint32_t version =
        (uint32_t)buf[4]        |
        ((uint32_t)buf[5] << 8) |
        ((uint32_t)buf[6] << 16)|
        ((uint32_t)buf[7] << 24);

    if (version < GGUF_VER_MIN || version > GGUF_VER_MAX) {
        return XMIND_ERR_CORRUPT;
    }

    hdr->magic   = magic;
    hdr->version = version;
    /* n_tensors at offset 8, n_kv at offset 16 */
    __builtin_memcpy(&hdr->n_tensors, buf + 8,  sizeof(uint64_t));
    __builtin_memcpy(&hdr->n_kv,      buf + 16, sizeof(uint64_t));

    return XMIND_OK;
}

/* ── IEEE 754 fp16-to-fp32 conversion (local, matches weights_loader.c) ── */
static float _f16_to_f32(uint16_t h)
{
    uint32_t sign     = (uint32_t)(h >> 15u) & 1u;
    uint32_t exponent = (uint32_t)(h >> 10u) & 0x1Fu;
    uint32_t mantissa = (uint32_t)(h)         & 0x3FFu;
    uint32_t f32;
    if (exponent == 0u) {
        if (mantissa == 0u) {
            f32 = sign << 31u;
        } else {
            exponent = 1u;
            while (!(mantissa & 0x400u)) { mantissa <<= 1u; exponent--; }
            mantissa &= 0x3FFu;
            f32 = (sign << 31u) | ((exponent + 112u) << 23u) | (mantissa << 13u);
        }
    } else if (exponent == 31u) {
        f32 = (sign << 31u) | 0x7F800000u | (mantissa << 13u);
    } else {
        f32 = (sign << 31u) | ((exponent + 112u) << 23u) | (mantissa << 13u);
    }
    float result;
    __builtin_memcpy(&result, &f32, 4u);
    return result;
}

/* ── Local string helpers for _wire_weight_pointers ──────────────────── */
static void _wm_memset(void *dst, uint8_t val, uint64_t n)
{
    uint8_t *p = (uint8_t *)dst;
    uint64_t i;
    for (i = 0u; i < n; i++) { p[i] = val; }
}

/**
 * _wire_weight_pointers — parse GGUF tensor index and set model weight
 * pointers into the mmap'd buffer.
 *
 * Algorithm:
 *   1. Parse the GGUF catalog from the mmap'd buffer (gguf_catalog_parse_mem).
 *   2. Detect the appropriate artifact interpreter (Llama, etc.).
 *   3. Build model config from GGUF metadata via the interpreter.
 *   4. Map every catalog tensor to a canonical role + layer via the interpreter.
 *   5. For each mapped tensor:
 *      - F32 (norms, embeddings): zero-copy pointer into mmap'd data.
 *      - Q4_0 (layer weights): allocate XMIND 20-byte blocks via xm_heap_alloc,
 *        convert GGUF 18-byte blocks (fp16 scale -> fp32 scale + nibble copy).
 *   6. Initialize the model config from the parsed metadata.
 *
 * If any step fails (corrupt GGUF, unknown arch, etc.), all weight pointers
 * are left as NULL and an error is logged.  The caller can detect this via
 * preflight checks (e.g. m->token_emb == NULL).
 */
static void _wire_weight_pointers(xmind_model_t *m, void *base, uint64_t size)
{
    uint32_t l;

    /* ── Zero all pointers first (safe default) ──────────────────────── */
    for (l = 0u; l < XMIND_MAX_LAYERS; l++) {
        m->wq[l]      = (xmind_q4_block_t *)0;
        m->wk[l]      = (xmind_q4_block_t *)0;
        m->wv[l]      = (xmind_q4_block_t *)0;
        m->wo[l]      = (xmind_q4_block_t *)0;
        m->w1[l]      = (xmind_q4_block_t *)0;
        m->w2[l]      = (xmind_q4_block_t *)0;
        m->w3[l]      = (xmind_q4_block_t *)0;
        m->rms_att[l] = (float *)0;
        m->rms_ffn[l] = (float *)0;
    }
    m->token_emb = (float *)0;
    m->rms_final = (float *)0;
    m->rope_cos  = (float *)0;
    m->rope_sin  = (float *)0;

    /* ── Guard: base and size must be valid ───────────────────────────── */
    if (!base || size < GGUF_HEADER_BYTES) {
        pal_console_puts("[xmind_mmap] _wire: buffer too small or NULL\n");
        return;
    }

    /* ── Step 1: parse GGUF catalog from mmap'd buffer ───────────────── */
    /*
     * gguf_catalog_t is ~40 KiB.  In freestanding, we cannot use VLA or
     * alloca for this size.  Use a file-scope static to avoid stack overflow.
     * This is safe because _wire_weight_pointers is only called from
     * xmind_load_weights_mmap, which is single-threaded (Protocol 3:
     * OLLAMA_NUM_PARALLEL=1, and XMIND has no concurrency protection).
     */
    static gguf_catalog_t s_mmap_wire_catalog;
    gguf_status_t gst = gguf_catalog_parse_mem(
        (const uint8_t *)base, size, &s_mmap_wire_catalog);

    if (gst != GGUF_OK) {
        pal_console_puts("[xmind_mmap] _wire: GGUF catalog parse failed\n");
        return;
    }

    pal_console_printf("[xmind_mmap] _wire: catalog parsed — "
                       "%u tensors, %u KV entries, data_offset=%llu\n",
                       s_mmap_wire_catalog.tensors_stored,
                       s_mmap_wire_catalog.kv_stored,
                       (unsigned long long)s_mmap_wire_catalog.data_offset);

    /* ── Step 2: detect interpreter ──────────────────────────────────── */
    xmind_interps_init();   /* idempotent — safe to call multiple times */

    const xmind_artifact_interp_t *interp =
        xmind_interp_detect(&s_mmap_wire_catalog);
    if (!interp) {
        pal_console_puts("[xmind_mmap] _wire: no interpreter matched\n");
        return;
    }

    pal_console_printf("[xmind_mmap] _wire: interpreter=%s\n",
                       interp->family_name ? interp->family_name : "?");

    /* ── Step 3: build model config from metadata ────────────────────── */
    xmind_config_t cfg;
    _wm_memset(&cfg, 0u, sizeof(cfg));
    if (interp->build_config(&s_mmap_wire_catalog, &cfg) != 0) {
        pal_console_puts("[xmind_mmap] _wire: config build failed\n");
        return;
    }

    /* Apply config to the model (overwrite existing config) */
    m->cfg = cfg;

    pal_console_printf("[xmind_mmap] _wire: config layers=%u heads=%u "
                       "kv=%u hidden=%u ffn=%u vocab=%u\n",
                       cfg.n_layers, cfg.n_heads, cfg.n_kv_heads,
                       cfg.hidden_dim, cfg.ffn_dim, cfg.vocab_size);

    /* ── Step 4: map all catalog tensors to canonical roles ──────────── */
    static xmind_weight_plan_t s_mmap_wire_plan;
    _wm_memset(&s_mmap_wire_plan, 0u, sizeof(s_mmap_wire_plan));
    {
        uint32_t ti;
        for (ti = 0u; ti < s_mmap_wire_catalog.tensors_stored; ti++) {
            xmind_tensor_role_t role = XMIND_ROLE_UNKNOWN;
            uint32_t layer = 0u;
            interp->map_tensor(&s_mmap_wire_catalog, ti, &role, &layer);

            if (s_mmap_wire_plan.count < XMIND_WEIGHT_PLAN_MAX) {
                s_mmap_wire_plan.mappings[s_mmap_wire_plan.count].role = role;
                s_mmap_wire_plan.mappings[s_mmap_wire_plan.count].layer_index = layer;
                s_mmap_wire_plan.mappings[s_mmap_wire_plan.count].tensor_index = ti;
                s_mmap_wire_plan.count++;
            }
        }
    }

    pal_console_printf("[xmind_mmap] _wire: weight plan — %u mappings\n",
                       s_mmap_wire_plan.count);

    /* Optional: validate the plan (warn only, do not abort) */
    if (interp->validate) {
        int32_t vrc = interp->validate(
            &s_mmap_wire_catalog, &s_mmap_wire_plan, cfg.n_layers);
        if (vrc < 0) {
            pal_console_printf("[xmind_mmap] _wire: WARN validation: "
                               "%d issues\n", -vrc);
        }
        s_mmap_wire_plan.validated = 1u;
    }

    /* ── Step 5: wire pointers from plan ─────────────────────────────── */
    uint32_t wired_f32 = 0u;
    uint32_t wired_q4  = 0u;
    uint32_t skipped   = 0u;

    {
        uint32_t pi;
        for (pi = 0u; pi < s_mmap_wire_plan.count; pi++) {
            const xmind_role_mapping_t *rm = &s_mmap_wire_plan.mappings[pi];
            if (rm->role == XMIND_ROLE_UNKNOWN) {
                skipped++;
                continue;
            }
            if (rm->tensor_index >= s_mmap_wire_catalog.tensors_stored) {
                skipped++;
                continue;
            }

            const gguf_tensor_desc_t *td =
                &s_mmap_wire_catalog.tensors[rm->tensor_index];
            uint32_t layer = rm->layer_index;

            /* Compute pointer to this tensor's data within the mmap'd region.
             * data_offset = byte offset from file start to the data section.
             * td->offset  = byte offset from data section start to this tensor. */
            uint64_t abs_offset = s_mmap_wire_catalog.data_offset + td->offset;
            if (abs_offset + td->data_bytes > size) {
                pal_console_printf("[xmind_mmap] _wire: tensor '%s' "
                                   "overflows buffer (off=%llu, bytes=%llu, "
                                   "buf=%llu) — skipping\n",
                                   td->name,
                                   (unsigned long long)abs_offset,
                                   (unsigned long long)td->data_bytes,
                                   (unsigned long long)size);
                skipped++;
                continue;
            }

            const uint8_t *tensor_data = (const uint8_t *)base + abs_offset;

            /* ── F32 tensors: zero-copy pointer into mmap'd data ────── */
            if ((uint32_t)td->type == GGML_TYPE_F32) {
                switch (rm->role) {
                case XMIND_ROLE_TOKEN_EMB:
                    m->token_emb = (float *)(uintptr_t)tensor_data;
                    wired_f32++;
                    break;
                case XMIND_ROLE_NORM_FINAL:
                    m->rms_final = (float *)(uintptr_t)tensor_data;
                    wired_f32++;
                    break;
                case XMIND_ROLE_NORM_ATTN:
                    if (layer < XMIND_MAX_LAYERS) {
                        m->rms_att[layer] = (float *)(uintptr_t)tensor_data;
                        wired_f32++;
                    }
                    break;
                case XMIND_ROLE_NORM_FFN:
                    if (layer < XMIND_MAX_LAYERS) {
                        m->rms_ffn[layer] = (float *)(uintptr_t)tensor_data;
                        wired_f32++;
                    }
                    break;
                case XMIND_ROLE_OUTPUT:
                    /* Output head — in weight-tied models (Llama 3.2),
                     * this shares token_emb.  Skip if token_emb is already
                     * wired; otherwise wire as token_emb for untied models. */
                    if (!m->token_emb) {
                        m->token_emb = (float *)(uintptr_t)tensor_data;
                        wired_f32++;
                    } else {
                        skipped++;
                    }
                    break;
                default:
                    skipped++;
                    break;
                }
                continue;
            }

            /* ── Q4_0 tensors: allocate + convert fp16->fp32 scale ──── */
            if ((uint32_t)td->type == GGML_TYPE_Q4_0) {
                xmind_q4_block_t **slot = (xmind_q4_block_t **)0;

                if (layer < XMIND_MAX_LAYERS) {
                    switch (rm->role) {
                    case XMIND_ROLE_ATTN_Q:   slot = &m->wq[layer]; break;
                    case XMIND_ROLE_ATTN_K:   slot = &m->wk[layer]; break;
                    case XMIND_ROLE_ATTN_V:   slot = &m->wv[layer]; break;
                    case XMIND_ROLE_ATTN_O:   slot = &m->wo[layer]; break;
                    case XMIND_ROLE_FFN_GATE: slot = &m->w1[layer]; break;
                    case XMIND_ROLE_FFN_DOWN: slot = &m->w2[layer]; break;
                    case XMIND_ROLE_FFN_UP:   slot = &m->w3[layer]; break;
                    default: break;
                    }
                }

                if (!slot) {
                    skipped++;
                    continue;
                }

                /* GGUF Q4_0: 18 bytes/block (fp16 scale + 16 nibble bytes).
                 * XMIND Q4_0: 20 bytes/block (fp32 scale + 16 nibble bytes).
                 * Must allocate and convert. */
                uint64_t n_blocks = td->n_elements / XMIND_Q4_BLOCK;
                uint64_t alloc_bytes = n_blocks * (uint64_t)sizeof(xmind_q4_block_t);

                xmind_q4_block_t *dst = (xmind_q4_block_t *)xm_heap_alloc(alloc_bytes);
                if (!dst) {
                    pal_console_printf("[xmind_mmap] _wire: alloc failed "
                                       "for '%s' (%llu bytes)\n",
                                       td->name,
                                       (unsigned long long)alloc_bytes);
                    skipped++;
                    continue;
                }

                /* Convert: iterate GGUF 18-byte blocks, expand to 20-byte */
                const uint8_t *src = tensor_data;
                uint64_t bi;
                for (bi = 0u; bi < n_blocks; bi++) {
                    const uint8_t *gb = src + bi * 18u;
                    /* fp16 scale is first 2 bytes, little-endian */
                    uint16_t sh = (uint16_t)gb[0] | ((uint16_t)gb[1] << 8u);
                    dst[bi].scale = _f16_to_f32(sh);
                    /* Copy 16 nibble bytes */
                    uint32_t ni;
                    for (ni = 0u; ni < 16u; ni++) {
                        dst[bi].nibbles[ni] = gb[2u + ni];
                    }
                }

                *slot = dst;
                wired_q4++;
                continue;
            }

            /* ── F16 tensors: allocate fp32 buffer and convert ──────── */
            if ((uint32_t)td->type == GGML_TYPE_F16) {
                float **f32_slot = (float **)0;
                switch (rm->role) {
                case XMIND_ROLE_TOKEN_EMB:  f32_slot = &m->token_emb; break;
                case XMIND_ROLE_NORM_FINAL: f32_slot = &m->rms_final; break;
                case XMIND_ROLE_NORM_ATTN:
                    if (layer < XMIND_MAX_LAYERS) f32_slot = &m->rms_att[layer];
                    break;
                case XMIND_ROLE_NORM_FFN:
                    if (layer < XMIND_MAX_LAYERS) f32_slot = &m->rms_ffn[layer];
                    break;
                default: break;
                }

                if (!f32_slot) {
                    skipped++;
                    continue;
                }

                uint64_t alloc_bytes = td->n_elements * 4u;
                float *dst_f32 = (float *)xm_heap_alloc(alloc_bytes);
                if (!dst_f32) {
                    skipped++;
                    continue;
                }

                const uint8_t *src = tensor_data;
                uint64_t ei;
                for (ei = 0u; ei < td->n_elements; ei++) {
                    uint16_t h = (uint16_t)src[ei * 2u]
                               | ((uint16_t)src[ei * 2u + 1u] << 8u);
                    dst_f32[ei] = _f16_to_f32(h);
                }

                *f32_slot = dst_f32;
                wired_f32++;
                continue;
            }

            /* ── Unsupported tensor type — skip ─────────────────────── */
            skipped++;
        }
    }

    /* ── Allocate RoPE tables (computed at runtime, not from GGUF) ──── */
    if (cfg.ctx_len > 0u && cfg.head_dim >= 2u) {
        uint64_t rope_elems = (uint64_t)cfg.ctx_len * (cfg.head_dim / 2u);
        uint64_t rope_bytes = rope_elems * 4u;
        if (!m->rope_cos) {
            m->rope_cos = (float *)xm_heap_alloc(rope_bytes);
        }
        if (!m->rope_sin) {
            m->rope_sin = (float *)xm_heap_alloc(rope_bytes);
        }
    }

    pal_console_printf("[xmind_mmap] _wire: DONE — "
                       "f32=%u q4=%u skipped=%u\n",
                       wired_f32, wired_q4, skipped);
}

/* ═══════════════════════════════════════════════════════════════════════════
 * §6  PUBLIC API
 * ═══════════════════════════════════════════════════════════════════════════ */

/**
 * xmind_load_weights_mmap — load XMIND weights from a GGUF file.
 *
 * Algorithm:
 *   1. Stat the file to get its size.
 *   2. Open the file via pal_file_open.
 *   3. Probe the GGUF header (24 bytes).
 *   4. Attempt mmap via pal_mmap (PAL_MMAP_PROT_READ, PAL_MMAP_PRIVATE).
 *   5. On mmap failure, fall back: allocate heap buffer, read entire file.
 *   6. Wire weight pointers via _wire_weight_pointers (implemented at line 285).
 *
 * @param path   null-terminated path to .gguf file
 * @param ctx    caller-allocated context (output)
 * @param m      caller-allocated model whose weight pointers are wired in
 * @return       XMIND_OK on success, or XMIND_ERR_* on failure
 */
xmind_status_t xmind_load_weights_mmap(const char *path,
                                        xmind_mmap_ctx_t *ctx,
                                        xmind_model_t *m)
{
    if (!path || !ctx || !m) {
        return XMIND_ERR_INVAL;
    }

    /* Zero-init context so partial initialisation is detectable */
    __builtin_memset(ctx, 0, sizeof(*ctx));
    ctx->magic_hi    = XMIND_MMAP_MAGIC_HI;
    ctx->magic_lo    = XMIND_MMAP_MAGIC_LO;
    ctx->map_handle  = PAL_HANDLE_INVALID;
    ctx->base        = (void *)0;
    ctx->is_mmap     = 0;
    ctx->file_open   = 0;

    /* ── Step 1: stat the file ─────────────────────────────────────────── */
    pal_file_stat_t fst;
    if (pal_file_stat(path, &fst) != PAL_OK || fst.size == 0) {
        pal_console_puts("[xmind_mmap] pal_file_stat failed or empty file\n");
        return XMIND_ERR_IO;
    }
    ctx->size = fst.size;

    /* ── Step 2: open the file ─────────────────────────────────────────── */
    if (pal_file_open(&ctx->file, path, PAL_FILE_READ) != PAL_OK) {
        pal_console_puts("[xmind_mmap] pal_file_open failed\n");
        return XMIND_ERR_IO;
    }
    ctx->file_open = 1;

    /* ── Step 3: probe GGUF header ──────────────────────────────────────── */
    xm_gguf_hdr_t hdr;
    xmind_status_t probe_rc = _probe_gguf(&ctx->file, fst.size, &hdr);
    if (probe_rc != XMIND_OK) {
        pal_console_puts("[xmind_mmap] GGUF probe failed\n");
        pal_file_close(&ctx->file);
        ctx->file_open = 0;
        return probe_rc;
    }

    /* ── Step 4: attempt pal_mmap ───────────────────────────────────────── */
    void        *va = (void *)0;
    pal_handle_t mh = PAL_HANDLE_INVALID;
    pal_status_t mmap_rc = pal_mmap(
        &ctx->file,
        /*offset=*/0,
        fst.size,
        PAL_MMAP_PROT_READ,
        PAL_MMAP_PRIVATE,
        &mh,
        &va
    );

    if (mmap_rc == PAL_OK && va != (void *)0 && va != PAL_MMAP_FAILED) {
        /* mmap succeeded */
        ctx->base       = va;
        ctx->map_handle = mh;
        ctx->is_mmap    = 1;
        pal_console_puts("[xmind_mmap] weights mapped via pal_mmap\n");
    } else {
        /* ── Step 5: heap-copy fallback ─────────────────────────────────── */
        pal_console_puts("[xmind_mmap] pal_mmap unavailable — heap-copy fallback\n");

        void *buf = xm_heap_alloc(fst.size);
        if (!buf) {
            pal_console_puts("[xmind_mmap] xm_heap_alloc failed\n");
            pal_file_close(&ctx->file);
            ctx->file_open = 0;
            return XMIND_ERR_NOMEM;
        }

        /* Seek to byte 0 and read the whole file */
        if (pal_file_seek(&ctx->file, 0, PAL_SEEK_SET) != PAL_OK) {
            xm_heap_free(buf);
            pal_file_close(&ctx->file);
            ctx->file_open = 0;
            return XMIND_ERR_IO;
        }

        uint64_t n_read = 0;
        pal_status_t read_rc = pal_file_read(&ctx->file, buf, fst.size, &n_read);
        if (read_rc != PAL_OK || n_read != fst.size) {
            pal_console_puts("[xmind_mmap] heap-copy read incomplete\n");
            xm_heap_free(buf);
            pal_file_close(&ctx->file);
            ctx->file_open = 0;
            return XMIND_ERR_IO;
        }

        ctx->base    = buf;
        ctx->is_mmap = 0;
        /* map_handle stays PAL_HANDLE_INVALID for non-mmap path */
        pal_console_puts("[xmind_mmap] weights loaded via file I/O fallback\n");
    }

    /* ── Step 6: wire weight pointers ──────────────────────────────────── */
    _wire_weight_pointers(m, ctx->base, ctx->size);

    return XMIND_OK;
}

/**
 * xmind_unload_weights_mmap — release all resources from xmind_load_weights_mmap.
 *
 * Safe to call on a zero-initialised or previously unloaded context.
 * Idempotent.
 */
void xmind_unload_weights_mmap(xmind_mmap_ctx_t *ctx)
{
    if (!_ctx_valid(ctx)) {
        return;
    }

    /* Release weight buffer */
    if (ctx->base && ctx->base != PAL_MMAP_FAILED) {
        if (ctx->is_mmap && ctx->map_handle != PAL_HANDLE_INVALID) {
            pal_status_t rc = pal_mmap_unmap(ctx->map_handle, ctx->base, ctx->size);
            if (rc != PAL_OK) {
                pal_console_puts("[xmind_mmap] pal_mmap_unmap error\n");
            }
            ctx->map_handle = PAL_HANDLE_INVALID;
        } else if (!ctx->is_mmap) {
            xm_heap_free(ctx->base);
        }
        ctx->base    = (void *)0;
        ctx->is_mmap = 0;
    }

    /* Close the file handle */
    if (ctx->file_open) {
        pal_file_close(&ctx->file);
        ctx->file_open = 0;
    }

    /* Invalidate context */
    ctx->magic_hi = 0;
    ctx->magic_lo = 0;
    ctx->size     = 0;
}

/* ═══════════════════════════════════════════════════════════════════════════
 * §7  QUERY HELPERS
 * ═══════════════════════════════════════════════════════════════════════════ */

/**
 * xmind_mmap_tensor_count — read n_tensors from the mapped GGUF header.
 * Returns 0 if ctx is invalid or too small.
 */
uint64_t xmind_mmap_tensor_count(const xmind_mmap_ctx_t *ctx)
{
    if (!_ctx_valid(ctx) || !ctx->base || ctx->size < GGUF_HEADER_BYTES) {
        return 0;
    }
    uint64_t n = 0;
    /* n_tensors lives at byte offset 8 in the GGUF header */
    __builtin_memcpy(&n, (const uint8_t *)ctx->base + 8, sizeof(uint64_t));
    return n;
}

/**
 * xmind_mmap_is_valid — lightweight sanity check.
 * Returns 1 if context is properly initialised with a non-NULL base.
 */
int xmind_mmap_is_valid(const xmind_mmap_ctx_t *ctx)
{
    return _ctx_valid(ctx)
        && ctx->base  != (void *)0
        && ctx->base  != PAL_MMAP_FAILED
        && ctx->size  > 0;
}
