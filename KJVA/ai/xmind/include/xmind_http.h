/*
 * xmind_http.h — XMIND HTTP Inference API
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Provides a minimal HTTP/1.1 server that exposes XMIND inference over
 * a POST /v1/completions endpoint.  100% freestanding — no libc, no
 * malloc, no stdio.  Static buffers only.
 *
 * Usage (from boot_chain.c or GENSD service):
 *   1. xmind_http_init(8080)
 *   2. pal_thread_create(…, xmind_http_serve_thread, NULL, …)
 *
 * Wire protocol:
 *   Request:  POST /v1/completions HTTP/1.1\r\n…\r\n\r\n{"prompt":"<text>"}
 *   Response: HTTP/1.1 200 OK\r\n…\r\n\r\n{"text":"<generated>"}
 */

#ifndef XMIND_HTTP_H
#define XMIND_HTTP_H

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "../../../pal/include/pal.h"

/* ═══════════════════════════════════════════════════════════════════
 * §1  CONFIGURATION CONSTANTS
 * ═══════════════════════════════════════════════════════════════════ */

/* Maximum size of a single HTTP request body we will read (8 KiB) */
#define XMIND_HTTP_REQ_BUF    8192u

/* Maximum size of the HTTP response we send (16 KiB) */
#define XMIND_HTTP_RESP_BUF   16384u

/* Maximum generated tokens per request */
#define XMIND_HTTP_MAX_TOKENS 256u

/* TCP listen backlog */
#define XMIND_HTTP_BACKLOG    4

/* ═══════════════════════════════════════════════════════════════════
 * §2  STATUS CODES
 * ═══════════════════════════════════════════════════════════════════ */

typedef int32_t xmind_http_status_t;

#define XMIND_HTTP_OK          ((xmind_http_status_t)  0)
#define XMIND_HTTP_ERR_INVAL   ((xmind_http_status_t) -1)
#define XMIND_HTTP_ERR_BIND    ((xmind_http_status_t) -2)
#define XMIND_HTTP_ERR_LISTEN  ((xmind_http_status_t) -3)

/* ═══════════════════════════════════════════════════════════════════
 * §3  PUBLIC API
 * ═══════════════════════════════════════════════════════════════════ */

/*
 * xmind_http_init — bind the HTTP server socket on the given port.
 * Must be called once before xmind_http_serve() or
 * xmind_http_serve_thread().
 * Returns XMIND_HTTP_OK on success; XMIND_HTTP_ERR_* on failure.
 */
xmind_http_status_t xmind_http_init(uint16_t port);

/*
 * xmind_http_serve — main accept loop.  Blocks forever, handling one
 * connection at a time.  Intended to run on a dedicated PAL thread.
 * Returns only on unrecoverable error.
 */
void xmind_http_serve(void);

/*
 * xmind_http_serve_thread — PAL thread entry point adapter.
 * Signature matches pal_thread_fn (void (*)(void *arg)).
 * Simply calls xmind_http_serve() and ignores arg.
 */
void xmind_http_serve_thread(void *arg);

#endif /* XMIND_HTTP_H */
