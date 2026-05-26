/*
 * xmind_http.c — XMIND HTTP Inference API Server
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Sprint 15: Exposes XMIND inference over a minimal HTTP/1.1 endpoint.
 *
 * Architecture:
 *   - Freestanding C, no libc, no malloc, no stdio.
 *   - Static buffers only; single-threaded accept loop.
 *   - Uses XNET socket API (xnet_socket / xnet_bind / xnet_listen /
 *     xnet_accept / xnet_recv / xnet_send / xnet_close).
 *   - JSON is hand-rolled: only enough to extract the "prompt" field
 *     from a request body and emit a {"text":"…"} response.
 *   - Inference via xmind_tokenize → xmind_generate (session API) or,
 *     when the session layer is unavailable, a direct
 *     xmind_forward + xmind_sample loop.
 *
 * Endpoint:
 *   POST /v1/completions
 *   Content-Type: application/json
 *   Body: {"prompt":"<text>"}
 *
 *   Response 200 OK:
 *   Content-Type: application/json
 *   Body: {"text":"<generated>"}
 *
 *   Response 400 Bad Request — missing/unparseable prompt.
 *   Response 503 Service Unavailable — XMIND model not ready.
 *
 * §1  Utility helpers (memset, memcpy, strlen, uint_to_dec)
 * §2  Hand-rolled JSON extractor  (json_extract_string_field)
 * §3  Hand-rolled JSON builder    (json_build_text_response)
 * §4  HTTP request parser         (http_parse_body_offset, http_is_post_completions)
 * §5  HTTP response builder       (http_build_response)
 * §6  Inference glue              (xmind_http_run_inference)
 * §7  Connection handler          (xmind_http_handle_conn)
 * §8  Public API                  (xmind_http_init, xmind_http_serve,
 *                                  xmind_http_serve_thread)
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "../../../pal/include/pal.h"
#include "../../../net/xnet/include/xnet.h"
#include "../include/xmind.h"
#include "../include/xmind_http.h"

/* ===================================================================
 * §1  UTILITY HELPERS
 *
 * No libc — implement the handful of primitives we need ourselves.
 * =================================================================== */

static void xh_memset(void *dst, uint8_t val, uint32_t n) {
    uint8_t *p = (uint8_t *)dst;
    uint32_t i;
    for (i = 0u; i < n; i++) { p[i] = val; }
}

static void xh_memcpy(void *dst, const void *src, uint32_t n) {
    uint8_t       *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;
    uint32_t i;
    for (i = 0u; i < n; i++) { d[i] = s[i]; }
}

static uint32_t xh_strlen(const char *s) {
    uint32_t n = 0u;
    while (s[n] != '\0') { n++; }
    return n;
}

/*
 * xh_strncmp — compare up to n bytes; returns 0 if equal.
 */
static int32_t xh_strncmp(const char *a, const char *b, uint32_t n) {
    uint32_t i;
    for (i = 0u; i < n; i++) {
        if (a[i] != b[i]) { return (int32_t)(uint8_t)a[i] - (int32_t)(uint8_t)b[i]; }
        if (a[i] == '\0') { return 0; }
    }
    return 0;
}

/*
 * xh_uint_to_dec — write decimal representation of v into buf.
 * buf must be at least 11 bytes.  Returns number of chars written
 * (not including null terminator).
 */
static uint32_t xh_uint_to_dec(char *buf, uint32_t v) {
    char tmp[11];
    uint32_t i = 0u;
    if (v == 0u) {
        buf[0] = '0';
        buf[1] = '\0';
        return 1u;
    }
    while (v > 0u && i < 10u) {
        tmp[i++] = (char)('0' + (v % 10u));
        v /= 10u;
    }
    uint32_t j;
    for (j = 0u; j < i; j++) { buf[j] = tmp[i - 1u - j]; }
    buf[i] = '\0';
    return i;
}

/*
 * xh_append — append src (up to src_len bytes) into dst[*pos].
 * *pos is advanced.  Returns 0 if cap was reached (truncated), 1 if ok.
 */
static int32_t xh_append(char *dst, uint32_t cap,
                          uint32_t *pos,
                          const char *src, uint32_t src_len) {
    uint32_t i;
    for (i = 0u; i < src_len; i++) {
        if (*pos >= cap - 1u) { dst[cap - 1u] = '\0'; return 0; }
        dst[(*pos)++] = src[i];
    }
    dst[*pos] = '\0';
    return 1;
}

/* ===================================================================
 * §1b UTF-16 / CODEPOINT TO UTF-8 CONVERSION
 *
 * Used by the JSON extractor to decode \uXXXX escape sequences
 * (including surrogate pairs) into proper UTF-8.
 * =================================================================== */

/*
 * utf16_to_utf8 — Convert a Unicode codepoint to UTF-8.
 * Returns number of bytes written (1-4), or 1 ('?') for invalid codepoints.
 */
static int utf16_to_utf8(unsigned int cp, char *out) {
    if (cp <= 0x7Fu) { out[0] = (char)cp; return 1; }
    if (cp <= 0x7FFu) {
        out[0] = (char)(0xC0u | (cp >> 6));
        out[1] = (char)(0x80u | (cp & 0x3Fu));
        return 2;
    }
    if (cp <= 0xFFFFu) {
        out[0] = (char)(0xE0u | (cp >> 12));
        out[1] = (char)(0x80u | ((cp >> 6) & 0x3Fu));
        out[2] = (char)(0x80u | (cp & 0x3Fu));
        return 3;
    }
    if (cp <= 0x10FFFFu) {
        out[0] = (char)(0xF0u | (cp >> 18));
        out[1] = (char)(0x80u | ((cp >> 12) & 0x3Fu));
        out[2] = (char)(0x80u | ((cp >> 6) & 0x3Fu));
        out[3] = (char)(0x80u | (cp & 0x3Fu));
        return 4;
    }
    out[0] = '?'; return 1;
}

/*
 * xh_hex_digit — return numeric value of a hex digit, or -1 if invalid.
 */
static int32_t xh_hex_digit(char c) {
    if (c >= '0' && c <= '9') { return (int32_t)(c - '0'); }
    if (c >= 'a' && c <= 'f') { return (int32_t)(c - 'a' + 10); }
    if (c >= 'A' && c <= 'F') { return (int32_t)(c - 'A' + 10); }
    return -1;
}

/*
 * xh_parse_hex4 — parse exactly 4 hex digits from s into *out.
 * Returns 1 on success, 0 on failure.
 */
static int32_t xh_parse_hex4(const char *s, unsigned int *out) {
    unsigned int val = 0u;
    int i;
    for (i = 0; i < 4; i++) {
        int32_t d = xh_hex_digit(s[i]);
        if (d < 0) { return 0; }
        val = (val << 4) | (unsigned int)d;
    }
    *out = val;
    return 1;
}

/* ===================================================================
 * §2  HAND-ROLLED JSON EXTRACTOR
 *
 * Minimal JSON string field extraction.  We only need to pull the
 * value of a single named string field, e.g. "prompt".
 * =================================================================== */

/*
 * json_extract_string_field — scan haystack for the pattern:
 *   "field_name" : "value"
 * and copy the value into out_buf (at most out_cap-1 chars).
 *
 * Handles standard JSON escape sequences inside the value:
 *   \\, \", \/, \n, \r, \t, \uXXXX (collapsed to '?')
 *
 * Returns the number of characters written on success, -1 if not found.
 */
static int32_t json_extract_string_field(const char *haystack,
                                          uint32_t haystack_len,
                                          const char *field_name,
                                          char *out_buf,
                                          uint32_t out_cap) {
    if (!haystack || !field_name || !out_buf || out_cap == 0u) { return -1; }

    uint32_t fname_len = xh_strlen(field_name);

    /* Search for: "field_name" */
    uint32_t i;
    for (i = 0u; i + fname_len + 4u < haystack_len; i++) {
        /* Look for opening quote of key */
        if (haystack[i] != '"') { continue; }
        if (xh_strncmp(&haystack[i + 1u], field_name, fname_len) != 0) { continue; }
        if (haystack[i + 1u + fname_len] != '"') { continue; }

        /* Skip past the key's closing quote */
        uint32_t p = i + 1u + fname_len + 1u;

        /* Skip optional whitespace and colon */
        while (p < haystack_len && (haystack[p] == ' '  ||
                                     haystack[p] == '\t' ||
                                     haystack[p] == '\r' ||
                                     haystack[p] == '\n')) { p++; }
        if (p >= haystack_len || haystack[p] != ':') { continue; }
        p++;

        /* Skip whitespace before value */
        while (p < haystack_len && (haystack[p] == ' '  ||
                                     haystack[p] == '\t' ||
                                     haystack[p] == '\r' ||
                                     haystack[p] == '\n')) { p++; }
        if (p >= haystack_len || haystack[p] != '"') { continue; }
        p++; /* skip opening quote of value */

        /* Copy value bytes, handling escape sequences */
        uint32_t out_pos = 0u;
        while (p < haystack_len && haystack[p] != '"') {
            if (out_pos >= out_cap - 1u) { break; }
            if (haystack[p] == '\\' && p + 1u < haystack_len) {
                char esc = haystack[p + 1u];
                p += 2u;
                switch (esc) {
                    case '"':  out_buf[out_pos++] = '"';  break;
                    case '\\': out_buf[out_pos++] = '\\'; break;
                    case '/':  out_buf[out_pos++] = '/';  break;
                    case 'n':  out_buf[out_pos++] = '\n'; break;
                    case 'r':  out_buf[out_pos++] = '\r'; break;
                    case 't':  out_buf[out_pos++] = '\t'; break;
                    case 'u': {
                        /* Decode \uXXXX (with surrogate pair support) */
                        unsigned int cp = 0u;
                        if (p + 4u <= haystack_len &&
                            xh_parse_hex4(&haystack[p], &cp)) {
                            p += 4u;
                            /* Check for UTF-16 surrogate pair: high surrogate 0xD800-0xDBFF */
                            if (cp >= 0xD800u && cp <= 0xDBFFu) {
                                /* Expect \uDCxx low surrogate immediately after */
                                unsigned int lo = 0u;
                                if (p + 6u <= haystack_len &&
                                    haystack[p] == '\\' && haystack[p + 1u] == 'u' &&
                                    xh_parse_hex4(&haystack[p + 2u], &lo) &&
                                    lo >= 0xDC00u && lo <= 0xDFFFu) {
                                    p += 6u; /* consume \uDCxx */
                                    cp = 0x10000u + ((cp - 0xD800u) << 10) + (lo - 0xDC00u);
                                } else {
                                    /* Lone high surrogate — emit replacement */
                                    out_buf[out_pos++] = '?';
                                    break;
                                }
                            } else if (cp >= 0xDC00u && cp <= 0xDFFFu) {
                                /* Lone low surrogate — emit replacement */
                                out_buf[out_pos++] = '?';
                                break;
                            }
                            /* Convert codepoint to UTF-8 */
                            if (out_pos + 4u < out_cap) {
                                int nb = utf16_to_utf8(cp, &out_buf[out_pos]);
                                out_pos += (uint32_t)nb;
                            }
                        } else {
                            /* Malformed \u — emit replacement */
                            out_buf[out_pos++] = '?';
                        }
                        break;
                    }
                    default:
                        out_buf[out_pos++] = esc;
                        break;
                }
            } else {
                out_buf[out_pos++] = haystack[p++];
            }
        }
        out_buf[out_pos] = '\0';
        return (int32_t)out_pos;
    }
    return -1; /* field not found */
}

/* ===================================================================
 * §3  HAND-ROLLED JSON BUILDER
 *
 * Build the HTTP response JSON body.
 * We emit: {"text":"<escaped_value>"}
 * =================================================================== */

/*
 * json_escape_string — write JSON-escaped form of src into dst.
 * Returns number of bytes written (not including null terminator).
 * Truncates gracefully if dst fills up.
 */
static uint32_t json_escape_string(char *dst, uint32_t dst_cap,
                                    const char *src, uint32_t src_len) {
    uint32_t out = 0u;
    uint32_t i;
    for (i = 0u; i < src_len; i++) {
        uint8_t c = (uint8_t)src[i];
        if (c == '"') {
            if (out + 2u >= dst_cap) { break; }
            dst[out++] = '\\'; dst[out++] = '"';
        } else if (c == '\\') {
            if (out + 2u >= dst_cap) { break; }
            dst[out++] = '\\'; dst[out++] = '\\';
        } else if (c == '\n') {
            if (out + 2u >= dst_cap) { break; }
            dst[out++] = '\\'; dst[out++] = 'n';
        } else if (c == '\r') {
            if (out + 2u >= dst_cap) { break; }
            dst[out++] = '\\'; dst[out++] = 'r';
        } else if (c == '\t') {
            if (out + 2u >= dst_cap) { break; }
            dst[out++] = '\\'; dst[out++] = 't';
        } else if (c < 0x20u) {
            /* Control character — skip */
        } else {
            if (out + 1u >= dst_cap) { break; }
            dst[out++] = (char)c;
        }
    }
    if (out < dst_cap) { dst[out] = '\0'; }
    return out;
}

/*
 * json_build_text_response — write {"text":"<text>"} into buf.
 * Returns total bytes written.
 */
static uint32_t json_build_text_response(char *buf, uint32_t cap,
                                          const char *text, uint32_t text_len) {
    /* Intermediate escape buffer — at most XMIND_HTTP_RESP_BUF */
    static char s_esc_buf[XMIND_HTTP_RESP_BUF];
    uint32_t esc_len = json_escape_string(s_esc_buf, sizeof(s_esc_buf),
                                           text, text_len);

    uint32_t pos = 0u;
    static const char prefix[] = "{\"text\":\"";
    static const char suffix[] = "\"}";
    xh_append(buf, cap, &pos, prefix, xh_strlen(prefix));
    xh_append(buf, cap, &pos, s_esc_buf, esc_len);
    xh_append(buf, cap, &pos, suffix, xh_strlen(suffix));
    return pos;
}

/* ===================================================================
 * §4  HTTP REQUEST PARSER
 *
 * We only need two things from the HTTP request:
 *   a) Is it POST /v1/completions?
 *   b) Where does the body start (after the blank line)?
 * =================================================================== */

/*
 * http_is_post_completions — return 1 if the request starts with
 * "POST /v1/completions".
 */
static int32_t http_is_post_completions(const char *req, uint32_t req_len) {
    static const char target[] = "POST /v1/completions";
    uint32_t tlen = xh_strlen(target);
    if (req_len < tlen) { return 0; }
    return (xh_strncmp(req, target, tlen) == 0) ? 1 : 0;
}

/*
 * http_parse_body_offset — find the start of the HTTP body (after "\r\n\r\n").
 * Returns the byte offset of the first body byte, or req_len if not found.
 */
static uint32_t http_parse_body_offset(const char *req, uint32_t req_len) {
    uint32_t i;
    /* Scan for \r\n\r\n */
    for (i = 0u; i + 3u < req_len; i++) {
        if (req[i]     == '\r' && req[i + 1u] == '\n' &&
            req[i + 2u] == '\r' && req[i + 3u] == '\n') {
            return i + 4u;
        }
    }
    return req_len; /* not found */
}

/* ===================================================================
 * §5  HTTP RESPONSE BUILDER
 * =================================================================== */

/*
 * http_build_response — compose a complete HTTP/1.1 response into buf.
 *
 * @status_line  e.g. "200 OK", "400 Bad Request", "503 Service Unavailable"
 * @body         response body bytes (may be NULL for empty body)
 * @body_len     length of body in bytes
 *
 * Returns total bytes written into buf.
 */
static uint32_t http_build_response(char *buf, uint32_t cap,
                                     const char *status_line,
                                     const char *body, uint32_t body_len) {
    static const char http_ver[]   = "HTTP/1.1 ";
    static const char crlf[]       = "\r\n";
    static const char ctype[]      = "Content-Type: application/json\r\n";
    static const char clen_hdr[]   = "Content-Length: ";
    static const char connection[] = "Connection: close\r\n";
    static const char server_hdr[] = "Server: XMIND-HTTP/1.0\r\n";

    char clen_val[12];
    xh_uint_to_dec(clen_val, body_len);

    uint32_t pos = 0u;
    xh_append(buf, cap, &pos, http_ver,    xh_strlen(http_ver));
    xh_append(buf, cap, &pos, status_line, xh_strlen(status_line));
    xh_append(buf, cap, &pos, crlf,        2u);
    xh_append(buf, cap, &pos, server_hdr,  xh_strlen(server_hdr));
    xh_append(buf, cap, &pos, ctype,       xh_strlen(ctype));
    xh_append(buf, cap, &pos, clen_hdr,    xh_strlen(clen_hdr));
    xh_append(buf, cap, &pos, clen_val,    xh_strlen(clen_val));
    xh_append(buf, cap, &pos, crlf,        2u);
    xh_append(buf, cap, &pos, connection,  xh_strlen(connection));
    xh_append(buf, cap, &pos, crlf,        2u); /* blank line */

    if (body && body_len > 0u) {
        xh_append(buf, cap, &pos, body, body_len);
    }
    return pos;
}

/* ===================================================================
 * §6  INFERENCE GLUE
 *
 * Run XMIND inference on a prompt string.
 * Outputs null-terminated text into out_buf (at most out_cap-1 chars).
 * Returns length of generated text on success, 0 on failure.
 * =================================================================== */

/*
 * Static token and detokenize buffers — reused across requests.
 * No dynamic allocation.
 */
static uint32_t s_prompt_tokens[XMIND_MAX_SEQ];
static uint32_t s_output_tokens[XMIND_HTTP_MAX_TOKENS];

/* Scratch buffer for detokenized fragments */
static char s_tok_frag[32];

static uint32_t xmind_http_run_inference(const char *prompt,
                                          char *out_buf,
                                          uint32_t out_cap) {
    if (!prompt || !out_buf || out_cap == 0u) { return 0u; }

    /* Retrieve global model singleton */
    xmind_model_t *model = xmind_get_global();
    if (!model || !model->initialized) {
        pal_console_printf("[XMIND-HTTP] model not initialized — returning error\n");
        return 0u;
    }

    /* Preflight check */
    if (xmind_preflight_check(model) != XMIND_OK) {
        pal_console_printf("[XMIND-HTTP] preflight check failed\n");
        return 0u;
    }

    /* Tokenize the prompt */
    uint32_t prompt_len = 0u;
    xmind_status_t rc = xmind_tokenize(prompt, s_prompt_tokens,
                                        &prompt_len, XMIND_MAX_SEQ);
    if (rc != XMIND_OK || prompt_len == 0u) {
        pal_console_printf("[XMIND-HTTP] tokenize failed (%d)\n", (int)rc);
        return 0u;
    }

    /* Create an inference session */
    xmind_session_t *sess = (xmind_session_t *)0;
    rc = xmind_session_create(&sess, XMIND_MAX_SEQ);
    if (rc != XMIND_OK || !sess) {
        pal_console_printf("[XMIND-HTTP] session_create failed (%d)\n", (int)rc);
        return 0u;
    }

    /* Configure sampler: temperature=0.7, top_p=0.9, seed=0 (default) */
    (void)xmind_session_set_sampler(sess, 0.7f, 0.9f, 0u);

    /* Run generation */
    uint32_t n_generated = 0u;
    rc = xmind_generate(sess,
                         s_prompt_tokens, prompt_len,
                         s_output_tokens, XMIND_HTTP_MAX_TOKENS,
                         &n_generated);

    (void)xmind_session_destroy(sess);

    if (rc != XMIND_OK && rc != XMIND_ERR_OVERFLOW) {
        pal_console_printf("[XMIND-HTTP] generate failed (%d)\n", (int)rc);
        return 0u;
    }

    /* Detokenize output tokens into out_buf */
    uint32_t out_pos = 0u;
    uint32_t ti;
    for (ti = 0u; ti < n_generated; ti++) {
        uint32_t tok = s_output_tokens[ti];
        /* Stop at EOS */
        if (tok == XMIND_TOK_EOS) { break; }
        xh_memset(s_tok_frag, 0, sizeof(s_tok_frag));
        xmind_detokenize(tok, s_tok_frag, (uint32_t)sizeof(s_tok_frag));
        uint32_t frag_len = xh_strlen(s_tok_frag);
        if (out_pos + frag_len >= out_cap - 1u) { break; }
        xh_memcpy(&out_buf[out_pos], s_tok_frag, frag_len);
        out_pos += frag_len;
    }
    out_buf[out_pos] = '\0';
    return out_pos;
}

/* ===================================================================
 * §7  CONNECTION HANDLER
 *
 * Reads one HTTP request, dispatches to inference, sends the response,
 * and closes the connection.  All I/O uses static buffers.
 * =================================================================== */

/* Static per-connection buffers — single-threaded, so no lock needed */
static char s_req_buf[XMIND_HTTP_REQ_BUF];
static char s_prompt_buf[XMIND_HTTP_REQ_BUF];  /* extracted prompt string */
static char s_gen_buf[XMIND_HTTP_RESP_BUF];     /* detokenized output */
static char s_json_body[XMIND_HTTP_RESP_BUF];   /* JSON response body */
static char s_resp_buf[XMIND_HTTP_RESP_BUF];    /* full HTTP response */

static void xmind_http_handle_conn(int conn_sd) {
    /* --- Read request --- */
    xh_memset(s_req_buf, 0, sizeof(s_req_buf));
    uint32_t total_read = 0u;
    int32_t  nr;
    while (total_read < (uint32_t)sizeof(s_req_buf) - 1u) {
        nr = xnet_recv(conn_sd,
                       &s_req_buf[total_read],
                       (size_t)((uint32_t)sizeof(s_req_buf) - 1u - total_read),
                       0);
        if (nr <= 0) { break; }
        total_read += (uint32_t)nr;
        /* Stop reading once we have the complete headers + some body.
         * We consider the request complete when we see \r\n\r\n and the
         * accumulated bytes include the declared Content-Length.  For
         * simplicity we stop as soon as we have the blank line and at
         * least 1 body byte, which is sufficient for well-formed clients
         * that send the body in the same segment as the headers. */
        uint32_t body_off = http_parse_body_offset(s_req_buf, total_read);
        if (body_off < total_read) { break; }
    }

    if (total_read == 0u) {
        xnet_close(conn_sd);
        return;
    }

    /* --- Validate method + path --- */
    if (!http_is_post_completions(s_req_buf, total_read)) {
        static const char not_found_body[] =
            "{\"error\":\"only POST /v1/completions is supported\"}";
        uint32_t resp_len = http_build_response(
            s_resp_buf, (uint32_t)sizeof(s_resp_buf),
            "404 Not Found",
            not_found_body,
            xh_strlen(not_found_body));
        (void)xnet_send(conn_sd, s_resp_buf, (size_t)resp_len, 0);
        xnet_close(conn_sd);
        return;
    }

    /* --- Extract JSON body --- */
    uint32_t body_off = http_parse_body_offset(s_req_buf, total_read);
    uint32_t body_len = (body_off < total_read) ? (total_read - body_off) : 0u;

    xh_memset(s_prompt_buf, 0, sizeof(s_prompt_buf));
    int32_t prompt_len = json_extract_string_field(
        &s_req_buf[body_off], body_len,
        "prompt",
        s_prompt_buf, (uint32_t)sizeof(s_prompt_buf));

    if (prompt_len <= 0) {
        static const char bad_req_body[] =
            "{\"error\":\"request body must contain \\\"prompt\\\" string field\"}";
        uint32_t resp_len = http_build_response(
            s_resp_buf, (uint32_t)sizeof(s_resp_buf),
            "400 Bad Request",
            bad_req_body,
            xh_strlen(bad_req_body));
        (void)xnet_send(conn_sd, s_resp_buf, (size_t)resp_len, 0);
        xnet_close(conn_sd);
        return;
    }

    /* --- Run inference --- */
    xh_memset(s_gen_buf, 0, sizeof(s_gen_buf));
    uint32_t gen_len = xmind_http_run_inference(
        s_prompt_buf, s_gen_buf, (uint32_t)sizeof(s_gen_buf));

    if (gen_len == 0u) {
        static const char unavail_body[] =
            "{\"error\":\"inference unavailable — model not ready\"}";
        uint32_t resp_len = http_build_response(
            s_resp_buf, (uint32_t)sizeof(s_resp_buf),
            "503 Service Unavailable",
            unavail_body,
            xh_strlen(unavail_body));
        (void)xnet_send(conn_sd, s_resp_buf, (size_t)resp_len, 0);
        xnet_close(conn_sd);
        return;
    }

    /* --- Build JSON response body --- */
    xh_memset(s_json_body, 0, sizeof(s_json_body));
    uint32_t json_len = json_build_text_response(
        s_json_body, (uint32_t)sizeof(s_json_body), s_gen_buf, gen_len);

    /* --- Build and send HTTP response --- */
    xh_memset(s_resp_buf, 0, sizeof(s_resp_buf));
    uint32_t resp_len = http_build_response(
        s_resp_buf, (uint32_t)sizeof(s_resp_buf),
        "200 OK",
        s_json_body, json_len);

    (void)xnet_send(conn_sd, s_resp_buf, (size_t)resp_len, 0);
    xnet_close(conn_sd);
}

/* ===================================================================
 * §8  PUBLIC API
 * =================================================================== */

/* Module-level listen socket descriptor */
static int s_listen_sd = XNET_SD_INVALID;

xmind_http_status_t xmind_http_init(uint16_t port) {
    /* Create a TCP stream socket */
    int sd = xnet_socket(XNET_AF_INET, XNET_SOCK_STREAM, 0);
    if (sd == XNET_SD_INVALID) {
        pal_console_printf("[XMIND-HTTP] xnet_socket() failed\n");
        return XMIND_HTTP_ERR_INVAL;
    }

    /* Enable SO_REUSEADDR so we can restart without waiting for TIME_WAIT */
    uint32_t reuseaddr = 1u;
    (void)xnet_setsockopt(sd, XNET_SOL_SOCKET, XNET_SO_REUSEADDR,
                           &reuseaddr, (uint32_t)sizeof(reuseaddr));

    /* Bind to 0.0.0.0:<port> */
    xnet_sockaddr_in_t addr;
    xh_memset(&addr, 0, (uint32_t)sizeof(addr));
    addr.family = (uint16_t)XNET_AF_INET;
    addr.port   = xnet_htons(port);
    addr.addr   = XNET_IPV4_ANY;   /* 0.0.0.0 */

    int brc = xnet_bind(sd,
                         (const xnet_sockaddr_t *)(const void *)&addr,
                         (uint32_t)sizeof(addr));
    if (brc != 0) {
        pal_console_printf("[XMIND-HTTP] xnet_bind() failed on port %u\n",
                           (unsigned)port);
        xnet_close(sd);
        return XMIND_HTTP_ERR_BIND;
    }

    int lrc = xnet_listen(sd, XMIND_HTTP_BACKLOG);
    if (lrc != 0) {
        pal_console_printf("[XMIND-HTTP] xnet_listen() failed\n");
        xnet_close(sd);
        return XMIND_HTTP_ERR_LISTEN;
    }

    s_listen_sd = sd;
    pal_console_printf("[XMIND-HTTP] listening on port %u\n",
                       (unsigned)port);
    return XMIND_HTTP_OK;
}

void xmind_http_serve(void) {
    if (s_listen_sd == XNET_SD_INVALID) {
        pal_console_printf("[XMIND-HTTP] serve called before init\n");
        return;
    }

    pal_console_printf("[XMIND-HTTP] entering accept loop\n");

    for (;;) {
        xnet_sockaddr_in_t remote;
        uint32_t remote_len = (uint32_t)sizeof(remote);
        xh_memset(&remote, 0, remote_len);

        int conn_sd = xnet_accept(s_listen_sd,
                                   (xnet_sockaddr_t *)(void *)&remote,
                                   &remote_len);
        if (conn_sd == XNET_SD_INVALID) {
            /* Accept failure is non-fatal — keep looping */
            pal_thread_yield();
            continue;
        }

        /* Handle the connection synchronously on this thread */
        xmind_http_handle_conn(conn_sd);
    }
    /* Unreachable — server runs until system halts */
}

void xmind_http_serve_thread(void *arg) {
    (void)arg;
    xmind_http_serve();
}
