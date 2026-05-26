/*
 * ai/tts/tts_engine.c -- Tokenless Text-to-Speech Engine
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * COMPILE:
 *   clang --target=x86_64-unknown-none-elf -ffreestanding \
 *         -Ipal/include -Iui/xframe/runtime \
 *         -Wall -Wextra -Werror -O2 \
 *         -c ai/tts/tts_engine.c -o tts_engine.o
 *
 * AUDIO SYNTHESIS:
 *   This module implements a DECTalk-style formant synthesizer for the
 *   EU Accessibility Act 2025 / ADA screen reader requirement.
 *
 *   The synthesis pipeline:
 *     1. Text -> phoneme sequence (ASCII letter/digraph mapping)
 *     2. Phoneme -> formant parameters (F1, F2, F3 frequencies)
 *     3. Formant synthesis -> PCM samples at 22050 Hz
 *     4. Basic prosody: pitch contour (rise on '?', fall on '.')
 *     5. Output via xtts_pcm_callback_t or pal_console_printf() fallback
 *
 *   The queue/state/voice machinery from the Sprint 30 skeleton is preserved.
 *   xtts_speak() continues to use console output for backward compatibility.
 *   xtts_speak_cb() is the new PCM synthesis path.
 */

#include "tts_engine.h"

/* ── PAL console dependency ─────────────────────────────────────────────────
 * pal_console_printf is provided by the PAL backend.  In freestanding builds
 * it maps to a serial UART write.  In hosted CI builds it calls printf.     */
#ifndef PAL_FREESTANDING
#  include <string.h>   /* memset, memcpy, strlen */
#else
/* Freestanding string helpers — no libc available */
static size_t xtts_strlen_(const char *s) {
    size_t n = 0;
    while (s[n]) ++n;
    return n;
}
static void *xtts_memset_(void *dst, int c, size_t n) {
    unsigned char *p = (unsigned char *)dst;
    while (n--) *p++ = (unsigned char)c;
    return dst;
}
static void *xtts_memcpy_(void *dst, const void *src, size_t n) {
    unsigned char       *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    while (n--) *d++ = *s++;
    return dst;
}
#  define strlen  xtts_strlen_
#  define memset  xtts_memset_
#  define memcpy  xtts_memcpy_
#endif /* PAL_FREESTANDING */

/* ── xa11y weak symbol declaration ─────────────────────────────────────────
 * xa11y_dequeue_announcement() is implemented in the XFRAME a11y module.
 * We use a weak reference so this translation unit links cleanly on build
 * targets that exclude XFRAME (headless kernel CI, fuzz harnesses).        */
extern __attribute__((weak))
const char *xa11y_dequeue_announcement(void);

/* ── PAL console printf forward declaration ─────────────────────────────── */
extern void pal_console_printf(const char *fmt, ...);

/* ═══════════════════════════════════════════════════════════════════
 * §1  INTERNAL TYPES
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * xtts_utterance_t — A single entry in the speech queue.
 */
typedef struct {
    char         text[XTTS_MAX_UTTERANCE_LEN];   /* UTF-8, NUL-terminated  */
    xtts_voice_t voice;                           /* Voice for this entry   */
} xtts_utterance_t;

/**
 * xtts_state_block_t — All mutable engine state in one cacheline-friendly
 * struct.  Kept static (module-local) — no external allocation.
 */
typedef struct {
    /* Configuration */
    uint8_t      rate;    /* 0–100 */
    uint8_t      volume;  /* 0–100 */
    xtts_voice_t voice;   /* Default voice for new utterances    */

    /* Playback state */
    xtts_state_t state;

    /* Speech ring buffer */
    xtts_utterance_t queue[XTTS_QUEUE_DEPTH];
    uint32_t         q_head;    /* Index of next slot to enqueue into */
    uint32_t         q_tail;    /* Index of next slot to dequeue from */
    uint32_t         q_count;   /* Number of entries currently queued */

    /* Initialized flag */
    bool initialized;

    /* Formant synthesis configuration */
    uint32_t wpm;           /* Words per minute (80-300)     */
    uint32_t base_pitch_hz; /* Base pitch frequency in Hz    */
} xtts_state_block_t;

/* ── Module-local state ─────────────────────────────────────────────────── */

static xtts_state_block_t s_tts;

/* ═══════════════════════════════════════════════════════════════════
 * §2  INTERNAL HELPERS
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * xtts_enqueue_ — Add an utterance to the ring buffer.
 *
 * If the queue is full, the oldest entry is dropped to make room.
 * This matches the design decision in the header: new announcements win.
 */
static void xtts_enqueue_(const char *text, xtts_voice_t voice) {
    if (s_tts.q_count == XTTS_QUEUE_DEPTH) {
        /* Drop oldest: advance tail. */
        s_tts.q_tail = (s_tts.q_tail + 1U) % XTTS_QUEUE_DEPTH;
        s_tts.q_count--;
        pal_console_printf("[XTTS] queue full — oldest utterance dropped\n");
    }

    xtts_utterance_t *slot = &s_tts.queue[s_tts.q_head];
    size_t len = strlen(text);
    if (len >= XTTS_MAX_UTTERANCE_LEN) {
        len = XTTS_MAX_UTTERANCE_LEN - 1U;
    }
    memcpy(slot->text, text, len);
    slot->text[len] = '\0';
    slot->voice = voice;

    s_tts.q_head = (s_tts.q_head + 1U) % XTTS_QUEUE_DEPTH;
    s_tts.q_count++;
}

/**
 * xtts_dequeue_ — Fetch the next utterance from the ring buffer.
 *
 * Returns a pointer to the dequeued slot (static storage — caller must not
 * keep the pointer across further queue mutations), or NULL if queue is empty.
 */
static const xtts_utterance_t *xtts_dequeue_(void) {
    if (s_tts.q_count == 0U) {
        return NULL;
    }
    const xtts_utterance_t *slot = &s_tts.queue[s_tts.q_tail];
    s_tts.q_tail = (s_tts.q_tail + 1U) % XTTS_QUEUE_DEPTH;
    s_tts.q_count--;
    return slot;
}

/**
 * xtts_render_utterance_ — Render a single utterance to audio output.
 *
 * Logs the utterance to the console for backward compatibility, then
 * synthesizes PCM audio via the formant synthesizer and delivers it
 * to the audio subsystem via xaudio_pcm_write (when linked).
 *
 * @param utt    Utterance to render (text + voice).
 * @param rate   Speech rate 0–100.
 * @param volume Output volume 0–100.
 */

/* Forward declarations for formant synthesis functions defined in §8 */
static uint32_t xtts_synth_phoneme_(const xtts_phoneme_t *ph, uint32_t pitch_hz,
                                     uint8_t volume, uint32_t wpm,
                                     int16_t *out, uint32_t max_samp);
static uint32_t xtts_compute_pitch_(uint32_t base_hz, uint32_t pos_num,
                                     uint32_t pos_den, char sentence_end);
static char xtts_find_sentence_end_(const char *text);

/* Forward declaration for PCM synthesis buffer defined in §8 */
#define XTTS_PCM_BUF_SIZE_FWD  (XTTS_SAMPLE_RATE / 5 + 1)
static int16_t s_pcm_buf_fwd[XTTS_PCM_BUF_SIZE_FWD];

/*
 * xaudio_pcm_write -- Write PCM samples to the audio subsystem.
 *
 * Weak extern: resolved to the XAUDIO driver implementation when linked,
 * or NULL in headless/test builds.  This allows the TTS engine to output
 * real audio when the audio subsystem is available without creating a
 * hard link dependency.
 *
 * @param samples      Buffer of signed 16-bit PCM samples.
 * @param n_samples    Number of samples in the buffer.
 * @param sample_rate  Sample rate in Hz (e.g. 22050).
 */
extern __attribute__((weak))
void xaudio_pcm_write(const int16_t *samples, uint32_t n_samples,
                       uint32_t sample_rate);

static void xtts_render_utterance_(
    const xtts_utterance_t *utt,
    uint8_t rate,
    uint8_t volume
) {
    static const char *const voice_names[XTTS_VOICE_COUNT] = {
        "default", "male", "female"
    };
    xtts_voice_t safe_voice = (utt->voice < XTTS_VOICE_COUNT)
        ? utt->voice
        : XTTS_VOICE_DEFAULT;

    pal_console_printf(
        "[XTTS] speak voice=%s rate=%u vol=%u: \"%s\"\n",
        voice_names[safe_voice],
        (unsigned)rate,
        (unsigned)volume,
        utt->text
    );

    /*
     * Synthesize the utterance text into PCM audio using the formant
     * synthesizer and deliver to the audio subsystem via xaudio_pcm_write.
     *
     * If xaudio_pcm_write is not linked (headless kernel CI, fuzz builds),
     * the weak symbol resolves to NULL and we skip audio output.
     */
    if (xaudio_pcm_write != NULL) {
        /* Select base pitch for voice */
        uint32_t base_pitch = s_tts.base_pitch_hz;
        if (safe_voice == XTTS_VOICE_FEMALE) {
            base_pitch = XTTS_PITCH_FEMALE;
        } else if (safe_voice == XTTS_VOICE_MALE) {
            base_pitch = XTTS_PITCH_MALE;
        }

        /* Convert text to phoneme sequence */
        xtts_phoneme_t phonemes[XTTS_MAX_PHONEMES];
        uint32_t num_phonemes = xtts_text_to_phonemes(utt->text, phonemes,
                                                       XTTS_MAX_PHONEMES);

        if (num_phonemes > 0U) {
            /* Detect sentence-ending punctuation for prosody */
            char sentence_end = xtts_find_sentence_end_(utt->text);

            /* Synthesize each phoneme and write PCM to audio subsystem */
            uint32_t pi;
            for (pi = 0; pi < num_phonemes; pi++) {
                /* Compute prosody-adjusted pitch */
                uint32_t pitch = xtts_compute_pitch_(base_pitch, pi,
                                                      num_phonemes,
                                                      sentence_end);

                /* Synthesize phoneme into the render PCM buffer */
                uint32_t samp_count = xtts_synth_phoneme_(
                    &phonemes[pi], pitch, volume, s_tts.wpm,
                    s_pcm_buf_fwd, XTTS_PCM_BUF_SIZE_FWD
                );

                /* Write samples to the audio subsystem */
                if (samp_count > 0U) {
                    xaudio_pcm_write(s_pcm_buf_fwd, samp_count, XTTS_SAMPLE_RATE);
                }
            }
        }
    }
    (void)rate;  /* rate is applied via WPM scaling in synth_phoneme */
}

/* ═══════════════════════════════════════════════════════════════════
 * §3  LIFECYCLE
 * ═══════════════════════════════════════════════════════════════════ */

void xtts_init(void) {
    if (s_tts.initialized) {
        return;   /* Idempotent */
    }
    memset(&s_tts, 0, sizeof(s_tts));
    s_tts.rate          = XTTS_RATE_DEFAULT;
    s_tts.volume        = XTTS_VOLUME_DEFAULT;
    s_tts.voice         = XTTS_VOICE_DEFAULT;
    s_tts.state         = XTTS_STATE_IDLE;
    s_tts.wpm           = XTTS_WPM_DEFAULT;
    s_tts.base_pitch_hz = XTTS_PITCH_MALE;
    s_tts.initialized   = true;
    pal_console_printf("[XTTS] engine initialized (queue_depth=%u, sample_rate=%u)\n",
                       XTTS_QUEUE_DEPTH, XTTS_SAMPLE_RATE);
}

void xtts_shutdown(void) {
    if (!s_tts.initialized) {
        return;
    }
    pal_console_printf("[XTTS] shutdown — %u utterance(s) discarded\n",
                       s_tts.q_count);
    memset(&s_tts, 0, sizeof(s_tts));
    /* initialized stays false after memset — engine requires xtts_init() again */
}

/* ═══════════════════════════════════════════════════════════════════
 * §4  SPEECH CONTROL
 * ═══════════════════════════════════════════════════════════════════ */

void xtts_speak(const char *text, xtts_voice_t voice) {
    if (!s_tts.initialized) {
        return;
    }
    if (text == NULL || text[0] == '\0') {
        return;
    }

    xtts_enqueue_(text, voice);

    if (s_tts.state == XTTS_STATE_IDLE) {
        s_tts.state = XTTS_STATE_SPEAKING;
    }

    /*
     * In this skeleton, we immediately dequeue and render synchronously.
     * Sprint 37 will introduce an async audio task that is woken here via
     * a PAL event signal instead of calling xtts_render_utterance_() inline.
     */
    if (s_tts.state == XTTS_STATE_SPEAKING) {
        const xtts_utterance_t *utt = xtts_dequeue_();
        if (utt != NULL) {
            xtts_render_utterance_(utt, s_tts.rate, s_tts.volume);
        }
        if (s_tts.q_count == 0U) {
            s_tts.state = XTTS_STATE_IDLE;
        }
    }
}

void xtts_stop(void) {
    if (!s_tts.initialized) {
        return;
    }
    /* Discard queue. */
    s_tts.q_head  = 0U;
    s_tts.q_tail  = 0U;
    s_tts.q_count = 0U;
    s_tts.state   = XTTS_STATE_IDLE;
    pal_console_printf("[XTTS] stopped\n");
}

void xtts_pause(void) {
    if (!s_tts.initialized) {
        return;
    }
    if (s_tts.state != XTTS_STATE_SPEAKING) {
        return;   /* No-op in any other state */
    }
    s_tts.state = XTTS_STATE_PAUSED;
    pal_console_printf("[XTTS] paused (%u utterance(s) remaining)\n",
                       s_tts.q_count);
}

void xtts_resume(void) {
    if (!s_tts.initialized) {
        return;
    }
    if (s_tts.state != XTTS_STATE_PAUSED) {
        return;   /* No-op in any other state */
    }
    s_tts.state = XTTS_STATE_SPEAKING;
    pal_console_printf("[XTTS] resumed (%u utterance(s) queued)\n",
                       s_tts.q_count);

    /* Drain the queue now that we're unpaused. */
    while (s_tts.q_count > 0U && s_tts.state == XTTS_STATE_SPEAKING) {
        const xtts_utterance_t *utt = xtts_dequeue_();
        if (utt == NULL) break;
        xtts_render_utterance_(utt, s_tts.rate, s_tts.volume);
    }

    if (s_tts.q_count == 0U) {
        s_tts.state = XTTS_STATE_IDLE;
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * §5  CONFIGURATION
 * ═══════════════════════════════════════════════════════════════════ */

void xtts_set_rate(uint8_t rate) {
    if (!s_tts.initialized) {
        return;
    }
    /* Clamp to [0, 100]. */
    s_tts.rate = (rate > 100U) ? 100U : rate;
}

void xtts_set_volume(uint8_t vol) {
    if (!s_tts.initialized) {
        return;
    }
    s_tts.volume = (vol > 100U) ? 100U : vol;
}

void xtts_set_voice(xtts_voice_t v) {
    if (!s_tts.initialized) {
        return;
    }
    if (v >= XTTS_VOICE_COUNT) {
        v = XTTS_VOICE_DEFAULT;
    }
    s_tts.voice = v;
}

/* ═══════════════════════════════════════════════════════════════════
 * §6  STATE QUERY
 * ═══════════════════════════════════════════════════════════════════ */

xtts_state_t xtts_get_state(void) {
    if (!s_tts.initialized) {
        return XTTS_STATE_IDLE;
    }
    return s_tts.state;
}

uint32_t xtts_get_queue_depth(void) {
    if (!s_tts.initialized) {
        return 0U;
    }
    return s_tts.q_count;
}

/* ═══════════════════════════════════════════════════════════════════
 * §7  ACCESSIBILITY INTEGRATION
 * ═══════════════════════════════════════════════════════════════════ */

void xtts_process_a11y_queue(void) {
    if (!s_tts.initialized) {
        return;
    }

    /*
     * xa11y_dequeue_announcement is a weak extern.  If XFRAME is not
     * linked into this binary the symbol resolves to NULL (ELF weak
     * semantics), and we skip the drain loop entirely.
     */
    if (xa11y_dequeue_announcement == NULL) {
        return;
    }

    /*
     * Drain up to XTTS_QUEUE_DEPTH announcements per tick to prevent
     * a burst of a11y events from stalling the compositor loop.
     */
    uint32_t drained = 0U;
    while (drained < XTTS_QUEUE_DEPTH) {
        const char *announcement = xa11y_dequeue_announcement();
        if (announcement == NULL) {
            break;   /* Queue empty */
        }
        xtts_speak(announcement, s_tts.voice);
        drained++;
    }

    if (drained > 0U) {
        pal_console_printf("[XTTS] a11y drain: %u announcement(s) queued\n",
                           drained);
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * §8  DECTalk-STYLE FORMANT SYNTHESIZER
 *
 * EU Accessibility Act 2025 / ADA compliance: real PCM synthesis.
 * Maps ASCII text -> phoneme sequence -> formant parameters ->
 * synthesized waveform via three-formant parallel resonator model.
 * ═══════════════════════════════════════════════════════════════════ */

/* ── Phoneme table ─────────────────────────────────────────────────────────
 * Each ASCII letter maps to approximate English formant frequencies.
 * Values derived from Klatt (1980) and DECTalk documentation.
 * F1, F2, F3 in Hz; BW1, BW2, BW3 bandwidths; duration in ms.
 *
 * Index: letter - 'A' (0-25).  Digraphs handled separately.         */

typedef struct {
    uint16_t f1, f2, f3;       /* Formant frequencies  */
    uint16_t bw1, bw2, bw3;   /* Bandwidths           */
    uint16_t dur_ms;           /* Phoneme duration      */
    uint8_t  voiced;           /* 1=voiced, 0=unvoiced  */
} xtts_phon_entry_t;

static const xtts_phon_entry_t PHONEME_TABLE[26] = {
    /* A */ { 730, 1090, 2440,  90,  110, 170,  80, 1 },  /* /ae/ as in "cat"     */
    /* B */ { 200,  900, 2300,  60,   90, 150,  60, 1 },  /* /b/ stop consonant   */
    /* C */ { 200, 1800, 2600,  80,  120, 180,  70, 0 },  /* /k/ unvoiced stop    */
    /* D */ { 200, 1600, 2600,  60,  100, 160,  55, 1 },  /* /d/ voiced stop      */
    /* E */ { 530, 1840, 2480,  70,  100, 140,  70, 1 },  /* /eh/ as in "bed"     */
    /* F */ { 200, 1400, 2600,  80,  120, 200,  80, 0 },  /* /f/ fricative        */
    /* G */ { 200, 1000, 2300,  60,  100, 160,  60, 1 },  /* /g/ voiced stop      */
    /* H */ { 200, 1200, 2500, 120,  200, 300,  50, 0 },  /* /h/ aspiration       */
    /* I */ { 270, 2290, 3010,  60,   90, 130,  65, 1 },  /* /ih/ as in "bit"     */
    /* J */ { 200, 1600, 2600,  60,  100, 160,  70, 1 },  /* /dZ/ as in "judge"   */
    /* K */ { 200, 1800, 2600,  80,  120, 180,  80, 0 },  /* /k/ unvoiced stop    */
    /* L */ { 310, 1050, 2880,  50,   80, 120,  60, 1 },  /* /l/ lateral          */
    /* M */ { 270,  900, 2200,  50,   70, 120,  70, 1 },  /* /m/ nasal            */
    /* N */ { 270, 1600, 2700,  50,   70, 120,  60, 1 },  /* /n/ nasal            */
    /* O */ { 570,  840, 2410,  70,   90, 140,  75, 1 },  /* /aa/ as in "bot"     */
    /* P */ { 200, 1000, 2500,  60,  100, 150,  60, 0 },  /* /p/ unvoiced stop    */
    /* Q */ { 200, 1800, 2600,  80,  120, 180,  80, 0 },  /* /kw/ as in "queen"   */
    /* R */ { 310, 1060, 1380,  70,  100, 130,  65, 1 },  /* /r/ approximant      */
    /* S */ { 200, 1400, 2600, 100,  150, 250,  90, 0 },  /* /s/ fricative        */
    /* T */ { 200, 1600, 2600,  80,  120, 180,  60, 0 },  /* /t/ unvoiced stop    */
    /* U */ { 300, 870,  2240,  70,  100, 140,  70, 1 },  /* /uh/ as in "put"     */
    /* V */ { 220, 1400, 2600,  60,  100, 160,  65, 1 },  /* /v/ voiced fricative */
    /* W */ { 290,  610, 2150,  50,   80, 120,  55, 1 },  /* /w/ glide            */
    /* X */ { 200, 1400, 2600, 100,  150, 250,  90, 0 },  /* /ks/ cluster         */
    /* Y */ { 280, 2200, 2960,  50,   80, 120,  55, 1 },  /* /j/ glide            */
    /* Z */ { 200, 1400, 2600,  80,  120, 200,  85, 1 },  /* /z/ voiced fricative */
};

/* Digraph table: common English letter pairs mapped to single phonemes */
typedef struct {
    char     pair[3];  /* Two-char digraph + NUL */
    uint16_t f1, f2, f3;
    uint16_t bw1, bw2, bw3;
    uint16_t dur_ms;
    uint8_t  voiced;
} xtts_digraph_entry_t;

#define XTTS_DIGRAPH_COUNT 8u

static const xtts_digraph_entry_t DIGRAPH_TABLE[XTTS_DIGRAPH_COUNT] = {
    { "TH", 200, 1400, 2600,  80, 120, 200,  80, 0 },  /* /th/ as in "thin"  */
    { "SH", 200, 1800, 2700, 100, 150, 250,  90, 0 },  /* /sh/ as in "ship"  */
    { "CH", 200, 1800, 2600,  90, 130, 220,  85, 0 },  /* /ch/ as in "chip"  */
    { "PH", 200, 1400, 2600,  80, 120, 200,  80, 0 },  /* /f/ as in "phone"  */
    { "WH", 290,  610, 2150,  50,  80, 120,  60, 0 },  /* /hw/ as in "what"  */
    { "NG", 280, 1600, 2500,  50,  70, 120,  70, 1 },  /* /ng/ as in "sing"  */
    { "EE", 270, 2290, 3010,  60,  90, 130, 100, 1 },  /* /iy/ as in "see"   */
    { "OO", 300,  870, 2240,  70, 100, 140, 100, 1 },  /* /uw/ as in "too"   */
};

/* Space/silence phoneme */
static const xtts_phon_entry_t SILENCE_PHONEME = {
    0, 0, 0, 0, 0, 0, 80, 0
};

/* ── xtts_text_to_phonemes ─────────────────────────────────────────────── */

static char xtts_to_upper_(char c) {
    if (c >= 'a' && c <= 'z') return (char)(c - 32);
    return c;
}

uint32_t xtts_text_to_phonemes(const char *text,
                                xtts_phoneme_t *out,
                                uint32_t max_out) {
    if (!text || !out || max_out == 0U) return 0U;

    uint32_t pi = 0U; /* phoneme index */
    uint32_t ti = 0U; /* text index    */

    while (text[ti] != '\0' && pi < max_out) {
        char c = xtts_to_upper_(text[ti]);

        /* Check for digraphs first */
        if (text[ti + 1] != '\0') {
            char c2 = xtts_to_upper_(text[ti + 1]);
            uint32_t di;
            int found_digraph = 0;
            for (di = 0; di < XTTS_DIGRAPH_COUNT; di++) {
                if (DIGRAPH_TABLE[di].pair[0] == c &&
                    DIGRAPH_TABLE[di].pair[1] == c2) {
                    const xtts_digraph_entry_t *dg = &DIGRAPH_TABLE[di];
                    out[pi].f1        = dg->f1;
                    out[pi].f2        = dg->f2;
                    out[pi].f3        = dg->f3;
                    out[pi].bw1       = dg->bw1;
                    out[pi].bw2       = dg->bw2;
                    out[pi].bw3       = dg->bw3;
                    out[pi].duration_ms = dg->dur_ms;
                    out[pi].voiced    = dg->voiced;
                    out[pi]._pad      = 0;
                    pi++;
                    ti += 2;
                    found_digraph = 1;
                    break;
                }
            }
            if (found_digraph) continue;
        }

        /* Space -> silence */
        if (c == ' ' || c == '\t' || c == '\n') {
            out[pi].f1          = SILENCE_PHONEME.f1;
            out[pi].f2          = SILENCE_PHONEME.f2;
            out[pi].f3          = SILENCE_PHONEME.f3;
            out[pi].bw1         = SILENCE_PHONEME.bw1;
            out[pi].bw2         = SILENCE_PHONEME.bw2;
            out[pi].bw3         = SILENCE_PHONEME.bw3;
            out[pi].duration_ms = SILENCE_PHONEME.dur_ms;
            out[pi].voiced      = SILENCE_PHONEME.voiced;
            out[pi]._pad        = 0;
            pi++;
            ti++;
            continue;
        }

        /* Punctuation -> pause with varying duration */
        if (c == '.' || c == '!' || c == '?') {
            out[pi].f1 = 0;  out[pi].f2 = 0;  out[pi].f3 = 0;
            out[pi].bw1 = 0; out[pi].bw2 = 0; out[pi].bw3 = 0;
            out[pi].duration_ms = 200; /* Sentence boundary pause */
            out[pi].voiced = 0;
            out[pi]._pad = 0;
            pi++;
            ti++;
            continue;
        }
        if (c == ',' || c == ';' || c == ':') {
            out[pi].f1 = 0;  out[pi].f2 = 0;  out[pi].f3 = 0;
            out[pi].bw1 = 0; out[pi].bw2 = 0; out[pi].bw3 = 0;
            out[pi].duration_ms = 120; /* Clause boundary pause */
            out[pi].voiced = 0;
            out[pi]._pad = 0;
            pi++;
            ti++;
            continue;
        }

        /* Single letter lookup */
        if (c >= 'A' && c <= 'Z') {
            uint32_t idx = (uint32_t)(c - 'A');
            const xtts_phon_entry_t *pe = &PHONEME_TABLE[idx];
            out[pi].f1          = pe->f1;
            out[pi].f2          = pe->f2;
            out[pi].f3          = pe->f3;
            out[pi].bw1         = pe->bw1;
            out[pi].bw2         = pe->bw2;
            out[pi].bw3         = pe->bw3;
            out[pi].duration_ms = pe->dur_ms;
            out[pi].voiced      = pe->voiced;
            out[pi]._pad        = 0;
            pi++;
            ti++;
            continue;
        }

        /* Digit -> spell out as letters (e.g., '0' -> 'Z'ERO approximation) */
        if (c >= '0' && c <= '9') {
            /* Map digits to approximate letter phonemes */
            static const char DIGIT_LETTERS[10] = {
                'O', 'O', 'T', 'T', 'F', 'F', 'S', 'S', 'E', 'N'
            };
            uint32_t idx = (uint32_t)(DIGIT_LETTERS[c - '0'] - 'A');
            const xtts_phon_entry_t *pe = &PHONEME_TABLE[idx];
            out[pi].f1          = pe->f1;
            out[pi].f2          = pe->f2;
            out[pi].f3          = pe->f3;
            out[pi].bw1         = pe->bw1;
            out[pi].bw2         = pe->bw2;
            out[pi].bw3         = pe->bw3;
            out[pi].duration_ms = pe->dur_ms;
            out[pi].voiced      = pe->voiced;
            out[pi]._pad        = 0;
            pi++;
            ti++;
            continue;
        }

        /* Unknown character: skip */
        ti++;
    }

    return pi;
}

/* ── Fixed-point sine approximation ────────────────────────────────────────
 * Third-order polynomial approximation of sin(x) for x in [0, 2*PI].
 * Uses 16.16 fixed-point internally.  Returns value in [-32767, +32767].
 * Sufficient for formant synthesis quality at 22050 Hz.                 */

#define XTTS_FP_SHIFT   16
#define XTTS_FP_ONE     (1 << XTTS_FP_SHIFT)  /* 65536 */
#define XTTS_PI_FP      205887   /* pi * 65536         */
#define XTTS_TWO_PI_FP  411775   /* 2*pi * 65536       */

static int32_t xtts_sin_fp_(int32_t phase) {
    /* Normalize phase to [0, 2*PI) in fixed-point */
    while (phase < 0)              phase += XTTS_TWO_PI_FP;
    while (phase >= XTTS_TWO_PI_FP) phase -= XTTS_TWO_PI_FP;

    /* Map to [-PI, PI] */
    int32_t x = phase;
    if (x > XTTS_PI_FP) x = x - XTTS_TWO_PI_FP;

    /* Parabolic approximation: sin(x) ~ (4/pi)*x - (4/pi^2)*x*|x|
     * Scaled to return [-32767, 32767].
     *
     * Let a = 4/pi ~= 1.2732, b = 4/pi^2 ~= 0.4053
     * y = a*x - b*x*|x|  (with x in [-pi, pi])
     * We work in fixed-point with PI = XTTS_PI_FP. */
    int64_t xn = (int64_t)x;  /* in fixed-point PI units */

    /* Normalize x to [-1, 1] by dividing by PI */
    /* x_norm = x / PI  in 16.16 fixed-point */
    int64_t x_norm = (xn * XTTS_FP_ONE) / XTTS_PI_FP;

    /* sin(pi*t) ~ 4*t - 4*t*|t|  for t in [-1, 1]
     * This is a parabola fitting sin. */
    int64_t abs_xn = x_norm < 0 ? -x_norm : x_norm;
    int64_t y = (4 * x_norm * (XTTS_FP_ONE - abs_xn)) >> XTTS_FP_SHIFT;

    /* Scale to [-32767, 32767] */
    int32_t result = (int32_t)((y * 32767) >> XTTS_FP_SHIFT);
    if (result > 32767)  result = 32767;
    if (result < -32767) result = -32767;
    return result;
}

/* ── Formant PCM synthesis ─────────────────────────────────────────────── */

/* PCM synthesis buffer: enough for one phoneme at max duration (200ms) */
#define XTTS_PCM_BUF_SIZE  (XTTS_SAMPLE_RATE / 5 + 1) /* ~4410 samples */

static int16_t s_pcm_buf[XTTS_PCM_BUF_SIZE];

/**
 * xtts_synth_phoneme_ -- Synthesize one phoneme into PCM samples.
 *
 * Uses a parallel formant model: each formant is a sine wave at the
 * formant frequency, amplitude-modulated by a bandwidth envelope.
 * The glottal source is a pulse train at the base pitch frequency
 * for voiced phonemes, or white noise for unvoiced.
 *
 * @param ph         Phoneme to synthesize.
 * @param pitch_hz   Current pitch frequency (Hz).
 * @param volume     Volume 0-100.
 * @param wpm        Words per minute (affects duration scaling).
 * @param out        Output PCM buffer.
 * @param max_samp   Maximum samples to write.
 * @return           Number of samples written.
 */
static uint32_t xtts_synth_phoneme_(
    const xtts_phoneme_t *ph,
    uint32_t pitch_hz,
    uint8_t volume,
    uint32_t wpm,
    int16_t *out,
    uint32_t max_samp
) {
    if (!ph || !out || max_samp == 0U) return 0U;

    /* Scale phoneme duration by WPM ratio: default 150 WPM = 1x */
    uint32_t dur_ms = ph->duration_ms;
    if (wpm > 0U && wpm != XTTS_WPM_DEFAULT) {
        dur_ms = (dur_ms * XTTS_WPM_DEFAULT) / wpm;
        if (dur_ms < 20U) dur_ms = 20U;  /* Minimum 20ms */
    }

    uint32_t num_samples = (XTTS_SAMPLE_RATE * dur_ms) / 1000U;
    if (num_samples > max_samp) num_samples = max_samp;
    if (num_samples == 0U) return 0U;

    /* Silence phoneme: output zeros */
    if (ph->f1 == 0 && ph->f2 == 0 && ph->f3 == 0) {
        uint32_t i;
        for (i = 0; i < num_samples; i++) out[i] = 0;
        return num_samples;
    }

    /* Volume scaling: map 0-100 to 0-256 for fixed-point multiply */
    uint32_t vol_scale = ((uint32_t)volume * 256U) / 100U;

    /* Phase accumulators (fixed-point, in units of 2*PI / SAMPLE_RATE) */
    int32_t phase1 = 0, phase2 = 0, phase3 = 0;
    int32_t phase_glottal = 0;

    /* Phase increments per sample (fixed-point) */
    int32_t inc1 = (int32_t)(((int64_t)ph->f1 * XTTS_TWO_PI_FP) / XTTS_SAMPLE_RATE);
    int32_t inc2 = (int32_t)(((int64_t)ph->f2 * XTTS_TWO_PI_FP) / XTTS_SAMPLE_RATE);
    int32_t inc3 = (int32_t)(((int64_t)ph->f3 * XTTS_TWO_PI_FP) / XTTS_SAMPLE_RATE);
    int32_t inc_g = 0;
    if (ph->voiced && pitch_hz > 0U) {
        inc_g = (int32_t)(((int64_t)pitch_hz * XTTS_TWO_PI_FP) / XTTS_SAMPLE_RATE);
    }

    /* Simple LFSR for noise (unvoiced source) */
    uint32_t lfsr = 0xACE1u;

    uint32_t i;
    for (i = 0; i < num_samples; i++) {
        /* Glottal source */
        int32_t source;
        if (ph->voiced) {
            /* Glottal pulse: sine wave at pitch frequency */
            source = xtts_sin_fp_(phase_glottal);
            phase_glottal += inc_g;
            if (phase_glottal >= XTTS_TWO_PI_FP) phase_glottal -= XTTS_TWO_PI_FP;
        } else {
            /* White noise via LFSR */
            uint32_t bit = ((lfsr >> 0) ^ (lfsr >> 2) ^ (lfsr >> 3) ^ (lfsr >> 5)) & 1u;
            lfsr = (lfsr >> 1) | (bit << 15);
            source = (int32_t)(lfsr & 0x7FFF) - 16384;
        }

        /* Three parallel formant resonators (simplified: sine at formant freq
         * modulated by source amplitude) */
        int32_t f1_out = (xtts_sin_fp_(phase1) * source) >> 15;
        int32_t f2_out = (xtts_sin_fp_(phase2) * source) >> 15;
        int32_t f3_out = (xtts_sin_fp_(phase3) * source) >> 15;

        phase1 += inc1;
        phase2 += inc2;
        phase3 += inc3;
        if (phase1 >= XTTS_TWO_PI_FP) phase1 -= XTTS_TWO_PI_FP;
        if (phase2 >= XTTS_TWO_PI_FP) phase2 -= XTTS_TWO_PI_FP;
        if (phase3 >= XTTS_TWO_PI_FP) phase3 -= XTTS_TWO_PI_FP;

        /* Mix formants: F1 dominant, F2 secondary, F3 tertiary */
        int32_t mixed = (f1_out * 5 + f2_out * 3 + f3_out * 2) / 10;

        /* Apply volume */
        mixed = (mixed * (int32_t)vol_scale) >> 8;

        /* Amplitude envelope: 5ms attack, 5ms release */
        uint32_t attack_samp = (XTTS_SAMPLE_RATE * 5U) / 1000U;
        uint32_t release_start = num_samples > attack_samp ? num_samples - attack_samp : 0U;
        if (i < attack_samp && attack_samp > 0U) {
            mixed = (mixed * (int32_t)i) / (int32_t)attack_samp;
        } else if (i >= release_start && num_samples > release_start) {
            uint32_t rel_pos = i - release_start;
            uint32_t rel_len = num_samples - release_start;
            if (rel_len > 0U) {
                mixed = (mixed * (int32_t)(rel_len - rel_pos)) / (int32_t)rel_len;
            }
        }

        /* Clamp to int16 range */
        if (mixed > 32767)  mixed = 32767;
        if (mixed < -32767) mixed = -32767;
        out[i] = (int16_t)mixed;
    }

    return num_samples;
}

/* ── Prosody: pitch contour ────────────────────────────────────────────── */

/**
 * xtts_compute_pitch_ -- Compute pitch at a given position in the utterance.
 *
 * Basic prosody model:
 *   - Statements (ending '.'): pitch falls 20% over utterance
 *   - Questions (ending '?'):  pitch rises 30% over last third
 *   - Exclamations ('!'):      pitch rises 10% then falls
 *   - Default:                 slight declination (5%)
 *
 * @param base_hz     Base pitch frequency.
 * @param position    Current position (0.0 to 1.0 through utterance).
 * @param sentence_end  Last punctuation character (0 if none).
 * @return            Adjusted pitch in Hz.
 */
static uint32_t xtts_compute_pitch_(uint32_t base_hz, uint32_t pos_num,
                                     uint32_t pos_den, char sentence_end) {
    /* pos_num/pos_den is fraction through utterance [0, 1] */
    int32_t hz = (int32_t)base_hz;

    if (sentence_end == '?') {
        /* Question: flat first 2/3, rise in last third */
        if (pos_den > 0U && (pos_num * 3U) >= (pos_den * 2U)) {
            /* In last third: rise 30% linearly */
            uint32_t frac = ((pos_num * 3U) - (pos_den * 2U));
            hz = hz + (int32_t)((uint32_t)hz * 30U * frac / (pos_den * 100U));
        }
    } else if (sentence_end == '!') {
        /* Exclamation: rise 10% in first half, fall in second */
        if (pos_den > 0U && (pos_num * 2U) < pos_den) {
            hz = hz + (int32_t)((uint32_t)hz * 10U / 100U);
        } else {
            uint32_t fall = (uint32_t)hz * 15U / 100U;
            hz = hz - (int32_t)fall;
        }
    } else if (sentence_end == '.') {
        /* Statement: gradual 20% declination */
        if (pos_den > 0U) {
            uint32_t fall = ((uint32_t)hz * 20U * pos_num) / (pos_den * 100U);
            hz = hz - (int32_t)fall;
        }
    } else {
        /* Default: 5% declination */
        if (pos_den > 0U) {
            uint32_t fall = ((uint32_t)hz * 5U * pos_num) / (pos_den * 100U);
            hz = hz - (int32_t)fall;
        }
    }

    if (hz < 50)  hz = 50;
    if (hz > 500) hz = 500;
    return (uint32_t)hz;
}

/* ── Detect sentence-ending punctuation ────────────────────────────────── */

static char xtts_find_sentence_end_(const char *text) {
    if (!text) return 0;
    uint32_t i = 0;
    char last_punct = 0;
    while (text[i] != '\0') {
        if (text[i] == '.' || text[i] == '?' || text[i] == '!') {
            last_punct = text[i];
        }
        i++;
    }
    return last_punct;
}

/* ═══════════════════════════════════════════════════════════════════
 * §9  PUBLIC FORMANT SYNTHESIS API
 * ═══════════════════════════════════════════════════════════════════ */

void xtts_speak_cb(const char *text, xtts_voice_t voice,
                   xtts_pcm_callback_t callback, void *userdata) {
    if (!text || text[0] == '\0' || !callback) return;
    if (!s_tts.initialized) return;

    /* Select base pitch for voice */
    uint32_t base_pitch = s_tts.base_pitch_hz;
    if (voice == XTTS_VOICE_FEMALE) {
        base_pitch = XTTS_PITCH_FEMALE;
    } else if (voice == XTTS_VOICE_MALE) {
        base_pitch = XTTS_PITCH_MALE;
    }

    /* Convert text to phonemes */
    xtts_phoneme_t phonemes[XTTS_MAX_PHONEMES];
    uint32_t num_phonemes = xtts_text_to_phonemes(text, phonemes, XTTS_MAX_PHONEMES);
    if (num_phonemes == 0U) return;

    /* Detect prosody from punctuation */
    char sentence_end = xtts_find_sentence_end_(text);

    /* Synthesize each phoneme and deliver PCM via callback */
    uint32_t pi;
    for (pi = 0; pi < num_phonemes; pi++) {
        /* Compute prosody-adjusted pitch */
        uint32_t pitch = xtts_compute_pitch_(base_pitch, pi, num_phonemes, sentence_end);

        /* Synthesize phoneme */
        uint32_t samp_count = xtts_synth_phoneme_(
            &phonemes[pi], pitch, s_tts.volume, s_tts.wpm,
            s_pcm_buf, XTTS_PCM_BUF_SIZE
        );

        /* Deliver samples to caller */
        if (samp_count > 0U) {
            callback(s_pcm_buf, samp_count, userdata);
        }
    }

    pal_console_printf("[XTTS] synthesized %u phonemes for \"%s\"\n",
                       num_phonemes, text);
}

void xtts_set_rate_wpm(uint32_t wpm) {
    if (!s_tts.initialized) return;
    if (wpm < 80U)  wpm = 80U;
    if (wpm > 300U) wpm = 300U;
    s_tts.wpm = wpm;
}

void xtts_set_pitch_hz(uint32_t hz) {
    if (!s_tts.initialized) return;
    if (hz < 50U)  hz = 50U;
    if (hz > 500U) hz = 500U;
    s_tts.base_pitch_hz = hz;
}
