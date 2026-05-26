/*
 * context_bridge.c — XMIND Memory Bridge (Gap 3 Closure)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Closes Gap 3: memory bridge between Bookworm/SoulManager and
 * r1_per_signal_t.context_shards.  Connects:
 *
 *   Bookworm (archival library)   → retrieves by semantic similarity
 *   SoulManager (episodic memory) → retrieves by session continuity
 *   RT4 salience filter           → scores and ranks shards
 *
 * Data flow:
 *   xmind_context_retrieve() → XNET TCP → Ahki daemon (port 18600)
 *     → dispatches to Bookworm + SoulManager
 *     → RT4 scores shards
 *     → returns up to 7 shards sorted by salience descending
 *   Shards packed into contiguous pal_pages_alloc() buffer.
 *
 * IPC protocol: JSON over TCP, length-prefixed (4 byte BE).
 *   Request:  {"msg_type":"context_shard_request","payload":{
 *              "entities":[<uint32 hashes>],
 *              "threshold":<uint16>,"max_shards":<uint8>}}
 *   Response: {"shard_count":<n>,"shards":[{"shard_id":<u32>,
 *              "memory_type":<u16>,"salience":<u16>,
 *              "compressed_size":<u32>,"raw_size":<u32>,
 *              "data_hex":"<hex>"},...]}
 *
 * On IPC failure: returns 0 shards (graceful degradation).
 * Inference continues without context; Heptagon pre_inference
 * falls back to keyword classification for domain tagging.
 *
 * Freestanding C11. No libc. PAL I/O + pal_pages_alloc only.
 * Compile: clang -ffreestanding -DPAL_FREESTANDING -Werror -c context_bridge.c
 */

#ifdef PAL_FREESTANDING
#include "../../../pal/include/pal.h"
#else
#include <stdint.h>
#endif

#include "../include/xmind_context.h"
#include "../../../xisc/include/xcog.h"

/* PAL §15 Network I/O — now declared in pal.h (included via xmind.h) */

/* ═══════════════════════════════════════════════════════════════════════
 * §1  Internal constants
 * ═══════════════════════════════════════════════════════════════════════ */

/* Ahki daemon address — loopback only; no external exposure */
#define AHKI_HOST          "127.0.0.1"
#define AHKI_PORT          18600u
#define AHKI_CONNECT_MS    5000u

/* IPC framing */
#define FRAME_HDR_LEN      4u     /* 4-byte BE length prefix            */

/* JSON request/response buffer size.  Must hold:
 *   - Request: ~128 bytes + 6 bytes per entity (FNV hash as decimal).
 *     With R1_PER_MAX_INSTRUCTIONS=64 entities: ~512 bytes max.
 *   - Response: shard metadata + hex data.  Each shard payload is
 *     bounded by context_shard_t.raw_size.  We cap at 4 KB per shard,
 *     7 shards = 28 KB hex + metadata.  Use 32 KB total.               */
#define CTX_REQ_BUF_SIZE   1024u
#define CTX_RESP_BUF_SIZE  (32u * 1024u)   /* 32 KiB — fits max 7 shards */

/* Max bytes in a single shard payload (4 KB) */
#define CTX_MAX_SHARD_BYTES (4u * 1024u)

/* ═══════════════════════════════════════════════════════════════════════
 * §2  Freestanding string/integer utilities
 * ═══════════════════════════════════════════════════════════════════════ */

static uint32_t ctx_strlen(const char *s) {
    uint32_t n = 0u; while (s[n]) n++; return n;
}

/* Append decimal uint32 to buf[pos]; advance *pos.  Returns 0 on success. */
static int ctx_append_u32(char *buf, uint32_t cap, uint32_t *pos, uint32_t val) {
    char tmp[10]; int32_t i = 0;
    if (val == 0u) {
        if (*pos >= cap - 1u) return -1;
        buf[(*pos)++] = '0';
        return 0;
    }
    while (val > 0u) { tmp[i++] = (char)('0' + val % 10u); val /= 10u; }
    while (i > 0) {
        if (*pos >= cap - 1u) return -1;
        buf[(*pos)++] = tmp[--i];
    }
    return 0;
}

/* Append a literal string to buf[pos].  Returns 0 on success. */
static int ctx_append_str(char *buf, uint32_t cap, uint32_t *pos, const char *s) {
    while (*s) {
        if (*pos >= cap - 1u) return -1;
        buf[(*pos)++] = *s++;
    }
    return 0;
}

/* Append char to buf[pos] */
static int ctx_append_char(char *buf, uint32_t cap, uint32_t *pos, char c) {
    if (*pos >= cap - 1u) return -1;
    buf[(*pos)++] = c;
    return 0;
}

/* Parse uint32 from JSON string at s[*i]; advances *i past digits.
 * Returns parsed value; *ok=0 on overflow/no-digits.                   */
static uint32_t parse_u32(const char *s, uint32_t len,
                           uint32_t *i, uint8_t *ok) {
    uint32_t val = 0u;
    uint8_t  digits = 0u;
    *ok = 0u;
    while (*i < len && s[*i] >= '0' && s[*i] <= '9') {
        uint32_t digit = (uint32_t)(s[*i] - '0');
        if (val > (0xFFFFFFFFu - digit) / 10u) { *ok = 0u; return 0u; }
        val = val * 10u + digit;
        digits++;
        (*i)++;
    }
    if (digits > 0u) *ok = 1u;
    return val;
}

/* Parse uint16 — same as u32 but clamped */
static uint16_t parse_u16(const char *s, uint32_t len,
                            uint32_t *i, uint8_t *ok) {
    uint32_t v = parse_u32(s, len, i, ok);
    return (*ok) ? (uint16_t)(v & 0xFFFFu) : 0u;
}

/* Skip whitespace */
static void skip_ws(const char *s, uint32_t len, uint32_t *i) {
    while (*i < len && (s[*i] == ' ' || s[*i] == '\t' ||
                        s[*i] == '\n' || s[*i] == '\r')) (*i)++;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §3  Network framing helpers
 * ═══════════════════════════════════════════════════════════════════════ */

static void encode_u32_be(uint8_t *buf, uint32_t val) {
    buf[0] = (uint8_t)(val >> 24);
    buf[1] = (uint8_t)(val >> 16);
    buf[2] = (uint8_t)(val >>  8);
    buf[3] = (uint8_t)(val      );
}

static uint32_t decode_u32_be(const uint8_t *buf) {
    return ((uint32_t)buf[0] << 24)
         | ((uint32_t)buf[1] << 16)
         | ((uint32_t)buf[2] <<  8)
         |  (uint32_t)buf[3];
}

/* Read exactly `need` bytes from sock into buf.
 * Returns PAL_OK on success, error on EOF or failure.                 */
static pal_status_t net_read_exact(pal_handle_t sock,
                                   void *buf, uint32_t need) {
    uint8_t  *p       = (uint8_t *)buf;
    uint32_t  total   = 0u;
    uint32_t  retries = 8u;

    while (total < need && retries > 0u) {
        uint32_t got = 0u;
        pal_status_t rc = pal_net_read(sock, p + total, need - total, &got);
        if (rc != PAL_OK) return rc;
        if (got == 0u) { retries--; continue; }
        total += got;
    }
    return (total == need) ? PAL_OK : PAL_ERR_IO;
}

/* Write exactly `len` bytes to sock.  Returns PAL_OK on success.     */
static pal_status_t net_write_exact(pal_handle_t sock,
                                    const void *buf, uint32_t len) {
    const uint8_t *p     = (const uint8_t *)buf;
    uint32_t       total = 0u;

    while (total < len) {
        uint32_t     written = 0u;
        pal_status_t rc      = pal_net_write(sock, p + total,
                                              len - total, &written);
        if (rc != PAL_OK) return rc;
        if (written == 0u) return PAL_ERR_IO;
        total += written;
    }
    return PAL_OK;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §4  JSON request builder
 *
 * Builds: {"msg_type":"context_shard_request","payload":{"entities":[<ref1>,...],
 *           "threshold":<u16>,"max_shards":<u8>}}
 *
 * Entity extraction: walk the XCOG instruction stream and collect the
 * .ref fields of all XCOG_ENTITY instructions.  The ref is the FNV-1a
 * hash low 16 bits used as the entity identifier for context lookup.
 * For XCOG_CONTEXT instructions we also emit the payload as an entity
 * reference because XCOG_CONTEXT carries vDRAM memory scope handles.
 *
 * If no XCOG_ENTITY or XCOG_CONTEXT instructions exist in the stream,
 * emit an empty entity array — Ahki handles this by returning
 * session-continuity shards from SoulManager.
 *
 * Returns byte length of request on success, 0 on buffer overflow.
 * ═══════════════════════════════════════════════════════════════════════ */

static uint32_t build_json_request(char          *buf,
                                   uint32_t       cap,
                                   const xcog_instr_t *instrs,
                                   uint32_t       count,
                                   uint16_t       threshold,
                                   uint16_t       max_shards) {
    uint32_t pos = 0u;
    int      rc  = 0;

    rc |= ctx_append_str(buf, cap, &pos,
                         "{\"msg_type\":\"context_shard_request\",\"payload\":{\"entities\":[");

    uint8_t first_entity = 1u;
    for (uint32_t i = 0u; i < count && rc == 0; i++) {
        uint8_t op = instrs[i].opcode;
        if (op == XCOG_ENTITY || op == XCOG_CONTEXT) {
            if (!first_entity) rc |= ctx_append_char(buf, cap, &pos, ',');
            /* Emit the ref value as the entity identifier */
            rc |= ctx_append_u32(buf, cap, &pos, (uint32_t)instrs[i].ref);
            first_entity = 0u;
        }
    }

    rc |= ctx_append_str(buf, cap, &pos, "],\"threshold\":");
    rc |= ctx_append_u32(buf, cap, &pos, (uint32_t)threshold);
    rc |= ctx_append_str(buf, cap, &pos, ",\"max_shards\":");
    rc |= ctx_append_u32(buf, cap, &pos, (uint32_t)max_shards);
    rc |= ctx_append_str(buf, cap, &pos, "}}"); /* close payload + outer */

    return (rc == 0) ? pos : 0u;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §5  JSON response parser (minimal, hand-rolled)
 *
 * Parses the response JSON from Ahki.  Designed to be robust under
 * partial or malformed responses — always fails safe (returns 0 shards).
 *
 * Expected structure:
 *   { "shard_count": N,
 *     "shards": [
 *       { "shard_id": U32, "memory_type": U16, "salience": U16,
 *         "compressed_size": U32, "raw_size": U32,
 *         "data_hex": "<hex_string>" },
 *       ...
 *     ] }
 *
 * Hex data from "data_hex" is decoded and written into a contiguous
 * staging buffer before final pal_pages_alloc.  This avoids
 * allocating per-shard pages (which would fragment the PAL allocator).
 *
 * Returns the number of shards successfully parsed.
 * ═══════════════════════════════════════════════════════════════════════ */

/* Simple scan for first occurrence of `key":` in JSON.
 * Returns index of the character AFTER the colon, or len on not-found. */
static uint32_t json_find_key(const char *s, uint32_t len,
                               uint32_t start, const char *key) {
    uint32_t klen = ctx_strlen(key);
    if (klen == 0u || len < klen) return len;

    for (uint32_t i = start; i + klen + 2u < len; i++) {
        if (s[i] != '"') continue;
        uint8_t match = 1u;
        for (uint32_t j = 0u; j < klen; j++) {
            if (s[i + 1u + j] != key[j]) { match = 0u; break; }
        }
        if (!match) continue;
        uint32_t after = i + 1u + klen;
        if (after < len && s[after] == '"') {
            /* Found "key" — now skip optional whitespace + colon */
            after++;
            while (after < len && (s[after] == ' ' || s[after] == '\t')) after++;
            if (after < len && s[after] == ':') return after + 1u;
        }
    }
    return len;
}

/* Decode 2 hex chars from s[i] and s[i+1] into *byte.
 * Returns 1 on success, 0 on invalid hex char.                        */
static int hex_decode_byte(const char *s, uint32_t i, uint8_t *byte) {
    uint8_t hi, lo;
    char c = s[i];
    if      (c >= '0' && c <= '9') hi = (uint8_t)(c - '0');
    else if (c >= 'a' && c <= 'f') hi = (uint8_t)(c - 'a' + 10);
    else if (c >= 'A' && c <= 'F') hi = (uint8_t)(c - 'A' + 10);
    else return 0;
    c = s[i + 1];
    if      (c >= '0' && c <= '9') lo = (uint8_t)(c - '0');
    else if (c >= 'a' && c <= 'f') lo = (uint8_t)(c - 'a' + 10);
    else if (c >= 'A' && c <= 'F') lo = (uint8_t)(c - 'A' + 10);
    else return 0;
    *byte = (uint8_t)((hi << 4) | lo);
    return 1;
}

/* Staging buffer for shard data before pal_pages_alloc.
 * Stack-allocated: 7 shards × 4 KB = 28 KB.  Safe for kernel stacks
 * with 64 KB default stack size (pal_thread_config_t.stack_size).     */
#define STAGING_BUF_SIZE  (XMIND_MAX_CONTEXT_SHARDS * CTX_MAX_SHARD_BYTES)

static uint32_t parse_response(const char          *resp,
                                uint32_t             resp_len,
                                xmind_context_shard_t *shards,
                                uint8_t             *staging_buf,
                                uint32_t            *staging_used,
                                uint32_t             max_s) {
    uint32_t shard_count = 0u;
    *staging_used = 0u;

    /* Find "shard_count" */
    uint32_t pos = json_find_key(resp, resp_len, 0u, "shard_count");
    if (pos >= resp_len) return 0u;
    skip_ws(resp, resp_len, &pos);
    uint8_t  ok  = 0u;
    uint32_t declared = parse_u32(resp, resp_len, &pos, &ok);
    if (!ok || declared == 0u) return 0u;

    /* Cap to max_s (caller's XMIND_MAX_CONTEXT_SHARDS) */
    if (declared > max_s) declared = max_s;

    /* Find "shards" array start */
    pos = json_find_key(resp, resp_len, 0u, "shards");
    if (pos >= resp_len) return 0u;
    skip_ws(resp, resp_len, &pos);
    if (pos >= resp_len || resp[pos] != '[') return 0u;
    pos++;  /* step past '[' */

    for (uint32_t s = 0u; s < declared; s++) {
        /* Skip to '{' */
        skip_ws(resp, resp_len, &pos);
        if (pos >= resp_len || resp[pos] != '{') break;
        uint32_t obj_start = pos;
        pos++;

        /* Find closing '}' — simple brace scan (no nesting in shard obj) */
        uint32_t obj_end = pos;
        while (obj_end < resp_len && resp[obj_end] != '}') obj_end++;
        if (obj_end >= resp_len) break;

        /* Parse shard fields within [obj_start, obj_end] */
        uint32_t pf;

        pf = json_find_key(resp, obj_end + 1u, obj_start, "shard_id");
        uint32_t shard_id = 0u;
        if (pf < obj_end) { skip_ws(resp, obj_end, &pf);
                            shard_id = parse_u32(resp, obj_end, &pf, &ok); }

        pf = json_find_key(resp, obj_end + 1u, obj_start, "memory_type");
        uint16_t mem_type = 0u;
        if (pf < obj_end) { skip_ws(resp, obj_end, &pf);
                            mem_type = parse_u16(resp, obj_end, &pf, &ok); }

        pf = json_find_key(resp, obj_end + 1u, obj_start, "salience");
        uint16_t salience = 0u;
        if (pf < obj_end) { skip_ws(resp, obj_end, &pf);
                            salience = parse_u16(resp, obj_end, &pf, &ok); }

        pf = json_find_key(resp, obj_end + 1u, obj_start, "compressed_size");
        uint32_t comp_size = 0u;
        if (pf < obj_end) { skip_ws(resp, obj_end, &pf);
                            comp_size = parse_u32(resp, obj_end, &pf, &ok); }

        pf = json_find_key(resp, obj_end + 1u, obj_start, "raw_size");
        uint32_t raw_size = 0u;
        if (pf < obj_end) { skip_ws(resp, obj_end, &pf);
                            raw_size = parse_u32(resp, obj_end, &pf, &ok); }

        /* Decode hex data */
        uint32_t data_bytes = 0u;
        pf = json_find_key(resp, obj_end + 1u, obj_start, "data_hex");
        if (pf < obj_end) {
            skip_ws(resp, obj_end, &pf);
            if (resp[pf] == '"') {
                pf++;  /* skip opening quote */
                uint32_t hex_start = pf;

                /* Count hex chars until closing quote */
                uint32_t hex_len = 0u;
                while (pf + hex_len < obj_end && resp[pf + hex_len] != '"') {
                    hex_len++;
                }

                /* Decode hex pairs into staging buffer */
                uint32_t decode_bytes = hex_len / 2u;
                if (decode_bytes > CTX_MAX_SHARD_BYTES) {
                    decode_bytes = CTX_MAX_SHARD_BYTES;
                }
                if (*staging_used + decode_bytes <= STAGING_BUF_SIZE) {
                    for (uint32_t b = 0u; b < decode_bytes; b++) {
                        uint8_t byte = 0u;
                        if (hex_decode_byte(resp, hex_start + b * 2u, &byte)) {
                            staging_buf[*staging_used + b] = byte;
                        }
                    }
                    data_bytes       = decode_bytes;
                    *staging_used   += decode_bytes;
                }
            }
        }

        /* Populate shard metadata */
        shards[shard_count].shard_id        = shard_id;
        shards[shard_count].memory_type     = mem_type;
        shards[shard_count].salience        = salience;
        shards[shard_count].compressed_size = comp_size;
        shards[shard_count].raw_size        = (raw_size > 0u) ? raw_size : data_bytes;
        shard_count++;

        /* Advance past '}' and optional ',' */
        pos = obj_end + 1u;
        skip_ws(resp, resp_len, &pos);
        if (pos < resp_len && resp[pos] == ',') pos++;
    }

    return shard_count;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §6  Salience sort — insertion sort O(n^2) for n <= 7
 *
 * n is bounded by XMIND_MAX_CONTEXT_SHARDS = 7 by the law of seven.
 * Insertion sort is optimal for n <= 16; no algorithmic complexity gain
 * from heapsort at this scale.
 *
 * Sorts shards[] and their corresponding shard_offsets[] together,
 * descending by salience.
 * ═══════════════════════════════════════════════════════════════════════ */

static void sort_shards_by_salience(xmind_context_shard_t *shards,
                                     uint32_t              *offsets,
                                     uint32_t               n) {
    for (uint32_t i = 1u; i < n; i++) {
        xmind_context_shard_t key_shard = shards[i];
        uint32_t              key_off   = offsets[i];
        int32_t j = (int32_t)i - 1;
        while (j >= 0 && shards[j].salience < key_shard.salience) {
            shards[j + 1] = shards[j];
            offsets[j + 1] = offsets[j];
            j--;
        }
        shards[j + 1] = key_shard;
        offsets[j + 1] = key_off;
    }
}

/* Forward declarations — handle table + alloc helper (defined in §8) */
static void ctx_register_handle(uintptr_t vaddr, pal_handle_t pages_h);
static pal_handle_t ctx_lookup_handle(uintptr_t vaddr);
static int alloc_and_register(uint32_t staging_used,
                               uint8_t *staging,
                               uint8_t **out_ptr);

/* ═══════════════════════════════════════════════════════════════════════
 * §7  Public API — xmind_context_retrieve
 *
 * Dispatcher: XMIND → (IPC) → Ahki → Bookworm + SoulManager → RT4
 *
 * Returns:
 *    N > 0  — number of shards returned in out->shards
 *    0      — no shards (graceful degradation; inference continues)
 *   -1      — IPC failure (also degrades gracefully; caller must handle)
 *   -2      — no shards after successful query
 * ═══════════════════════════════════════════════════════════════════════ */

int xmind_context_retrieve(const xmind_context_request_t *req,
                            xmind_context_result_t        *out) {
    if (req == NULL || out == NULL) return -1;

    /* Zero output */
    {
        uint8_t *p = (uint8_t *)out;
        for (uint32_t i = 0u; i < (uint32_t)sizeof(*out); i++) p[i] = 0u;
    }

    /* Short-circuit: no query instructions means no context to fetch */
    if (req->query_count == 0u) return 0;

    /* ── Build JSON request ── */
    char req_buf[CTX_REQ_BUF_SIZE];
    uint16_t eff_max = req->max_shards;
    if (eff_max == 0u || eff_max > (uint16_t)XMIND_MAX_CONTEXT_SHARDS) {
        eff_max = (uint16_t)XMIND_MAX_CONTEXT_SHARDS;
    }

    uint32_t req_len = build_json_request(req_buf, CTX_REQ_BUF_SIZE,
                                          req->query_instructions,
                                          req->query_count,
                                          req->salience_threshold,
                                          eff_max);
    if (req_len == 0u) return -1;  /* Request buffer overflow */

    /* ── Connect to Ahki daemon ── */
    pal_handle_t sock = PAL_HANDLE_INVALID;
    pal_status_t rc   = pal_net_connect(AHKI_HOST, AHKI_PORT,
                                         AHKI_CONNECT_MS, &sock);
    if (rc != PAL_OK || sock == PAL_HANDLE_INVALID) {
        /* Graceful degradation — Ahki may not be running (Sprint 46 mode) */
        return 0;
    }

    /* ── Send framed JSON request ── */
    uint8_t hdr[FRAME_HDR_LEN];
    encode_u32_be(hdr, req_len);

    rc = net_write_exact(sock, hdr, FRAME_HDR_LEN);
    if (rc != PAL_OK) { pal_handle_close(sock); return 0; }

    rc = net_write_exact(sock, req_buf, req_len);
    if (rc != PAL_OK) { pal_handle_close(sock); return 0; }

    /* ── Read framed response ── */
    uint8_t resp_hdr[FRAME_HDR_LEN];
    rc = net_read_exact(sock, resp_hdr, FRAME_HDR_LEN);
    if (rc != PAL_OK) { pal_handle_close(sock); return 0; }

    uint32_t resp_payload_len = decode_u32_be(resp_hdr);

    /* Sanity check: response must not exceed our buffer */
    if (resp_payload_len == 0u || resp_payload_len > CTX_RESP_BUF_SIZE) {
        pal_handle_close(sock);
        return 0;
    }

    /* Stack allocation for response — safe given CTX_RESP_BUF_SIZE = 32 KB
     * and PAL default thread stack = 64 KB.                            */
    char resp_buf[CTX_RESP_BUF_SIZE];
    rc = net_read_exact(sock, resp_buf, resp_payload_len);
    pal_handle_close(sock);  /* Close socket immediately after read */

    if (rc != PAL_OK) return 0;

    /* ── Parse response + collect shard data into staging buffer ── */

    /* Staging on stack: 7 × 4 KB = 28 KB.  Fits within 64 KB stack. */
    static uint8_t staging[STAGING_BUF_SIZE];  /* BSS — not per-call stack */
    uint32_t       staging_used = 0u;

    /* Temporary shard array + per-shard byte offsets into staging */
    xmind_context_shard_t tmp_shards[XMIND_MAX_CONTEXT_SHARDS];
    uint32_t              shard_offsets[XMIND_MAX_CONTEXT_SHARDS];

    /* Zero temporaries */
    for (uint32_t i = 0u; i < XMIND_MAX_CONTEXT_SHARDS; i++) {
        uint8_t *p = (uint8_t *)&tmp_shards[i];
        for (uint32_t b = 0u; b < (uint32_t)sizeof(xmind_context_shard_t); b++) p[b] = 0u;
        shard_offsets[i] = 0u;
    }

    /* Build offsets as we parse (staging_used tracks cumulative offset) */
    uint32_t pre_parse_used = 0u;
    uint32_t shard_count = parse_response(resp_buf, resp_payload_len,
                                           tmp_shards,
                                           staging,
                                           &staging_used,
                                           (uint32_t)eff_max);
    (void)pre_parse_used;

    if (shard_count == 0u) return -2;

    /* Recompute per-shard offsets from compressed_size metadata.
     * parse_response fills staging contiguously in order, so we can
     * derive offsets by walking the raw_size fields.                    */
    {
        uint32_t cursor = 0u;
        for (uint32_t i = 0u; i < shard_count; i++) {
            shard_offsets[i] = cursor;
            uint32_t data_len = (tmp_shards[i].compressed_size > 0u)
                              ? tmp_shards[i].compressed_size
                              : tmp_shards[i].raw_size;
            cursor += data_len;
        }
    }

    /* ── Sort by salience descending ── */
    sort_shards_by_salience(tmp_shards, shard_offsets, shard_count);

    /* ── Cap to eff_max ── */
    if (shard_count > (uint32_t)eff_max) shard_count = (uint32_t)eff_max;

    /* ── Allocate contiguous PAL pages for final shard data buffer ──
     * Uses alloc_and_register() which also registers the pages handle
     * in the module-static table so xmind_context_release() can free
     * via ctx_lookup_handle().  This closes the F-6 page leak.        */
    if (staging_used > 0u) {
        uint8_t *data_ptr = (uint8_t *)0;
        int alloc_rc = alloc_and_register(staging_used, staging, &data_ptr);

        if (alloc_rc == 0 && data_ptr != (uint8_t *)0) {
            out->shard_data      = data_ptr;
            out->total_data_size = staging_used;
        } else {
            /* Memory pressure — return shards with no data buffer.
             * Shard metadata is still useful for Heptagon domain tagging. */
            out->shard_data      = (uint8_t *)0;
            out->total_data_size = 0u;
        }
    }

    /* ── Populate output shards ── */
    for (uint32_t i = 0u; i < shard_count; i++) {
        out->shards[i] = tmp_shards[i];
    }
    out->shard_count = shard_count;

    return (int)shard_count;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §8  Module-static handle table for context_release
 *
 * Since xmind_context_result_t does not carry a pal_handle_t, and the
 * frozen header cannot be touched, we maintain a small static table of
 * (vaddr → pages_handle) mappings.  Max 7 entries — one per live
 * retrieve call (law of seven).  Linear scan is O(7) = O(1).
 * ═══════════════════════════════════════════════════════════════════════ */

#define HANDLE_TABLE_SIZE  XMIND_MAX_CONTEXT_SHARDS

typedef struct {
    uintptr_t    vaddr;
    pal_handle_t pages_h;
    uint8_t      used;
} ctx_handle_entry_t;

static ctx_handle_entry_t s_handle_table[HANDLE_TABLE_SIZE];
static pal_spinlock_t     s_handle_lock = PAL_SPINLOCK_INIT;

/* Register a vaddr→pages_h mapping.  Called from retrieve after alloc. */
static void ctx_register_handle(uintptr_t vaddr, pal_handle_t pages_h) {
    pal_spin_lock(&s_handle_lock);
    for (uint32_t i = 0u; i < HANDLE_TABLE_SIZE; i++) {
        if (!s_handle_table[i].used) {
            s_handle_table[i].vaddr   = vaddr;
            s_handle_table[i].pages_h = pages_h;
            s_handle_table[i].used    = 1u;
            break;
        }
    }
    pal_spin_unlock(&s_handle_lock);
}

/* Look up and evict a vaddr entry.  Returns PAL_HANDLE_INVALID if missing. */
static pal_handle_t ctx_lookup_handle(uintptr_t vaddr) {
    pal_handle_t found = PAL_HANDLE_INVALID;
    pal_spin_lock(&s_handle_lock);
    for (uint32_t i = 0u; i < HANDLE_TABLE_SIZE; i++) {
        if (s_handle_table[i].used && s_handle_table[i].vaddr == vaddr) {
            found = s_handle_table[i].pages_h;
            s_handle_table[i].used = 0u;
            break;
        }
    }
    pal_spin_unlock(&s_handle_lock);
    return found;
}

/* Re-open the retrieve path to wire ctx_register_handle after pal_map_pages.
 * The goto-based control flow above needs a post-map hook.  We patch it here
 * by wrapping the actual allocation in a helper that also registers.      */
static int alloc_and_register(uint32_t  staging_used,
                               uint8_t  *staging,
                               uint8_t **out_ptr) {
    uint64_t     pages_needed = (staging_used + PAL_PAGE_SIZE_4K - 1u)
                               / PAL_PAGE_SIZE_4K;
    pal_handle_t pages_h = PAL_HANDLE_INVALID;
    pal_handle_t map_h   = PAL_HANDLE_INVALID;
    uintptr_t    vaddr   = 0u;

    pal_status_t rc = pal_pages_alloc(pages_needed, PAL_PAGE_SIZE_4K,
                                       (uint32_t)PAL_MEM_ZEROED,
                                       PAL_NUMA_ANY, &pages_h);
    if (rc != PAL_OK) return -1;

    rc = pal_map_pages(pages_h, 0u, 0u, pages_needed,
                       (uint32_t)(PAL_MAP_READ | PAL_MAP_WRITE),
                       &map_h, &vaddr);
    if (rc != PAL_OK) { pal_pages_free(pages_h); return -1; }

    uint8_t *dst = (uint8_t *)vaddr;
    for (uint32_t i = 0u; i < staging_used; i++) dst[i] = staging[i];

    ctx_register_handle(vaddr, pages_h);
    *out_ptr = dst;
    return 0;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §9  Public API — xmind_context_release
 *
 * Frees the shard_data buffer allocated by xmind_context_retrieve().
 * Looks up the pages handle from the static table, unmaps, frees.
 * Safe to call with result->shard_data == NULL.
 * ═══════════════════════════════════════════════════════════════════════ */

void xmind_context_release(xmind_context_result_t *result) {
    if (result == NULL) return;

    if (result->shard_data != NULL) {
        uintptr_t    vaddr   = (uintptr_t)result->shard_data;
        pal_handle_t pages_h = ctx_lookup_handle(vaddr);

        if (pages_h != PAL_HANDLE_INVALID) {
            /* pal_pages_free also invalidates any mappings of these pages
             * on PAL-Aether; on PAL-Linux it munmaps via the linux shim. */
            pal_pages_free(pages_h);
        }
        /* If lookup failed the pages are leaked — this indicates a double-
         * release or a mismatched retrieve/release pair.  Log and continue. */
    }

    /* Zero the result struct to prevent use-after-free */
    uint8_t *p = (uint8_t *)result;
    for (uint32_t i = 0u; i < (uint32_t)sizeof(*result); i++) p[i] = 0u;
}

/* ═══════════════════════════════════════════════════════════════════════
 * §10  End of context_bridge.c
 *
 * alloc_and_register() is now wired directly into xmind_context_retrieve().
 * ctx_register_handle()/ctx_lookup_handle() close the F-6 page leak:
 * every pal_pages_alloc is tracked, and xmind_context_release() frees it.
 * ═══════════════════════════════════════════════════════════════════════ */
