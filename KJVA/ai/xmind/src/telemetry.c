/*
 * telemetry.c — XMIND → Council Bidirectional Telemetry Emitter
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Closes Seam 2: bidirectional telemetry between XMIND (C, per-token,
 * microseconds) and Council daemons (Python, per-request, seconds).
 *
 * Two emission paths per inference cycle:
 *   (1) XSEC audit ring — via xsec_audit_log() with XSEC_MODULE_COGNITIVE
 *       and XSEC_AUDIT_XCOG_ENCODE.  Always local; never fails silently.
 *   (2) Council daemon mesh — binary packet over XNET socket
 *       (pal_net_write) if telemetry_fd >= 0.  Socket loss degrades
 *       gracefully — inference continues; audit ring is the truth source.
 *
 * Wire format: xmind_telemetry_packet_t serialised as packed binary,
 * prefixed by a 4-byte network-order length field (matches the
 * council_gate_runner.c framing contract).
 *
 * Freestanding C11. No libc. PAL I/O only.
 * Compile: clang -ffreestanding -DPAL_FREESTANDING -Werror -c telemetry.c
 */

#ifdef PAL_FREESTANDING
#include "../../../pal/include/pal.h"
#else
#include <stdint.h>
#endif

#include "../include/xmind_heptagon.h"
#include "../include/xmind_telemetry.h"
#include "../../../sec/xsec/include/causal_log_cog.h"

/* ═══════════════════════════════════════════════════════════════════════
 * XSEC — audit log API (freestanding, only includes pal.h internally)
 * ═══════════════════════════════════════════════════════════════════════ */
#include "../../../sec/xsec/include/xsec.h"

/* PAL §15 Network I/O — now declared in pal.h (included above) */

/* ═══════════════════════════════════════════════════════════════════════
 * §1  Internal string helpers (no libc)
 * ═══════════════════════════════════════════════════════════════════════ */

static uint32_t telem_strlen(const char *s) {
    uint32_t n = 0u;
    while (s[n] != '\0') n++;
    return n;
}

static char *telem_u32_dec(char *buf, uint32_t val) {
    if (val == 0u) { *buf++ = '0'; return buf; }
    char tmp[10]; int32_t i = 0;
    while (val > 0u) { tmp[i++] = (char)('0' + val % 10u); val /= 10u; }
    while (i > 0)    { *buf++ = tmp[--i]; }
    return buf;
}

static char *telem_f32_str(char *buf, float val) {
    if (val < 0.0f) { *buf++ = '-'; val = -val; }
    uint32_t whole = (uint32_t)val;
    uint32_t frac  = (uint32_t)((val - (float)whole) * 100.0f + 0.5f);
    if (frac >= 100u) { whole++; frac = 0u; }
    buf = telem_u32_dec(buf, whole);
    *buf++ = '.';
    *buf++ = (char)('0' + frac / 10u);
    *buf++ = (char)('0' + frac % 10u);
    return buf;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §2  Audit detail formatter
 *
 * Produces: "seq=%u eval=%.2f conf=%.2f halt=%d"
 * Bounded to XSEC_AUDIT_DETAIL_LEN (64 bytes) including NUL.
 * ═══════════════════════════════════════════════════════════════════════ */

#define AUDIT_DETAIL_CAP  64u

static void format_audit_detail(char       *out,
                                 uint32_t    seq,
                                 float       eval,
                                 float       conf,
                                 uint8_t     halt) {
    char *p         = out;
    const char *lim = out + AUDIT_DETAIL_CAP - 1u;

#define TELEM_PUTS(s) do { \
    const char *_s = (s); \
    while (*_s && p < lim) *p++ = *_s++; \
} while (0)

    TELEM_PUTS("seq=");
    { char t[12]; char *e = telem_u32_dec(t, seq); *e = '\0'; TELEM_PUTS(t); }
    TELEM_PUTS(" eval=");
    { char t[16]; char *e = telem_f32_str(t, eval); *e = '\0'; TELEM_PUTS(t); }
    TELEM_PUTS(" conf=");
    { char t[16]; char *e = telem_f32_str(t, conf); *e = '\0'; TELEM_PUTS(t); }
    TELEM_PUTS(" halt=");
    if (p < lim) *p++ = (char)('0' + (halt & 1u));

#undef TELEM_PUTS
    *p = '\0';
}

/* ═══════════════════════════════════════════════════════════════════════
 * §3  Wire serialisation — 4-byte big-endian length prefix + payload
 *
 * Matches the council_gate_runner.c framing contract so the Python
 * Council daemon can frame-read without a custom parser.
 *
 * Frame layout:
 *   [u32 big-endian payload_len][payload_bytes]
 *
 * The payload is the raw packed xmind_telemetry_packet_t bytes.
 * ═══════════════════════════════════════════════════════════════════════ */

static void encode_u32_be(uint8_t *buf, uint32_t val) {
    buf[0] = (uint8_t)(val >> 24);
    buf[1] = (uint8_t)(val >> 16);
    buf[2] = (uint8_t)(val >>  8);
    buf[3] = (uint8_t)(val      );
}

/* ═══════════════════════════════════════════════════════════════════════
 * §4  Public API — xmind_telemetry_emit
 *
 * Two-channel emission:
 *   Channel 1 (always): XSEC audit ring — tamper-evident causal record.
 *   Channel 2 (if fd >= 0): binary framed write to Council daemon socket.
 *
 * On socket write failure the fd is left intact — the next cycle will
 * attempt to write again.  Socket lifecycle is managed by the caller
 * (inference.c session manager); we never reconnect here.
 * ═══════════════════════════════════════════════════════════════════════ */

void xmind_telemetry_emit(const xmind_heptagon_t        *h,
                           const xmind_telemetry_packet_t *pkt) {
    if (h == NULL || pkt == NULL) return;

    /* ── Channel 1: XSEC audit ring ── */
    {
        char detail[AUDIT_DETAIL_CAP];
        format_audit_detail(detail,
                            h->telemetry_seq,
                            pkt->eval_score,
                            pkt->avg_confidence,
                            pkt->safety_halted);

        xsec_audit_log((xsec_audit_event_t)XSEC_AUDIT_XCOG_ENCODE,
                       (xsec_module_id_t)XSEC_MODULE_COGNITIVE,
                       detail);
    }

    /* ── Channel 2: Council daemon XNET socket (best-effort) ──
     * Wire format: 4-byte BE length prefix + UTF-8 JSON payload.
     * Matches the council IPC framing contract so Python daemons
     * can deserialize without a binary struct parser.               */
    if (h->telemetry_fd >= 0) {
        /* Reinterpret the int32 fd as pal_handle_t — the fd value IS the
         * opaque handle token as established by pal_net_connect().       */
        pal_handle_t sock = (pal_handle_t)(uint32_t)h->telemetry_fd;

        /* Build JSON payload into static buffer.
         * Max size: ~256 bytes (well within 512 byte capacity).        */
        char json_buf[512];
        char *p = json_buf;
        const char *lim = json_buf + sizeof(json_buf) - 1u;

        #define TELEM_JSON_PUTS(s) do { \
            const char *_s = (s); \
            while (*_s && p < lim) *p++ = *_s++; \
        } while (0)

        TELEM_JSON_PUTS("{\"msg_type\":\"xmind_telemetry\",\"eval_score\":");
        { char t[16]; char *e = telem_f32_str(t, pkt->eval_score); *e = '\0'; TELEM_JSON_PUTS(t); }
        TELEM_JSON_PUTS(",\"confidence\":");
        { char t[16]; char *e = telem_f32_str(t, pkt->avg_confidence); *e = '\0'; TELEM_JSON_PUTS(t); }
        TELEM_JSON_PUTS(",\"entropy\":");
        { char t[16]; char *e = telem_f32_str(t, pkt->attention_entropy); *e = '\0'; TELEM_JSON_PUTS(t); }
        TELEM_JSON_PUTS(",\"violations\":");
        { char t[12]; char *e = telem_u32_dec(t, pkt->invariant_violations); *e = '\0'; TELEM_JSON_PUTS(t); }
        TELEM_JSON_PUTS(",\"safety_halted\":");
        TELEM_JSON_PUTS(pkt->safety_halted ? "true" : "false");
        TELEM_JSON_PUTS(",\"tokens\":");
        { char t[12]; char *e = telem_u32_dec(t, pkt->tokens_generated); *e = '\0'; TELEM_JSON_PUTS(t); }
        TELEM_JSON_PUTS(",\"input_hash\":\"");
        /* Emit first 8 bytes of input hash as 16 hex chars */
        for (uint32_t hi = 0u; hi < 8u && p + 2 < lim; hi++) {
            uint8_t b = pkt->input_hash[hi];
            const char hex[] = "0123456789abcdef";
            *p++ = hex[(b >> 4) & 0x0Fu];
            *p++ = hex[b & 0x0Fu];
        }
        TELEM_JSON_PUTS("\"}");
        #undef TELEM_JSON_PUTS
        *p = '\0';

        uint32_t json_len = (uint32_t)(p - json_buf);

        /* Build 4-byte BE length header */
        uint8_t hdr[4];
        encode_u32_be(hdr, json_len);

        uint32_t written = 0u;
        pal_status_t rc;

        /* Write length header */
        rc = pal_net_write(sock, hdr, 4u, &written);
        if (rc != PAL_OK || written != 4u) {
            xsec_audit_log(
                (xsec_audit_event_t)XSEC_AUDIT_XCOG_FALLBACK,
                (xsec_module_id_t)XSEC_MODULE_COGNITIVE,
                "telemetry_header_write_fail");
            return;
        }

        /* Write JSON payload */
        written = 0u;
        rc = pal_net_write(sock, json_buf, json_len, &written);
        if (rc != PAL_OK || written != json_len) {
            xsec_audit_log(
                (xsec_audit_event_t)XSEC_AUDIT_XCOG_FALLBACK,
                (xsec_module_id_t)XSEC_MODULE_COGNITIVE,
                "telemetry_payload_write_fail");
        }
    }

    /* ── Advance sequence number ── (non-const — caller must pass mutable h) */
    /* Note: h is declared const in the API to signal we only read fields,
     * but telemetry_seq is a monotonic counter we must advance.
     * Use a const-stripping cast — this is the one sanctioned mutation.  */
    ((xmind_heptagon_t *)h)->telemetry_seq++;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §5  Public API — xmind_telemetry_register_consumer
 *
 * Opens an XNET socket to the Council telemetry aggregator.
 * Returns pal_handle_t value cast to int32_t on success, -1 on failure.
 *
 * Timeout: 5000 ms — enough for a cold-start Council daemon.
 * On failure the caller continues with telemetry disabled; this is
 * intentional graceful degradation (not a critical path).
 * ═══════════════════════════════════════════════════════════════════════ */

int xmind_telemetry_register_consumer(const char *host, uint16_t port) {
    if (host == NULL) return -1;

    pal_handle_t sock = PAL_HANDLE_INVALID;
    pal_status_t rc   = pal_net_connect(host, port, 5000u, &sock);

    if (rc != PAL_OK || sock == PAL_HANDLE_INVALID) {
        xsec_audit_log(
            (xsec_audit_event_t)XSEC_AUDIT_XCOG_FALLBACK,
            (xsec_module_id_t)XSEC_MODULE_COGNITIVE,
            "telemetry_consumer_connect_fail");
        return -1;
    }

    /* Return the handle value as int32 for storage in telemetry_fd.
     * The pal_handle_t is 64-bit but the lower 32 bits are the fd token
     * on both PAL-Linux and PAL-Aether backends.                        */
    return (int)(uint32_t)(sock & 0xFFFFFFFFu);
}
