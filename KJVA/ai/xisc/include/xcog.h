/*
 * xcog.h — XCOG opcode type stubs for the XISC platform layer.
 *
 * STATUS: PLATFORM STUB — minimal definitions allowing r1_per.h + r1_per.c
 * to compile when the full XISC subsystem is not present in this repo checkout.
 *
 * The real xcog.h is part of the XISC subsystem. This stub preserves the
 * ABI invariant sizeof(xcog_instr_t) == 8 (enforced by r1_per.c:1312).
 *
 * Derived by inspecting r1_per.c usage:
 *   - instr->opcode   (uint8_t, primary opcode selector)
 *   - instr->subtype  (uint8_t, opcode sub-category)
 *   - instr->ref      (uint16_t, reference index or immediate)
 *   - instr->payload  (uint32_t, primary data payload)
 *
 * DO NOT change the struct layout — 8-byte size is an ABI invariant.
 */
#pragma once
#include <stdint.h>

/*
 * xcog_instr_t — single XCOG instruction word (8 bytes).
 */
typedef struct {
    uint8_t  opcode;    /* primary XCOG_* opcode */
    uint8_t  subtype;   /* opcode sub-category (XCOG_INTENT_*, XCOG_ENT_*, etc.) */
    uint16_t ref;       /* reference index / 16-bit immediate */
    uint32_t payload;   /* primary 32-bit data payload */
} xcog_instr_t;

/* ABI size guard (matches r1_per.c:1312) */
typedef char xcog_size_check[(sizeof(xcog_instr_t) == 8) ? 1 : -1];

/* Constructor macro */
#define XCOG_INSTR(op, sub, ref_, payload_) \
    ((xcog_instr_t){(uint8_t)(op), (uint8_t)(sub), (uint16_t)(ref_), (uint32_t)(payload_)})

/* ─── Primary opcodes (first byte of xcog_instr_t) ─────────────────────── */
#define XCOG_INTENT     0x01u   /* Intent classification */
#define XCOG_ENTITY     0x02u   /* Named entity */
#define XCOG_PREDICATE  0x03u   /* Verb-object predicate */
#define XCOG_NEGATE     0x04u   /* Negation marker */
#define XCOG_QUANTIFY   0x05u   /* Quantifier (all, any, none, count) */
#define XCOG_FILTER     0x06u   /* Adjective-noun filter */
#define XCOG_TEMPORAL   0x07u   /* Temporal reference */
#define XCOG_EMIT       0x08u   /* Output directive */
#define XCOG_SALIENCE   0x09u   /* Salience weight annotation */
#define XCOG_CONTEXT    0x0Au   /* Context window reference */
#define XCOG_REFERENCE  0x0Bu   /* Cross-instruction reference */
#define XCOG_SEQUENCE   0x0Cu   /* Instruction ordering constraint */
#define XCOG_COMPOUND   0x0Du   /* Compound expression */
#define XCOG_MODALITY   0x0Eu   /* Modality (question, imperative, conditional) */

/* Routing-domain opcodes (0x80+) — tested by XCOG_IS_ROUTING() */
#define XCOG_OP_EQ      0x80u   /* Equality routing condition */
#define XCOG_OP_        0x81u   /* Routing opcode base (unspecified) */
#define XCOG_IS_ROUTING(op)  ((uint8_t)(op) >= 0x80u)

/* ─── Intent subtypes (XCOG_INTENT.subtype) ─────────────────────────────── */
#define XCOG_INTENT_CONVERSE    0x00u   /* General conversation */
#define XCOG_INTENT_NAVIGATE    0x01u   /* Navigate to a location / resource */
#define XCOG_INTENT_QUERY       0x02u   /* Information query */
#define XCOG_INTENT_CREATE      0x03u   /* Create an entity */
#define XCOG_INTENT_DELETE      0x04u   /* Delete an entity */
#define XCOG_INTENT_MODIFY      0x05u   /* Modify an entity */
#define XCOG_INTENT_CONFIGURE   0x06u   /* Configure a setting */
#define XCOG_INTENT_ANALYZE     0x07u   /* Analyze / explain */
#define XCOG_INTENT_COMMAND     0x08u   /* Execute a system command */
#define XCOG_INTENT_            0xFFu   /* Unresolved intent */

/* ─── Entity subtypes (XCOG_ENTITY.subtype) ──────────────────────────────── */
#define XCOG_ENT_FILE           0x01u
#define XCOG_ENT_DIRECTORY      0x02u
#define XCOG_ENT_APP            0x03u
#define XCOG_ENT_CONTACT        0x04u
#define XCOG_ENT_EMAIL          0x05u
#define XCOG_ENT_EVENT          0x06u
#define XCOG_ENT_DATE           0x07u
#define XCOG_ENT_TIME           0x08u
#define XCOG_ENT_DURATION       0x09u
#define XCOG_ENT_DEVICE         0x0Au
#define XCOG_ENT_PROCESS        0x0Bu
#define XCOG_ENT_SETTING        0x0Cu
#define XCOG_ENT_NUMBER         0x0Du
#define XCOG_ENT_TEXT_FRAGMENT  0x0Eu
#define XCOG_ENT_USER_SELF      0x0Fu
#define XCOG_ENT_USER_OTHER     0x10u
#define XCOG_ENT_PASSTHROUGH    0xFFu   /* Unclassified / pass-through */
