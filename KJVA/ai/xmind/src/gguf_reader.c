/*
 * gguf_reader.c — Generic GGUF Artifact Reader (Family-Neutral)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Parses a GGUF file into a neutral gguf_catalog_t.  Handles magic
 *   verification, KV metadata extraction, tensor descriptor parsing,
 *   and data section offset computation.
 *
 *   Supports GGUF versions 1, 2, and 3.  Handles all GGUF value types
 *   including nested arrays of strings.
 *
 *   Zero family assumptions.  No "llama.*" constants.
 *
 * No libc.  Freestanding C11.  PAL types only.
 *
 * S1  String/byte helpers
 * S2  LE readers
 * S3  GGUF header verification
 * S4  KV metadata parser (file I/O)
 * S5  Tensor info parser (file I/O)
 * S6  Public API: gguf_catalog_parse
 * S7  Public API: gguf_catalog_parse_mem
 * S8  Query helpers
 * S9  Type size utilities
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "../include/xmind_gguf.h"

/* ===================================================================
 * S1  STRING / BYTE HELPERS
 * =================================================================== */

static uint32_t gr_strlen(const char *s) {
    uint32_t n = 0u;
    while (s[n]) { n++; }
    return n;
}

static int32_t gr_strncmp(const char *a, const char *b, uint32_t n) {
    uint32_t i;
    for (i = 0u; i < n; i++) {
        if ((uint8_t)a[i] != (uint8_t)b[i]) {
            return (int32_t)(uint8_t)a[i] - (int32_t)(uint8_t)b[i];
        }
        if (!a[i]) { return 0; }
    }
    return 0;
}

static void gr_memset(void *dst, uint8_t val, uint64_t n) {
    uint8_t *p = (uint8_t *)dst;
    uint64_t i;
    for (i = 0u; i < n; i++) { p[i] = val; }
}

static void gr_memcpy(void *dst, const void *src, uint64_t n) {
    uint8_t *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;
    uint64_t i;
    for (i = 0u; i < n; i++) { d[i] = s[i]; }
}

/* ===================================================================
 * S2  LITTLE-ENDIAN READERS
 * =================================================================== */

static uint32_t gr_le32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8u)
         | ((uint32_t)p[2] << 16u) | ((uint32_t)p[3] << 24u);
}

static uint64_t gr_le64(const uint8_t *p) {
    uint64_t v = 0ULL;
    uint32_t i;
    for (i = 0u; i < 8u; i++) { v |= (uint64_t)p[i] << (i * 8u); }
    return v;
}

/* ===================================================================
 * S3  FILE I/O HELPERS — small buffered reads
 * =================================================================== */

static gguf_status_t gr_read_exact(pal_file_t *fh, void *buf,
                                     uint64_t len) {
    uint64_t nr = 0u;
    pal_status_t rc = pal_file_read(fh, buf, len, &nr);
    if (rc != PAL_OK || nr < len) { return GGUF_ERR_IO; }
    return GGUF_OK;
}

/* ===================================================================
 * S4  GGUF VALUE TYPE SIZE (for fixed-size scalars)
 * =================================================================== */

static uint32_t gr_vtype_size(uint32_t vtype) {
    switch (vtype) {
    case GGUF_TYPE_UINT8:   case GGUF_TYPE_INT8:   case GGUF_TYPE_BOOL:   return 1u;
    case GGUF_TYPE_UINT16:  case GGUF_TYPE_INT16:                          return 2u;
    case GGUF_TYPE_UINT32:  case GGUF_TYPE_INT32:   case GGUF_TYPE_FLOAT32: return 4u;
    case GGUF_TYPE_UINT64:  case GGUF_TYPE_INT64:   case GGUF_TYPE_FLOAT64: return 8u;
    default: return 0u;
    }
}

/* ===================================================================
 * S5  KV METADATA PARSER (file I/O path)
 *
 * Reads all n_kv metadata entries from the file, storing up to
 * GGUF_MAX_KV entries in the catalog.  Tracks file_pos for alignment.
 * =================================================================== */

static gguf_status_t gr_parse_kv_file(pal_file_t *fh,
                                        uint64_t n_kv,
                                        gguf_catalog_t *cat,
                                        uint64_t *file_pos) {
    uint64_t kvi;
    uint8_t buf8[8];
    uint8_t buf4[4];
    uint8_t buf12[12];

    for (kvi = 0u; kvi < n_kv; kvi++) {
        gguf_kv_t entry;
        gr_memset(&entry, 0u, sizeof(entry));

        /* Key: uint64_t len + len bytes */
        if (gr_read_exact(fh, buf8, 8u) != GGUF_OK) return GGUF_ERR_IO;
        uint64_t key_len = gr_le64(buf8);
        *file_pos += 8u;

        if (key_len > 8192u) return GGUF_ERR_CORRUPT;

        /* Read key bytes */
        uint32_t store_len = (uint32_t)(key_len < (GGUF_KV_KEY_MAX - 1u)
                                         ? key_len : (GGUF_KV_KEY_MAX - 1u));
        if (key_len <= (GGUF_KV_KEY_MAX - 1u)) {
            if (gr_read_exact(fh, entry.key, key_len) != GGUF_OK)
                return GGUF_ERR_IO;
        } else {
            /* Read what fits, skip the rest */
            if (gr_read_exact(fh, entry.key, store_len) != GGUF_OK)
                return GGUF_ERR_IO;
            uint64_t skip = key_len - store_len;
            if (pal_file_seek(fh, (int64_t)skip, PAL_SEEK_CUR) != PAL_OK)
                return GGUF_ERR_IO;
        }
        entry.key[store_len] = '\0';
        entry.key_len = (uint32_t)key_len;
        *file_pos += key_len;

        /* Value type: uint32_t */
        if (gr_read_exact(fh, buf4, 4u) != GGUF_OK) return GGUF_ERR_IO;
        entry.vtype = (gguf_value_type_t)gr_le32(buf4);
        *file_pos += 4u;

        /* Parse value based on type */
        switch ((uint32_t)entry.vtype) {
        case GGUF_TYPE_UINT8:
        case GGUF_TYPE_INT8:
        case GGUF_TYPE_BOOL: {
            uint8_t v;
            if (gr_read_exact(fh, &v, 1u) != GGUF_OK) return GGUF_ERR_IO;
            entry.val.u8 = v;
            *file_pos += 1u;
            break;
        }
        case GGUF_TYPE_UINT16:
        case GGUF_TYPE_INT16: {
            uint8_t vb[2];
            if (gr_read_exact(fh, vb, 2u) != GGUF_OK) return GGUF_ERR_IO;
            entry.val.u64 = (uint64_t)((uint32_t)vb[0] | ((uint32_t)vb[1] << 8u));
            *file_pos += 2u;
            break;
        }
        case GGUF_TYPE_UINT32:
        case GGUF_TYPE_INT32: {
            if (gr_read_exact(fh, buf4, 4u) != GGUF_OK) return GGUF_ERR_IO;
            entry.val.u64 = (uint64_t)gr_le32(buf4);
            *file_pos += 4u;
            break;
        }
        case GGUF_TYPE_FLOAT32: {
            if (gr_read_exact(fh, buf4, 4u) != GGUF_OK) return GGUF_ERR_IO;
            uint32_t bits = gr_le32(buf4);
            __builtin_memcpy(&entry.val.f32, &bits, 4u);
            *file_pos += 4u;
            break;
        }
        case GGUF_TYPE_UINT64:
        case GGUF_TYPE_INT64: {
            if (gr_read_exact(fh, buf8, 8u) != GGUF_OK) return GGUF_ERR_IO;
            entry.val.u64 = gr_le64(buf8);
            *file_pos += 8u;
            break;
        }
        case GGUF_TYPE_FLOAT64: {
            if (gr_read_exact(fh, buf8, 8u) != GGUF_OK) return GGUF_ERR_IO;
            entry.val.u64 = gr_le64(buf8);
            __builtin_memcpy(&entry.val.f64, &entry.val.u64, 8u);
            *file_pos += 8u;
            break;
        }
        case GGUF_TYPE_STRING: {
            if (gr_read_exact(fh, buf8, 8u) != GGUF_OK) return GGUF_ERR_IO;
            uint64_t slen = gr_le64(buf8);
            *file_pos += 8u;
            /* Skip string data (not stored in KV — too large for inline) */
            entry.val.str.str_ptr = (const char *)0;  /* not accessible */
            entry.val.str.str_len = slen;
            if (slen > 0u) {
                if (pal_file_seek(fh, (int64_t)slen, PAL_SEEK_CUR) != PAL_OK)
                    return GGUF_ERR_IO;
                *file_pos += slen;
            }
            break;
        }
        case GGUF_TYPE_ARRAY: {
            if (gr_read_exact(fh, buf12, 12u) != GGUF_OK) return GGUF_ERR_IO;
            uint32_t elem_type = gr_le32(buf12);
            uint64_t arr_count = gr_le64(buf12 + 4u);
            *file_pos += 12u;

            entry.val.arr.arr_count     = arr_count;
            entry.val.arr.arr_elem_type = elem_type;
            entry.val.arr.arr_data_offset = *file_pos;

            /* Skip array elements */
            if (elem_type == (uint32_t)GGUF_TYPE_STRING) {
                uint64_t ai;
                for (ai = 0u; ai < arr_count; ai++) {
                    if (gr_read_exact(fh, buf8, 8u) != GGUF_OK) return GGUF_ERR_IO;
                    uint64_t elen = gr_le64(buf8);
                    *file_pos += 8u;
                    if (elen > 0u) {
                        if (pal_file_seek(fh, (int64_t)elen, PAL_SEEK_CUR) != PAL_OK)
                            return GGUF_ERR_IO;
                        *file_pos += elen;
                    }
                }
            } else {
                uint32_t esz = gr_vtype_size(elem_type);
                if (esz == 0u) esz = 8u;  /* conservative skip for unknown */
                uint64_t skip = arr_count * (uint64_t)esz;
                if (pal_file_seek(fh, (int64_t)skip, PAL_SEEK_CUR) != PAL_OK)
                    return GGUF_ERR_IO;
                *file_pos += skip;
            }
            break;
        }
        default:
            return GGUF_ERR_CORRUPT;
        }

        /* Store entry if room */
        if (cat->kv_stored < GGUF_MAX_KV) {
            cat->kv[cat->kv_stored] = entry;
            cat->kv_stored++;
        }

        /* Check for architecture key */
        {
            const char *arch_key = "general.architecture";
            uint32_t akl = gr_strlen(arch_key);
            if (entry.key_len == akl &&
                gr_strncmp(entry.key, arch_key, akl) == 0 &&
                (uint32_t)entry.vtype == GGUF_TYPE_STRING) {
                /* The string value was skipped; re-read it.
                 * For architecture string, we saved the length but not data.
                 * We need to seek back and read it.  But since we already
                 * advanced past, we store from key match instead.
                 * Alternative: detect arch from "llama.block_count" etc.
                 * For now, mark arch_len=0 and let interpreters use KV
                 * key prefix detection. */
                cat->arch_len = 0u;
            }
        }

        /* Detect architecture from key prefixes — e.g. if any key starts
         * with "llama." and arch is not yet set, infer arch = "llama" */
        if (cat->arch_len == 0u && entry.key_len > 6u) {
            /* Check for "XXX.YYY" pattern where XXX is the arch */
            uint32_t dot_pos = 0u;
            uint32_t ki;
            for (ki = 0u; ki < entry.key_len && ki < (GGUF_KV_KEY_MAX - 1u); ki++) {
                if (entry.key[ki] == '.') { dot_pos = ki; break; }
            }
            if (dot_pos > 0u && dot_pos < GGUF_ARCH_MAX) {
                /* Skip "general." and "tokenizer." prefixes */
                if (!(dot_pos == 7u && gr_strncmp(entry.key, "general", 7u) == 0) &&
                    !(dot_pos == 9u && gr_strncmp(entry.key, "tokenizer", 9u) == 0)) {
                    for (ki = 0u; ki < dot_pos; ki++) {
                        cat->arch[ki] = entry.key[ki];
                    }
                    cat->arch[dot_pos] = '\0';
                    cat->arch_len = dot_pos;
                }
            }
        }
    }

    return GGUF_OK;
}

/* ===================================================================
 * S6  TENSOR INFO PARSER (file I/O path)
 *
 * Reads n_tensors tensor info entries from the current file position.
 * Each entry: name_len(u64) + name + n_dims(u32) + dims(n*u64)
 *             + type(u32) + offset(u64).
 * =================================================================== */

static gguf_status_t gr_parse_tensors_file(pal_file_t *fh,
                                             uint64_t n_tensors,
                                             gguf_catalog_t *cat,
                                             uint64_t *file_pos) {
    uint64_t ti;
    uint8_t buf8[8];
    uint8_t buf4[4];

    for (ti = 0u; ti < n_tensors; ti++) {
        gguf_tensor_desc_t desc;
        gr_memset(&desc, 0u, sizeof(desc));

        /* Name: uint64_t len + bytes */
        if (gr_read_exact(fh, buf8, 8u) != GGUF_OK) return GGUF_ERR_IO;
        uint64_t name_len = gr_le64(buf8);
        *file_pos += 8u;
        if (name_len > 8192u) return GGUF_ERR_CORRUPT;

        uint32_t store_len = (uint32_t)(name_len < (GGUF_TENSOR_NAME_MAX - 1u)
                                         ? name_len : (GGUF_TENSOR_NAME_MAX - 1u));
        if (name_len <= (GGUF_TENSOR_NAME_MAX - 1u)) {
            if (gr_read_exact(fh, desc.name, name_len) != GGUF_OK)
                return GGUF_ERR_IO;
        } else {
            if (gr_read_exact(fh, desc.name, store_len) != GGUF_OK)
                return GGUF_ERR_IO;
            uint64_t skip = name_len - store_len;
            if (pal_file_seek(fh, (int64_t)skip, PAL_SEEK_CUR) != PAL_OK)
                return GGUF_ERR_IO;
        }
        desc.name[store_len] = '\0';
        desc.name_len = (uint32_t)name_len;
        *file_pos += name_len;

        /* n_dims: uint32_t */
        if (gr_read_exact(fh, buf4, 4u) != GGUF_OK) return GGUF_ERR_IO;
        desc.n_dims = gr_le32(buf4);
        *file_pos += 4u;
        if (desc.n_dims > GGUF_TENSOR_MAX_DIMS) return GGUF_ERR_CORRUPT;

        /* dims: n_dims * uint64_t */
        uint64_t n_elem = 1u;
        uint32_t d;
        for (d = 0u; d < desc.n_dims; d++) {
            if (gr_read_exact(fh, buf8, 8u) != GGUF_OK) return GGUF_ERR_IO;
            desc.dims[d] = gr_le64(buf8);
            n_elem *= desc.dims[d];
            *file_pos += 8u;
        }
        desc.n_elements = n_elem;

        /* type: uint32_t */
        if (gr_read_exact(fh, buf4, 4u) != GGUF_OK) return GGUF_ERR_IO;
        desc.type = (ggml_type_t)gr_le32(buf4);
        *file_pos += 4u;

        /* offset: uint64_t (from data section start) */
        if (gr_read_exact(fh, buf8, 8u) != GGUF_OK) return GGUF_ERR_IO;
        desc.offset = gr_le64(buf8);
        *file_pos += 8u;

        /* Compute data bytes from actual type + elements */
        desc.data_bytes = gguf_tensor_data_bytes(desc.type, desc.n_elements);

        /* Store if room */
        if (cat->tensors_stored < GGUF_MAX_TENSORS) {
            cat->tensors[cat->tensors_stored] = desc;
            cat->tensors_stored++;
        }
    }

    return GGUF_OK;
}

/* ===================================================================
 * S7  PUBLIC API: gguf_catalog_parse (file I/O path)
 * =================================================================== */

gguf_status_t gguf_catalog_parse(pal_file_t *fh, gguf_catalog_t *catalog) {
    if (!fh || !catalog) return GGUF_ERR_INVAL;
    gr_memset(catalog, 0u, sizeof(*catalog));
    catalog->alignment = GGUF_DEFAULT_ALIGN;

    /* Read 24-byte header */
    uint8_t hdr[24];
    if (gr_read_exact(fh, hdr, 24u) != GGUF_OK) return GGUF_ERR_IO;

    uint32_t magic = gr_le32(hdr);
    if (magic != GGUF_MAGIC) {
        pal_console_printf("[GGUF-RDR] magic mismatch: 0x%08lx\n",
                           (unsigned long)magic);
        return GGUF_ERR_CORRUPT;
    }

    catalog->version   = gr_le32(hdr + 4u);
    catalog->n_tensors = gr_le64(hdr + 8u);
    catalog->n_kv      = gr_le64(hdr + 16u);

    if (catalog->version < GGUF_VER_MIN || catalog->version > GGUF_VER_MAX) {
        pal_console_printf("[GGUF-RDR] unsupported version: %u\n",
                           catalog->version);
        return GGUF_ERR_CORRUPT;
    }

    pal_console_printf("[GGUF-RDR] v%u: %llu KV, %llu tensors\n",
                       catalog->version,
                       (unsigned long long)catalog->n_kv,
                       (unsigned long long)catalog->n_tensors);

    uint64_t file_pos = 24u;

    /* Parse KV metadata */
    gguf_status_t st = gr_parse_kv_file(fh, catalog->n_kv, catalog, &file_pos);
    if (st != GGUF_OK) return st;

    /* Parse tensor info section */
    st = gr_parse_tensors_file(fh, catalog->n_tensors, catalog, &file_pos);
    if (st != GGUF_OK) return st;

    /* Compute data section offset (aligned) */
    uint32_t align = catalog->alignment;
    catalog->data_offset = ((file_pos + align - 1u) / align) * align;

    /* Seek to data section start */
    {
        uint64_t pad = catalog->data_offset - file_pos;
        if (pad > 0u) {
            if (pal_file_seek(fh, (int64_t)pad, PAL_SEEK_CUR) != PAL_OK)
                return GGUF_ERR_IO;
        }
    }

    pal_console_printf("[GGUF-RDR] catalog: %u KV stored, %u tensors stored, "
                       "data @ 0x%llx\n",
                       catalog->kv_stored, catalog->tensors_stored,
                       (unsigned long long)catalog->data_offset);
    return GGUF_OK;
}

/* ===================================================================
 * S8  PUBLIC API: gguf_catalog_parse_mem (in-memory path)
 * =================================================================== */

gguf_status_t gguf_catalog_parse_mem(const uint8_t *base,
                                       uint64_t file_size,
                                       gguf_catalog_t *catalog) {
    if (!base || !catalog) return GGUF_ERR_INVAL;
    if (file_size < 24u) return GGUF_ERR_CORRUPT;

    gr_memset(catalog, 0u, sizeof(*catalog));
    catalog->alignment = GGUF_DEFAULT_ALIGN;

    /* Header */
    uint32_t magic = gr_le32(base);
    if (magic != GGUF_MAGIC) return GGUF_ERR_CORRUPT;

    catalog->version   = gr_le32(base + 4u);
    catalog->n_tensors = gr_le64(base + 8u);
    catalog->n_kv      = gr_le64(base + 16u);

    if (catalog->version < GGUF_VER_MIN || catalog->version > GGUF_VER_MAX)
        return GGUF_ERR_CORRUPT;

    uint64_t pos = 24u;

    /* Parse KV metadata in-memory */
    uint64_t kvi;
    for (kvi = 0u; kvi < catalog->n_kv; kvi++) {
        gguf_kv_t entry;
        gr_memset(&entry, 0u, sizeof(entry));

        if (pos + 8u > file_size) break;
        uint64_t key_len = gr_le64(base + pos); pos += 8u;
        if (key_len > 8192u) return GGUF_ERR_CORRUPT;
        if (pos + key_len > file_size) break;

        uint32_t store_len = (uint32_t)(key_len < (GGUF_KV_KEY_MAX - 1u)
                                         ? key_len : (GGUF_KV_KEY_MAX - 1u));
        gr_memcpy(entry.key, base + pos, store_len);
        entry.key[store_len] = '\0';
        entry.key_len = (uint32_t)key_len;
        pos += key_len;

        if (pos + 4u > file_size) break;
        entry.vtype = (gguf_value_type_t)gr_le32(base + pos); pos += 4u;

        switch ((uint32_t)entry.vtype) {
        case GGUF_TYPE_UINT8: case GGUF_TYPE_INT8: case GGUF_TYPE_BOOL:
            if (pos + 1u > file_size) goto mem_done;
            entry.val.u8 = base[pos]; pos += 1u; break;
        case GGUF_TYPE_UINT16: case GGUF_TYPE_INT16:
            if (pos + 2u > file_size) goto mem_done;
            entry.val.u64 = (uint64_t)((uint32_t)base[pos] | ((uint32_t)base[pos+1u] << 8u));
            pos += 2u; break;
        case GGUF_TYPE_UINT32: case GGUF_TYPE_INT32:
            if (pos + 4u > file_size) goto mem_done;
            entry.val.u64 = (uint64_t)gr_le32(base + pos); pos += 4u; break;
        case GGUF_TYPE_FLOAT32: {
            if (pos + 4u > file_size) goto mem_done;
            uint32_t bits = gr_le32(base + pos); pos += 4u;
            __builtin_memcpy(&entry.val.f32, &bits, 4u);
            break;
        }
        case GGUF_TYPE_UINT64: case GGUF_TYPE_INT64:
            if (pos + 8u > file_size) goto mem_done;
            entry.val.u64 = gr_le64(base + pos); pos += 8u; break;
        case GGUF_TYPE_FLOAT64:
            if (pos + 8u > file_size) goto mem_done;
            entry.val.u64 = gr_le64(base + pos);
            __builtin_memcpy(&entry.val.f64, &entry.val.u64, 8u);
            pos += 8u; break;
        case GGUF_TYPE_STRING: {
            if (pos + 8u > file_size) goto mem_done;
            uint64_t slen = gr_le64(base + pos); pos += 8u;
            if (pos + slen > file_size) goto mem_done;
            entry.val.str.str_ptr = (const char *)(base + pos);
            entry.val.str.str_len = slen;
            pos += slen;
            break;
        }
        case GGUF_TYPE_ARRAY: {
            if (pos + 12u > file_size) goto mem_done;
            uint32_t et = gr_le32(base + pos); pos += 4u;
            uint64_t ac = gr_le64(base + pos); pos += 8u;
            entry.val.arr.arr_count = ac;
            entry.val.arr.arr_elem_type = et;
            entry.val.arr.arr_data_offset = pos;
            if (et == (uint32_t)GGUF_TYPE_STRING) {
                uint64_t ai;
                for (ai = 0u; ai < ac; ai++) {
                    if (pos + 8u > file_size) goto mem_done;
                    uint64_t el = gr_le64(base + pos); pos += 8u;
                    if (pos + el > file_size) goto mem_done;
                    pos += el;
                }
            } else {
                uint32_t esz = gr_vtype_size(et);
                if (esz == 0u) esz = 8u;
                uint64_t skip = ac * (uint64_t)esz;
                if (pos + skip > file_size) goto mem_done;
                pos += skip;
            }
            break;
        }
        default:
            goto mem_done;
        }

        /* Store entry */
        if (catalog->kv_stored < GGUF_MAX_KV) {
            catalog->kv[catalog->kv_stored] = entry;
            catalog->kv_stored++;
        }

        /* Detect architecture from string value of "general.architecture" */
        {
            const char *arch_key = "general.architecture";
            uint32_t akl = gr_strlen(arch_key);
            if (entry.key_len == akl &&
                gr_strncmp(entry.key, arch_key, akl) == 0 &&
                (uint32_t)entry.vtype == GGUF_TYPE_STRING &&
                entry.val.str.str_ptr &&
                entry.val.str.str_len > 0u &&
                entry.val.str.str_len < GGUF_ARCH_MAX) {
                uint32_t al = (uint32_t)entry.val.str.str_len;
                gr_memcpy(catalog->arch, entry.val.str.str_ptr, al);
                catalog->arch[al] = '\0';
                catalog->arch_len = al;
            }
        }

        /* Fallback: detect arch from KV key prefix */
        if (catalog->arch_len == 0u && entry.key_len > 6u) {
            uint32_t dot_pos = 0u, ki;
            for (ki = 0u; ki < entry.key_len && ki < (GGUF_KV_KEY_MAX - 1u); ki++) {
                if (entry.key[ki] == '.') { dot_pos = ki; break; }
            }
            if (dot_pos > 0u && dot_pos < GGUF_ARCH_MAX) {
                if (!(dot_pos == 7u && gr_strncmp(entry.key, "general", 7u) == 0) &&
                    !(dot_pos == 9u && gr_strncmp(entry.key, "tokenizer", 9u) == 0)) {
                    gr_memcpy(catalog->arch, entry.key, dot_pos);
                    catalog->arch[dot_pos] = '\0';
                    catalog->arch_len = dot_pos;
                }
            }
        }
    }

    /* Parse tensor info in-memory */
    {
        uint64_t ti;
        for (ti = 0u; ti < catalog->n_tensors; ti++) {
            gguf_tensor_desc_t desc;
            gr_memset(&desc, 0u, sizeof(desc));

            if (pos + 8u > file_size) break;
            uint64_t nl = gr_le64(base + pos); pos += 8u;
            if (nl > 8192u || pos + nl > file_size) break;

            uint32_t sl = (uint32_t)(nl < (GGUF_TENSOR_NAME_MAX - 1u)
                                      ? nl : (GGUF_TENSOR_NAME_MAX - 1u));
            gr_memcpy(desc.name, base + pos, sl);
            desc.name[sl] = '\0';
            desc.name_len = (uint32_t)nl;
            pos += nl;

            if (pos + 4u > file_size) break;
            desc.n_dims = gr_le32(base + pos); pos += 4u;
            if (desc.n_dims > GGUF_TENSOR_MAX_DIMS) break;

            uint64_t n_elem = 1u;
            uint32_t d;
            for (d = 0u; d < desc.n_dims; d++) {
                if (pos + 8u > file_size) { n_elem = 0u; break; }
                desc.dims[d] = gr_le64(base + pos);
                n_elem *= desc.dims[d];
                pos += 8u;
            }
            if (n_elem == 0u) break;
            desc.n_elements = n_elem;

            if (pos + 4u > file_size) break;
            desc.type = (ggml_type_t)gr_le32(base + pos); pos += 4u;

            if (pos + 8u > file_size) break;
            desc.offset = gr_le64(base + pos); pos += 8u;

            desc.data_bytes = gguf_tensor_data_bytes(desc.type, desc.n_elements);

            if (catalog->tensors_stored < GGUF_MAX_TENSORS) {
                catalog->tensors[catalog->tensors_stored] = desc;
                catalog->tensors_stored++;
            }
        }
    }

    /* Compute data offset */
    {
        uint32_t align = catalog->alignment;
        catalog->data_offset = ((pos + align - 1u) / align) * align;
    }

mem_done:
    return GGUF_OK;
}

/* ===================================================================
 * S9  QUERY HELPERS
 * =================================================================== */

const gguf_kv_t *gguf_find_kv(const gguf_catalog_t *catalog,
                                const char *key) {
    if (!catalog || !key) return (const gguf_kv_t *)0;
    uint32_t target_len = gr_strlen(key);
    uint32_t i;
    for (i = 0u; i < catalog->kv_stored; i++) {
        if (catalog->kv[i].key_len == target_len &&
            gr_strncmp(catalog->kv[i].key, key, target_len) == 0) {
            return &catalog->kv[i];
        }
    }
    return (const gguf_kv_t *)0;
}

const gguf_tensor_desc_t *gguf_find_tensor(const gguf_catalog_t *catalog,
                                             const char *name) {
    if (!catalog || !name) return (const gguf_tensor_desc_t *)0;
    uint32_t target_len = gr_strlen(name);
    uint32_t i;
    for (i = 0u; i < catalog->tensors_stored; i++) {
        if (catalog->tensors[i].name_len == target_len &&
            gr_strncmp(catalog->tensors[i].name, name, target_len) == 0) {
            return &catalog->tensors[i];
        }
    }
    return (const gguf_tensor_desc_t *)0;
}

/* ===================================================================
 * S10  TYPE SIZE UTILITIES
 * =================================================================== */

uint32_t ggml_type_block_size(ggml_type_t type) {
    switch ((uint32_t)type) {
    case GGML_TYPE_F32:   return 1u;
    case GGML_TYPE_F16:   return 1u;
    case GGML_TYPE_Q4_0:  return 32u;
    case GGML_TYPE_Q4_1:  return 32u;
    case GGML_TYPE_Q4_K:  return 256u;
    case GGML_TYPE_Q5_K:  return 256u;
    case GGML_TYPE_Q6_K:  return 256u;
    case GGML_TYPE_Q8_K:  return 256u;
    default:              return 0u;
    }
}

uint32_t ggml_type_byte_size(ggml_type_t type) {
    switch ((uint32_t)type) {
    case GGML_TYPE_F32:   return 4u;    /* 4 bytes per element  */
    case GGML_TYPE_F16:   return 2u;    /* 2 bytes per element  */
    case GGML_TYPE_Q4_0:  return 18u;   /* 2 fp16 + 16 nibbles  */
    case GGML_TYPE_Q4_1:  return 20u;   /* 2 fp16 + 2 fp16 + 16 nibbles */
    case GGML_TYPE_Q4_K:  return 144u;  /* Q4_K_M super-block   */
    case GGML_TYPE_Q5_K:  return 176u;
    case GGML_TYPE_Q6_K:  return 210u;
    case GGML_TYPE_Q8_K:  return 292u;
    default:              return 0u;
    }
}

uint64_t gguf_tensor_data_bytes(ggml_type_t type, uint64_t n_elements) {
    uint32_t blk_sz = ggml_type_block_size(type);
    uint32_t blk_bytes = ggml_type_byte_size(type);
    if (blk_sz == 0u || blk_bytes == 0u) return 0u;

    if (blk_sz == 1u) {
        /* Unquantized: byte_size * n_elements */
        return n_elements * (uint64_t)blk_bytes;
    }

    /* Quantized: (n_elements / block_size) * block_bytes */
    uint64_t n_blocks = n_elements / (uint64_t)blk_sz;
    return n_blocks * (uint64_t)blk_bytes;
}
