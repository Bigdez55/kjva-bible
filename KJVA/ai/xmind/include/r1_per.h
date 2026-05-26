/*
 * r1_per.h — R1_PER Perception Layer Binary Signal Contract
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Defines the binary contract between the Heptagon R1_PER perception
 *   layer and the XMIND inference engine.  The r1_per_signal_t structure
 *   carries a stream of XCOG cognitive opcodes (typed binary semantic
 *   encoding of user input), salience scores, compressed context shards,
 *   and a tamper-evident dual hash.
 *
 * FRAMING (load-bearing):
 *   R1_PER performs LOSSLESS SEMANTIC ENCODING, not lossy reduction.
 *   The model receives equivalent meaning at higher information density
 *   per bit.  Every bit that reaches the inference engine is semantically
 *   load-bearing.  Zero bits are wasted on syntax, grammar, or linguistic
 *   convention.  Any quality degradation is a BUG in R1_PER — not an
 *   expected tradeoff.  L5.2 anti-Goodhart enforces this via the
 *   (r1_per_encoding_fidelity, task_completion_quality) cross-metric pair.
 *
 * SECURITY:
 *   Typed XCOG opcodes structurally prevent prompt injection.  The model
 *   never receives raw text from untrusted sources — only typed binary
 *   structures from R1_PER.  Document content is encoded as
 *   XCOG_ENTITY(TEXT_FRAGMENT), never as instructions.
 *
 *   Dual hash: input_hash (SHA-256 of original NL) + output_hash (SHA-256
 *   of XCOG instruction stream) creates a tamper-evident encoding chain.
 *
 * DATA FLOW:
 *   User NL → R1_PER Stage 1 (lexical) → Stage 2 (semantic parse)
 *           → Stage 3 (XCOG compile) → Stage 4 (RT4 context resolve)
 *           → r1_per_signal_t → XMIND inference
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef R1_PER_H
#define R1_PER_H

#ifdef PAL_FREESTANDING
#include "../../pal/include/pal.h"
#else
#include <stdint.h>
#endif

#include "../../xisc/include/xcog.h"

/* ═══════════════════════════════════════════════════════════════════════
 * §1  CONSTANTS
 * ═══════════════════════════════════════════════════════════════════════ */

#define R1_PER_MAGIC               0x52315045u  /* "R1PE" (little-endian)     */
#define R1_PER_VERSION             1u
#define R1_PER_MAX_INSTRUCTIONS    64u          /* Max XCOG instructions      */
#define R1_PER_MAX_CONTEXT_SHARDS  7u           /* Law of seven               */

/* Stage completion flags (stage_flags bitmask) */
#define R1_STAGE_LEXICAL    (1u << 0)  /* Stage 1: POS tagging complete      */
#define R1_STAGE_SEMANTIC   (1u << 1)  /* Stage 2: Dependency parse complete  */
#define R1_STAGE_COMPILED   (1u << 2)  /* Stage 3: XCOG compilation complete  */
#define R1_STAGE_RESOLVED   (1u << 3)  /* Stage 4: Context resolution done    */

/* Source channel identifiers */
#define R1_SOURCE_KEYBOARD  0u
#define R1_SOURCE_VOICE     1u
#define R1_SOURCE_API       2u
#define R1_SOURCE_DOCUMENT  3u
#define R1_SOURCE_CLIPBOARD 4u
#define R1_SOURCE_SYSTEM    5u

/* ═══════════════════════════════════════════════════════════════════════
 * §2  R1_PER SIGNAL STRUCTURE
 *
 * The complete output of the R1_PER perception pipeline.
 * This is the binary contract between perception and inference.
 * ═══════════════════════════════════════════════════════════════════════ */

typedef struct __attribute__((packed)) {
    /* ── Header ──────────────────────────────────────────────────────── */
    uint32_t  magic;                /* R1_PER_MAGIC (0x52315045)          */
    uint8_t   version;              /* R1_PER_VERSION                     */
    uint8_t   stage_flags;          /* Which pipeline stages completed    */
    uint16_t  instruction_count;    /* Number of XCOG instructions (≤64)  */

    /* ── Cognitive instruction stream ────────────────────────────────── */
    xcog_instr_t instructions[R1_PER_MAX_INSTRUCTIONS]; /* 64 × 8 = 512B */

    /* ── Context shards (RT4 salience-filtered) ─────────────────────── */
    uint16_t  context_shard_count;  /* Number of attached context shards  */
    uint32_t  context_total_size;   /* Total bytes of all shard payloads  */
    /* Shard data follows the signal in a separate buffer (not inline).
     * context_total_size bytes, AIT-compressed when available.
     * Referenced via vDRAM handle in the XCOG_CONTEXT instruction.     */

    /* ── Per-instruction salience scores ─────────────────────────────── */
    uint16_t  salience_scores[R1_PER_MAX_INSTRUCTIONS]; /* 0..65535 fp   */

    /* ── Tamper-evident dual hash ────────────────────────────────────── */
    uint8_t   input_hash[32];       /* SHA-256 of original NL input       */
    uint8_t   output_hash[32];      /* SHA-256 of instruction stream      */

    /* ── Audit metadata ──────────────────────────────────────────────── */
    uint64_t  timestamp_ns;         /* pal_time_now_ns() at encoding      */
    uint8_t   source_channel;       /* R1_SOURCE_* identifier             */
    uint8_t   fallback_flag;        /* 1 = R1_PER fell back to raw text   */
    uint16_t  _pad;                 /* Alignment padding                  */
} r1_per_signal_t;

/* Verify struct size is reasonable (should be < 1 KB) */
_Static_assert(sizeof(r1_per_signal_t) < 1024,
    "r1_per_signal_t exceeds 1 KB — check packing");

/* ═══════════════════════════════════════════════════════════════════════
 * §3  R1_PER API SURFACE
 *
 * These functions are implemented in ai/xmind/src/r1_per.c (Sprint 50).
 * Declared here so XMIND and GENSD can compile against the contract now.
 * ═══════════════════════════════════════════════════════════════════════ */

/*
 * r1_per_init — Initialize the perception pipeline.
 * Called from GENSD after XMIND is ready.  Loads entity registry,
 * initializes the POS tagger FSM, and prepares the decision tree.
 */
void r1_per_init(void);

/*
 * r1_per_encode — Convert natural language to XCOG binary stream.
 *
 * @param nl_input  UTF-8 natural language string
 * @param nl_len    Byte length of nl_input
 * @param out       Output signal structure (caller-allocated)
 * @return          0 on success, negative on error
 *
 * If encoding confidence is below the fallback threshold (L3.8
 * CognitiveEngine.fallback_threshold), sets fallback_flag=1 and
 * the signal contains a single XCOG_INTENT(CONVERSE) instruction
 * with the original text passed through to the tokenizer.
 */
int r1_per_encode(const char *nl_input, uint32_t nl_len,
                  r1_per_signal_t *out);

/*
 * r1_per_translate_to_tokens — Convert XCOG binary stream to token IDs.
 *
 * Translation layer (Architecture Option B): maps XCOG instructions to
 * a minimal token sequence that the standard XMIND BPE tokenizer can
 * process.  This allows existing model weights to consume R1_PER output
 * without model retraining.
 *
 * Model-agnostic: accepts a tokenizer config pointer so the translation
 * works with any model's vocabulary (Llama 3.2, Qwen3, XMIND-1, etc.).
 * The model_config is opaque — cast to xmind_config_t* internally.
 *
 * @param signal       Input R1_PER signal
 * @param model_config Opaque pointer to model config (xmind_config_t*)
 *                     for vocab_size, special token IDs, etc.
 *                     NULL = use default Llama 3.2 vocab assumptions.
 * @param token_ids    Output token ID array (caller-allocated)
 * @param max_tokens   Maximum tokens to produce
 * @param out_count    Number of tokens actually produced
 * @return             0 on success, negative on error
 */
int r1_per_translate_to_tokens(const r1_per_signal_t *signal,
                               const void *model_config,
                               uint32_t *token_ids, uint32_t max_tokens,
                               uint32_t *out_count);

/*
 * r1_per_verify — Verify signal integrity via dual hash.
 *
 * Recomputes SHA-256 of the instruction stream and compares against
 * output_hash.  Returns 0 if valid, -1 if tampered.
 */
int r1_per_verify(const r1_per_signal_t *signal);

#endif /* R1_PER_H */
