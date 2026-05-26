/*
 * xmind_telemetry.h — XMIND → Council Bidirectional Telemetry
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Closes Seam 2: bidirectional telemetry between XMIND (C, per-token,
 *   microseconds) and Council daemons (Python, per-request, seconds).
 *
 *   XMIND emits telemetry after each inference cycle to:
 *   (1) XSEC audit ring — via causal_log_cog.h event types (local)
 *   (2) Council daemon mesh — via XNET socket (IPC)
 *
 *   Conforms to FROZEN Sprint 49 contracts: causal_log_cog.h.
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef XMIND_TELEMETRY_H
#define XMIND_TELEMETRY_H

#ifdef PAL_FREESTANDING
#include "../../pal/include/pal.h"
#else
#include <stdint.h>
#endif

/* Full type from xmind_heptagon.h — needed for const xmind_heptagon_t* param */
#include "xmind_heptagon.h"

/* ═══════════════════════════════════════════════════════════════════════
 * §1  TELEMETRY PACKET — Emitted after each inference cycle
 * ═══════════════════════════════════════════════════════════════════════ */

#define XMIND_TELEMETRY_MAGIC  0x584D544Cu  /* "XMTL" */

typedef struct __attribute__((packed)) {
    uint32_t  magic;               /* XMIND_TELEMETRY_MAGIC              */
    uint64_t  timestamp_ns;        /* pal_time_now_ns() at emission      */
    uint32_t  session_id;          /* Inference session identifier        */
    uint16_t  tokens_generated;    /* Token count this cycle              */
    uint16_t  intent_code;         /* From R1_PER signal or 0             */
    float     eval_score;          /* L5 evaluation score (0.0-1.0)      */
    float     avg_confidence;      /* L4 per-token mean confidence        */
    float     attention_entropy;   /* L4 attention distribution entropy   */
    uint32_t  invariant_violations;/* L7 violation count this cycle       */
    uint8_t   safety_halted;       /* 1 if L7 stopped generation          */
    uint8_t   fallback_used;       /* 1 if R1_PER fell back to raw text   */
    uint8_t   input_hash[32];      /* From r1_per_signal_t (audit chain)  */
    uint8_t   _pad[2];             /* Alignment                           */
} xmind_telemetry_packet_t;

/* ═══════════════════════════════════════════════════════════════════════
 * §2  TELEMETRY API
 * ═══════════════════════════════════════════════════════════════════════ */

/*
 * xmind_telemetry_emit — Emit telemetry packet.
 *
 * Writes to:
 *   1. XSEC audit ring (causal_log_cog.h: XSEC_AUDIT_XCOG_ENCODE event)
 *   2. Council daemon XNET socket (if telemetry_fd >= 0 in heptagon)
 *
 * Uses the same IPC pattern as council_gate_runner.c (JSON-framed TCP).
 */
void xmind_telemetry_emit(const xmind_heptagon_t *h,
                           const xmind_telemetry_packet_t *pkt);

/*
 * xmind_telemetry_register_consumer — Connect to Council daemon.
 *
 * Opens an XNET socket to the Council telemetry aggregator.
 * Returns socket fd on success, -1 on failure (telemetry silently disabled).
 */
int xmind_telemetry_register_consumer(const char *host, uint16_t port);

#endif /* XMIND_TELEMETRY_H */
