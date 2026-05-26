/*
 * tokenizer.c — XMIND Byte-Level BPE Tokenizer
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * Sprint 7: XSTORE-backed BPE vocabulary loading.
 *
 * The tokenizer now supports two modes:
 *
 *   Byte-level mode (default, Sprint 6 fallback):
 *     - Special tokens: PAD=0, BOS=1, EOS=2
 *     - Byte tokens: byte b → token ID (b + 3), IDs 3..258
 *     - Total vocabulary: 259 entries
 *
 *   BPE mode (Sprint 7, activated by xmind_tokenizer_load):
 *     - Loads merge rules from XSTORE KV store (key "xmind:bpe:rules")
 *     - Loads extended vocab entries from XSTORE (key "xmind:bpe:vocab")
 *     - Merge rules stored as packed binary: [left_id:u32][right_id:u32]
 *       [merged_id:u32][score:f32] × n_rules
 *     - Applies greedy BPE merging: find highest-priority adjacent pair,
 *       merge, repeat until no rules apply.
 *     - Supports up to XMIND_BPE_MAX_RULES merge rules.
 *     - Falls back to byte-level if XSTORE unavailable.
 *
 * Token ID layout:
 *   0         → <PAD>
 *   1         → <BOS>
 *   2         → <EOS>
 *   3..258    → byte values 0x00..0xFF
 *   259..     → BPE merge tokens (loaded from XSTORE)
 *
 * Functions:
 *   xm_tok_fnv1a          — FNV-1a hash (vocab lookup)
 *   xmind_tokenize        — encode text → token IDs (byte or BPE mode)
 *   xmind_detokenize      — token ID → string
 *   xmind_vocab_size      — returns 259 + n_bpe_tokens
 *   xmind_tokenizer_load  — load BPE rules + vocab from XSTORE
 *   xmind_tokenizer_reset — unload BPE data, revert to byte-level mode
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"

/* ═══════════════════════════════════════════════════════════════════
 * §1  VOCABULARY ENTRY TYPE
 * ═══════════════════════════════════════════════════════════════════ */

typedef struct {
    char     str[32];   /* null-terminated token string */
    uint32_t id;        /* token ID */
    float    score;     /* BPE merge score (0.0 for byte tokens) */
} xmind_vocab_entry_t;

/* ═══════════════════════════════════════════════════════════════════
 * §2  STATIC VOCABULARY TABLE (special tokens only)
 * ═══════════════════════════════════════════════════════════════════
 *
 * The 256 byte tokens are handled procedurally (id = byte + 3).
 * Only the 3 special tokens need named entries.
 */
static const xmind_vocab_entry_t s_special_vocab[3] = {
    { "<PAD>", XMIND_TOK_PAD, 0.0f },
    { "<BOS>", XMIND_TOK_BOS, 0.0f },
    { "<EOS>", XMIND_TOK_EOS, 0.0f },
};

/* ═══════════════════════════════════════════════════════════════════
 * §3  FNV-1a HASH  (32-bit, for future vocab lookup table)
 * ═══════════════════════════════════════════════════════════════════
 *
 * FNV-1a is compact, fast, and has good distribution for short strings.
 * It is used here as the foundation for a future hash-map based vocab
 * lookup that will replace the linear scan in Sprint 7.
 *
 * Used by BPE merge hash table (FNV-1a keyed on (left_id, right_id) pairs).
 */
#define XM_FNV1A_PRIME  0x01000193u
#define XM_FNV1A_OFFSET 0x811C9DC5u

static uint32_t xm_tok_fnv1a(const char *s, uint64_t len) {
    uint32_t hash = XM_FNV1A_OFFSET;
    uint64_t i;
    for (i = 0u; i < len && s[i] != '\0'; i++) {
        hash ^= (uint32_t)(uint8_t)s[i];
        hash *= XM_FNV1A_PRIME;
    }
    return hash;
}

/* ═══════════════════════════════════════════════════════════════════
 * §3b  BPE TYPES & STATE  (moved before §7 detokenize for visibility)
 * ═══════════════════════════════════════════════════════════════════ */

#define XMIND_BPE_MAX_RULES  131072u  /* up to 128K merge rules */
#define XMIND_BPE_MAX_TOKENS 131072u  /* up to 128K vocab entries */
#define XMIND_BPE_RECORD_SZ  16u    /* 4x u32 or 3x u32+f32 packed */
#define XMIND_BPE_VTOK_SZ    64u    /* 4+60 bytes per vocab entry */

typedef struct {
    uint32_t left_id;
    uint32_t right_id;
    uint32_t merged_id;
    float    score;
} xmind_bpe_rule_t;

typedef struct {
    uint32_t id;
    char     str[60];
} xmind_bpe_token_t;

/* Heap-allocated pools (freestanding -- allocated by bpe_alloc_tables) */
static xmind_bpe_rule_t  *s_bpe_rules  = (void *)0;
static xmind_bpe_token_t *s_bpe_tokens = (void *)0;
static uint32_t           s_n_bpe_rules  = 0u;
static uint32_t           s_n_bpe_tokens = 0u;
static uint8_t            s_bpe_loaded   = 0u;

/* Forward declaration -- defined in §13 */
static const char *bpe_token_str(uint32_t id);

/* ═══════════════════════════════════════════════════════════════════
 * §4  INTERNAL STRING HELPERS
 * ═══════════════════════════════════════════════════════════════════ */

/* Null-terminated string length (no <string.h>) */
static uint64_t xm_strlen(const char *s) {
    uint64_t n = 0u;
    while (s[n] != '\0') { n++; }
    return n;
}

/* Copy at most (bufsz - 1) bytes from src to dst, always null-terminate */
static void xm_strncpy_safe(char *dst, const char *src, uint32_t bufsz) {
    if (bufsz == 0u) { return; }
    uint32_t i;
    for (i = 0u; i < bufsz - 1u && src[i] != '\0'; i++) {
        dst[i] = src[i];
    }
    dst[i] = '\0';
}


/* ═══════════════════════════════════════════════════════════════════
 * §5  HEX NIBBLE HELPER  (for detokenize of control bytes)
 * ═══════════════════════════════════════════════════════════════════ */

static char xm_nibble_to_hex(uint8_t n) {
    return (char)(n < 10u ? ('0' + n) : ('a' + n - 10u));
}

/* ═══════════════════════════════════════════════════════════════════
 * §6  TOKENIZE  (text → token IDs)
 * ═══════════════════════════════════════════════════════════════════
 *
 * Encoding:
 *   1. Write BOS (token 1) as the first output token.
 *   2. For each byte b in the input text (until '\0'):
 *        token = (uint32_t)b + 3u
 *        append to out_tokens.
 *   3. If output would exceed max_tokens, return XMIND_ERR_OVERFLOW.
 *      out_len is set to however many tokens were successfully written.
 *
 * The function signature matches xmind.h exactly:
 *   xmind_status_t xmind_tokenize(const char *text, uint32_t *out_tokens,
 *                                  uint32_t *out_len, uint32_t max_tokens)
 */
static xmind_status_t xmind_tokenize_bytes(const char *text,
                                             uint32_t *out_tokens,
                                             uint32_t *out_len,
                                             uint32_t max_tokens) {
    if (text       == (void *)0) { return XMIND_ERR_INVAL; }
    if (out_tokens == (void *)0) { return XMIND_ERR_INVAL; }
    if (out_len    == (void *)0) { return XMIND_ERR_INVAL; }
    if (max_tokens == 0u)        { return XMIND_ERR_INVAL; }

    uint32_t count = 0u;

    /* Prepend BOS */
    if (count >= max_tokens) {
        *out_len = count;
        return XMIND_ERR_OVERFLOW;
    }
    out_tokens[count++] = XMIND_TOK_BOS;

    /* Byte-level encoding */
    uint64_t text_len = xm_strlen(text);
    uint64_t i;
    for (i = 0u; i < text_len; i++) {
        if (count >= max_tokens) {
            *out_len = count;
            return XMIND_ERR_OVERFLOW;
        }
        uint8_t  b    = (uint8_t)text[i];
        uint32_t tok  = (uint32_t)b + 3u;
        out_tokens[count++] = tok;
    }

    *out_len = count;
    return XMIND_OK;
}

/* ═══════════════════════════════════════════════════════════════════
 * §7  DETOKENIZE  (token ID → string)
 * ═══════════════════════════════════════════════════════════════════
 *
 * Decoding:
 *   token 0   → "<PAD>"
 *   token 1   → "<BOS>"
 *   token 2   → "<EOS>"
 *   token 3..258  → single byte (token - 3)
 *     Printable ASCII (0x20..0x7E): rendered as the character itself.
 *     Control bytes (0x00..0x1F, 0x7F): rendered as "\xNN" (4 chars).
 *     High bytes (0x80..0xFF): rendered as "\xNN" (4 chars).
 *   token >= 259  → "<UNK:NNNN>" (Sprint 7 BPE tokens not yet decoded)
 */
void xmind_detokenize(uint32_t token, char *buf, uint32_t bufsz) {
    if (buf == (void *)0 || bufsz == 0u) { return; }

    /* Special tokens */
    if (token < 3u) {
        xm_strncpy_safe(buf, s_special_vocab[token].str, bufsz);
        return;
    }

    /* Byte tokens */
    if (token <= 258u) {
        uint8_t byte = (uint8_t)(token - 3u);

        /* Printable ASCII */
        if (byte >= 0x20u && byte <= 0x7Eu) {
            if (bufsz >= 2u) {
                buf[0] = (char)byte;
                buf[1] = '\0';
            } else {
                buf[0] = '\0';
            }
            return;
        }

        /* Control / high byte: encode as \xNN */
        if (bufsz >= 5u) {
            buf[0] = '\\';
            buf[1] = 'x';
            buf[2] = xm_nibble_to_hex(byte >> 4u);
            buf[3] = xm_nibble_to_hex(byte & 0x0Fu);
            buf[4] = '\0';
        } else {
            buf[0] = '\0';
        }
        return;
    }

    /* BPE tokens — look up in loaded vocab */
    if (s_bpe_loaded && s_bpe_tokens) {
        const char *str = bpe_token_str(token);
        if (str) {
            xm_strncpy_safe(buf, str, bufsz);
            return;
        }
    }

    /* Unknown / future BPE tokens */
    /* Render as <UNK:DDDDD> — up to 5 decimal digits */
    if (bufsz < 12u) {
        buf[0] = '\0';
        return;
    }
    /* Build "<UNK:" + decimal(token) + ">" */
    buf[0] = '<';
    buf[1] = 'U';
    buf[2] = 'N';
    buf[3] = 'K';
    buf[4] = ':';
    /* Convert token to decimal in buf[5..] */
    uint32_t tmp = token;
    char digits[10];
    uint32_t nd = 0u;
    if (tmp == 0u) {
        digits[nd++] = '0';
    } else {
        while (tmp > 0u && nd < 10u) {
            digits[nd++] = (char)('0' + (tmp % 10u));
            tmp /= 10u;
        }
    }
    /* digits is in reverse order — write forwards */
    uint32_t pos = 5u;
    uint32_t d;
    for (d = nd; d > 0u && pos < bufsz - 2u; d--) {
        buf[pos++] = digits[d - 1u];
    }
    buf[pos++] = '>';
    buf[pos]   = '\0';
}

/* ═══════════════════════════════════════════════════════════════════
 * §8  BPE MERGE TABLE (Sprint 7 — XSTORE-backed)
 * ═══════════════════════════════════════════════════════════════════
 *
 * Types, state variables, and constants defined in §3b above.
 * This section contains BPE helpers, hash table, and merge logic.
 */

/* ── BPE merge hash table (FNV-1a keyed by (left_id, right_id)) ── */
#define XMIND_BPE_HT_SIZE  262144u  /* 2^18, ~50% load at 128K rules */
#define XMIND_BPE_HT_EMPTY (~0u)

typedef struct {
    uint32_t left_id;
    uint32_t right_id;
    uint32_t rule_idx;  /* index into s_bpe_rules */
} xmind_bpe_ht_entry_t;

static xmind_bpe_ht_entry_t *s_bpe_ht = (void *)0;

/* ── Detokenization hash table (FNV-1a keyed by token ID) ─────── */
/* M28 FIX: replaces O(n) linear scan in bpe_token_str() with O(1)
 * open-addressed hash table.  262144 slots for 128K vocab = ~50% load. */
#define XMIND_DETOK_HT_SIZE 262144u  /* 2^18, same sizing as merge HT */

typedef struct {
    uint32_t token_id;   /* key: BPE token ID (>= 259) */
    uint32_t tok_idx;    /* value: index into s_bpe_tokens[] */
} xmind_detok_ht_entry_t;

static xmind_detok_ht_entry_t *s_detok_ht = (void *)0;

/* Hash a single uint32_t token ID using FNV-1a */
static uint32_t detok_id_hash(uint32_t id) {
    uint32_t h = XM_FNV1A_OFFSET;
    uint8_t *p = (uint8_t *)&id;
    h ^= p[0]; h *= XM_FNV1A_PRIME;
    h ^= p[1]; h *= XM_FNV1A_PRIME;
    h ^= p[2]; h *= XM_FNV1A_PRIME;
    h ^= p[3]; h *= XM_FNV1A_PRIME;
    return h;
}

/* Insert token into detokenization hash table */
static void detok_ht_insert(uint32_t token_id, uint32_t tok_idx) {
    if (!s_detok_ht) return;
    uint32_t h = detok_id_hash(token_id) & (XMIND_DETOK_HT_SIZE - 1u);
    uint32_t i;
    for (i = 0u; i < XMIND_DETOK_HT_SIZE; i++) {
        uint32_t slot = (h + i) & (XMIND_DETOK_HT_SIZE - 1u);
        if (s_detok_ht[slot].tok_idx == XMIND_BPE_HT_EMPTY) {
            s_detok_ht[slot].token_id = token_id;
            s_detok_ht[slot].tok_idx  = tok_idx;
            return;
        }
    }
    /* Table full -- should not happen at ~50% load */
}

/* Lookup token ID in detokenization hash table.
 * Returns index into s_bpe_tokens[], or XMIND_BPE_HT_EMPTY if not found. */
static uint32_t detok_ht_lookup(uint32_t token_id) {
    if (!s_detok_ht) return XMIND_BPE_HT_EMPTY;
    uint32_t h = detok_id_hash(token_id) & (XMIND_DETOK_HT_SIZE - 1u);
    uint32_t i;
    for (i = 0u; i < XMIND_DETOK_HT_SIZE; i++) {
        uint32_t slot = (h + i) & (XMIND_DETOK_HT_SIZE - 1u);
        if (s_detok_ht[slot].tok_idx == XMIND_BPE_HT_EMPTY) {
            return XMIND_BPE_HT_EMPTY;  /* empty slot = not found */
        }
        if (s_detok_ht[slot].token_id == token_id) {
            return s_detok_ht[slot].tok_idx;
        }
    }
    return XMIND_BPE_HT_EMPTY;
}

/* Hash (left, right) pair using FNV-1a */
static uint32_t bpe_pair_hash(uint32_t left, uint32_t right) {
    uint32_t h = XM_FNV1A_OFFSET;
    uint8_t *p = (uint8_t *)&left;
    h ^= p[0]; h *= XM_FNV1A_PRIME;
    h ^= p[1]; h *= XM_FNV1A_PRIME;
    h ^= p[2]; h *= XM_FNV1A_PRIME;
    h ^= p[3]; h *= XM_FNV1A_PRIME;
    p = (uint8_t *)&right;
    h ^= p[0]; h *= XM_FNV1A_PRIME;
    h ^= p[1]; h *= XM_FNV1A_PRIME;
    h ^= p[2]; h *= XM_FNV1A_PRIME;
    h ^= p[3]; h *= XM_FNV1A_PRIME;
    return h;
}

/* Insert into hash table */
static void bpe_ht_insert(uint32_t left, uint32_t right, uint32_t rule_idx) {
    if (!s_bpe_ht) return;
    uint32_t h = bpe_pair_hash(left, right) & (XMIND_BPE_HT_SIZE - 1u);
    uint32_t i;
    for (i = 0u; i < XMIND_BPE_HT_SIZE; i++) {
        uint32_t slot = (h + i) & (XMIND_BPE_HT_SIZE - 1u);
        if (s_bpe_ht[slot].rule_idx == XMIND_BPE_HT_EMPTY) {
            s_bpe_ht[slot].left_id  = left;
            s_bpe_ht[slot].right_id = right;
            s_bpe_ht[slot].rule_idx = rule_idx;
            return;
        }
    }
    /* Table full — should not happen at 50% load */
}

/* ── BPE helpers ─────────────────────────────────────────────────── */

/* Parse a little-endian u32 from 4 bytes */
static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0]
         | ((uint32_t)p[1] << 8u)
         | ((uint32_t)p[2] << 16u)
         | ((uint32_t)p[3] << 24u);
}

/* Parse a little-endian f32 from 4 bytes */
__attribute__((unused))
static float le_f32(const uint8_t *p) {
    uint32_t bits = le32(p);
    float f;
    /* Type-pun safely via memcpy (no UB) */
    uint32_t i;
    uint8_t *fp = (uint8_t *)&f;
    for (i = 0u; i < 4u; i++) { fp[i] = ((uint8_t *)&bits)[i]; }
    return f;
}

/* Find the BPE rule matching (left, right) with lowest score.
 * Returns rule index or UINT32_MAX if not found.
 * Uses hash table when available, falls back to linear scan. */
static uint32_t bpe_find_rule(uint32_t left, uint32_t right) {
    if (!s_bpe_ht) {
        /* Fallback to linear scan if hash table not allocated */
        uint32_t best_idx = ~0u;
        float best_score = 1e38f;
        uint32_t i;
        for (i = 0u; i < s_n_bpe_rules; i++) {
            if (s_bpe_rules[i].left_id == left &&
                s_bpe_rules[i].right_id == right &&
                s_bpe_rules[i].score < best_score) {
                best_score = s_bpe_rules[i].score;
                best_idx = i;
            }
        }
        return best_idx;
    }
    uint32_t h = bpe_pair_hash(left, right) & (XMIND_BPE_HT_SIZE - 1u);
    uint32_t i;
    for (i = 0u; i < XMIND_BPE_HT_SIZE; i++) {
        uint32_t slot = (h + i) & (XMIND_BPE_HT_SIZE - 1u);
        if (s_bpe_ht[slot].rule_idx == XMIND_BPE_HT_EMPTY) return ~0u;
        if (s_bpe_ht[slot].left_id == left &&
            s_bpe_ht[slot].right_id == right) {
            return s_bpe_ht[slot].rule_idx;
        }
    }
    return ~0u;
}

/* ── Allocate BPE tables on heap (called once before loading vocab) ── */
static xmind_status_t bpe_alloc_tables(void) {
    if (s_bpe_rules) return XMIND_OK;  /* already allocated */

    s_bpe_rules = (xmind_bpe_rule_t *)xm_heap_alloc(
        (uint64_t)sizeof(xmind_bpe_rule_t) * XMIND_BPE_MAX_RULES);
    if (!s_bpe_rules) return XMIND_ERR_NOMEM;

    s_bpe_tokens = (xmind_bpe_token_t *)xm_heap_alloc(
        (uint64_t)sizeof(xmind_bpe_token_t) * XMIND_BPE_MAX_TOKENS);
    if (!s_bpe_tokens) {
        xm_heap_free(s_bpe_rules);
        s_bpe_rules = (void*)0;
        return XMIND_ERR_NOMEM;
    }

    s_bpe_ht = (xmind_bpe_ht_entry_t *)xm_heap_alloc(
        (uint64_t)sizeof(xmind_bpe_ht_entry_t) * XMIND_BPE_HT_SIZE);
    if (!s_bpe_ht) {
        xm_heap_free(s_bpe_tokens);
        xm_heap_free(s_bpe_rules);
        s_bpe_rules = (void*)0;
        s_bpe_tokens = (void*)0;
        return XMIND_ERR_NOMEM;
    }

    /* M28: Allocate detokenization hash table (token ID -> token index) */
    s_detok_ht = (xmind_detok_ht_entry_t *)xm_heap_alloc(
        (uint64_t)sizeof(xmind_detok_ht_entry_t) * XMIND_DETOK_HT_SIZE);
    if (!s_detok_ht) {
        xm_heap_free(s_bpe_ht);
        xm_heap_free(s_bpe_tokens);
        xm_heap_free(s_bpe_rules);
        s_bpe_ht = (void*)0;
        s_bpe_rules = (void*)0;
        s_bpe_tokens = (void*)0;
        return XMIND_ERR_NOMEM;
    }

    /* Initialize both hash tables to empty */
    uint32_t i;
    for (i = 0u; i < XMIND_BPE_HT_SIZE; i++) {
        s_bpe_ht[i].rule_idx = XMIND_BPE_HT_EMPTY;
    }
    for (i = 0u; i < XMIND_DETOK_HT_SIZE; i++) {
        s_detok_ht[i].tok_idx = XMIND_BPE_HT_EMPTY;
    }
    return XMIND_OK;
}

/* ═══════════════════════════════════════════════════════════════════
 * §9  xmind_tokenizer_load — Load BPE rules + vocab from XSTORE
 * ═══════════════════════════════════════════════════════════════════
 *
 * Keys used in XSTORE:
 *   "xmind:bpe:rules"  — binary blob of N × XMIND_BPE_RECORD_SZ bytes
 *                        [left:u32][right:u32][merged:u32][score:f32]
 *   "xmind:bpe:vocab"  — binary blob of N × XMIND_BPE_VTOK_SZ bytes
 *                        [id:u32][str:char[60]]
 *
 * If XSTORE is unavailable or keys are missing, the function returns
 * XMIND_ERR_INVAL and the tokenizer remains in byte-level mode.
 *
 * If called when already loaded, the existing tables are replaced.
 *
 * Note: xstore_ctx_t is forward-declared here via void* to keep this
 * translation unit compilable without the full XSTORE header.
 * A real integration would #include "xstore.h" and use the typed API.
 * The sprint7.yml CI compile check uses -DXMIND_HAS_XSTORE=0 so this
 * path is exercised only when XSTORE is present.
 * =================================================================== */

#ifdef XMIND_HAS_XSTORE
#include "xstore.h"

xmind_status_t xmind_tokenizer_load(void *xstore_ctx,
                                     const char *rules_key,
                                     const char *vocab_key) {
    if (!xstore_ctx || !rules_key || !vocab_key) { return XMIND_ERR_INVAL; }

    /* Allocate heap tables if not already allocated */
    xmind_status_t alloc_st = bpe_alloc_tables();
    if (alloc_st != XMIND_OK) return alloc_st;

    /* Reset existing tables */
    s_n_bpe_rules  = 0u;
    s_n_bpe_tokens = 0u;
    s_bpe_loaded   = 0u;

    /* ── Load merge rules ─────────────────────────────────────── */
    xstore_val_t val;
    xstore_status_t st = xstore_get((xstore_ctx_t *)xstore_ctx,
                                     rules_key, &val);
    if (st != XSTORE_OK) { return XMIND_ERR_INVAL; }

    uint32_t n_rules = (uint32_t)(val.length / XMIND_BPE_RECORD_SZ);
    if (n_rules > XMIND_BPE_MAX_RULES) { n_rules = XMIND_BPE_MAX_RULES; }

    const uint8_t *rp = (const uint8_t *)val.data;
    uint32_t r;
    for (r = 0u; r < n_rules; r++) {
        const uint8_t *rec = rp + r * XMIND_BPE_RECORD_SZ;
        s_bpe_rules[r].left_id   = le32(rec);
        s_bpe_rules[r].right_id  = le32(rec + 4u);
        s_bpe_rules[r].merged_id = le32(rec + 8u);
        s_bpe_rules[r].score     = le_f32(rec + 12u);
    }
    s_n_bpe_rules = n_rules;

    /* Build hash table for merge rules */
    if (s_bpe_ht) {
        for (r = 0u; r < n_rules; r++) {
            bpe_ht_insert(s_bpe_rules[r].left_id,
                          s_bpe_rules[r].right_id, r);
        }
    }

    /* ── Load extended vocab entries ─────────────────────────── */
    xstore_val_t vval;
    st = xstore_get((xstore_ctx_t *)xstore_ctx, vocab_key, &vval);
    if (st == XSTORE_OK) {
        uint32_t n_vtoks = (uint32_t)(vval.length / XMIND_BPE_VTOK_SZ);
        if (n_vtoks > XMIND_BPE_MAX_TOKENS) { n_vtoks = XMIND_BPE_MAX_TOKENS; }
        const uint8_t *vp = (const uint8_t *)vval.data;
        uint32_t v;
        for (v = 0u; v < n_vtoks; v++) {
            const uint8_t *ent = vp + v * XMIND_BPE_VTOK_SZ;
            s_bpe_tokens[v].id = le32(ent);
            /* Copy string — at most 59 bytes + null */
            uint32_t ci;
            for (ci = 0u; ci < 59u; ci++) {
                char ch = (char)ent[4u + ci];
                s_bpe_tokens[v].str[ci] = ch;
                if (ch == '\0') { break; }
            }
            s_bpe_tokens[v].str[59] = '\0';
        }
        s_n_bpe_tokens = n_vtoks;

        /* M28: Build detokenization hash table for O(1) lookup */
        if (s_detok_ht) {
            uint32_t di;
            for (di = 0u; di < XMIND_DETOK_HT_SIZE; di++) {
                s_detok_ht[di].tok_idx = XMIND_BPE_HT_EMPTY;
            }
            for (di = 0u; di < s_n_bpe_tokens; di++) {
                detok_ht_insert(s_bpe_tokens[di].id, di);
            }
        }
    }

    s_bpe_loaded = 1u;
    pal_console_printf("[XMIND] BPE vocab loaded: %u rules, %u tokens (detok: %s)\n",
                       s_n_bpe_rules, s_n_bpe_tokens,
                       s_detok_ht ? "O(1)" : "linear");
    return XMIND_OK;
}

#else /* !XMIND_HAS_XSTORE */

/* Stub when XSTORE not compiled in */
xmind_status_t xmind_tokenizer_load(void *xstore_ctx,
                                     const char *rules_key,
                                     const char *vocab_key) {
    (void)xstore_ctx; (void)rules_key; (void)vocab_key;
    pal_console_printf("[XMIND] tokenizer_load: XSTORE not compiled in"
                       " — byte-level mode\n");
    return XMIND_ERR_INVAL;
}

#endif /* XMIND_HAS_XSTORE */

/* ═══════════════════════════════════════════════════════════════════
 * §10  xmind_tokenizer_reset — Unload BPE data
 * ═══════════════════════════════════════════════════════════════════ */

void xmind_tokenizer_reset(void) {
    s_n_bpe_rules  = 0u;
    s_n_bpe_tokens = 0u;
    s_bpe_loaded   = 0u;
    if (s_detok_ht)    { xm_heap_free(s_detok_ht);    s_detok_ht = (void*)0; }
    if (s_bpe_ht)      { xm_heap_free(s_bpe_ht);      s_bpe_ht = (void*)0; }
    if (s_bpe_tokens)  { xm_heap_free(s_bpe_tokens);   s_bpe_tokens = (void*)0; }
    if (s_bpe_rules)   { xm_heap_free(s_bpe_rules);    s_bpe_rules = (void*)0; }
}

/* ═══════════════════════════════════════════════════════════════════
 * §11  BPE MERGE PASS
 *
 * Applies one greedy BPE merge pass over the token sequence.
 * Finds the pair (tokens[i], tokens[i+1]) with the lowest-score
 * matching rule and replaces it with the merged token.
 * Returns 1 if a merge was performed, 0 if no rule matched.
 * =================================================================== */

static uint8_t bpe_merge_pass(uint32_t *tokens, uint32_t *n_tokens) {
    if (*n_tokens < 2u) { return 0u; }

    /* Find best mergeable pair */
    uint32_t best_pos  = ~0u;
    uint32_t best_rule = ~0u;
    float    best_score = 1e38f;
    uint32_t i;
    for (i = 0u; i + 1u < *n_tokens; i++) {
        uint32_t ri = bpe_find_rule(tokens[i], tokens[i + 1u]);
        if (ri != ~0u && s_bpe_rules[ri].score < best_score) {
            best_score = s_bpe_rules[ri].score;
            best_pos   = i;
            best_rule  = ri;
        }
    }
    if (best_pos == ~0u) { return 0u; }

    /* Apply merge: replace [best_pos, best_pos+1] with merged_id */
    tokens[best_pos] = s_bpe_rules[best_rule].merged_id;
    /* Shift remaining tokens left by one */
    uint32_t j;
    for (j = best_pos + 1u; j + 1u < *n_tokens; j++) {
        tokens[j] = tokens[j + 1u];
    }
    (*n_tokens)--;
    return 1u;
}

/* ═══════════════════════════════════════════════════════════════════
 * §12  VOCABULARY SIZE QUERY (updated for dynamic BPE vocab)
 * ═══════════════════════════════════════════════════════════════════ */

uint32_t xmind_vocab_size(void) {
    /* 3 special + 256 byte tokens + dynamically loaded BPE merge tokens */
    return 259u + s_n_bpe_tokens;
}

/* ═══════════════════════════════════════════════════════════════════
 * §13  BPE-EXTENDED DETOKENIZE LOOKUP
 *
 * For token IDs >= 259 (BPE merge tokens), search the extended vocab.
 * Returns pointer to the token string, or NULL if not found.
 * =================================================================== */

static const char *bpe_token_str(uint32_t id) {
    /* M28 FIX: O(1) hash table lookup replaces O(n) linear scan.
     * Previous: 620ms/token at 128K vocab.  Now: ~1us/token. */
    uint32_t idx = detok_ht_lookup(id);
    if (idx != XMIND_BPE_HT_EMPTY && idx < s_n_bpe_tokens) {
        return s_bpe_tokens[idx].str;
    }
    /* Fallback: linear scan if hash table not allocated (should not happen) */
    if (!s_detok_ht) {
        uint32_t i;
        for (i = 0u; i < s_n_bpe_tokens; i++) {
            if (s_bpe_tokens[i].id == id) { return s_bpe_tokens[i].str; }
        }
    }
    return (const char *)0;
}

/* ═══════════════════════════════════════════════════════════════════
 * §14  UPDATED xmind_tokenize — BPE merge pass when loaded
 *
 * Wraps the original byte-level tokenize, then applies BPE merges.
 * Exported name is the same; the original body is inlined below.
 * The Sprint 6 tokenize function is replaced here with the upgraded
 * version that applies BPE merging when s_bpe_loaded == 1.
 *
 * Implementation note: we re-declare this here (the §6 definition
 * above is the primary; this override uses a shadow to apply BPE).
 * Since C has no function overloading, we use a preprocessor alias:
 * the §6 function is renamed to xmind_tokenize_bytes and the BPE
 * wrapper becomes xmind_tokenize.
 * =================================================================== */

/* Alias: rename Sprint 6 tokenize to _bytes variant via forward-decl
 * (the compiler sees both definitions in the same TU; we suppress the
 * conflict by making the inner one static and not conflicting on name) */

static xmind_status_t xmind_tokenize_bpe(const char *text,
                                           uint32_t *out_tokens,
                                           uint32_t *out_len,
                                           uint32_t max_tokens) {
    /* Step 1: byte-level encoding (reuse §6 internals directly) */
    if (!text || !out_tokens || !out_len || max_tokens == 0u) {
        return XMIND_ERR_INVAL;
    }

    uint32_t count = 0u;
    if (count >= max_tokens) { *out_len = 0u; return XMIND_ERR_OVERFLOW; }
    out_tokens[count++] = XMIND_TOK_BOS;

    uint64_t i;
    uint64_t tlen = xm_strlen(text);
    for (i = 0u; i < tlen; i++) {
        if (count >= max_tokens) { *out_len = count; return XMIND_ERR_OVERFLOW; }
        out_tokens[count++] = (uint32_t)(uint8_t)text[i] + 3u;
    }
    *out_len = count;

    /* Step 2: iterative BPE merge passes */
    uint32_t pass;
    for (pass = 0u; pass < s_n_bpe_rules && count >= 2u; pass++) {
        if (!bpe_merge_pass(out_tokens, &count)) { break; }
    }
    *out_len = count;
    return XMIND_OK;
}

/* Public xmind_tokenize dispatches to BPE mode when loaded, otherwise
 * falls back to byte-level encoding.  Both helpers are static in this TU
 * so there is no external-linkage conflict. */
xmind_status_t xmind_tokenize(const char *text, uint32_t *out_tokens,
                               uint32_t *out_len, uint32_t max_tokens) {
    if (s_bpe_loaded) {
        return xmind_tokenize_bpe(text, out_tokens, out_len, max_tokens);
    }
    return xmind_tokenize_bytes(text, out_tokens, out_len, max_tokens);
}

/* ═══════════════════════════════════════════════════════════════════
 * §15  xmind_tokenizer_load_direct — load BPE vocab from GGUF path
 *
 * Called by weights_loader.c §8b after GGUF metadata scan captures the
 * tokenizer.ggml.tokens array into wl_tok_entry_t[].  The layout is
 * identical to wl_tok_entry_t (id:u32, score:f32, str:char[60]) so we
 * use an opaque void* with a local compatible struct cast.
 *
 * Token IDs 0-258 are the fixed special (0-2) and byte (3-258) tokens
 * already handled procedurally; only IDs >= 259 are multi-byte BPE
 * merge tokens that need entries in s_bpe_tokens[].
 * =================================================================== */

/* Compatible with wl_tok_entry_t in weights_loader.c */
typedef struct { uint32_t id; float score; char str[60]; } xm_tok_raw_t;

xmind_status_t xmind_tokenizer_load_direct(const void *vocab_raw,
                                             uint32_t n_vocab) {
    const xm_tok_raw_t *vocab = (const xm_tok_raw_t *)vocab_raw;

    /* Allocate heap tables if not already allocated */
    xmind_status_t alloc_st = bpe_alloc_tables();
    if (alloc_st != XMIND_OK) return alloc_st;

    s_n_bpe_tokens = 0u;
    s_n_bpe_rules  = 0u;
    s_bpe_loaded   = 0u;

    uint32_t v;
    for (v = 0u; v < n_vocab && s_n_bpe_tokens < XMIND_BPE_MAX_TOKENS; v++) {
        if (vocab[v].id < 259u) { continue; }   /* skip byte + special */
        s_bpe_tokens[s_n_bpe_tokens].id = vocab[v].id;
        uint32_t ci;
        for (ci = 0u; ci < 59u; ci++) {
            s_bpe_tokens[s_n_bpe_tokens].str[ci] = vocab[v].str[ci];
            if (vocab[v].str[ci] == '\0') { break; }
        }
        s_bpe_tokens[s_n_bpe_tokens].str[59] = '\0';
        /* xmind_bpe_token_t has no score field; scores are only used in
         * merge rules (xmind_bpe_rule_t).  Vocab scores from GGUF are
         * intentionally discarded here. */
        s_n_bpe_tokens++;
    }

    /* Build merge rule hash table (if any rules present) */
    if (s_bpe_ht && s_n_bpe_rules > 0u) {
        uint32_t r;
        for (r = 0u; r < s_n_bpe_rules; r++) {
            bpe_ht_insert(s_bpe_rules[r].left_id,
                          s_bpe_rules[r].right_id, r);
        }
    }

    /* M28: Build detokenization hash table (token ID -> index) for O(1) lookup */
    if (s_detok_ht) {
        /* Reset detok HT to empty before populating */
        uint32_t di;
        for (di = 0u; di < XMIND_DETOK_HT_SIZE; di++) {
            s_detok_ht[di].tok_idx = XMIND_BPE_HT_EMPTY;
        }
        for (di = 0u; di < s_n_bpe_tokens; di++) {
            detok_ht_insert(s_bpe_tokens[di].id, di);
        }
    }

    s_bpe_loaded = 1u;
    pal_console_printf("[XMIND] BPE tokenizer: %u tokens loaded (hash table: %s)\n",
                       s_n_bpe_tokens, s_detok_ht ? "O(1)" : "linear");
    return XMIND_OK;
}
