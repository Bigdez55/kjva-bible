/*
 * writeback.c — Memory Bridge Write-Back (ADR-S49-01 Phase 3)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Implements write-back APIs for retained learning consolidation.
 * Uses IPC to SoulManager (port 18610), Citadel Archives (port 18611),
 * and EventJournal (port 18612) via the same XNET fabric as
 * context_bridge.c.
 *
 * QUALITY GATE ENFORCEMENT:
 *   - improvement_score < 0.3 -> rejection (XM_WB_NONE forced)
 *   - mastery_reached < 1 -> soul-only (no archive write)
 *   - evidence_count < 3 -> no generation advancement
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"
#include "../include/xmind_writeback.h"

/* ===================================================================
 * S1  INTERNAL HELPERS
 * =================================================================== */

/* Zero a block of memory */
static void wb_memzero(void *dst, uint64_t n)
{
    uint8_t *p = (uint8_t *)dst;
    uint64_t i;
    for (i = 0u; i < n; i++) {
        p[i] = 0u;
    }
}

/* Copy bytes */
static void wb_memcpy(void *dst, const void *src, uint64_t n)
{
    uint8_t       *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;
    uint64_t i;
    for (i = 0u; i < n; i++) {
        d[i] = s[i];
    }
}

/* ===================================================================
 * S2  XNET IPC STUBS
 *
 * These wrap the XNET socket layer for write-back IPC.
 * In the current sprint, XNET sockets may not be fully wired in the
 * freestanding kernel.  We provide a complete implementation that
 * builds the wire-format message and attempts IPC.  If the XNET
 * stack is not yet available, the functions return -1 (IPC failure)
 * which is handled gracefully by the consolidation logic.
 *
 * Wire format:
 *   [xm_wb_msg_header_t (16 bytes)] [payload (variable)]
 * =================================================================== */

/* PAL §15 Network I/O — now declared in pal.h (included via xmind.h) */

/*
 * wb_ipc_send — Send a write-back message to a target port.
 *
 * Builds the header, connects to localhost:port, sends header + payload,
 * then closes the connection.
 *
 * Returns 0 on success, -1 on connection failure, -2 on send failure.
 */
static int wb_ipc_send(uint16_t port,
                        uint16_t msg_type,
                        uint32_t session_id,
                        const uint8_t *payload,
                        uint32_t payload_size)
{
    xm_wb_msg_header_t hdr;
    pal_handle_t       sock = PAL_HANDLE_INVALID;
    pal_status_t       ps;
    uint32_t           written = 0u;

    hdr.magic        = XM_WB_MSG_MAGIC;
    hdr.version      = XM_WB_MSG_VERSION;
    hdr.msg_type     = msg_type;
    hdr.payload_size = payload_size;
    hdr.session_id   = session_id;

    ps = pal_net_connect("127.0.0.1", port, 5000u, &sock);
    if (ps != PAL_OK) {
        return -1;
    }

    ps = pal_net_write(sock, &hdr, (uint32_t)sizeof(hdr), &written);
    if (ps != PAL_OK) {
        pal_net_close(sock);
        return -2;
    }

    if (payload && payload_size > 0u) {
        ps = pal_net_write(sock, payload, payload_size, &written);
        if (ps != PAL_OK) {
            pal_net_close(sock);
            return -2;
        }
    }

    pal_net_close(sock);
    return 0;
}

/* ===================================================================
 * S3  JOURNAL WIRE FORMAT
 *
 * The journal entry is a compact binary record appended to the
 * EventJournal via IPC.  The journal assigns an event_id on receipt.
 * =================================================================== */

typedef struct __attribute__((packed)) {
    uint32_t session_id;
    uint16_t domain_id;
    uint8_t  mastery_reached;
    uint8_t  accepted;
    /* improvement_score as 4 bytes (IEEE 754) */
    float    improvement_score;
} wb_journal_entry_t;

_Static_assert(sizeof(wb_journal_entry_t) == 12u,
               "journal entry must be 12 bytes");

/* ===================================================================
 * S4  SOUL WRITE-BACK WIRE FORMAT
 *
 * Sent to SoulManager: input_hash (32 bytes) + delta_data (variable).
 * =================================================================== */

#define WB_SOUL_HASH_SIZE  32u

/* ===================================================================
 * S5  ARCHIVE WRITE-BACK WIRE FORMAT
 *
 * Sent to Citadel Archives: domain_id (2 bytes) + input_hash (32 bytes)
 * + delta_data (variable).
 * =================================================================== */

typedef struct __attribute__((packed)) {
    uint16_t domain_id;
    uint8_t  input_hash[32];
} wb_archive_prefix_t;

_Static_assert(sizeof(wb_archive_prefix_t) == 34u,
               "archive prefix must be 34 bytes");

/* ===================================================================
 * S6  PUBLIC API: xmind_context_writeback_soul
 * =================================================================== */

int xmind_context_writeback_soul(uint32_t session_id,
                                  const uint8_t *delta_data,
                                  uint32_t delta_size,
                                  const uint8_t *input_hash)
{
    uint8_t *payload;
    uint32_t total;
    int rc;

    if (!delta_data || delta_size == 0u || !input_hash) {
        return -1;
    }

    /* Payload: [input_hash (32)] [delta_data (N)] */
    total = WB_SOUL_HASH_SIZE + delta_size;
    payload = (uint8_t *)xm_heap_alloc((uint64_t)total);
    if (!payload) {
        return -1;
    }

    wb_memcpy(payload, input_hash, WB_SOUL_HASH_SIZE);
    wb_memcpy(payload + WB_SOUL_HASH_SIZE, delta_data, delta_size);

    rc = wb_ipc_send(XM_WB_PORT_SOUL, 0u, session_id, payload, total);

    xm_heap_free(payload);
    return rc;
}

/* ===================================================================
 * S7  PUBLIC API: xmind_context_writeback_archive
 * =================================================================== */

int xmind_context_writeback_archive(uint32_t session_id,
                                     uint16_t domain_id,
                                     const uint8_t *delta_data,
                                     uint32_t delta_size,
                                     const uint8_t *input_hash)
{
    uint8_t *payload;
    uint32_t total;
    wb_archive_prefix_t prefix;
    int rc;

    if (!delta_data || delta_size == 0u || !input_hash) {
        return -1;
    }

    /* Build prefix */
    prefix.domain_id = domain_id;
    wb_memcpy(prefix.input_hash, input_hash, 32u);

    /* Payload: [prefix (34)] [delta_data (N)] */
    total = (uint32_t)sizeof(prefix) + delta_size;
    payload = (uint8_t *)xm_heap_alloc((uint64_t)total);
    if (!payload) {
        return -1;
    }

    wb_memcpy(payload, &prefix, sizeof(prefix));
    wb_memcpy(payload + sizeof(prefix), delta_data, delta_size);

    rc = wb_ipc_send(XM_WB_PORT_ARCHIVE, 1u, session_id, payload, total);

    xm_heap_free(payload);
    return rc;
}

/* ===================================================================
 * S8  PUBLIC API: xmind_context_writeback_journal
 * =================================================================== */

int xmind_context_writeback_journal(uint32_t session_id,
                                     uint16_t domain_id,
                                     float improvement_score,
                                     uint8_t mastery_reached,
                                     uint8_t accepted,
                                     uint32_t *out_event_id)
{
    wb_journal_entry_t entry;
    int rc;

    if (!out_event_id) {
        return -1;
    }

    entry.session_id        = session_id;
    entry.domain_id         = domain_id;
    entry.mastery_reached   = mastery_reached;
    entry.accepted          = accepted;
    entry.improvement_score = improvement_score;

    rc = wb_ipc_send(XM_WB_PORT_JOURNAL, 2u, session_id,
                      (const uint8_t *)&entry, (uint32_t)sizeof(entry));

    if (rc == 0) {
        /* EventJournal assigns event_id.  In the current sprint,
         * we use a monotonic counter as the journal does not yet
         * return the ID via IPC response.  This will be upgraded
         * to a request-response pattern when XNET bidirectional
         * sockets are wired. */
        static uint32_t s_wb_event_seq = 1u;
        *out_event_id = s_wb_event_seq;
        s_wb_event_seq++;
    } else {
        *out_event_id = 0u;
    }

    return rc;
}

/* ===================================================================
 * S9  PUBLIC API: xmind_context_consolidate
 *
 * Master consolidation entry point.  Enforces quality gates, then
 * dispatches to the appropriate write-back targets.
 * =================================================================== */

int xmind_context_consolidate(const xmind_consolidation_request_t *req,
                               xmind_consolidation_result_t *result)
{
    int rc_soul    = 0;
    int rc_archive = 0;
    int rc_journal = 0;
    uint32_t event_id = 0u;

    if (!req || !result) {
        return -1;
    }

    wb_memzero(result, sizeof(*result));

    /* ── Quality Gate 1: Minimum improvement score ────────────────── */
    if (req->improvement_score < XM_WB_MIN_IMPROVEMENT) {
        result->accepted        = 0u;
        result->event_id        = 0u;
        result->generation_index = 0u;

        /* Still journal the rejection for audit trail */
        rc_journal = xmind_context_writeback_journal(
            req->session_id, req->domain_id,
            req->improvement_score, req->mastery_reached,
            0u, /* accepted = false */
            &event_id);
        result->event_id        = event_id;
        result->journal_written = (rc_journal == 0) ? 1u : 0u;

        return -2; /* Quality reject */
    }

    /* ── Quality Gate 2: Target override ──────────────────────────── */
    if (req->target == XM_WB_NONE) {
        result->accepted = 0u;
        return -2;
    }

    /* ── Accepted: dispatch to targets ────────────────────────────── */
    result->accepted = 1u;

    /* Soul write (private continuity) */
    if (req->target == XM_WB_SOUL_ONLY || req->target == XM_WB_BOTH) {
        if (req->delta_data && req->delta_size > 0u) {
            rc_soul = xmind_context_writeback_soul(
                req->session_id, req->delta_data,
                req->delta_size, req->input_hash);
            result->soul_written = (rc_soul == 0) ? 1u : 0u;
        }
    }

    /* Archive write (shared knowledge) — requires innerstanding */
    if (req->target == XM_WB_ARCHIVE_ONLY || req->target == XM_WB_BOTH) {
        if (req->mastery_reached >= XM_WB_MIN_MASTERY_ARCH &&
            req->delta_data && req->delta_size > 0u) {
            rc_archive = xmind_context_writeback_archive(
                req->session_id, req->domain_id,
                req->delta_data, req->delta_size,
                req->input_hash);
            result->archive_written = (rc_archive == 0) ? 1u : 0u;
        }
        /* If mastery too low, silently skip archive (not an error) */
    }

    /* Journal write (always, for audit trail) */
    rc_journal = xmind_context_writeback_journal(
        req->session_id, req->domain_id,
        req->improvement_score, req->mastery_reached,
        1u, /* accepted = true */
        &event_id);
    result->event_id        = event_id;
    result->journal_written = (rc_journal == 0) ? 1u : 0u;

    /* Generation advancement requires sufficient evidence */
    if (req->evidence_count >= XM_WB_MIN_EVIDENCE_GEN) {
        /* Generation index is managed by the lineage store.
         * Here we report 1 to signal that advancement is warranted.
         * The actual counter is advanced by xmind_lineage_advance_generation(). */
        result->generation_index = 1u;
    } else {
        result->generation_index = 0u;
    }

    /* If all IPC writes failed, report IPC failure */
    if (rc_soul < 0 && rc_archive < 0 && rc_journal < 0) {
        return -1;
    }

    return 0;
}
