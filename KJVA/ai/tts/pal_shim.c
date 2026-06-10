/*
 * ai/tts/pal_shim.c -- Hosted PAL shim for the TTS engine ctypes build.
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE
 *   tts_engine.c declares `pal_console_printf` as a *hard* (non-weak) extern.
 *   In the freestanding kernel build this is provided by the PAL backend
 *   (serial UART write). For the hosted ctypes build (libtts.dylib consumed
 *   by tts_bridge.py) there is no PAL, so the dynamic library would fail to
 *   link with an undefined symbol.
 *
 *   This shim provides a libc-backed implementation so the engine links and
 *   runs in a normal hosted process. It is ONLY compiled into the hosted
 *   dylib — it is never part of the freestanding/kernel build, which keeps
 *   the freestanding contract (no libc) intact.
 *
 *   Note: the weak externs `xaudio_pcm_write`, `xa11y_dequeue_announcement`
 *   intentionally resolve to NULL in this build. The xtts_speak_cb() PCM
 *   path does not touch them, so NULL is correct and safe here.
 */

#include <stdio.h>
#include <stdarg.h>
#include <stdint.h>

void pal_console_printf(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
}

/*
 * Weak-extern resolution for the hosted dylib.
 *
 * tts_engine.c declares `xa11y_dequeue_announcement` and `xaudio_pcm_write`
 * as `__attribute__((weak))` so kernel/fuzz builds can omit XFRAME/XAUDIO.
 * On macOS the linker does NOT auto-resolve an *undefined* weak reference to
 * NULL when producing a -dynamiclib without -undefined dynamic_lookup; it
 * errors. Rather than weaken the link policy globally (which would also let
 * the hard `pal_console_printf` extern slip through silently), we provide
 * concrete inert definitions here. Neither is reachable from the
 * xtts_speak_cb() PCM path the bridge drives — they exist only to satisfy the
 * linker for the audio-render / a11y-poll code paths the bridge never calls.
 */
const char *xa11y_dequeue_announcement(void) {
    return (const char *)0;  /* no queued announcement in hosted bridge */
}

void xaudio_pcm_write(const int16_t *samples, uint32_t n_samples,
                      uint32_t sample_rate) {
    (void)samples;
    (void)n_samples;
    (void)sample_rate;  /* hosted bridge captures PCM via callback, not this */
}
