/*
 * xmind_model_spec.h -- XMIND-1 Native Model Architecture Specification
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Defines the XMIND-1 model architecture constants and the XMWF
 *   (XMIND Weight Format) binary header. XMIND-1 is the first model
 *   trained on Tokenless Models's own BPE vocabulary (ASCII-first, 32K tokens)
 *   with a 24-layer GQA transformer architecture.
 *
 *   This header is freestanding: no libc, no stdlib, only stdint via PAL.
 *
 * XMWF FORMAT (binary, little-endian):
 *   Offset 0x00: xmwf_header_t (64 bytes)
 *   Offset 0x40: token embeddings  [vocab_size * hidden_dim * quant_bpw]
 *   Offset varies: per-layer weights (attention + FFN)
 *   Offset varies: output norm + lm_head
 *
 * RELATIONSHIP TO xmind.h:
 *   xmind.h defines the runtime engine (128K Llama-3.2 vocab, configurable).
 *   This header defines the XMIND-1 NATIVE model spec (32K own-BPE vocab).
 *   The runtime loads either format; this header provides the constants
 *   for the native architecture target.
 */

#ifndef XMIND_MODEL_SPEC_H
#define XMIND_MODEL_SPEC_H

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "../../../pal/include/pal.h"

/* =====================================================================
 * S1  XMIND-1 ARCHITECTURE CONSTANTS
 * =====================================================================
 *
 * 24-layer GQA transformer, 1024 hidden, 4:1 KV-head ratio.
 * Designed for inference on HP EliteBook x360 (16 GB RAM, no GPU).
 *
 * Parameter count estimate (fp16):
 *   Embeddings: 32768 * 1024 = 33.5M
 *   Per-layer:  ~4.2M * 24  = 100.8M
 *   Output:     ~33.5M
 *   Total:      ~168M params (~336 MB fp16, ~84 MB Q4_0)
 */

#define XMIND1_VOCAB_SIZE      32768u    /* Own BPE, ASCII-first           */
#define XMIND1_N_LAYERS        24u       /* Transformer layers             */
#define XMIND1_N_HEADS         16u       /* Query attention heads          */
#define XMIND1_N_KV_HEADS      4u        /* Key/Value heads (GQA 4:1)     */
#define XMIND1_HIDDEN_DIM      1024u     /* Model hidden dimension        */
#define XMIND1_FFN_DIM         2816u     /* FFN intermediate (~2.75x)     */
#define XMIND1_MAX_SEQ         4096u     /* Maximum sequence length       */
#define XMIND1_ROPE_BASE       100000.0f /* RoPE theta base frequency     */
#define XMIND1_HEAD_DIM        (XMIND1_HIDDEN_DIM / XMIND1_N_HEADS) /* 64 */
#define XMIND1_GQA_RATIO       (XMIND1_N_HEADS / XMIND1_N_KV_HEADS) /* 4 */

/* Special token IDs for XMIND-1 BPE vocabulary */
#define XMIND1_BOS_ID          1u        /* <s> begin-of-sequence         */
#define XMIND1_EOS_ID          2u        /* </s> end-of-sequence          */
#define XMIND1_PAD_ID          0u        /* <pad> padding                 */
#define XMIND1_UNK_ID          3u        /* <unk> unknown                 */

/* RMSNorm epsilon (matches Llama family convention) */
#define XMIND1_NORM_EPS        1e-5f

/* =====================================================================
 * S2  XMWF (XMIND WEIGHT FORMAT) HEADER
 * =====================================================================
 *
 * 64-byte fixed header at offset 0 of every .xmwf file.
 * All fields are little-endian. Magic is 0x584D5746 ("XMWF" ASCII).
 *
 * Quantization field:
 *   0 = fp32   (4 bytes/param)
 *   1 = fp16   (2 bytes/param)
 *   2 = q8_0   (1 byte/param + 2-byte scale per 32-block)
 *   3 = q4_0   (0.5 byte/param + 2-byte scale per 32-block)
 *   4 = q4_k_m (mixed 4-bit with importance scaling)
 */

#define XMWF_MAGIC    0x584D5746u  /* "XMWF" in little-endian           */
#define XMWF_VERSION  1u           /* Current format version             */

/* Quantization type constants */
#define XMWF_QUANT_FP32    0u
#define XMWF_QUANT_FP16    1u
#define XMWF_QUANT_Q8_0    2u
#define XMWF_QUANT_Q4_0    3u
#define XMWF_QUANT_Q4_K_M  4u

typedef struct __attribute__((packed)) {
    uint32_t magic;           /* XMWF_MAGIC (0x584D5746)               */
    uint32_t version;         /* Format version (currently 1)           */
    uint32_t vocab_size;      /* Vocabulary size                        */
    uint32_t n_layers;        /* Number of transformer layers           */
    uint32_t n_heads;         /* Number of query attention heads        */
    uint32_t n_kv_heads;      /* Number of KV attention heads (GQA)    */
    uint32_t hidden_dim;      /* Hidden dimension                       */
    uint32_t ffn_dim;         /* FFN intermediate dimension             */
    uint32_t max_seq;         /* Maximum sequence length                */
    float    rope_base;       /* RoPE base frequency                    */
    uint32_t quantization;    /* Quantization type (XMWF_QUANT_*)      */
    uint32_t bos_id;          /* Begin-of-sequence token ID             */
    uint32_t eos_id;          /* End-of-sequence token ID               */
    uint32_t pad_id;          /* Padding token ID                       */
    uint8_t  reserved[8];     /* Reserved for future use (zero-filled)  */
} xmwf_header_t;

_Static_assert(sizeof(xmwf_header_t) == 64, "XMWF header must be 64 bytes");

/* =====================================================================
 * S3  XMWF VALIDATION HELPERS
 * ===================================================================== */

/**
 * xmwf_validate_magic -- check if header has correct magic bytes.
 * Returns 1 on valid, 0 on invalid.
 */
static inline int xmwf_validate_magic(const xmwf_header_t *hdr)
{
    return (hdr != (void *)0) && (hdr->magic == XMWF_MAGIC);
}

/**
 * xmwf_validate_header -- full sanity check on a loaded header.
 * Returns 1 on valid, 0 on invalid.
 */
static inline int xmwf_validate_header(const xmwf_header_t *hdr)
{
    if (!xmwf_validate_magic(hdr))
        return 0;
    if (hdr->version == 0 || hdr->version > XMWF_VERSION)
        return 0;
    if (hdr->vocab_size == 0 || hdr->vocab_size > 262144u)
        return 0;
    if (hdr->n_layers == 0 || hdr->n_layers > 128u)
        return 0;
    if (hdr->n_heads == 0 || hdr->n_kv_heads == 0)
        return 0;
    if (hdr->n_heads % hdr->n_kv_heads != 0)
        return 0;  /* GQA ratio must be integer */
    if (hdr->hidden_dim == 0 || hdr->hidden_dim % hdr->n_heads != 0)
        return 0;  /* hidden_dim must be divisible by n_heads */
    if (hdr->ffn_dim == 0)
        return 0;
    if (hdr->max_seq == 0 || hdr->max_seq > 131072u)
        return 0;
    if (hdr->quantization > XMWF_QUANT_Q4_K_M)
        return 0;
    return 1;
}

/**
 * xmwf_is_xmind1 -- check if header matches the XMIND-1 architecture.
 * Returns 1 if the header describes an XMIND-1 model, 0 otherwise.
 */
static inline int xmwf_is_xmind1(const xmwf_header_t *hdr)
{
    if (!xmwf_validate_header(hdr))
        return 0;
    return (hdr->vocab_size == XMIND1_VOCAB_SIZE) &&
           (hdr->n_layers   == XMIND1_N_LAYERS)   &&
           (hdr->n_heads    == XMIND1_N_HEADS)     &&
           (hdr->n_kv_heads == XMIND1_N_KV_HEADS)  &&
           (hdr->hidden_dim == XMIND1_HIDDEN_DIM)  &&
           (hdr->ffn_dim    == XMIND1_FFN_DIM);
}

#endif /* XMIND_MODEL_SPEC_H */
