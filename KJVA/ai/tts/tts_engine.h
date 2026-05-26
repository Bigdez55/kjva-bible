/*
 * ai/tts/tts_engine.h - Tokenless Text-to-Speech Engine
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Public API for the XTTS speech synthesis engine.  This layer sits between
 *   the accessibility tree (xa11y) and the audio output path (PAL audio, future
 *   sprint).  It provides:
 *     - A queued async speech pipeline (ring buffer of 8 utterances).
 *     - Rate, volume, and voice configuration.
 *     - A11y queue drain hook: xtts_process_a11y_queue() pulls from xa11y's
 *       announcement ring and feeds each entry into xtts_speak().
 *
 * DESIGN:
 *   All state is static (module-local in tts_engine.c).  No dynamic allocation.
 *   Thread safety: xtts_speak() and xtts_stop()/pause()/resume() are intended
 *   to be called from a single orchestration thread.  If multi-threaded access
 *   is later required, a PAL mutex guard must be added.
 *
 * FREESTANDING:
 *   Compiles clean under:
 *     clang --target=x86_64-unknown-none-elf -ffreestanding \
 *           -Ipal/include -Iui/xframe/runtime -Wall -Wextra
 *
 * AUDIO SYNTHESIS:
 *   Actual waveform synthesis is deferred to a future sprint.  The current
 *   implementation queues text entries and logs them via pal_console_printf().
 *   The skeleton is wire-compatible: when the audio backend is ready, only
 *   xtts_engine.c's internal render path changes — the header is frozen.
 */

#ifndef TOKENLESS_TTS_ENGINE_H
#define TOKENLESS_TTS_ENGINE_H

#include "../../pal/include/pal.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ═══════════════════════════════════════════════════════════════════
 * §1  ENUMERATED TYPES
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * xtts_voice_t — Available speech voice profiles.
 *
 * Voice characteristics are determined by the synthesis backend.
 * XTTS_VOICE_DEFAULT selects the system-configured voice.
 */
typedef enum {
    XTTS_VOICE_DEFAULT = 0,   /* System default voice                     */
    XTTS_VOICE_MALE    = 1,   /* Male voice profile                       */
    XTTS_VOICE_FEMALE  = 2,   /* Female voice profile                     */
    XTTS_VOICE_COUNT          /* Sentinel — number of voices; must be last */
} xtts_voice_t;

/**
 * xtts_state_t — Current engine playback state.
 *
 * Transitions:
 *   IDLE    → SPEAKING : xtts_speak() called with non-empty queue
 *   SPEAKING → PAUSED  : xtts_pause()
 *   PAUSED  → SPEAKING : xtts_resume()
 *   SPEAKING → IDLE    : queue drained naturally
 *   SPEAKING → IDLE    : xtts_stop() called
 *   PAUSED  → IDLE     : xtts_stop() called
 */
typedef enum {
    XTTS_STATE_IDLE     = 0,   /* Engine is silent, queue empty            */
    XTTS_STATE_SPEAKING = 1,   /* Currently outputting audio               */
    XTTS_STATE_PAUSED   = 2,   /* Mid-utterance pause; queue preserved     */
} xtts_state_t;

/* ═══════════════════════════════════════════════════════════════════
 * §2  CONSTANTS
 * ═══════════════════════════════════════════════════════════════════ */

/** Maximum length of a single queued utterance, including NUL terminator. */
#define XTTS_MAX_UTTERANCE_LEN  256U

/** Number of utterance slots in the speech ring buffer. */
#define XTTS_QUEUE_DEPTH        8U

/** Default speech rate (maps to 1x normal speed). */
#define XTTS_RATE_DEFAULT       50U

/** Default volume (full). */
#define XTTS_VOLUME_DEFAULT     100U

/** Audio sample rate for PCM output (Hz). */
#define XTTS_SAMPLE_RATE        22050U

/** Maximum phonemes per utterance. */
#define XTTS_MAX_PHONEMES       512U

/** Default words-per-minute speech rate. */
#define XTTS_WPM_DEFAULT        150U

/** Default base pitch for male voice (Hz). */
#define XTTS_PITCH_MALE         150U

/** Default base pitch for female voice (Hz). */
#define XTTS_PITCH_FEMALE       220U

/* ═══════════════════════════════════════════════════════════════════
 * §2a FORMANT SYNTHESIS TYPES
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * xtts_pcm_callback_t -- Callback invoked with generated PCM samples.
 *
 * @param samples   Buffer of 16-bit signed PCM samples at XTTS_SAMPLE_RATE.
 * @param count     Number of samples in the buffer.
 * @param userdata  Opaque pointer passed to xtts_speak_cb().
 */
typedef void (*xtts_pcm_callback_t)(const int16_t *samples,
                                     uint32_t count,
                                     void *userdata);

/**
 * xtts_phoneme_t -- A single phoneme with formant frequencies.
 *
 * DECTalk-style formant model: three formant frequencies (F1, F2, F3)
 * plus bandwidth and duration parameters.
 */
typedef struct {
    uint16_t f1;            /* First formant frequency  (Hz) */
    uint16_t f2;            /* Second formant frequency (Hz) */
    uint16_t f3;            /* Third formant frequency  (Hz) */
    uint16_t bw1;           /* Bandwidth of F1 (Hz)          */
    uint16_t bw2;           /* Bandwidth of F2 (Hz)          */
    uint16_t bw3;           /* Bandwidth of F3 (Hz)          */
    uint16_t duration_ms;   /* Duration in milliseconds      */
    uint8_t  voiced;        /* 1 = voiced, 0 = unvoiced      */
    uint8_t  _pad;
} xtts_phoneme_t;

/* ═══════════════════════════════════════════════════════════════════
 * §3  LIFECYCLE
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * xtts_init — Initialize the TTS engine.
 *
 * Must be called once at system startup before any other XTTS function.
 * Sets rate to XTTS_RATE_DEFAULT, volume to XTTS_VOLUME_DEFAULT, voice to
 * XTTS_VOICE_DEFAULT, state to XTTS_STATE_IDLE, and clears the queue.
 *
 * Safe to call multiple times (idempotent after first call).
 */
void xtts_init(void);

/**
 * xtts_shutdown — Tear down the TTS engine.
 *
 * Stops any in-progress utterance, drains and discards the queue,
 * and resets all state to initial values.  After this call, xtts_init()
 * must be called again before using the engine.
 */
void xtts_shutdown(void);

/* ═══════════════════════════════════════════════════════════════════
 * §4  SPEECH CONTROL
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * xtts_speak — Enqueue text for asynchronous speech synthesis.
 *
 * @param text   NUL-terminated UTF-8 string.  Maximum XTTS_MAX_UTTERANCE_LEN-1
 *               characters; longer strings are truncated silently.
 *               NULL or empty string is silently ignored.
 * @param voice  Voice profile to use for this utterance.
 *
 * If the queue is full (XTTS_QUEUE_DEPTH entries pending), the oldest
 * entry is discarded to make room (priority: new announcements win).
 *
 * Sets engine state to XTTS_STATE_SPEAKING if it was XTTS_STATE_IDLE.
 */
void xtts_speak(const char *text, xtts_voice_t voice);

/**
 * xtts_stop — Immediately stop speech and clear the queue.
 *
 * Transitions state to XTTS_STATE_IDLE.  Any in-progress audio frame
 * is abandoned.  Safe to call from any state.
 */
void xtts_stop(void);

/**
 * xtts_pause — Pause speech at the next utterance boundary.
 *
 * Only valid in XTTS_STATE_SPEAKING.  Calling in other states is a no-op.
 * Transitions to XTTS_STATE_PAUSED.  The queue is preserved.
 */
void xtts_pause(void);

/**
 * xtts_resume — Resume paused speech.
 *
 * Only valid in XTTS_STATE_PAUSED.  Calling in other states is a no-op.
 * Transitions to XTTS_STATE_SPEAKING and continues from where the queue left off.
 */
void xtts_resume(void);

/* ═══════════════════════════════════════════════════════════════════
 * §5  CONFIGURATION
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * xtts_set_rate — Set the speech rate.
 *
 * @param rate  0–100 where 0 = slowest, 50 = normal, 100 = fastest.
 *              Values outside [0, 100] are clamped silently.
 *
 * Takes effect from the next utterance (current utterance is unaffected).
 */
void xtts_set_rate(uint8_t rate);

/**
 * xtts_set_volume — Set the output volume.
 *
 * @param vol  0–100 where 0 = silent, 100 = maximum.
 *             Values outside [0, 100] are clamped silently.
 *
 * Takes effect immediately, including during playback.
 */
void xtts_set_volume(uint8_t vol);

/**
 * xtts_set_voice — Set the active voice profile.
 *
 * @param v  Voice to select.  Invalid values fall back to XTTS_VOICE_DEFAULT.
 *
 * Takes effect from the next utterance.
 */
void xtts_set_voice(xtts_voice_t v);

/* ═══════════════════════════════════════════════════════════════════
 * §6  STATE QUERY
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * xtts_get_state — Return the current engine state.
 *
 * Callers may poll this or wire it to a condition variable (future sprint).
 */
xtts_state_t xtts_get_state(void);

/**
 * xtts_get_queue_depth — Return the number of utterances currently queued.
 *
 * 0 means idle.  Maximum is XTTS_QUEUE_DEPTH.
 */
uint32_t xtts_get_queue_depth(void);

/* ═══════════════════════════════════════════════════════════════════
 * §7  ACCESSIBILITY INTEGRATION
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * xtts_process_a11y_queue — Drain the xa11y announcement queue into XTTS.
 *
 * Intended to be called periodically from the accessibility event loop or
 * the compositor's tick handler.  Pulls all pending announcements from
 * xa11y_dequeue_announcement() and feeds each into xtts_speak() using
 * the current voice profile.
 *
 * This function is a no-op when the xa11y subsystem is not initialized.
 * It is safe to call before xtts_init() — it will return immediately.
 *
 * NOTE: xa11y_dequeue_announcement() is declared in ui/xframe/runtime/xframe.h
 *       and implemented in xframe's a11y module.  The TTS engine declares it
 *       here as an extern weak symbol so the engine remains link-safe when
 *       XFRAME is excluded from a build target (e.g., headless CI).
 */
void xtts_process_a11y_queue(void);

/* ═══════════════════════════════════════════════════════════════════
 * §8  FORMANT SYNTHESIS API (EU Accessibility Act 2025 / ADA)
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * xtts_speak_cb -- Synthesize text to PCM audio via callback.
 *
 * Converts text to phonemes via the built-in phoneme table, then
 * generates PCM samples using a DECTalk-style three-formant synthesizer
 * with basic prosody (pitch rise on questions, fall on statements).
 *
 * @param text      NUL-terminated text to speak.
 * @param voice     Voice profile (selects base pitch).
 * @param callback  Called with PCM sample buffers as they are generated.
 * @param userdata  Opaque pointer forwarded to callback.
 */
void xtts_speak_cb(const char *text, xtts_voice_t voice,
                   xtts_pcm_callback_t callback, void *userdata);

/**
 * xtts_set_rate_wpm -- Set speech rate in words per minute.
 *
 * @param wpm  Words per minute (80-300). Clamped to valid range.
 *             Default is XTTS_WPM_DEFAULT (150).
 */
void xtts_set_rate_wpm(uint32_t wpm);

/**
 * xtts_set_pitch_hz -- Set base pitch frequency.
 *
 * @param hz  Base pitch in Hz (50-500). Clamped to valid range.
 *            Default: XTTS_PITCH_MALE (150 Hz) or XTTS_PITCH_FEMALE (220 Hz).
 */
void xtts_set_pitch_hz(uint32_t hz);

/**
 * xtts_text_to_phonemes -- Convert text to phoneme sequence.
 *
 * Exposed for testing and screen reader inspection. Populates the
 * output array with phonemes derived from the ASCII phoneme table.
 *
 * @param text        NUL-terminated input text.
 * @param out         Output phoneme array.
 * @param max_out     Maximum number of phonemes to write.
 * @return            Number of phonemes written.
 */
uint32_t xtts_text_to_phonemes(const char *text,
                                xtts_phoneme_t *out,
                                uint32_t max_out);

#ifdef __cplusplus
}
#endif

#endif /* TOKENLESS_TTS_ENGINE_H */
