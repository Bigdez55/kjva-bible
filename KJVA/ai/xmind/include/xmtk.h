/*
 * xmtk.h -- XMTK (XMIND Tokenizer Format) Specification
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Defines the binary header format for XMIND tokenizer files (.xmtk).
 *   The XMTK format stores a byte-level BPE vocabulary alongside merge
 *   rules, enabling the XMIND runtime to perform tokenization without
 *   any external dependencies.
 *
 *   This header is freestanding: no libc, no stdlib, only stdint via PAL.
 *
 * XMTK FILE LAYOUT (binary, little-endian):
 *   Offset 0x00: xmtk_header_t (32 bytes)
 *   Offset 0x20: vocab table   [vocab_size entries]
 *     Each entry: [uint16_t token_len] [token_len bytes of UTF-8 token]
 *   Offset varies: merge table  [n_merges entries]
 *     Each entry: [uint32_t left_id] [uint32_t right_id] [uint32_t merged_id]
 *   Offset varies: score table  [vocab_size entries]
 *     Each entry: [float score] (merge priority / token frequency)
 *
 * RELATIONSHIP TO xmind.h:
 *   xmind.h defines xmind_bpe_t which is the runtime BPE state.
 *   This header defines the on-disk serialization format that
 *   xmind_bpe_load() reads into xmind_bpe_t.
 */

#ifndef XMTK_H
#define XMTK_H

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "../../../pal/include/pal.h"

/* =====================================================================
 * S1  XMTK HEADER
 * =====================================================================
 *
 * 32-byte fixed header at offset 0 of every .xmtk file.
 * Magic is 0x584D544B ("XMTK" ASCII, little-endian).
 */

#define XMTK_MAGIC    0x584D544Bu  /* "XMTK" in little-endian           */
#define XMTK_VERSION  1u           /* Current format version             */

typedef struct __attribute__((packed)) {
    uint32_t magic;           /* XMTK_MAGIC (0x584D544B)               */
    uint32_t version;         /* Format version (currently 1)           */
    uint32_t vocab_size;      /* Number of tokens in vocabulary         */
    uint32_t n_merges;        /* Number of BPE merge rules              */
    uint32_t bos_id;          /* Begin-of-sequence token ID             */
    uint32_t eos_id;          /* End-of-sequence token ID               */
    uint8_t  reserved[8];     /* Reserved for future use (zero-filled)  */
} xmtk_header_t;

_Static_assert(sizeof(xmtk_header_t) == 32, "XMTK header must be 32 bytes");

/* =====================================================================
 * S2  XMTK MERGE ENTRY (on-disk layout for merge table)
 * =====================================================================
 *
 * Each merge rule maps (left_id, right_id) -> merged_id.
 * Merges are ordered by priority (index 0 = highest priority).
 */

typedef struct __attribute__((packed)) {
    uint32_t left_id;         /* Left token ID in the merge pair        */
    uint32_t right_id;        /* Right token ID in the merge pair       */
    uint32_t merged_id;       /* Resulting merged token ID              */
} xmtk_merge_t;

_Static_assert(sizeof(xmtk_merge_t) == 12, "XMTK merge entry must be 12 bytes");

/* =====================================================================
 * S3  XMTK VALIDATION HELPERS
 * ===================================================================== */

/**
 * xmtk_validate_magic -- check if header has correct magic bytes.
 * Returns 1 on valid, 0 on invalid.
 */
static inline int xmtk_validate_magic(const xmtk_header_t *hdr)
{
    return (hdr != (void *)0) && (hdr->magic == XMTK_MAGIC);
}

/**
 * xmtk_validate_header -- full sanity check on a loaded tokenizer header.
 * Returns 1 on valid, 0 on invalid.
 */
static inline int xmtk_validate_header(const xmtk_header_t *hdr)
{
    if (!xmtk_validate_magic(hdr))
        return 0;
    if (hdr->version == 0 || hdr->version > XMTK_VERSION)
        return 0;
    if (hdr->vocab_size == 0 || hdr->vocab_size > 262144u)
        return 0;
    /* n_merges can be 0 for character-level tokenizers */
    if (hdr->n_merges > hdr->vocab_size)
        return 0;  /* Cannot have more merges than vocab entries */
    if (hdr->bos_id >= hdr->vocab_size)
        return 0;
    if (hdr->eos_id >= hdr->vocab_size)
        return 0;
    return 1;
}

/**
 * xmtk_validate_merge -- check if a merge entry references valid token IDs.
 * Returns 1 on valid, 0 on invalid.
 */
static inline int xmtk_validate_merge(
    const xmtk_merge_t *merge,
    uint32_t vocab_size
)
{
    if (merge == (void *)0)
        return 0;
    if (merge->left_id >= vocab_size)
        return 0;
    if (merge->right_id >= vocab_size)
        return 0;
    if (merge->merged_id >= vocab_size)
        return 0;
    return 1;
}

#endif /* XMTK_H */
