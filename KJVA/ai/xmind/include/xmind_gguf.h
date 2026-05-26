/*
 * xmind_gguf.h — Generic GGUF Artifact Reader (Family-Neutral)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Neutral GGUF container parser.  Reads magic, version, KV metadata,
 *   and tensor descriptors into a gguf_catalog_t without assuming any
 *   model family.  The catalog is then consumed by a family-specific
 *   artifact interpreter (e.g. interp_llama.c) which extracts
 *   xmind_config_t fields and maps tensors to canonical roles.
 *
 *   This header defines:
 *     - GGUF magic, version limits, alignment
 *     - gguf_value_type_t  (all GGUF metadata value types)
 *     - ggml_type_t        (quantization types XMIND supports)
 *     - gguf_kv_t          (one KV metadata entry)
 *     - gguf_tensor_desc_t (one tensor descriptor)
 *     - gguf_catalog_t     (the complete neutral catalog)
 *     - Reader + query API
 *
 * DESIGN INVARIANT:
 *   Zero family assumptions.  No "llama.*" key constants.
 *   No formula-based allocation.  Tensor byte sizes come from
 *   actual dims + ggml_type, never from assumed model shapes.
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef XMIND_GGUF_H
#define XMIND_GGUF_H

#ifdef PAL_FREESTANDING
#include "../../../pal/include/pal.h"
#else
#include <stdint.h>
#include <stddef.h>
#endif

/* ===================================================================
 * S1  GGUF FORMAT CONSTANTS
 * =================================================================== */

#define GGUF_MAGIC          0x46554747UL   /* "GGUF" little-endian       */
#define GGUF_VER_MIN        1u
#define GGUF_VER_MAX        3u
#define GGUF_DEFAULT_ALIGN  32u            /* default tensor alignment   */

/* ===================================================================
 * S2  GGUF VALUE TYPE ENUM
 * =================================================================== */

typedef enum {
    GGUF_TYPE_UINT8   =  0u,
    GGUF_TYPE_INT8    =  1u,
    GGUF_TYPE_UINT16  =  2u,
    GGUF_TYPE_INT16   =  3u,
    GGUF_TYPE_UINT32  =  4u,
    GGUF_TYPE_INT32   =  5u,
    GGUF_TYPE_FLOAT32 =  6u,
    GGUF_TYPE_BOOL    =  7u,
    GGUF_TYPE_STRING  =  8u,
    GGUF_TYPE_ARRAY   =  9u,
    GGUF_TYPE_UINT64  = 10u,
    GGUF_TYPE_INT64   = 11u,
    GGUF_TYPE_FLOAT64 = 12u,
} gguf_value_type_t;

/* ===================================================================
 * S3  GGML QUANTIZATION TYPE ENUM
 *
 * Only types XMIND actually supports are given named constants.
 * The enum covers the full range so catalogs can store any type;
 * unsupported types are detected at interpreter validation time.
 * =================================================================== */

typedef enum {
    GGML_TYPE_F32    =  0u,
    GGML_TYPE_F16    =  1u,
    GGML_TYPE_Q4_0   =  2u,
    GGML_TYPE_Q4_1   =  3u,
    /* 4..11 reserved for other ggml quant types */
    GGML_TYPE_Q4_K   = 12u,   /* Q4_K_M super-block format */
    GGML_TYPE_Q5_K   = 13u,
    GGML_TYPE_Q6_K   = 14u,
    GGML_TYPE_Q8_K   = 15u,
} ggml_type_t;

/* ===================================================================
 * S4  KV METADATA ENTRY
 *
 * Union payload large enough for scalar types.  String values store
 * a pointer into the raw scan buffer (NOT heap-allocated).  Array
 * values store element count + element type; element data is accessed
 * via offset into the raw buffer.
 * =================================================================== */

#define GGUF_KV_KEY_MAX  128u   /* max key length stored (truncated) */

typedef struct {
    char               key[GGUF_KV_KEY_MAX];
    uint32_t           key_len;       /* actual key length (may > KEY_MAX)  */
    gguf_value_type_t  vtype;

    /* Scalar payload — union avoids wasting space.
     * For STRING: str_ptr points into scan buffer, str_len is byte count.
     * For ARRAY:  arr_count, arr_elem_type, arr_data_offset (into raw buf). */
    union {
        uint64_t u64;
        int64_t  i64;
        float    f32;
        double   f64;
        uint8_t  u8;
        struct { const char *str_ptr; uint64_t str_len; } str;
        struct { uint64_t arr_count; uint32_t arr_elem_type;
                 uint64_t arr_data_offset; } arr;
    } val;
} gguf_kv_t;

/* ===================================================================
 * S5  TENSOR DESCRIPTOR
 *
 * Describes one tensor entry from the GGUF tensor info section.
 * data_bytes is computed from dims + ggml_type (not from assumptions).
 * =================================================================== */

#define GGUF_TENSOR_NAME_MAX  64u   /* max name length stored */
#define GGUF_TENSOR_MAX_DIMS   8u   /* GGUF spec max dimensions */

typedef struct {
    char       name[GGUF_TENSOR_NAME_MAX];
    uint32_t   name_len;               /* actual name length               */
    ggml_type_t type;                  /* quantization / data type         */
    uint32_t   n_dims;                 /* number of dimensions             */
    uint64_t   dims[GGUF_TENSOR_MAX_DIMS]; /* dimension sizes              */
    uint64_t   n_elements;             /* product of all dims              */
    uint64_t   offset;                 /* byte offset from data section    */
    uint64_t   data_bytes;             /* actual byte size in GGUF file    */
} gguf_tensor_desc_t;

/* ===================================================================
 * S6  CATALOG — THE COMPLETE NEUTRAL PARSE RESULT
 *
 * After gguf_catalog_parse(), this struct holds everything needed to
 * build a model config and load tensors, without any family coupling.
 * =================================================================== */

#define GGUF_MAX_KV       256u
#define GGUF_MAX_TENSORS  512u
#define GGUF_ARCH_MAX      32u   /* max architecture string length */

typedef struct {
    /* Header fields */
    uint32_t           version;
    uint64_t           n_kv;
    uint64_t           n_tensors;

    /* Parsed metadata */
    gguf_kv_t          kv[GGUF_MAX_KV];
    uint32_t           kv_stored;      /* actual KV entries parsed */

    /* Parsed tensor descriptors */
    gguf_tensor_desc_t tensors[GGUF_MAX_TENSORS];
    uint32_t           tensors_stored; /* actual tensor entries parsed */

    /* Data section offset (bytes from file start) */
    uint64_t           data_offset;

    /* Alignment (from metadata or GGUF_DEFAULT_ALIGN) */
    uint32_t           alignment;

    /* Architecture string extracted from "general.architecture" */
    char               arch[GGUF_ARCH_MAX];
    uint32_t           arch_len;
} gguf_catalog_t;

/* ===================================================================
 * S7  API — READER
 *
 * gguf_catalog_parse reads from a PAL file handle.  On success the
 * catalog is fully populated (KV + tensor descriptors + data_offset).
 * The file position after return is at the start of tensor data.
 * =================================================================== */

/* Forward-declare PAL file handle (avoids pulling pal.h internals).
 * The actual type is defined in weights_loader.c / gguf_reader.c. */
#ifndef PAL_FILE_IO_DEFINED
#define PAL_FILE_IO_DEFINED

#define PAL_FILE_READ   0u
#define PAL_FILE_WRITE  1u
#define PAL_FILE_RDWR   2u
#define PAL_ERR_EOF     ((pal_status_t)0x7FFF0001u)

typedef struct { pal_handle_t _h; uint64_t _pos; } pal_file_t;

typedef struct {
    uint64_t size;
    uint64_t mtime_ns;
} pal_file_stat_t;

typedef enum {
    PAL_SEEK_SET = 0,
    PAL_SEEK_CUR = 1,
    PAL_SEEK_END = 2,
} pal_seek_whence_t;

#endif /* PAL_FILE_IO_DEFINED */

/* PAL file I/O function declarations */
pal_status_t pal_file_open(pal_file_t *out_fh, const char *path,
                             uint32_t mode);
pal_status_t pal_file_read(pal_file_t *fh, void *buf, uint64_t len,
                             uint64_t *out_read);
pal_status_t pal_file_close(pal_file_t *fh);
pal_status_t pal_file_seek(pal_file_t *fh, int64_t offset,
                             pal_seek_whence_t whence);
pal_status_t pal_file_stat(const char *path, pal_file_stat_t *out_stat);

/* Status type (reuse XMIND status codes) */
typedef int32_t gguf_status_t;

#define GGUF_OK           ((gguf_status_t)  0)
#define GGUF_ERR_INVAL    ((gguf_status_t) -1)
#define GGUF_ERR_CORRUPT  ((gguf_status_t) -3)
#define GGUF_ERR_IO       ((gguf_status_t) -5)

/*
 * gguf_catalog_parse — Parse a GGUF file into a neutral catalog.
 *
 * @param fh       Open PAL file handle, positioned at byte 0
 * @param catalog  Caller-allocated catalog struct (zeroed by callee)
 * @return         GGUF_OK on success; negative on error
 *
 * On return, the file handle is positioned at the start of tensor data
 * (catalog->data_offset bytes from file start).
 */
gguf_status_t gguf_catalog_parse(pal_file_t *fh, gguf_catalog_t *catalog);

/*
 * gguf_catalog_parse_mem — Parse GGUF from an in-memory buffer.
 *
 * @param base      Pointer to GGUF file data in memory
 * @param file_size Total size of the buffer in bytes
 * @param catalog   Caller-allocated catalog struct (zeroed by callee)
 * @return          GGUF_OK on success; negative on error
 */
gguf_status_t gguf_catalog_parse_mem(const uint8_t *base,
                                       uint64_t file_size,
                                       gguf_catalog_t *catalog);

/*
 * gguf_find_kv — Find a KV entry by key name.
 *
 * @param catalog  Parsed catalog
 * @param key      Null-terminated key string
 * @return         Pointer to gguf_kv_t if found; NULL otherwise
 */
const gguf_kv_t *gguf_find_kv(const gguf_catalog_t *catalog,
                                const char *key);

/*
 * gguf_find_tensor — Find a tensor descriptor by name.
 *
 * @param catalog  Parsed catalog
 * @param name     Null-terminated tensor name
 * @return         Pointer to gguf_tensor_desc_t if found; NULL otherwise
 */
const gguf_tensor_desc_t *gguf_find_tensor(const gguf_catalog_t *catalog,
                                             const char *name);

/*
 * ggml_type_block_size — Number of elements per quantization block.
 * F32: 1, Q4_0: 32, Q4_K: 256, etc.
 */
uint32_t ggml_type_block_size(ggml_type_t type);

/*
 * ggml_type_byte_size — Byte size of one quantization block.
 * F32: 4, Q4_0: 18 (GGUF on-disk), Q4_K: 144, etc.
 */
uint32_t ggml_type_byte_size(ggml_type_t type);

/*
 * gguf_tensor_data_bytes — Compute byte size of tensor data in GGUF.
 * Uses actual n_elements and ggml_type to compute bytes.
 * Returns 0 for unknown types.
 */
uint64_t gguf_tensor_data_bytes(ggml_type_t type, uint64_t n_elements);

#endif /* XMIND_GGUF_H */
