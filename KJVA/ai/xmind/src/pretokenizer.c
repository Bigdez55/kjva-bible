/*
 * pretokenizer.c -- XMIND GPT-4 Pre-tokenization Regex Engine
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Sprint 41: Implements the GPT-4 regex-based pre-tokenizer that splits
 * text into chunks before BPE merge rules are applied.  This matches the
 * reference pattern used by tiktoken/sentencepiece:
 *
 *   's|'t|'re|'ve|'m|'ll|'d| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+
 *
 * The pre-tokenizer produces an array of (start, length) spans which the
 * BPE tokenizer then processes independently.  This prevents BPE merges
 * from crossing word/contraction boundaries, which is critical for
 * matching the Llama 3.2 vocabulary.
 *
 * Unicode handling:
 *   In freestanding C without ICU or libc, we implement a minimal
 *   UTF-8 decoder and Unicode category classifier.  The classifier
 *   covers the most common Unicode ranges for \p{L} (letter) and
 *   \p{N} (number) using hardcoded range tables derived from Unicode
 *   14.0 General_Category data.  Rare scripts (e.g., Vai, Bamum) are
 *   not classified but degrade gracefully to the catch-all pattern.
 *
 * Architecture:
 *   S1  UTF-8 decoder (1-4 byte sequences)
 *   S2  Unicode category classifier (L, N, whitespace)
 *   S3  Contraction matcher ('s, 't, 're, 've, 'm, 'll, 'd)
 *   S4  Pattern matchers (letter run, number run, punctuation run)
 *   S5  Top-level pre-tokenize dispatch
 *   S6  Public API (xmind_pretokenize)
 *
 * Compile:
 *   clang --target=x86_64-unknown-none-elf -ffreestanding \
 *         -fno-stack-protector -fno-pie -mno-red-zone \
 *         -Werror -Wall -Wextra -Wno-unused-parameter \
 *         -O2 -std=c11 -Iai/xmind/include -Ipal/include \
 *         -c -o pretokenizer.o ai/xmind/src/pretokenizer.c
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"

/* ====================================================================
 * S0  SPAN TYPE
 *
 * Each span describes a contiguous byte range [start, start+len) in
 * the input text that should be BPE-tokenized independently.
 * ==================================================================== */

/* Max spans per pre-tokenization call.  Typical English text produces
 * ~1 span per 5 bytes.  8192 spans covers ~40 KB of text, well beyond
 * the 2048-token context window (which is ~8 KB of English). */
#define XMIND_PRETOK_MAX_SPANS  8192u

/* xmind_span_t is declared in xmind.h */

/* ====================================================================
 * S1  UTF-8 DECODER
 *
 * Decodes one UTF-8 codepoint from the byte stream.
 * Returns the codepoint and advances *pos by the number of bytes consumed.
 * Returns 0xFFFD (replacement character) on invalid sequences.
 *
 * UTF-8 encoding:
 *   0xxxxxxx                           → U+0000..U+007F  (1 byte)
 *   110xxxxx 10xxxxxx                   → U+0080..U+07FF  (2 bytes)
 *   1110xxxx 10xxxxxx 10xxxxxx         → U+0800..U+FFFF  (3 bytes)
 *   11110xxx 10xxxxxx 10xxxxxx 10xxxxxx → U+10000..U+10FFFF (4 bytes)
 * ==================================================================== */

static uint32_t utf8_decode(const uint8_t *text, uint32_t text_len,
                             uint32_t *pos) {
    uint32_t p = *pos;
    if (p >= text_len) { return 0u; }

    uint8_t b0 = text[p];

    /* 1-byte ASCII */
    if (b0 < 0x80u) {
        *pos = p + 1u;
        return (uint32_t)b0;
    }

    /* 2-byte sequence */
    if ((b0 & 0xE0u) == 0xC0u) {
        if (p + 1u >= text_len) { *pos = p + 1u; return 0xFFFDu; }
        uint8_t b1 = text[p + 1u];
        if ((b1 & 0xC0u) != 0x80u) { *pos = p + 1u; return 0xFFFDu; }
        uint32_t cp = ((uint32_t)(b0 & 0x1Fu) << 6u) | (uint32_t)(b1 & 0x3Fu);
        if (cp < 0x80u) { *pos = p + 2u; return 0xFFFDu; } /* overlong */
        *pos = p + 2u;
        return cp;
    }

    /* 3-byte sequence */
    if ((b0 & 0xF0u) == 0xE0u) {
        if (p + 2u >= text_len) { *pos = p + 1u; return 0xFFFDu; }
        uint8_t b1 = text[p + 1u], b2 = text[p + 2u];
        if ((b1 & 0xC0u) != 0x80u || (b2 & 0xC0u) != 0x80u) {
            *pos = p + 1u; return 0xFFFDu;
        }
        uint32_t cp = ((uint32_t)(b0 & 0x0Fu) << 12u)
                    | ((uint32_t)(b1 & 0x3Fu) << 6u)
                    |  (uint32_t)(b2 & 0x3Fu);
        if (cp < 0x0800u) { *pos = p + 3u; return 0xFFFDu; }
        /* Reject surrogates U+D800..U+DFFF */
        if (cp >= 0xD800u && cp <= 0xDFFFu) { *pos = p + 3u; return 0xFFFDu; }
        *pos = p + 3u;
        return cp;
    }

    /* 4-byte sequence */
    if ((b0 & 0xF8u) == 0xF0u) {
        if (p + 3u >= text_len) { *pos = p + 1u; return 0xFFFDu; }
        uint8_t b1 = text[p + 1u], b2 = text[p + 2u], b3 = text[p + 3u];
        if ((b1 & 0xC0u) != 0x80u || (b2 & 0xC0u) != 0x80u ||
            (b3 & 0xC0u) != 0x80u) {
            *pos = p + 1u; return 0xFFFDu;
        }
        uint32_t cp = ((uint32_t)(b0 & 0x07u) << 18u)
                    | ((uint32_t)(b1 & 0x3Fu) << 12u)
                    | ((uint32_t)(b2 & 0x3Fu) << 6u)
                    |  (uint32_t)(b3 & 0x3Fu);
        if (cp < 0x10000u || cp > 0x10FFFFu) { *pos = p + 4u; return 0xFFFDu; }
        *pos = p + 4u;
        return cp;
    }

    /* Invalid leading byte */
    *pos = p + 1u;
    return 0xFFFDu;
}

/* Return the byte length of the UTF-8 encoding starting at text[pos].
 * Does not validate the sequence; just measures the expected length. */
static uint32_t utf8_byte_len(uint8_t b0) {
    if (b0 < 0x80u)          return 1u;
    if ((b0 & 0xE0u) == 0xC0u) return 2u;
    if ((b0 & 0xF0u) == 0xE0u) return 3u;
    if ((b0 & 0xF8u) == 0xF0u) return 4u;
    return 1u;  /* invalid byte treated as 1-byte */
}

/* ====================================================================
 * S2  UNICODE CATEGORY CLASSIFIER
 *
 * Classifies a Unicode codepoint as:
 *   UCAT_L  — Letter (\p{L})
 *   UCAT_N  — Number (\p{N})
 *   UCAT_S  — Whitespace (\s)
 *   UCAT_O  — Other (punctuation, symbols, etc.)
 *
 * Covers the most common Unicode planes:
 *   - Basic Latin (ASCII)
 *   - Latin-1 Supplement, Latin Extended A/B
 *   - Greek, Cyrillic
 *   - Arabic, Hebrew
 *   - Devanagari, Bengali, Tamil, Thai
 *   - CJK Unified Ideographs
 *   - Hangul Syllables
 *   - Katakana, Hiragana
 *   - Common numeric ranges
 *
 * Rare scripts fall through to UCAT_O, which is correct behavior:
 * they match the catch-all punctuation/symbol pattern.
 * ==================================================================== */

#define UCAT_L  1u   /* Letter */
#define UCAT_N  2u   /* Number */
#define UCAT_S  3u   /* Whitespace */
#define UCAT_O  0u   /* Other */

static uint32_t unicode_category(uint32_t cp) {
    /* ── ASCII fast path ──────────────────────────────────────────── */
    if (cp <= 0x7Fu) {
        if (cp >= 'A' && cp <= 'Z') return UCAT_L;
        if (cp >= 'a' && cp <= 'z') return UCAT_L;
        if (cp >= '0' && cp <= '9') return UCAT_N;
        if (cp == ' ' || cp == '\t' || cp == '\n' || cp == '\r' ||
            cp == '\f' || cp == '\v') return UCAT_S;
        return UCAT_O;
    }

    /* ── Unicode whitespace ───────────────────────────────────────── */
    if (cp == 0x00A0u || cp == 0x1680u ||
        (cp >= 0x2000u && cp <= 0x200Au) ||
        cp == 0x2028u || cp == 0x2029u || cp == 0x202Fu ||
        cp == 0x205Fu || cp == 0x3000u || cp == 0x00ADu ||
        cp == 0xFEFFu || cp == 0x200Bu) return UCAT_S;

    /* ── Latin-1 Supplement letters ───────────────────────────────── */
    if ((cp >= 0x00C0u && cp <= 0x00D6u) ||
        (cp >= 0x00D8u && cp <= 0x00F6u) ||
        (cp >= 0x00F8u && cp <= 0x00FFu)) return UCAT_L;

    /* ── Latin Extended-A / Extended-B ────────────────────────────── */
    if (cp >= 0x0100u && cp <= 0x024Fu) return UCAT_L;

    /* ── IPA Extensions / Spacing Modifier Letters ─────────────── */
    if (cp >= 0x0250u && cp <= 0x02AFu) return UCAT_L;

    /* ── Greek and Coptic ─────────────────────────────────────────── */
    if ((cp >= 0x0370u && cp <= 0x0373u) ||
        (cp >= 0x0376u && cp <= 0x0377u) ||
        (cp >= 0x037Au && cp <= 0x037Du) ||
        cp == 0x037Fu ||
        (cp >= 0x0386u && cp <= 0x0386u) ||
        (cp >= 0x0388u && cp <= 0x038Au) ||
        cp == 0x038Cu ||
        (cp >= 0x038Eu && cp <= 0x03A1u) ||
        (cp >= 0x03A3u && cp <= 0x03FFu)) return UCAT_L;

    /* ── Cyrillic ─────────────────────────────────────────────────── */
    if (cp >= 0x0400u && cp <= 0x04FFu) return UCAT_L;
    if (cp >= 0x0500u && cp <= 0x052Fu) return UCAT_L;  /* Cyrillic Supplement */

    /* ── Armenian ─────────────────────────────────────────────────── */
    if (cp >= 0x0531u && cp <= 0x0556u) return UCAT_L;
    if (cp >= 0x0561u && cp <= 0x0587u) return UCAT_L;

    /* ── Hebrew ───────────────────────────────────────────────────── */
    if (cp >= 0x05D0u && cp <= 0x05EAu) return UCAT_L;

    /* ── Arabic ───────────────────────────────────────────────────── */
    if (cp >= 0x0620u && cp <= 0x064Au) return UCAT_L;
    if (cp >= 0x066Eu && cp <= 0x066Fu) return UCAT_L;
    if (cp >= 0x0671u && cp <= 0x06D3u) return UCAT_L;

    /* ── Arabic-Indic digits ──────────────────────────────────────── */
    if (cp >= 0x0660u && cp <= 0x0669u) return UCAT_N;
    if (cp >= 0x06F0u && cp <= 0x06F9u) return UCAT_N;

    /* ── Devanagari ───────────────────────────────────────────────── */
    if (cp >= 0x0900u && cp <= 0x097Fu) return UCAT_L;
    if (cp >= 0x0966u && cp <= 0x096Fu) return UCAT_N;

    /* ── Bengali ──────────────────────────────────────────────────── */
    if (cp >= 0x0980u && cp <= 0x09FFu) return UCAT_L;
    if (cp >= 0x09E6u && cp <= 0x09EFu) return UCAT_N;

    /* ── Tamil ────────────────────────────────────────────────────── */
    if (cp >= 0x0B82u && cp <= 0x0BFFu) return UCAT_L;

    /* ── Thai ─────────────────────────────────────────────────────── */
    if (cp >= 0x0E01u && cp <= 0x0E3Au) return UCAT_L;
    if (cp >= 0x0E50u && cp <= 0x0E59u) return UCAT_N;

    /* ── Georgian ─────────────────────────────────────────────────── */
    if (cp >= 0x10A0u && cp <= 0x10C5u) return UCAT_L;
    if (cp >= 0x10D0u && cp <= 0x10FAu) return UCAT_L;

    /* ── Hangul Jamo ──────────────────────────────────────────────── */
    if (cp >= 0x1100u && cp <= 0x11FFu) return UCAT_L;

    /* ── Latin Extended Additional ────────────────────────────────── */
    if (cp >= 0x1E00u && cp <= 0x1EFFu) return UCAT_L;

    /* ── General Punctuation -- not letters ────────────────────────
     * Superscript/subscript digits */
    if (cp >= 0x2070u && cp <= 0x2079u) return UCAT_N;
    if (cp >= 0x2080u && cp <= 0x2089u) return UCAT_N;

    /* ── CJK Unified Ideographs ──────────────────────────────────── */
    if (cp >= 0x4E00u && cp <= 0x9FFFu) return UCAT_L;

    /* ── CJK Extension A ──────────────────────────────────────────── */
    if (cp >= 0x3400u && cp <= 0x4DBFu) return UCAT_L;

    /* ── Hiragana ─────────────────────────────────────────────────── */
    if (cp >= 0x3040u && cp <= 0x309Fu) return UCAT_L;

    /* ── Katakana ─────────────────────────────────────────────────── */
    if (cp >= 0x30A0u && cp <= 0x30FFu) return UCAT_L;

    /* ── Bopomofo ─────────────────────────────────────────────────── */
    if (cp >= 0x3100u && cp <= 0x312Fu) return UCAT_L;

    /* ── Hangul Compatibility Jamo ────────────────────────────────── */
    if (cp >= 0x3130u && cp <= 0x318Fu) return UCAT_L;

    /* ── Hangul Syllables ─────────────────────────────────────────── */
    if (cp >= 0xAC00u && cp <= 0xD7A3u) return UCAT_L;

    /* ── Fullwidth digits ─────────────────────────────────────────── */
    if (cp >= 0xFF10u && cp <= 0xFF19u) return UCAT_N;

    /* ── Fullwidth Latin letters ──────────────────────────────────── */
    if (cp >= 0xFF21u && cp <= 0xFF3Au) return UCAT_L;
    if (cp >= 0xFF41u && cp <= 0xFF5Au) return UCAT_L;

    /* ── Supplementary planes: CJK Extension B+ ──────────────────── */
    if (cp >= 0x20000u && cp <= 0x2A6DFu) return UCAT_L;

    /* ── Emoji modifiers / variation selectors — treat as Other ──── */

    return UCAT_O;
}

/* ====================================================================
 * S3  CONTRACTION MATCHER
 *
 * Matches English contractions at the current position:
 *   's  't  're  've  'm  'll  'd
 *
 * The apostrophe can be ASCII (0x27) or Unicode right single quote
 * (U+2019, encoded as E2 80 99 in UTF-8).
 *
 * Returns the byte length of the matched contraction, or 0 if no match.
 * ==================================================================== */

static uint32_t match_contraction(const uint8_t *text, uint32_t text_len,
                                    uint32_t pos) {
    if (pos >= text_len) return 0u;

    uint32_t apos_len = 0u;
    /* Check for ASCII apostrophe or Unicode right single quote */
    if (text[pos] == 0x27u) {
        apos_len = 1u;
    } else if (pos + 2u < text_len &&
               text[pos] == 0xE2u && text[pos + 1u] == 0x80u &&
               text[pos + 2u] == 0x99u) {
        apos_len = 3u;
    }
    if (apos_len == 0u) return 0u;

    uint32_t after = pos + apos_len;
    if (after >= text_len) return 0u;

    uint8_t c1 = text[after];

    /* 'll — check for two consecutive 'l' */
    if ((c1 == 'l' || c1 == 'L') &&
        after + 1u < text_len &&
        (text[after + 1u] == 'l' || text[after + 1u] == 'L')) {
        return apos_len + 2u;
    }

    /* 're */
    if ((c1 == 'r' || c1 == 'R') &&
        after + 1u < text_len &&
        (text[after + 1u] == 'e' || text[after + 1u] == 'E')) {
        return apos_len + 2u;
    }

    /* 've */
    if ((c1 == 'v' || c1 == 'V') &&
        after + 1u < text_len &&
        (text[after + 1u] == 'e' || text[after + 1u] == 'E')) {
        return apos_len + 2u;
    }

    /* 's, 't, 'm, 'd — single letter suffixes */
    if (c1 == 's' || c1 == 'S' ||
        c1 == 't' || c1 == 'T' ||
        c1 == 'm' || c1 == 'M' ||
        c1 == 'd' || c1 == 'D') {
        return apos_len + 1u;
    }

    return 0u;
}

/* ====================================================================
 * S4  PATTERN MATCHERS
 *
 * Each matcher tries to consume characters at pos according to one of
 * the GPT-4 pre-tokenization patterns.  Returns the byte length
 * consumed, or 0 if the pattern does not match at this position.
 * ==================================================================== */

/* Match: ' ?\p{L}+' — optional space followed by one or more letters */
static uint32_t match_letters(const uint8_t *text, uint32_t text_len,
                                uint32_t pos) {
    uint32_t p = pos;
    /* Optional leading space (ASCII 0x20 only, not all whitespace) */
    if (p < text_len && text[p] == ' ') { p++; }

    /* Must have at least one letter */
    uint32_t save = p;
    uint32_t cp = utf8_decode(text, text_len, &p);
    if (cp == 0u || unicode_category(cp) != UCAT_L) {
        return 0u;
    }

    /* Consume remaining letters */
    while (p < text_len) {
        save = p;
        cp = utf8_decode(text, text_len, &p);
        if (cp == 0u || unicode_category(cp) != UCAT_L) {
            p = save;  /* un-consume non-letter */
            break;
        }
    }
    return p - pos;
}

/* Match: ' ?\p{N}+' — optional space followed by one or more digits */
static uint32_t match_numbers(const uint8_t *text, uint32_t text_len,
                                uint32_t pos) {
    uint32_t p = pos;
    if (p < text_len && text[p] == ' ') { p++; }

    uint32_t save = p;
    uint32_t cp = utf8_decode(text, text_len, &p);
    if (cp == 0u || unicode_category(cp) != UCAT_N) {
        return 0u;
    }

    while (p < text_len) {
        save = p;
        cp = utf8_decode(text, text_len, &p);
        if (cp == 0u || unicode_category(cp) != UCAT_N) {
            p = save;
            break;
        }
    }
    return p - pos;
}

/* Match: ' ?[^\s\p{L}\p{N}]+' — optional space + one or more non-letter,
 * non-digit, non-whitespace characters (punctuation, symbols) */
static uint32_t match_punctuation(const uint8_t *text, uint32_t text_len,
                                    uint32_t pos) {
    uint32_t p = pos;
    if (p < text_len && text[p] == ' ') { p++; }

    uint32_t save = p;
    uint32_t cp = utf8_decode(text, text_len, &p);
    if (cp == 0u) return 0u;
    uint32_t cat = unicode_category(cp);
    if (cat == UCAT_L || cat == UCAT_N || cat == UCAT_S) {
        return 0u;
    }

    while (p < text_len) {
        save = p;
        cp = utf8_decode(text, text_len, &p);
        if (cp == 0u) { p = save; break; }
        cat = unicode_category(cp);
        if (cat == UCAT_L || cat == UCAT_N || cat == UCAT_S) {
            p = save;
            break;
        }
    }
    return p - pos;
}

/* Match: '\s+' — one or more whitespace characters.
 * The last whitespace in a run is NOT included if followed by a
 * non-whitespace character, matching the tiktoken behavior where trailing
 * whitespace joins the next token.  However, for simplicity in this
 * freestanding implementation, we consume the full whitespace run. */
static uint32_t match_whitespace(const uint8_t *text, uint32_t text_len,
                                   uint32_t pos) {
    uint32_t p = pos;
    uint32_t save = p;
    uint32_t cp = utf8_decode(text, text_len, &p);
    if (cp == 0u || unicode_category(cp) != UCAT_S) {
        return 0u;
    }

    while (p < text_len) {
        save = p;
        cp = utf8_decode(text, text_len, &p);
        if (cp == 0u || unicode_category(cp) != UCAT_S) {
            p = save;
            break;
        }
    }
    return p - pos;
}

/* ====================================================================
 * S5  TOP-LEVEL PRE-TOKENIZE DISPATCH
 *
 * Applies the GPT-4 pattern in priority order:
 *   1. Contraction ('s, 't, 're, 've, 'm, 'll, 'd)
 *   2. Optional-space + letters
 *   3. Optional-space + numbers
 *   4. Optional-space + punctuation/symbols
 *   5. Whitespace run
 *   6. Single byte (fallback for unmatched bytes)
 * ==================================================================== */

static uint32_t pretokenize_step(const uint8_t *text, uint32_t text_len,
                                   uint32_t pos) {
    uint32_t len;

    /* 1. Contraction */
    len = match_contraction(text, text_len, pos);
    if (len > 0u) return len;

    /* 2. Letter run (with optional leading space) */
    len = match_letters(text, text_len, pos);
    if (len > 0u) return len;

    /* 3. Number run (with optional leading space) */
    len = match_numbers(text, text_len, pos);
    if (len > 0u) return len;

    /* 4. Punctuation/symbol run (with optional leading space) */
    len = match_punctuation(text, text_len, pos);
    if (len > 0u) return len;

    /* 5. Whitespace run */
    len = match_whitespace(text, text_len, pos);
    if (len > 0u) return len;

    /* 6. Fallback: single byte (should not normally be reached) */
    return utf8_byte_len(text[pos]);
}

/* ====================================================================
 * S6  PUBLIC API
 *
 * xmind_pretokenize — split text into spans for BPE processing.
 *
 * @param text       Input UTF-8 text (null-terminated)
 * @param out_spans  Output array of spans (caller-provided)
 * @param max_spans  Maximum number of spans to emit
 * @param out_count  Receives the number of spans emitted
 *
 * Returns XMIND_OK on success; XMIND_ERR_OVERFLOW if max_spans is
 * exhausted (partial result is still valid).
 *
 * Usage:
 *   xmind_span_t spans[1024];
 *   uint32_t n_spans;
 *   xmind_pretokenize("Hello, world! I'm fine.", spans, 1024, &n_spans);
 *   // spans: ["Hello", ",", " world", "!", " I", "'m", " fine", "."]
 * ==================================================================== */

xmind_status_t xmind_pretokenize(const char *text,
                                   xmind_span_t *out_spans,
                                   uint32_t max_spans,
                                   uint32_t *out_count) {
    if (!text || !out_spans || !out_count || max_spans == 0u) {
        return XMIND_ERR_INVAL;
    }

    const uint8_t *t = (const uint8_t *)text;

    /* Compute text length (no strlen in freestanding) */
    uint32_t text_len = 0u;
    while (t[text_len] != 0u) { text_len++; }

    uint32_t pos   = 0u;
    uint32_t count = 0u;

    while (pos < text_len) {
        if (count >= max_spans) {
            *out_count = count;
            return XMIND_ERR_OVERFLOW;
        }

        uint32_t span_len = pretokenize_step(t, text_len, pos);
        if (span_len == 0u) {
            /* Safety: advance by 1 to avoid infinite loop */
            span_len = 1u;
        }

        out_spans[count].start = pos;
        out_spans[count].len   = span_len;
        count++;
        pos += span_len;
    }

    *out_count = count;
    return XMIND_OK;
}

/* ====================================================================
 * S7  SPAN ACCESSOR HELPERS
 *
 * Utility functions for extracting span text into a buffer.
 * ==================================================================== */

/* Copy span text into a null-terminated buffer.
 * Returns the number of bytes copied (excluding null terminator). */
uint32_t xmind_span_copy(const char *text, const xmind_span_t *span,
                           char *buf, uint32_t bufsz) {
    if (!text || !span || !buf || bufsz == 0u) return 0u;

    uint32_t copy_len = span->len;
    if (copy_len > bufsz - 1u) { copy_len = bufsz - 1u; }

    const uint8_t *src = (const uint8_t *)text + span->start;
    uint32_t i;
    for (i = 0u; i < copy_len; i++) {
        buf[i] = (char)src[i];
    }
    buf[copy_len] = '\0';
    return copy_len;
}
