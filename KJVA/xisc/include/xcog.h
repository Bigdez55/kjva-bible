/*
 * xcog.h — Consumer-build XCOG cognitive opcode shim.
 * Covers the API surface used by r1_per.c + context_bridge.c.
 */
#ifndef GENOS_XCOG_SHIM_H
#define GENOS_XCOG_SHIM_H

#include "pal.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ── Top-level opcodes (xcog_op_t / xcog_opcode_t — both names used) ─ */
typedef uint8_t xcog_op_t;
typedef uint8_t xcog_opcode_t;

#define XCOG_OP_NOP        0x00
#define XCOG_OP_PERCEIVE   0x10
#define XCOG_OP_TOKENIZE   0x11
#define XCOG_OP_CONTEXT    0x12
#define XCOG_OP_REASON     0x20
#define XCOG_OP_GENERATE   0x30
#define XCOG_OP_VERIFY     0x40
#define XCOG_OP_EMIT       0x50
#define XCOG_OP_EQ         0x60
#define XCOG_OP_HALT       0xFF

/* ── R1_PER opcode categories ───────────────────────────────────── */
#define XCOG_INTENT            0x80
#define XCOG_ENTITY            0x81
#define XCOG_CONTEXT           0x82
#define XCOG_MODALITY          0x83
#define XCOG_TEMPORAL          0x84
#define XCOG_SALIENCE          0x85
#define XCOG_NEGATE            0x86
#define XCOG_QUANTIFY          0x87
#define XCOG_COMPOUND          0x88
#define XCOG_REFERENCE         0x89
#define XCOG_PREDICATE         0x8A
#define XCOG_SEQUENCE          0x8B
#define XCOG_FILTER            0x8C
#define XCOG_DIVERGENCE        0x8D
#define XCOG_ESCALATION        0x8E
#define XCOG_FALLBACK          0x8F
#define XCOG_ENCODE            0x90
#define XCOG_EMIT              0x91

/* ── Intent subtypes ────────────────────────────────────────────── */
#define XCOG_INTENT_QUERY      0x01
#define XCOG_INTENT_COMMAND    0x02
#define XCOG_INTENT_NAVIGATE   0x03
#define XCOG_INTENT_CREATE     0x04
#define XCOG_INTENT_MODIFY     0x05
#define XCOG_INTENT_DELETE     0x06
#define XCOG_INTENT_ANALYZE    0x07
#define XCOG_INTENT_CONVERSE   0x08
#define XCOG_INTENT_CONFIGURE  0x09

/* ── Entity types ───────────────────────────────────────────────── */
#define XCOG_ENT_TEXT_FRAGMENT  0x01
#define XCOG_ENT_USER_SELF      0x02
#define XCOG_ENT_USER_OTHER     0x03
#define XCOG_ENT_FILE           0x04
#define XCOG_ENT_DIRECTORY      0x05
#define XCOG_ENT_APP            0x06
#define XCOG_ENT_DEVICE         0x07
#define XCOG_ENT_SETTING        0x08
#define XCOG_ENT_DATE           0x09
#define XCOG_ENT_TIME           0x0A
#define XCOG_ENT_DURATION       0x0B
#define XCOG_ENT_NUMBER         0x0C
#define XCOG_ENT_EMAIL          0x0D
#define XCOG_ENT_CONTACT        0x0E
#define XCOG_ENT_EVENT          0x0F
#define XCOG_ENT_PROCESS        0x10
#define XCOG_ENT_PASSTHROUGH    0xFF

/* ── Generic instruction record (8 bytes, used by R1_PER) ───────── */
typedef struct {
    uint8_t  opcode;    /* top-level category (XCOG_INTENT, XCOG_ENTITY, …) */
    uint8_t  subtype;   /* intent/entity sub-category */
    uint8_t  payload;   /* confidence or small inline value (0-255) */
    uint8_t  reserved;
    uint32_t ref;       /* reference id (token offset, entity index, …) */
} xcog_instr_t;

#define XCOG_INSTR(_op, _sub, _pay, _ref) \
    ((xcog_instr_t){ .opcode=(_op), .subtype=(_sub), .payload=(_pay), .reserved=0, .ref=(_ref) })

/* ── Routing helper (used by context_bridge) ────────────────────── */
#define XCOG_IS_ROUTING(op) ((op) == XCOG_INTENT || (op) == XCOG_ESCALATION)

#ifdef __cplusplus
}
#endif
#endif
