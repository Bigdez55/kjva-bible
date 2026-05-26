/*
 * weights_loader.c — XMIND Weight Loading Orchestrator
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Sprint 49 refactor: This file is now a thin orchestrator that
 * delegates GGUF parsing to gguf_reader.c (family-neutral catalog)
 * and model-specific interpretation to artifact interpreters
 * (e.g. interp_llama.c).
 *
 * Orchestration flow:
 *   1. Map / open the file
 *   2. gguf_catalog_parse()          — neutral GGUF catalog
 *   3. xmind_interp_detect()         — find the right interpreter
 *   4. interp->build_config()        — xmind_config_t from metadata
 *   5. interp->map_tensor()          — build weight plan (roles)
 *   6. interp->validate()            — completeness check
 *   7. Allocate from ACTUAL catalog tensor metadata
 *   8. Load tensor data into model
 *
 * Public API (signature-preserved):
 *   xmind_weights_load_file()
 *   xmind_weights_load()
 *   xmind_weights_unload()
 *   xmind_weights_map_phys()
 *
 * S1   PAL file I/O extension (guarded)
 * S2   String / byte helpers
 * S3   Weight memory allocator (PAL pages + slab + fallback)
 * S4   F16-to-F32 conversion
 * S5   Tensor data loader (file I/O path)
 * S6   Tensor data loader (mmap path)
 * S7   Tokenizer load bridge
 * S8   Public API: xmind_weights_load_file
 * S9   Public API: xmind_weights_map_phys
 * S10  Public API: xmind_weights_unload / xmind_weights_load
 * S11  XBLOB-backed loader (conditional)
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"
#include "../include/xmind_gguf.h"
#include "../include/xmind_tensor_roles.h"
#include "../include/xmind_artifact_interp.h"

/* ===================================================================
 * S1  PAL FILE I/O EXTENSION (guarded against duplicate typedef)
 *
 * Already declared in xmind_gguf.h via PAL_FILE_IO_DEFINED guard.
 * No redeclaration needed.
 * =================================================================== */

/* ===================================================================
 * S2  STRING / BYTE HELPERS
 * =================================================================== */

static void wl_memset(void *dst, uint8_t val, uint32_t n) {
    uint8_t *p = (uint8_t *)dst;
    uint32_t i;
    for (i = 0u; i < n; i++) { p[i] = val; }
}

/* ===================================================================
 * S3  WEIGHT MEMORY ALLOCATOR
 *
 * PAL pages slab + static fallback pool.  Unchanged from Sprint 42.
 * =================================================================== */

#define WL_SLAB_SLOTS 512U

static struct {
    pal_handle_t ph;
    pal_handle_t mh;
} s_wl_slab[WL_SLAB_SLOTS];

static uint32_t s_wl_slab_n = 0u;

/* Static fallback pool — single 4 KiB page reserved in BSS */
#define WL_FALLBACK_SLOTS  4U
#define WL_FALLBACK_SIZE   PAL_PAGE_SIZE_4K

static uint8_t  s_wl_fallback_pool[WL_FALLBACK_SLOTS][WL_FALLBACK_SIZE]
    __attribute__((aligned(4096)));
static uint8_t  s_wl_fallback_used[WL_FALLBACK_SLOTS];
static uint32_t s_wl_fallback_init = 0u;

static void wl_fallback_pool_init(void) {
    uint32_t i;
    for (i = 0u; i < WL_FALLBACK_SLOTS; i++) {
        s_wl_fallback_used[i] = 0u;
    }
    s_wl_fallback_init = 1u;
}

static void *wl_fallback_alloc(uint64_t bytes) {
    uint32_t i;
    if (bytes > WL_FALLBACK_SIZE) { return (void *)0; }
    if (!s_wl_fallback_init) { wl_fallback_pool_init(); }
    for (i = 0u; i < WL_FALLBACK_SLOTS; i++) {
        if (!s_wl_fallback_used[i]) {
            s_wl_fallback_used[i] = 1u;
            uint8_t *p = s_wl_fallback_pool[i];
            uint64_t j;
            for (j = 0u; j < WL_FALLBACK_SIZE; j++) { p[j] = 0u; }
            pal_console_puts("[XMIND-WL] WARN: PAL alloc failed — "
                             "using fallback pool slot\n");
            return (void *)p;
        }
    }
    return (void *)0;
}

static void wl_free_all_pages(void) {
    uint32_t i;
    for (i = 0u; i < s_wl_slab_n; i++) {
        if (s_wl_slab[i].mh != PAL_HANDLE_INVALID) {
            (void)pal_unmap(s_wl_slab[i].mh);
        }
        (void)pal_pages_free(s_wl_slab[i].ph);
    }
    s_wl_slab_n = 0u;
    if (s_wl_fallback_init) {
        for (i = 0u; i < WL_FALLBACK_SLOTS; i++) {
            s_wl_fallback_used[i] = 0u;
        }
    }
}

static void *wl_alloc_pages(uint64_t bytes) {
    if (bytes == 0u) { return (void *)0; }
    uint64_t n_pages = (bytes + PAL_PAGE_SIZE_4K - 1u) / PAL_PAGE_SIZE_4K;
    pal_handle_t ph = PAL_HANDLE_INVALID;
    pal_handle_t mh = PAL_HANDLE_INVALID;
    uintptr_t    va = 0u;

    if (pal_pages_alloc(n_pages, PAL_PAGE_SIZE_4K,
                        (uint32_t)PAL_MEM_ZEROED, PAL_NUMA_ANY,
                        &ph) != PAL_OK) {
        return wl_fallback_alloc(bytes);
    }
    if (pal_map_pages(ph, 0u, 0u, n_pages,
                      (uint32_t)(PAL_MAP_READ | PAL_MAP_WRITE),
                      &mh, &va) != PAL_OK) {
        pal_pages_free(ph);
        return wl_fallback_alloc(bytes);
    }
    if (s_wl_slab_n < WL_SLAB_SLOTS) {
        s_wl_slab[s_wl_slab_n].ph = ph;
        s_wl_slab[s_wl_slab_n].mh = mh;
        s_wl_slab_n++;
    } else {
        pal_console_puts("[XMIND-WL] WARN: wl slab full — handle untracked\n");
    }
    return (void *)va;
}

/* ===================================================================
 * S4  IEEE 754 FLOAT16 TO FLOAT32 CONVERSION
 * =================================================================== */

static float wl_f16_to_f32(uint16_t h) {
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

/* ===================================================================
 * S5  TENSOR DATA LOADER (file I/O path)
 *
 * Reads tensor data from the GGUF file (positioned at data section)
 * into the pre-allocated xmind_model_t weight buffers, guided by
 * the weight plan.
 * =================================================================== */

#define WL_IO_BUF_SIZE  4096u
static uint8_t s_io_buf[WL_IO_BUF_SIZE];

/* Read raw bytes from file into a buffer via streaming chunks */
static void wl_stream_read(pal_file_t *fh, uint8_t *dst, uint64_t bytes) {
    uint64_t rb = 0u;
    while (rb < bytes) {
        uint64_t chunk = (bytes - rb) < WL_IO_BUF_SIZE ? (bytes - rb) : WL_IO_BUF_SIZE;
        uint64_t nr = 0u;
        if (pal_file_read(fh, s_io_buf, chunk, &nr) != PAL_OK || nr == 0u) break;
        uint64_t ci;
        for (ci = 0u; ci < nr; ci++) { dst[rb + ci] = s_io_buf[ci]; }
        rb += nr;
    }
}

/* Read Q4_0 tensor data: convert GGUF 18-byte blocks to XMIND 20-byte blocks */
static void wl_stream_q4_0(pal_file_t *fh, xmind_q4_block_t *dst,
                              uint64_t n_blocks) {
    uint64_t bi;
    for (bi = 0u; bi < n_blocks; bi++) {
        uint8_t gb[18];
        uint64_t nr = 0u;
        if (pal_file_read(fh, gb, 18u, &nr) != PAL_OK || nr < 18u) break;
        uint16_t sh = (uint16_t)gb[0] | ((uint16_t)gb[1] << 8u);
        dst[bi].scale = wl_f16_to_f32(sh);
        uint32_t ni;
        for (ni = 0u; ni < 16u; ni++) { dst[bi].nibbles[ni] = gb[2u + ni]; }
    }
}

/* Skip bytes by reading and discarding */
static void wl_skip_bytes(pal_file_t *fh, uint64_t bytes) {
    while (bytes > 0u) {
        uint64_t chunk = bytes < WL_IO_BUF_SIZE ? bytes : WL_IO_BUF_SIZE;
        uint64_t nr = 0u;
        pal_file_read(fh, s_io_buf, chunk, &nr);
        if (nr == 0u) break;
        bytes -= nr;
    }
}

/*
 * wl_load_tensors_from_plan — Load tensor data guided by weight plan.
 *
 * The file must be positioned at the tensor data section start
 * (catalog->data_offset from file start).  Tensors in the catalog
 * are in ascending offset order.
 */
static xmind_status_t wl_load_tensors_from_plan(
    pal_file_t *fh,
    const gguf_catalog_t *catalog,
    const xmind_weight_plan_t *plan,
    xmind_model_t *m) {

    /* Seek to data section */
    if (pal_file_seek(fh, (int64_t)catalog->data_offset, PAL_SEEK_SET) != PAL_OK)
        return XMIND_ERR_IO;

    uint64_t data_pos = 0u;
    uint32_t ti;

    for (ti = 0u; ti < catalog->tensors_stored; ti++) {
        const gguf_tensor_desc_t *td = &catalog->tensors[ti];

        /* Skip to this tensor's offset if needed */
        if (td->offset > data_pos) {
            uint64_t gap = td->offset - data_pos;
            wl_skip_bytes(fh, gap);
            data_pos = td->offset;
        }

        /* Find this tensor in the plan */
        const xmind_role_mapping_t *rm = (const xmind_role_mapping_t *)0;
        uint32_t pi;
        for (pi = 0u; pi < plan->count; pi++) {
            if (plan->mappings[pi].tensor_index == ti) {
                rm = &plan->mappings[pi];
                break;
            }
        }

        if (!rm || rm->role == XMIND_ROLE_UNKNOWN) {
            /* Unplanned tensor — skip its data */
            wl_skip_bytes(fh, td->data_bytes);
            data_pos += td->data_bytes;
            continue;
        }

        uint32_t layer = rm->layer_index;

        /* Dispatch by role + type */
        switch (rm->role) {
        case XMIND_ROLE_TOKEN_EMB:
            if (m->token_emb && (uint32_t)td->type == GGML_TYPE_F32) {
                wl_stream_read(fh, (uint8_t *)m->token_emb, td->n_elements * 4u);
            } else {
                wl_skip_bytes(fh, td->data_bytes);
            }
            break;

        case XMIND_ROLE_NORM_FINAL:
            if (m->rms_final && (uint32_t)td->type == GGML_TYPE_F32) {
                wl_stream_read(fh, (uint8_t *)m->rms_final, td->n_elements * 4u);
            } else {
                wl_skip_bytes(fh, td->data_bytes);
            }
            break;

        case XMIND_ROLE_OUTPUT:
            /* Output head weight — may share with token_emb in some models.
             * XMIND currently uses token_emb as output head; skip if separate. */
            wl_skip_bytes(fh, td->data_bytes);
            break;

        case XMIND_ROLE_NORM_ATTN:
            if (layer < XMIND_MAX_LAYERS && m->rms_att[layer] &&
                (uint32_t)td->type == GGML_TYPE_F32) {
                wl_stream_read(fh, (uint8_t *)m->rms_att[layer], td->n_elements * 4u);
            } else {
                wl_skip_bytes(fh, td->data_bytes);
            }
            break;

        case XMIND_ROLE_NORM_FFN:
            if (layer < XMIND_MAX_LAYERS && m->rms_ffn[layer] &&
                (uint32_t)td->type == GGML_TYPE_F32) {
                wl_stream_read(fh, (uint8_t *)m->rms_ffn[layer], td->n_elements * 4u);
            } else {
                wl_skip_bytes(fh, td->data_bytes);
            }
            break;

        case XMIND_ROLE_ATTN_Q:
        case XMIND_ROLE_ATTN_K:
        case XMIND_ROLE_ATTN_V:
        case XMIND_ROLE_ATTN_O:
        case XMIND_ROLE_FFN_GATE:
        case XMIND_ROLE_FFN_DOWN:
        case XMIND_ROLE_FFN_UP: {
            /* Q4_0 per-layer weight tensors */
            xmind_q4_block_t **slot = (xmind_q4_block_t **)0;
            if (layer < XMIND_MAX_LAYERS) {
                switch (rm->role) {
                case XMIND_ROLE_ATTN_Q:    slot = &m->wq[layer]; break;
                case XMIND_ROLE_ATTN_K:    slot = &m->wk[layer]; break;
                case XMIND_ROLE_ATTN_V:    slot = &m->wv[layer]; break;
                case XMIND_ROLE_ATTN_O:    slot = &m->wo[layer]; break;
                case XMIND_ROLE_FFN_GATE:  slot = &m->w1[layer]; break;
                case XMIND_ROLE_FFN_DOWN:  slot = &m->w2[layer]; break;
                case XMIND_ROLE_FFN_UP:    slot = &m->w3[layer]; break;
                default: break;
                }
            }
            if (slot && *slot && (uint32_t)td->type == GGML_TYPE_Q4_0) {
                uint64_t n_blocks = td->n_elements / 32u;
                wl_stream_q4_0(fh, *slot, n_blocks);
            } else {
                wl_skip_bytes(fh, td->data_bytes);
            }
            break;
        }

        default:
            wl_skip_bytes(fh, td->data_bytes);
            break;
        }

        data_pos += td->data_bytes;
    }

    pal_console_printf("[XMIND-WL] tensor load complete: %u tensors\n",
                       catalog->tensors_stored);
    return XMIND_OK;
}

/* ===================================================================
 * S6  TENSOR DATA LOADER (mmap path)
 *
 * Assigns weight pointers from an in-memory GGUF buffer.
 * F32 tensors: zero-copy (pointer into mapped data).
 * Q4_0 tensors: fp16->fp32 scale conversion into pre-allocated buffers.
 * =================================================================== */

#ifndef XMIND_HHDM_BASE
#define XMIND_HHDM_BASE  0xFFFF888000000000ULL
#endif
#define XMIND_PHYS_TO_VIRT(p) ((void *)((uint64_t)(p) + XMIND_HHDM_BASE))

static xmind_status_t wl_mmap_load_from_plan(
    const uint8_t *base,
    uint64_t file_size,
    const gguf_catalog_t *catalog,
    const xmind_weight_plan_t *plan,
    xmind_model_t *m) {

    (void)file_size;
    uint32_t ti;

    for (ti = 0u; ti < catalog->tensors_stored; ti++) {
        const gguf_tensor_desc_t *td = &catalog->tensors[ti];

        /* Find in plan */
        const xmind_role_mapping_t *rm = (const xmind_role_mapping_t *)0;
        uint32_t pi;
        for (pi = 0u; pi < plan->count; pi++) {
            if (plan->mappings[pi].tensor_index == ti) {
                rm = &plan->mappings[pi];
                break;
            }
        }
        if (!rm || rm->role == XMIND_ROLE_UNKNOWN) continue;

        uint64_t data_va = (uint64_t)base + catalog->data_offset + td->offset;
        uint32_t layer = rm->layer_index;

        /* F32 zero-copy assignments */
        if ((uint32_t)td->type == GGML_TYPE_F32) {
            switch (rm->role) {
            case XMIND_ROLE_TOKEN_EMB:
                m->token_emb = (float *)data_va; break;
            case XMIND_ROLE_NORM_FINAL:
                m->rms_final = (float *)data_va; break;
            case XMIND_ROLE_NORM_ATTN:
                if (layer < XMIND_MAX_LAYERS) m->rms_att[layer] = (float *)data_va;
                break;
            case XMIND_ROLE_NORM_FFN:
                if (layer < XMIND_MAX_LAYERS) m->rms_ffn[layer] = (float *)data_va;
                break;
            default: break;
            }
        }

        /* Q4_0: convert GGUF 18-byte to XMIND 20-byte blocks */
        if ((uint32_t)td->type == GGML_TYPE_Q4_0) {
            xmind_q4_block_t **slot = (xmind_q4_block_t **)0;
            if (layer < XMIND_MAX_LAYERS) {
                switch (rm->role) {
                case XMIND_ROLE_ATTN_Q:    slot = &m->wq[layer]; break;
                case XMIND_ROLE_ATTN_K:    slot = &m->wk[layer]; break;
                case XMIND_ROLE_ATTN_V:    slot = &m->wv[layer]; break;
                case XMIND_ROLE_ATTN_O:    slot = &m->wo[layer]; break;
                case XMIND_ROLE_FFN_GATE:  slot = &m->w1[layer]; break;
                case XMIND_ROLE_FFN_DOWN:  slot = &m->w2[layer]; break;
                case XMIND_ROLE_FFN_UP:    slot = &m->w3[layer]; break;
                default: break;
                }
            }
            if (slot && *slot) {
                uint64_t n_blocks = td->n_elements / 32u;
                const uint8_t *src = (const uint8_t *)data_va;
                xmind_q4_block_t *dst = *slot;
                uint64_t bi;
                for (bi = 0u; bi < n_blocks; bi++) {
                    const uint8_t *gb = src + bi * 18u;
                    uint16_t sh = (uint16_t)gb[0] | ((uint16_t)gb[1] << 8u);
                    dst[bi].scale = wl_f16_to_f32(sh);
                    uint32_t ni;
                    for (ni = 0u; ni < 16u; ni++) {
                        dst[bi].nibbles[ni] = gb[2u + ni];
                    }
                }
            }
        }
    }

    return XMIND_OK;
}

/* ===================================================================
 * S7  TOKENIZER LOAD BRIDGE
 *
 * GGUF tokenizer vocab loading is handled by the catalog + tokenizer.c.
 * The new catalog does not inline string arrays into KV structs, so
 * tokenizer loading from GGUF requires re-reading the file at the
 * array data offset.  For backward compat, we keep the old vocabulary
 * capture structure for direct-load.
 * =================================================================== */

#define WL_TOK_STR_MAX    60u
#define WL_TOK_MAX_VOCAB  128256u

typedef struct { uint32_t id; float score; char str[WL_TOK_STR_MAX]; } wl_tok_entry_t;
static wl_tok_entry_t  s_wl_vocab[WL_TOK_MAX_VOCAB];
static uint32_t        s_wl_vocab_n = 0u;

extern xmind_status_t xmind_tokenizer_load_direct(
    const void *vocab_raw, uint32_t n_vocab);

/* Load tokenizer vocab from GGUF catalog KV (file I/O re-read path).
 * Seeks to the array data offset for "tokenizer.ggml.tokens" and reads
 * string elements. */
static void wl_load_tokenizer_from_catalog(pal_file_t *fh,
                                             const gguf_catalog_t *catalog) {
    const gguf_kv_t *tok_kv = gguf_find_kv(catalog, "tokenizer.ggml.tokens");
    if (!tok_kv || (uint32_t)tok_kv->vtype != GGUF_TYPE_ARRAY) {
        pal_console_printf("[XMIND-WL] tokenizer: no vocab in GGUF — "
                           "byte-level mode\n");
        return;
    }

    uint64_t arr_count = tok_kv->val.arr.arr_count;
    uint64_t arr_offset = tok_kv->val.arr.arr_data_offset;

    if (arr_count == 0u) return;

    /* Seek to array data offset and read string entries */
    if (pal_file_seek(fh, (int64_t)arr_offset, PAL_SEEK_SET) != PAL_OK) return;

    s_wl_vocab_n = 0u;
    uint64_t ai;
    for (ai = 0u; ai < arr_count && s_wl_vocab_n < WL_TOK_MAX_VOCAB; ai++) {
        uint8_t len_buf[8];
        uint64_t nr = 0u;
        if (pal_file_read(fh, len_buf, 8u, &nr) != PAL_OK || nr < 8u) break;
        uint64_t slen = len_buf[0] | ((uint64_t)len_buf[1] << 8u)
                       | ((uint64_t)len_buf[2] << 16u) | ((uint64_t)len_buf[3] << 24u)
                       | ((uint64_t)len_buf[4] << 32u) | ((uint64_t)len_buf[5] << 40u)
                       | ((uint64_t)len_buf[6] << 48u) | ((uint64_t)len_buf[7] << 56u);

        uint32_t copy_len = (uint32_t)(slen < (WL_TOK_STR_MAX - 1u)
                                        ? slen : (WL_TOK_STR_MAX - 1u));
        if (slen <= (WL_TOK_STR_MAX - 1u)) {
            if (pal_file_read(fh, s_wl_vocab[s_wl_vocab_n].str, slen, &nr) != PAL_OK)
                break;
        } else {
            if (pal_file_read(fh, s_wl_vocab[s_wl_vocab_n].str, copy_len, &nr) != PAL_OK)
                break;
            /* Skip remaining */
            pal_file_seek(fh, (int64_t)(slen - copy_len), PAL_SEEK_CUR);
        }
        s_wl_vocab[s_wl_vocab_n].str[copy_len] = '\0';
        s_wl_vocab[s_wl_vocab_n].id = (uint32_t)ai;
        s_wl_vocab[s_wl_vocab_n].score = 0.0f;
        s_wl_vocab_n++;
    }

    /* Load scores if present */
    const gguf_kv_t *score_kv = gguf_find_kv(catalog, "tokenizer.ggml.scores");
    if (score_kv && (uint32_t)score_kv->vtype == GGUF_TYPE_ARRAY &&
        score_kv->val.arr.arr_count > 0u) {
        if (pal_file_seek(fh, (int64_t)score_kv->val.arr.arr_data_offset,
                           PAL_SEEK_SET) == PAL_OK) {
            uint64_t si;
            for (si = 0u; si < score_kv->val.arr.arr_count && si < s_wl_vocab_n; si++) {
                uint8_t fbuf[4];
                uint64_t nr2 = 0u;
                if (pal_file_read(fh, fbuf, 4u, &nr2) != PAL_OK || nr2 < 4u) break;
                uint32_t bits = fbuf[0] | ((uint32_t)fbuf[1] << 8u)
                              | ((uint32_t)fbuf[2] << 16u) | ((uint32_t)fbuf[3] << 24u);
                __builtin_memcpy(&s_wl_vocab[si].score, &bits, 4u);
            }
        }
    }

    if (s_wl_vocab_n > 0u) {
        pal_console_printf("[XMIND-WL] tokenizer: loading %u vocab entries\n",
                           s_wl_vocab_n);
        xmind_tokenizer_load_direct(s_wl_vocab, s_wl_vocab_n);
    }
}

/* ===================================================================
 * S8  BUFFER ALLOCATION FROM CATALOG
 *
 * Allocates weight buffers using ACTUAL tensor dimensions from the
 * catalog, not from assumed Llama formulas.  Each tensor in the plan
 * provides its own n_elements and ggml_type, which determines the
 * exact byte count.
 * =================================================================== */

static void wl_allocate_from_plan(const gguf_catalog_t *catalog,
                                    const xmind_weight_plan_t *plan,
                                    const xmind_config_t *cfg,
                                    xmind_model_t *m) {
    uint32_t pi;

    for (pi = 0u; pi < plan->count; pi++) {
        const xmind_role_mapping_t *rm = &plan->mappings[pi];
        if (rm->role == XMIND_ROLE_UNKNOWN) continue;
        if (rm->tensor_index >= catalog->tensors_stored) continue;

        const gguf_tensor_desc_t *td = &catalog->tensors[rm->tensor_index];
        uint32_t layer = rm->layer_index;

        /* For Q4_0 tensors, allocate in XMIND 20-byte block format
         * (not the GGUF 18-byte format).  n_blocks = n_elements / 32. */
        if ((uint32_t)td->type == GGML_TYPE_Q4_0) {
            uint64_t n_blocks = td->n_elements / 32u;
            uint64_t alloc_bytes = n_blocks * (uint64_t)sizeof(xmind_q4_block_t);

            xmind_q4_block_t **slot = (xmind_q4_block_t **)0;
            if (layer < XMIND_MAX_LAYERS) {
                switch (rm->role) {
                case XMIND_ROLE_ATTN_Q:    slot = &m->wq[layer]; break;
                case XMIND_ROLE_ATTN_K:    slot = &m->wk[layer]; break;
                case XMIND_ROLE_ATTN_V:    slot = &m->wv[layer]; break;
                case XMIND_ROLE_ATTN_O:    slot = &m->wo[layer]; break;
                case XMIND_ROLE_FFN_GATE:  slot = &m->w1[layer]; break;
                case XMIND_ROLE_FFN_DOWN:  slot = &m->w2[layer]; break;
                case XMIND_ROLE_FFN_UP:    slot = &m->w3[layer]; break;
                default: break;
                }
            }
            if (slot) {
                *slot = (xmind_q4_block_t *)wl_alloc_pages(alloc_bytes);
            }
        }

        /* For F32 tensors (norms, embeddings) */
        if ((uint32_t)td->type == GGML_TYPE_F32) {
            uint64_t alloc_bytes = td->n_elements * 4u;
            switch (rm->role) {
            case XMIND_ROLE_TOKEN_EMB:
                m->token_emb = (float *)wl_alloc_pages(alloc_bytes);
                break;
            case XMIND_ROLE_NORM_FINAL:
                m->rms_final = (float *)wl_alloc_pages(alloc_bytes);
                break;
            case XMIND_ROLE_NORM_ATTN:
                if (layer < XMIND_MAX_LAYERS)
                    m->rms_att[layer] = (float *)wl_alloc_pages(alloc_bytes);
                break;
            case XMIND_ROLE_NORM_FFN:
                if (layer < XMIND_MAX_LAYERS)
                    m->rms_ffn[layer] = (float *)wl_alloc_pages(alloc_bytes);
                break;
            default: break;
            }
        }
    }

    /* RoPE tables (computed, not in GGUF — always allocated from config) */
    uint64_t rope_bytes = (uint64_t)cfg->ctx_len * (cfg->head_dim / 2u) * 4u;
    m->rope_cos = (float *)wl_alloc_pages(rope_bytes);
    m->rope_sin = (float *)wl_alloc_pages(rope_bytes);
}

/* ===================================================================
 * S9  PUBLIC API: xmind_weights_load_file
 *
 * Orchestrator flow:
 *   1. Open file, parse catalog
 *   2. Detect interpreter
 *   3. Build config from metadata
 *   4. Map all tensors to roles
 *   5. Validate plan
 *   6. Allocate from ACTUAL tensor metadata
 *   7. Init model + alloc state
 *   8. Load tensor data
 *   9. Load tokenizer
 * =================================================================== */

xmind_status_t xmind_weights_load_file(xmind_model_t *m,
                                         const char *gguf_path) {
    if (!m || !gguf_path) { return XMIND_ERR_INVAL; }

    pal_console_printf("[XMIND-WL] loading model from: %s\n", gguf_path);

    /* Check file exists */
    pal_file_stat_t fstat;
    if (pal_file_stat(gguf_path, &fstat) != PAL_OK) {
        pal_console_printf("[XMIND-WL] file not found: %s\n", gguf_path);
        return XMIND_ERR_INVAL;
    }
    pal_console_printf("[XMIND-WL] model file: %llu bytes\n",
                       (unsigned long long)fstat.size);

    /* Open file */
    pal_file_t fh;
    if (pal_file_open(&fh, gguf_path, PAL_FILE_READ) != PAL_OK)
        return XMIND_ERR_IO;

    /* Step 1: Parse neutral GGUF catalog */
    static gguf_catalog_t s_catalog;
    gguf_status_t gst = gguf_catalog_parse(&fh, &s_catalog);
    if (gst != GGUF_OK) {
        pal_console_printf("[XMIND-WL] GGUF parse failed: %d\n", gst);
        pal_file_close(&fh);
        return (xmind_status_t)gst;
    }

    /* Step 2: Detect interpreter */
    const xmind_artifact_interp_t *interp = xmind_interp_detect(&s_catalog);
    if (!interp) {
        pal_console_printf("[XMIND-WL] no interpreter for arch: %s\n",
                           s_catalog.arch_len > 0u ? s_catalog.arch : "<unknown>");
        pal_file_close(&fh);
        return XMIND_ERR_INVAL;
    }

    /* Step 3: Build config from actual metadata */
    xmind_config_t cfg;
    wl_memset(&cfg, 0u, sizeof(cfg));
    if (interp->build_config(&s_catalog, &cfg) != 0) {
        pal_console_printf("[XMIND-WL] config build failed\n");
        pal_file_close(&fh);
        return XMIND_ERR_INVAL;
    }

    pal_console_printf("[XMIND-WL] config: layers=%u heads=%u kv=%u "
                       "head_dim=%u hidden=%u ffn=%u vocab=%u ctx=%u\n",
                       cfg.n_layers, cfg.n_heads, cfg.n_kv_heads,
                       cfg.head_dim, cfg.hidden_dim, cfg.ffn_dim,
                       cfg.vocab_size, cfg.ctx_len);

    /* Step 4: Map all catalog tensors to canonical roles */
    static xmind_weight_plan_t s_plan;
    wl_memset(&s_plan, 0u, sizeof(s_plan));
    {
        uint32_t ti;
        for (ti = 0u; ti < s_catalog.tensors_stored; ti++) {
            xmind_tensor_role_t role = XMIND_ROLE_UNKNOWN;
            uint32_t layer = 0u;
            interp->map_tensor(&s_catalog, ti, &role, &layer);

            if (s_plan.count < XMIND_WEIGHT_PLAN_MAX) {
                s_plan.mappings[s_plan.count].role = role;
                s_plan.mappings[s_plan.count].layer_index = layer;
                s_plan.mappings[s_plan.count].tensor_index = ti;
                s_plan.count++;
            }
        }
    }

    /* Step 5: Validate plan */
    int32_t vrc = interp->validate(&s_catalog, &s_plan, cfg.n_layers);
    if (vrc < 0) {
        pal_console_printf("[XMIND-WL] WARN: validation found %d issues "
                           "(proceeding)\n", -vrc);
    }
    s_plan.validated = 1u;

    /* Step 6: Initialize model + allocate state */
    xmind_status_t st = xmind_init(m, &cfg);
    if (st != XMIND_OK) {
        pal_console_printf("[XMIND-WL] xmind_init failed: %d\n", st);
        pal_file_close(&fh);
        return st;
    }

    st = xmind_alloc_state(m);
    if (st != XMIND_OK) {
        pal_console_printf("[XMIND-WL] xmind_alloc_state failed: %d\n", st);
        xmind_shutdown(m);
        pal_file_close(&fh);
        return st;
    }

    /* Step 7: Allocate weight buffers from ACTUAL tensor metadata */
    wl_allocate_from_plan(&s_catalog, &s_plan, &cfg, m);

    pal_console_printf("[XMIND-WL] buffers allocated: %u layers\n",
                       cfg.n_layers);

    /* Step 8: Load tokenizer vocab from catalog */
    s_wl_vocab_n = 0u;
    wl_load_tokenizer_from_catalog(&fh, &s_catalog);

    /* Step 9: Load tensor data */
    st = wl_load_tensors_from_plan(&fh, &s_catalog, &s_plan, m);
    pal_file_close(&fh);

    if (st != XMIND_OK) {
        pal_console_printf("[XMIND-WL] tensor load error: %d\n", st);
        return st;
    }

    pal_console_printf("[XMIND-WL] model ready: %u layers, weights loaded\n",
                       cfg.n_layers);
    return XMIND_OK;
}

/* ===================================================================
 * S10  PUBLIC API: xmind_weights_map_phys
 *
 * Zero-copy path for bootloader-loaded GGUF files.
 * =================================================================== */

xmind_status_t xmind_weights_map_phys(xmind_model_t *m,
                                        uint64_t phys_base,
                                        uint64_t file_size) {
    if (!m || phys_base == 0u || file_size < 24u) return XMIND_ERR_INVAL;

    if (phys_base % PAL_PAGE_SIZE_4K != 0u) {
        pal_console_printf("[XMIND-WL] phys_base not page-aligned: 0x%llx\n",
                           (unsigned long long)phys_base);
        return XMIND_ERR_INVAL;
    }

    const uint8_t *base = (const uint8_t *)XMIND_PHYS_TO_VIRT(phys_base);

    pal_console_printf("[XMIND-WL] mmap: phys=0x%llx virt=0x%llx size=%llu\n",
                       (unsigned long long)phys_base,
                       (unsigned long long)(uint64_t)base,
                       (unsigned long long)file_size);

    /* Parse catalog from memory */
    static gguf_catalog_t s_mmap_catalog;
    gguf_status_t gst = gguf_catalog_parse_mem(base, file_size, &s_mmap_catalog);
    if (gst != GGUF_OK) return (xmind_status_t)gst;

    /* Detect interpreter */
    const xmind_artifact_interp_t *interp = xmind_interp_detect(&s_mmap_catalog);
    if (!interp) return XMIND_ERR_INVAL;

    /* Build config */
    xmind_config_t cfg;
    wl_memset(&cfg, 0u, sizeof(cfg));
    if (interp->build_config(&s_mmap_catalog, &cfg) != 0) return XMIND_ERR_INVAL;

    pal_console_printf("[XMIND-WL] mmap config: layers=%u heads=%u "
                       "hidden=%u ffn=%u vocab=%u\n",
                       cfg.n_layers, cfg.n_heads,
                       cfg.hidden_dim, cfg.ffn_dim, cfg.vocab_size);

    /* Build weight plan */
    static xmind_weight_plan_t s_mmap_plan;
    wl_memset(&s_mmap_plan, 0u, sizeof(s_mmap_plan));
    {
        uint32_t ti;
        for (ti = 0u; ti < s_mmap_catalog.tensors_stored; ti++) {
            xmind_tensor_role_t role = XMIND_ROLE_UNKNOWN;
            uint32_t layer = 0u;
            interp->map_tensor(&s_mmap_catalog, ti, &role, &layer);
            if (s_mmap_plan.count < XMIND_WEIGHT_PLAN_MAX) {
                s_mmap_plan.mappings[s_mmap_plan.count].role = role;
                s_mmap_plan.mappings[s_mmap_plan.count].layer_index = layer;
                s_mmap_plan.mappings[s_mmap_plan.count].tensor_index = ti;
                s_mmap_plan.count++;
            }
        }
    }
    s_mmap_plan.validated = 1u;

    /* Init model */
    xmind_status_t st = xmind_init(m, &cfg);
    if (st != XMIND_OK) return st;

    st = xmind_alloc_state(m);
    if (st != XMIND_OK) { xmind_shutdown(m); return st; }

    /* Allocate Q4_0 buffers from ACTUAL catalog metadata.
     * F32 tensors will be zero-copy (no allocation needed). */
    {
        uint32_t pi;
        for (pi = 0u; pi < s_mmap_plan.count; pi++) {
            const xmind_role_mapping_t *rm = &s_mmap_plan.mappings[pi];
            if (rm->role == XMIND_ROLE_UNKNOWN) continue;
            if (rm->tensor_index >= s_mmap_catalog.tensors_stored) continue;

            const gguf_tensor_desc_t *td = &s_mmap_catalog.tensors[rm->tensor_index];
            uint32_t layer = rm->layer_index;

            /* Only allocate for Q4_0 (needs fp16->fp32 conversion) */
            if ((uint32_t)td->type == GGML_TYPE_Q4_0 && layer < XMIND_MAX_LAYERS) {
                uint64_t n_blocks = td->n_elements / 32u;
                uint64_t alloc_bytes = n_blocks * (uint64_t)sizeof(xmind_q4_block_t);
                xmind_q4_block_t **slot = (xmind_q4_block_t **)0;
                switch (rm->role) {
                case XMIND_ROLE_ATTN_Q:    slot = &m->wq[layer]; break;
                case XMIND_ROLE_ATTN_K:    slot = &m->wk[layer]; break;
                case XMIND_ROLE_ATTN_V:    slot = &m->wv[layer]; break;
                case XMIND_ROLE_ATTN_O:    slot = &m->wo[layer]; break;
                case XMIND_ROLE_FFN_GATE:  slot = &m->w1[layer]; break;
                case XMIND_ROLE_FFN_DOWN:  slot = &m->w2[layer]; break;
                case XMIND_ROLE_FFN_UP:    slot = &m->w3[layer]; break;
                default: break;
                }
                if (slot) *slot = (xmind_q4_block_t *)wl_alloc_pages(alloc_bytes);
            }
        }
    }

    /* RoPE tables */
    uint64_t rope_bytes = (uint64_t)cfg.ctx_len * (cfg.head_dim / 2u) * 4u;
    m->rope_cos = (float *)wl_alloc_pages(rope_bytes);
    m->rope_sin = (float *)wl_alloc_pages(rope_bytes);

    /* Assign weights (zero-copy F32, convert Q4_0) */
    st = wl_mmap_load_from_plan(base, file_size, &s_mmap_catalog,
                                  &s_mmap_plan, m);
    if (st != XMIND_OK) {
        pal_console_printf("[XMIND-WL] mmap: weight assignment failed: %d\n", st);
        return st;
    }

    pal_console_printf("[XMIND-WL] mmap: model ready — zero-copy F32, "
                       "converted Q4_0 (%u layers)\n", cfg.n_layers);
    return XMIND_OK;
}

/* ===================================================================
 * S11  PUBLIC API: xmind_weights_unload / xmind_weights_load
 * =================================================================== */

void xmind_weights_unload(xmind_model_t *m) {
    if (!m) { return; }
    uint32_t l;
    for (l = 0u; l < XMIND_MAX_LAYERS; l++) {
        m->wq[l] = (xmind_q4_block_t *)0;
        m->wk[l] = (xmind_q4_block_t *)0;
        m->wv[l] = (xmind_q4_block_t *)0;
        m->wo[l] = (xmind_q4_block_t *)0;
        m->w1[l] = (xmind_q4_block_t *)0;
        m->w2[l] = (xmind_q4_block_t *)0;
        m->w3[l] = (xmind_q4_block_t *)0;
        m->rms_att[l] = (float *)0;
        m->rms_ffn[l] = (float *)0;
    }
    m->token_emb  = (float *)0;
    m->rms_final  = (float *)0;
    m->rope_cos   = (float *)0;
    m->rope_sin   = (float *)0;
    xmind_shutdown(m);
    wl_free_all_pages();
    pal_console_printf("[XMIND-WL] model unloaded — all weight pages freed\n");
}

xmind_status_t xmind_weights_load(xmind_model_t *m,
                                    const char *gguf_path) {
    return xmind_weights_load_file(m, gguf_path);
}

/* ===================================================================
 * S12  XBLOB-BACKED WEIGHT LOADER (conditional)
 * =================================================================== */

#ifdef XMIND_HAS_XBLOB
#include "xblob.h"

xmind_status_t xmind_weights_load_blob(xmind_model_t *m,
                                         xblob_t *blob,
                                         const uint8_t hash[XBLOB_HASH_LEN]) {
    if (!m || !blob || !hash) { return XMIND_ERR_INVAL; }

    pal_console_printf("[XMIND-WL] loading model from XBLOB hash "
                       "%02x%02x%02x%02x...\n",
                       hash[0], hash[1], hash[2], hash[3]);

    uint32_t blob_len = 0u;
    xblob_status_t bst = xblob_size(blob, hash, &blob_len);
    if (bst != XBLOB_OK) {
        pal_console_printf("[XMIND-WL] blob not found in XBLOB store\n");
        return XMIND_ERR_INVAL;
    }
    if (blob_len > XBLOB_MAX_BLOB_SIZE) return XMIND_ERR_OVERFLOW;

    void *buf = wl_alloc_pages((uint64_t)blob_len);
    if (!buf) { return XMIND_ERR_NOMEM; }

    uint32_t out_len = 0u;
    bst = xblob_get(blob, hash, buf, blob_len, &out_len);
    if (bst != XBLOB_OK) {
        pal_console_printf("[XMIND-WL] xblob_get failed: %d\n", bst);
        return XMIND_ERR_IO;
    }

    /* Parse from in-memory buffer using the new catalog path */
    static gguf_catalog_t s_blob_catalog;
    gguf_status_t gst = gguf_catalog_parse_mem((const uint8_t *)buf,
                                                 (uint64_t)out_len,
                                                 &s_blob_catalog);
    if (gst != GGUF_OK) return XMIND_ERR_CORRUPT;

    const xmind_artifact_interp_t *interp = xmind_interp_detect(&s_blob_catalog);
    if (!interp) return XMIND_ERR_INVAL;

    xmind_config_t cfg;
    wl_memset(&cfg, 0u, sizeof(cfg));
    if (interp->build_config(&s_blob_catalog, &cfg) != 0) return XMIND_ERR_INVAL;

    xmind_status_t st = xmind_init(m, &cfg);
    if (st != XMIND_OK) { return st; }
    return xmind_alloc_state(m);
}
#endif /* XMIND_HAS_XBLOB */
