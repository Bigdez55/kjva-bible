/*
 * xmind_writeback.h — Memory Bridge Write-Back (ADR-S49-01 Phase 3)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Extends the Memory Bridge (xmind_context.h) with write-back
 *   contracts per ADR Section 9.4.  After an assimilation cycle
 *   completes, retained learning is consolidated and written back
 *   to SoulManager (private continuity) and/or Citadel Archives
 *   (shared knowledge).
 *
 *   This header EXTENDS xmind_context.h — it does NOT replace it.
 *   The read path (xmind_context_retrieve) is unchanged.  This adds
 *   the write path: consolidate, writeback_soul, writeback_archive,
 *   and writeback_journal.
 *
 * DATA FLOW:
 *   XMIND inference completes
 *     -> Heptagon post_inference evaluates output quality
 *     -> xmind_context_consolidate(request, result)
 *         -> if accepted:
 *            -> xmind_context_writeback_soul()   [SoulManager port 18610]
 *            -> xmind_context_writeback_archive() [Citadel port 18611]
 *            -> xmind_context_writeback_journal() [EventJournal port 18612]
 *
 * QUALITY GATE:
 *   improvement_score >= 0.3 required for acceptance.
 *   mastery_reached >= 1 (innerstanding) required for archive write.
 *   evidence_count >= 3 required for generation advancement.
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef XMIND_WRITEBACK_H
#define XMIND_WRITEBACK_H

#ifdef PAL_FREESTANDING
#include "../../../pal/include/pal.h"
#else
#include <stdint.h>
#include <stddef.h>
#endif

/* ===================================================================
 * S1  WRITE-BACK TARGET ENUM
 * =================================================================== */

typedef enum {
    XM_WB_SOUL_ONLY    = 0,  /* Private: SoulManager continuity only     */
    XM_WB_ARCHIVE_ONLY = 1,  /* Shared: Citadel Archives only            */
    XM_WB_BOTH         = 2,  /* Both private and shared                  */
    XM_WB_NONE         = 3   /* Discard -- evaluation negative           */
} xmind_writeback_target_t;

/* ===================================================================
 * S2  IPC PORT CONSTANTS
 *
 * SoulManager, Citadel Archives, and EventJournal each listen on
 * a dedicated XNET port for write-back requests.
 * =================================================================== */

#define XM_WB_PORT_SOUL     18610u  /* SoulManager IPC port              */
#define XM_WB_PORT_ARCHIVE  18611u  /* Citadel Archives IPC port         */
#define XM_WB_PORT_JOURNAL  18612u  /* EventJournal IPC port             */

/* ===================================================================
 * S3  QUALITY GATE THRESHOLDS
 *
 * Hard-coded quality gates for write-back acceptance.
 * These are NOT tunable at runtime — they are integrity invariants.
 * =================================================================== */

#define XM_WB_MIN_IMPROVEMENT    0.3f   /* Minimum improvement_score     */
#define XM_WB_MIN_MASTERY_ARCH   1u     /* innerstanding for archive     */
#define XM_WB_MIN_EVIDENCE_GEN   3u     /* evidence for gen advancement  */

/* ===================================================================
 * S4  CONSOLIDATION REQUEST — What to write back
 * =================================================================== */

typedef struct {
    uint32_t                 session_id;       /* Active session ID        */
    uint16_t                 domain_id;        /* Domain classification    */
    xmind_writeback_target_t target;           /* Where to persist         */
    float                    improvement_score;/* Evidence of benefit 0-1  */
    uint8_t                  mastery_reached;  /* 0=under 1=inner 2=over  */
    uint8_t                  input_hash[32];   /* SHA-256 of input signal  */
    uint32_t                 evidence_count;   /* Supporting evidence      */
    const uint8_t           *delta_data;       /* Retained delta payload   */
    uint32_t                 delta_size;        /* Size of delta payload   */
} xmind_consolidation_request_t;

/* ===================================================================
 * S5  CONSOLIDATION RESULT
 * =================================================================== */

typedef struct {
    uint8_t  accepted;           /* 1 = retained, 0 = rejected            */
    uint32_t event_id;           /* EventJournal record ID                */
    uint32_t generation_index;   /* Lineage generation advanced           */
    uint8_t  soul_written;       /* 1 = SoulManager write succeeded       */
    uint8_t  archive_written;    /* 1 = Archive write succeeded           */
    uint8_t  journal_written;    /* 1 = Journal write succeeded           */
} xmind_consolidation_result_t;

/* ===================================================================
 * S6  IPC MESSAGE HEADER — Wire format for write-back IPC
 *
 * All write-back IPC messages share this 16-byte header.
 * The receiver validates magic + version before processing.
 * =================================================================== */

#define XM_WB_MSG_MAGIC    0x57424B31u  /* "WBK1" little-endian          */
#define XM_WB_MSG_VERSION  1u

typedef struct __attribute__((packed)) {
    uint32_t magic;               /* XM_WB_MSG_MAGIC                     */
    uint16_t version;             /* XM_WB_MSG_VERSION                   */
    uint16_t msg_type;            /* 0=soul, 1=archive, 2=journal        */
    uint32_t payload_size;        /* Bytes following this header          */
    uint32_t session_id;          /* Session this belongs to              */
} xm_wb_msg_header_t;

_Static_assert(sizeof(xm_wb_msg_header_t) == 16u,
               "write-back IPC header must be 16 bytes");

/* ===================================================================
 * S7  PUBLIC API — Write-Back Extensions to Memory Bridge
 * =================================================================== */

/*
 * xmind_context_consolidate — Write back retained learning.
 *
 * Evaluates the consolidation request against quality gates.
 * If accepted, dispatches to the appropriate write-back targets.
 *
 * @param req     Consolidation request
 * @param result  Output result
 * @return        0 on success, -1 on IPC failure, -2 on quality reject
 */
int xmind_context_consolidate(const xmind_consolidation_request_t *req,
                               xmind_consolidation_result_t *result);

/*
 * xmind_context_writeback_soul — Persist to SoulManager.
 *
 * Sends the delta payload to SoulManager via XNET IPC (port 18610).
 *
 * @param session_id    Active session
 * @param delta_data    Delta payload bytes
 * @param delta_size    Size of delta payload
 * @param input_hash    SHA-256 linking to r1_per_signal_t
 * @return              0 on success, negative on IPC error
 */
int xmind_context_writeback_soul(uint32_t session_id,
                                  const uint8_t *delta_data,
                                  uint32_t delta_size,
                                  const uint8_t *input_hash);

/*
 * xmind_context_writeback_archive — Persist to Citadel Archives.
 *
 * Sends the delta payload to Citadel Archives via XNET IPC (port 18611).
 *
 * @param session_id    Active session
 * @param domain_id     Domain classification
 * @param delta_data    Delta payload bytes
 * @param delta_size    Size of delta payload
 * @param input_hash    SHA-256 linking to r1_per_signal_t
 * @return              0 on success, negative on IPC error
 */
int xmind_context_writeback_archive(uint32_t session_id,
                                     uint16_t domain_id,
                                     const uint8_t *delta_data,
                                     uint32_t delta_size,
                                     const uint8_t *input_hash);

/*
 * xmind_context_writeback_journal — Record in EventJournal.
 *
 * Sends a journal entry for this consolidation event (port 18612).
 *
 * @param session_id        Active session
 * @param domain_id         Domain classification
 * @param improvement_score Evidence of benefit
 * @param mastery_reached   Mastery level achieved
 * @param accepted          Whether the consolidation was accepted
 * @param out_event_id      Output: assigned event ID
 * @return                  0 on success, negative on IPC error
 */
int xmind_context_writeback_journal(uint32_t session_id,
                                     uint16_t domain_id,
                                     float improvement_score,
                                     uint8_t mastery_reached,
                                     uint8_t accepted,
                                     uint32_t *out_event_id);

#endif /* XMIND_WRITEBACK_H */
