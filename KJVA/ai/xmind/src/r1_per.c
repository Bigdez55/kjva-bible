/*
 * r1_per.c --- R1_PER Phase 1 Deterministic Perception Pipeline
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Implements the R1_PER perception layer that converts natural language
 *   input into XCOG cognitive opcodes.  Three-stage pipeline:
 *     Stage 1 (Lexical):  Tokenize + POS-tag via FSM + lookup table
 *     Stage 2 (Semantic): Intent classification via decision tree,
 *                          entity extraction, predicate extraction
 *     Stage 3 (Compile):  Emit XCOG instruction stream with dual SHA-256
 *
 *   This is the Phase 1 implementation: fully deterministic, no ML,
 *   no heap allocation at steady-state.  Entity registry and intent
 *   decision tree are static const.
 *
 * SECURITY:
 *   - Raw NL text is NEVER forwarded to the model except via fallback path
 *   - Typed XCOG opcodes structurally prevent prompt injection
 *   - Dual SHA-256 creates tamper-evident encoding chain
 *   - Confidence threshold enforces fallback to CONVERSE on ambiguity
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#include "../include/r1_per.h"
#include "../include/xmind.h"
#include "../../pal/include/pal.h"
#include "../../sec/xsec/include/xsec.h"
#include "../../sec/xsec/include/causal_log_cog.h"
#include "../../xisc/include/xcog.h"

/* ═══════════════════════════════════════════════════════════════════════
 * S0  INTERNAL CONSTANTS
 * ═══════════════════════════════════════════════════════════════════════ */

#define R1_MAX_WORDS          128u   /* max words per input sentence        */
#define R1_MAX_WORD_LEN        64u   /* max bytes per word                  */
#define R1_FALLBACK_THRESHOLD 153u   /* 0.60 * 255 ~= 153                  */
#define R1_FNV1A_OFFSET  0x811C9DC5u
#define R1_FNV1A_PRIME   0x01000193u

/* Confidence scaling: fixed-point 0..255 maps to 0.0..1.0 */
#define R1_CONF_FULL     255u
#define R1_CONF_HIGH     204u   /* 0.80 */
#define R1_CONF_MED      153u   /* 0.60 */
#define R1_CONF_LOW      102u   /* 0.40 */

/* ═══════════════════════════════════════════════════════════════════════
 * S1  INLINE MEMORY UTILITIES (freestanding -- no libc)
 * ═══════════════════════════════════════════════════════════════════════ */

static inline void r1_memset(void *dst, uint8_t val, size_t n)
{
    uint8_t *d = (uint8_t *)dst;
    for (size_t i = 0; i < n; i++) d[i] = val;
}

static inline void r1_memcpy(void *dst, const void *src, size_t n)
{
    uint8_t       *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;
    for (size_t i = 0; i < n; i++) d[i] = s[i];
}

static inline size_t r1_strlen(const char *s)
{
    size_t n = 0;
    while (s[n]) n++;
    return n;
}

/* Case-insensitive byte comparison (ASCII only) */
static inline uint8_t r1_tolower(uint8_t c)
{
    return (c >= 'A' && c <= 'Z') ? (uint8_t)(c + 32) : c;
}

static inline int32_t r1_strcasecmp(const char *a, const char *b)
{
    while (*a && *b) {
        uint8_t ca = r1_tolower((uint8_t)*a);
        uint8_t cb = r1_tolower((uint8_t)*b);
        if (ca != cb) return (int32_t)ca - (int32_t)cb;
        a++;
        b++;
    }
    return (int32_t)r1_tolower((uint8_t)*a) - (int32_t)r1_tolower((uint8_t)*b);
}

/* FNV-1a hash (32-bit) for entity/word hashing */
static inline uint32_t r1_fnv1a(const char *s, size_t len)
{
    uint32_t h = R1_FNV1A_OFFSET;
    for (size_t i = 0; i < len; i++) {
        h ^= (uint32_t)r1_tolower((uint8_t)s[i]);
        h *= R1_FNV1A_PRIME;
    }
    return h;
}

/* ═══════════════════════════════════════════════════════════════════════
 * S2  POS TAG TYPES
 * ═══════════════════════════════════════════════════════════════════════ */

typedef enum {
    POS_UNKNOWN = 0,
    POS_NOUN    = 1,
    POS_VERB    = 2,
    POS_ADJ     = 3,
    POS_PREP    = 4,
    POS_DET     = 5,
    POS_PRON    = 6,
    POS_WH      = 7,
    POS_ADV     = 8,
    POS_CONJ    = 9,
    POS_NEG     = 10,
    POS_QUANT   = 11
} r1_pos_t;

/* ═══════════════════════════════════════════════════════════════════════
 * S3  WORD TOKEN (output of Stage 1 lexer)
 * ═══════════════════════════════════════════════════════════════════════ */

typedef struct {
    char     text[R1_MAX_WORD_LEN];
    uint32_t len;
    r1_pos_t pos;
    uint32_t hash;       /* FNV-1a of lowercased text */
} r1_word_t;

/* ═══════════════════════════════════════════════════════════════════════
 * S4  ENTITY REGISTRY (static const, no dynamic allocation)
 *
 * Maps known entity keywords to XCOG entity subtypes.
 * ═══════════════════════════════════════════════════════════════════════ */

typedef struct {
    const char *keyword;
    uint8_t     entity_subtype;
} r1_entity_entry_t;

static const r1_entity_entry_t s_entity_registry[] = {
    /* ── Files & directories ────────────────────────── */
    { "file",       XCOG_ENT_FILE      },
    { "files",      XCOG_ENT_FILE      },
    { "document",   XCOG_ENT_FILE      },
    { "documents",  XCOG_ENT_FILE      },
    { "doc",        XCOG_ENT_FILE      },
    { "docs",       XCOG_ENT_FILE      },
    { "pdf",        XCOG_ENT_FILE      },
    { "photo",      XCOG_ENT_FILE      },
    { "photos",     XCOG_ENT_FILE      },
    { "image",      XCOG_ENT_FILE      },
    { "images",     XCOG_ENT_FILE      },
    { "video",      XCOG_ENT_FILE      },
    { "videos",     XCOG_ENT_FILE      },
    { "folder",     XCOG_ENT_DIRECTORY },
    { "folders",    XCOG_ENT_DIRECTORY },
    { "directory",  XCOG_ENT_DIRECTORY },
    { "dir",        XCOG_ENT_DIRECTORY },

    /* ── Applications ───────────────────────────────── */
    { "app",        XCOG_ENT_APP       },
    { "apps",       XCOG_ENT_APP       },
    { "application", XCOG_ENT_APP      },
    { "program",    XCOG_ENT_APP       },
    { "browser",    XCOG_ENT_APP       },
    { "editor",     XCOG_ENT_APP       },
    { "terminal",   XCOG_ENT_APP       },
    { "calculator", XCOG_ENT_APP       },
    { "calendar",   XCOG_ENT_APP       },
    { "notes",      XCOG_ENT_APP       },

    /* ── Contacts & people ──────────────────────────── */
    { "contact",    XCOG_ENT_CONTACT   },
    { "contacts",   XCOG_ENT_CONTACT   },
    { "person",     XCOG_ENT_CONTACT   },
    { "people",     XCOG_ENT_CONTACT   },

    /* ── Email ──────────────────────────────────────── */
    { "email",      XCOG_ENT_EMAIL     },
    { "emails",     XCOG_ENT_EMAIL     },
    { "mail",       XCOG_ENT_EMAIL     },
    { "message",    XCOG_ENT_EMAIL     },
    { "messages",   XCOG_ENT_EMAIL     },
    { "inbox",      XCOG_ENT_EMAIL     },

    /* ── Events / calendar ──────────────────────────── */
    { "event",      XCOG_ENT_EVENT     },
    { "events",     XCOG_ENT_EVENT     },
    { "meeting",    XCOG_ENT_EVENT     },
    { "meetings",   XCOG_ENT_EVENT     },
    { "appointment", XCOG_ENT_EVENT    },
    { "reminder",   XCOG_ENT_EVENT     },
    { "reminders",  XCOG_ENT_EVENT     },

    /* ── Settings & system ──────────────────────────── */
    { "setting",    XCOG_ENT_SETTING   },
    { "settings",   XCOG_ENT_SETTING   },
    { "preference", XCOG_ENT_SETTING   },
    { "preferences", XCOG_ENT_SETTING  },
    { "config",     XCOG_ENT_SETTING   },
    { "configuration", XCOG_ENT_SETTING },
    { "brightness", XCOG_ENT_SETTING   },
    { "volume",     XCOG_ENT_SETTING   },
    { "wifi",       XCOG_ENT_SETTING   },
    { "bluetooth",  XCOG_ENT_SETTING   },
    { "network",    XCOG_ENT_SETTING   },
    { "display",    XCOG_ENT_SETTING   },
    { "theme",      XCOG_ENT_SETTING   },
    { "wallpaper",  XCOG_ENT_SETTING   },
    { "password",   XCOG_ENT_SETTING   },

    /* ── Devices ────────────────────────────────────── */
    { "device",     XCOG_ENT_DEVICE    },
    { "devices",    XCOG_ENT_DEVICE    },
    { "printer",    XCOG_ENT_DEVICE    },
    { "monitor",    XCOG_ENT_DEVICE    },
    { "speaker",    XCOG_ENT_DEVICE    },
    { "speakers",   XCOG_ENT_DEVICE    },
    { "keyboard",   XCOG_ENT_DEVICE    },
    { "mouse",      XCOG_ENT_DEVICE    },
    { "camera",     XCOG_ENT_DEVICE    },
    { "microphone", XCOG_ENT_DEVICE    },
    { "headphones", XCOG_ENT_DEVICE    },
    { "usb",        XCOG_ENT_DEVICE    },
    { "disk",       XCOG_ENT_DEVICE    },
    { "drive",      XCOG_ENT_DEVICE    },

    /* ── Processes ──────────────────────────────────── */
    { "process",    XCOG_ENT_PROCESS   },
    { "processes",  XCOG_ENT_PROCESS   },
    { "task",       XCOG_ENT_PROCESS   },
    { "tasks",      XCOG_ENT_PROCESS   },
    { "service",    XCOG_ENT_PROCESS   },
    { "daemon",     XCOG_ENT_PROCESS   },
};

#define R1_ENTITY_REGISTRY_COUNT \
    (sizeof(s_entity_registry) / sizeof(s_entity_registry[0]))

/* ═══════════════════════════════════════════════════════════════════════
 * S5  POS LOOKUP TABLE (static const, deterministic POS tagging)
 *
 * A small vocabulary of function words for POS classification.
 * Content words (nouns, verbs) are classified by suffix heuristics.
 * ═══════════════════════════════════════════════════════════════════════ */

typedef struct {
    const char *word;
    r1_pos_t    pos;
} r1_pos_entry_t;

static const r1_pos_entry_t s_pos_table[] = {
    /* ── WH-words ──────────────────────────────── */
    { "what",     POS_WH   },
    { "where",    POS_WH   },
    { "when",     POS_WH   },
    { "which",    POS_WH   },
    { "who",      POS_WH   },
    { "whom",     POS_WH   },
    { "whose",    POS_WH   },
    { "why",      POS_WH   },
    { "how",      POS_WH   },

    /* ── Determiners ───────────────────────────── */
    { "the",      POS_DET  },
    { "a",        POS_DET  },
    { "an",       POS_DET  },
    { "this",     POS_DET  },
    { "that",     POS_DET  },
    { "these",    POS_DET  },
    { "those",    POS_DET  },
    { "my",       POS_DET  },
    { "your",     POS_DET  },
    { "his",      POS_DET  },
    { "her",      POS_DET  },
    { "its",      POS_DET  },
    { "our",      POS_DET  },
    { "their",    POS_DET  },
    { "every",    POS_DET  },
    { "each",     POS_DET  },
    { "some",     POS_DET  },
    { "any",      POS_DET  },

    /* ── Pronouns ──────────────────────────────── */
    { "i",        POS_PRON },
    { "me",       POS_PRON },
    { "we",       POS_PRON },
    { "us",       POS_PRON },
    { "you",      POS_PRON },
    { "he",       POS_PRON },
    { "she",      POS_PRON },
    { "it",       POS_PRON },
    { "they",     POS_PRON },
    { "them",     POS_PRON },

    /* ── Prepositions ──────────────────────────── */
    { "in",       POS_PREP },
    { "on",       POS_PREP },
    { "at",       POS_PREP },
    { "to",       POS_PREP },
    { "for",      POS_PREP },
    { "from",     POS_PREP },
    { "by",       POS_PREP },
    { "with",     POS_PREP },
    { "about",    POS_PREP },
    { "into",     POS_PREP },
    { "of",       POS_PREP },
    { "between",  POS_PREP },
    { "after",    POS_PREP },
    { "before",   POS_PREP },
    { "during",   POS_PREP },
    { "through",  POS_PREP },
    { "above",    POS_PREP },
    { "below",    POS_PREP },
    { "under",    POS_PREP },
    { "over",     POS_PREP },
    { "near",     POS_PREP },

    /* ── Conjunctions ──────────────────────────── */
    { "and",      POS_CONJ },
    { "or",       POS_CONJ },
    { "but",      POS_CONJ },
    { "then",     POS_CONJ },

    /* ── Negation ──────────────────────────────── */
    { "not",      POS_NEG  },
    { "no",       POS_NEG  },
    { "never",    POS_NEG  },
    { "none",     POS_NEG  },

    /* ── Quantifiers ───────────────────────────── */
    { "all",      POS_QUANT },
    { "many",     POS_QUANT },
    { "few",      POS_QUANT },
    { "several",  POS_QUANT },
    { "most",     POS_QUANT },
    { "first",    POS_QUANT },
    { "last",     POS_QUANT },
    { "latest",   POS_QUANT },
    { "recent",   POS_QUANT },
    { "oldest",   POS_QUANT },
    { "newest",   POS_QUANT },

    /* ── Adverbs ───────────────────────────────── */
    { "now",      POS_ADV  },
    { "here",     POS_ADV  },
    { "there",    POS_ADV  },
    { "always",   POS_ADV  },
    { "quickly",  POS_ADV  },
    { "please",   POS_ADV  },
    { "just",     POS_ADV  },
    { "also",     POS_ADV  },

    /* ── Common verbs (imperative/action) ──────── */
    { "open",     POS_VERB },
    { "close",    POS_VERB },
    { "show",     POS_VERB },
    { "hide",     POS_VERB },
    { "find",     POS_VERB },
    { "search",   POS_VERB },
    { "create",   POS_VERB },
    { "make",     POS_VERB },
    { "add",      POS_VERB },
    { "new",      POS_VERB },     /* treated as verb for intent: CREATE */
    { "delete",   POS_VERB },
    { "remove",   POS_VERB },
    { "move",     POS_VERB },
    { "copy",     POS_VERB },
    { "rename",   POS_VERB },
    { "edit",     POS_VERB },
    { "update",   POS_VERB },
    { "modify",   POS_VERB },
    { "change",   POS_VERB },
    { "set",      POS_VERB },
    { "turn",     POS_VERB },
    { "enable",   POS_VERB },
    { "disable",  POS_VERB },
    { "start",    POS_VERB },
    { "stop",     POS_VERB },
    { "restart",  POS_VERB },
    { "kill",     POS_VERB },
    { "run",      POS_VERB },
    { "launch",   POS_VERB },
    { "install",  POS_VERB },
    { "uninstall", POS_VERB },
    { "download", POS_VERB },
    { "upload",   POS_VERB },
    { "save",     POS_VERB },
    { "send",     POS_VERB },
    { "print",    POS_VERB },
    { "share",    POS_VERB },
    { "go",       POS_VERB },
    { "navigate", POS_VERB },
    { "list",     POS_VERB },
    { "check",    POS_VERB },
    { "tell",     POS_VERB },
    { "explain",  POS_VERB },
    { "describe", POS_VERB },
    { "analyze",  POS_VERB },
    { "compare",  POS_VERB },
    { "help",     POS_VERB },
    { "sort",     POS_VERB },
    { "filter",   POS_VERB },
    { "connect",  POS_VERB },
    { "disconnect", POS_VERB },
    { "pair",     POS_VERB },
    { "unpair",   POS_VERB },
    { "configure", POS_VERB },
    { "reset",    POS_VERB },
    { "lock",     POS_VERB },
    { "unlock",   POS_VERB },
    { "switch",   POS_VERB },
    { "toggle",   POS_VERB },
    { "schedule", POS_VERB },
    { "cancel",   POS_VERB },

    /* ── Common adjectives ─────────────────────── */
    { "big",      POS_ADJ  },
    { "small",    POS_ADJ  },
    { "large",    POS_ADJ  },
    { "old",      POS_ADJ  },
    { "new",      POS_ADJ  },   /* dual: verb (create) + adj */
    { "dark",     POS_ADJ  },
    { "light",    POS_ADJ  },
    { "high",     POS_ADJ  },
    { "low",      POS_ADJ  },
    { "full",     POS_ADJ  },
    { "empty",    POS_ADJ  },
    { "free",     POS_ADJ  },
    { "available", POS_ADJ },
    { "current",  POS_ADJ  },
    { "default",  POS_ADJ  },
    { "unread",   POS_ADJ  },
    { "read",     POS_ADJ  },
};

#define R1_POS_TABLE_COUNT \
    (sizeof(s_pos_table) / sizeof(s_pos_table[0]))

/* ═══════════════════════════════════════════════════════════════════════
 * S6  INTENT DECISION TREE (static const, deterministic)
 *
 * The tree is traversed top-down.  First match wins.
 * Priority order:
 *   1. WH-word at position 0 or 1          -> QUERY
 *   2. Verb "create"/"new"/"add"/"make"     -> CREATE
 *   3. Verb "delete"/"remove"/"kill"        -> DELETE
 *   4. Verb "edit"/"update"/"modify"/"change"/"set"/"rename" -> MODIFY
 *   5. Verb "go"/"navigate"/"open"/"switch" -> NAVIGATE
 *   6. Verb "configure"/"enable"/"disable"/"toggle"/"turn"/"reset" -> CONFIGURE
 *   7. Verb "analyze"/"explain"/"describe"/"compare"/"check" -> ANALYZE
 *   8. Any imperative verb at position 0    -> COMMAND
 *   9. Default                              -> CONVERSE
 * ═══════════════════════════════════════════════════════════════════════ */

typedef enum {
    R1_RULE_WH_QUERY,
    R1_RULE_CREATE,
    R1_RULE_DELETE,
    R1_RULE_MODIFY,
    R1_RULE_NAVIGATE,
    R1_RULE_CONFIGURE,
    R1_RULE_ANALYZE,
    R1_RULE_COMMAND,
    R1_RULE_COUNT
} r1_intent_rule_t;

typedef struct {
    const char *verb;
    r1_intent_rule_t rule;
} r1_verb_intent_t;

static const r1_verb_intent_t s_verb_intent_map[] = {
    /* CREATE verbs */
    { "create",    R1_RULE_CREATE    },
    { "new",       R1_RULE_CREATE    },
    { "add",       R1_RULE_CREATE    },
    { "make",      R1_RULE_CREATE    },
    { "schedule",  R1_RULE_CREATE    },

    /* DELETE verbs */
    { "delete",    R1_RULE_DELETE    },
    { "remove",    R1_RULE_DELETE    },
    { "kill",      R1_RULE_DELETE    },
    { "uninstall", R1_RULE_DELETE    },
    { "cancel",    R1_RULE_DELETE    },

    /* MODIFY verbs */
    { "edit",      R1_RULE_MODIFY    },
    { "update",    R1_RULE_MODIFY    },
    { "modify",    R1_RULE_MODIFY    },
    { "change",    R1_RULE_MODIFY    },
    { "set",       R1_RULE_MODIFY    },
    { "rename",    R1_RULE_MODIFY    },
    { "move",      R1_RULE_MODIFY    },
    { "copy",      R1_RULE_MODIFY    },
    { "save",      R1_RULE_MODIFY    },

    /* NAVIGATE verbs */
    { "go",        R1_RULE_NAVIGATE  },
    { "navigate",  R1_RULE_NAVIGATE  },
    { "open",      R1_RULE_NAVIGATE  },
    { "switch",    R1_RULE_NAVIGATE  },
    { "launch",    R1_RULE_NAVIGATE  },

    /* CONFIGURE verbs */
    { "configure", R1_RULE_CONFIGURE },
    { "enable",    R1_RULE_CONFIGURE },
    { "disable",   R1_RULE_CONFIGURE },
    { "toggle",    R1_RULE_CONFIGURE },
    { "turn",      R1_RULE_CONFIGURE },
    { "reset",     R1_RULE_CONFIGURE },
    { "connect",   R1_RULE_CONFIGURE },
    { "disconnect", R1_RULE_CONFIGURE },
    { "pair",      R1_RULE_CONFIGURE },
    { "unpair",    R1_RULE_CONFIGURE },
    { "lock",      R1_RULE_CONFIGURE },
    { "unlock",    R1_RULE_CONFIGURE },
    { "install",   R1_RULE_CONFIGURE },

    /* ANALYZE verbs */
    { "analyze",   R1_RULE_ANALYZE   },
    { "explain",   R1_RULE_ANALYZE   },
    { "describe",  R1_RULE_ANALYZE   },
    { "compare",   R1_RULE_ANALYZE   },
    { "check",     R1_RULE_ANALYZE   },
    { "tell",      R1_RULE_ANALYZE   },
    { "help",      R1_RULE_ANALYZE   },
    { "list",      R1_RULE_ANALYZE   },
};

#define R1_VERB_INTENT_COUNT \
    (sizeof(s_verb_intent_map) / sizeof(s_verb_intent_map[0]))

/* Map rule enum to XCOG intent subtype */
static const uint8_t s_rule_to_intent[] = {
    [R1_RULE_WH_QUERY]  = XCOG_INTENT_QUERY,
    [R1_RULE_CREATE]     = XCOG_INTENT_CREATE,
    [R1_RULE_DELETE]     = XCOG_INTENT_DELETE,
    [R1_RULE_MODIFY]     = XCOG_INTENT_MODIFY,
    [R1_RULE_NAVIGATE]   = XCOG_INTENT_NAVIGATE,
    [R1_RULE_CONFIGURE]  = XCOG_INTENT_CONFIGURE,
    [R1_RULE_ANALYZE]    = XCOG_INTENT_ANALYZE,
    [R1_RULE_COMMAND]    = XCOG_INTENT_COMMAND,
};

/* Confidence per rule (higher = more deterministic match) */
static const uint8_t s_rule_confidence[] = {
    [R1_RULE_WH_QUERY]  = R1_CONF_FULL,   /* WH-word is unambiguous      */
    [R1_RULE_CREATE]     = R1_CONF_HIGH,
    [R1_RULE_DELETE]     = R1_CONF_HIGH,
    [R1_RULE_MODIFY]     = R1_CONF_HIGH,
    [R1_RULE_NAVIGATE]   = R1_CONF_HIGH,
    [R1_RULE_CONFIGURE]  = R1_CONF_HIGH,
    [R1_RULE_ANALYZE]    = R1_CONF_MED,    /* "tell" is ambiguous          */
    [R1_RULE_COMMAND]    = R1_CONF_MED,    /* generic imperative           */
};

/* ═══════════════════════════════════════════════════════════════════════
 * S7  TEMPORAL KEYWORD TABLE
 * ═══════════════════════════════════════════════════════════════════════ */

typedef struct {
    const char *keyword;
    int32_t     relative_seconds;  /* 0 = now, negative = past, positive = future */
} r1_temporal_entry_t;

static const r1_temporal_entry_t s_temporal_table[] = {
    { "now",        0         },
    { "today",      0         },
    { "tonight",    43200     },  /* +12h  */
    { "tomorrow",   86400     },  /* +24h  */
    { "yesterday",  -86400    },  /* -24h  */
    { "morning",    0         },
    { "afternoon",  0         },
    { "evening",    0         },
    { "night",      0         },
    { "monday",     0         },  /* relative TBD -- encode as 0 for Phase 1 */
    { "tuesday",    0         },
    { "wednesday",  0         },
    { "thursday",   0         },
    { "friday",     0         },
    { "saturday",   0         },
    { "sunday",     0         },
    { "week",       604800    },  /* 7d  */
    { "month",      2592000   },  /* 30d */
    { "year",       31536000  },  /* 365d */
    { "hour",       3600      },
    { "hours",      3600      },
    { "minute",     60        },
    { "minutes",    60        },
    { "second",     1         },
    { "seconds",    1         },
    { "soon",       300       },  /* +5min */
    { "later",      3600      },  /* +1h   */
    { "ago",        0         },  /* modifier, relative_seconds negated by context */
};

#define R1_TEMPORAL_TABLE_COUNT \
    (sizeof(s_temporal_table) / sizeof(s_temporal_table[0]))

/* ═══════════════════════════════════════════════════════════════════════
 * S8  MODULE STATE (initialized once via r1_per_init)
 * ═══════════════════════════════════════════════════════════════════════ */

static uint8_t s_initialized = 0;

/* ═══════════════════════════════════════════════════════════════════════
 * S9  STAGE 1: LEXICAL ANALYSIS
 *
 * Tokenizes input into words and assigns POS tags.
 * FSM states: SKIP_WS -> IN_WORD -> SKIP_WS
 * Non-alpha characters are word boundaries.
 * ═══════════════════════════════════════════════════════════════════════ */

static inline int r1_is_alpha(uint8_t c)
{
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z');
}

static inline int r1_is_alnum(uint8_t c)
{
    return r1_is_alpha(c) || (c >= '0' && c <= '9');
}

static inline int r1_is_digit(uint8_t c)
{
    return (c >= '0' && c <= '9');
}

/* Look up POS from the static table.  Returns POS_UNKNOWN if not found. */
static r1_pos_t r1_pos_lookup(const char *word)
{
    for (size_t i = 0; i < R1_POS_TABLE_COUNT; i++) {
        if (r1_strcasecmp(word, s_pos_table[i].word) == 0)
            return s_pos_table[i].pos;
    }
    return POS_UNKNOWN;
}

/* Suffix-based POS heuristic for words not in the lookup table. */
static r1_pos_t r1_pos_suffix_heuristic(const char *word, uint32_t len)
{
    if (len < 3) return POS_NOUN;  /* short unknown words default to noun */

    /* -ing -> verb (gerund) */
    if (len >= 4 && word[len-3] == 'i' && word[len-2] == 'n' && word[len-1] == 'g')
        return POS_VERB;
    /* -ed -> verb (past tense) */
    if (len >= 3 && word[len-2] == 'e' && word[len-1] == 'd')
        return POS_VERB;
    /* -ly -> adverb */
    if (len >= 3 && word[len-2] == 'l' && word[len-1] == 'y')
        return POS_ADV;
    /* -tion, -sion -> noun */
    if (len >= 4 && word[len-3] == 'i' && word[len-2] == 'o' && word[len-1] == 'n')
        return POS_NOUN;
    /* -ness -> noun */
    if (len >= 4 && word[len-4] == 'n' && word[len-3] == 'e' &&
        word[len-2] == 's' && word[len-1] == 's')
        return POS_NOUN;
    /* -ment -> noun */
    if (len >= 4 && word[len-4] == 'm' && word[len-3] == 'e' &&
        word[len-2] == 'n' && word[len-1] == 't')
        return POS_NOUN;
    /* -able, -ible -> adjective */
    if (len >= 4 && word[len-3] == 'b' && word[len-2] == 'l' && word[len-1] == 'e')
        return POS_ADJ;
    /* -ful -> adjective */
    if (len >= 3 && word[len-3] == 'f' && word[len-2] == 'u' && word[len-1] == 'l')
        return POS_ADJ;
    /* -ous -> adjective */
    if (len >= 3 && word[len-3] == 'o' && word[len-2] == 'u' && word[len-1] == 's')
        return POS_ADJ;
    /* -ive -> adjective */
    if (len >= 3 && word[len-3] == 'i' && word[len-2] == 'v' && word[len-1] == 'e')
        return POS_ADJ;
    /* -er -> noun (agent) or adjective (comparative).  Default noun. */
    if (len >= 3 && word[len-2] == 'e' && word[len-1] == 'r')
        return POS_NOUN;
    /* -al -> adjective */
    if (len >= 3 && word[len-2] == 'a' && word[len-1] == 'l')
        return POS_ADJ;
    /* -s -> noun (plural) as default */
    if (word[len-1] == 's')
        return POS_NOUN;

    /* All digits -> treat as noun (number) */
    {
        int all_digit = 1;
        for (uint32_t k = 0; k < len; k++) {
            if (!r1_is_digit((uint8_t)word[k])) { all_digit = 0; break; }
        }
        if (all_digit) return POS_NOUN;
    }

    return POS_NOUN;  /* default: noun */
}

/*
 * r1_lex_tokenize --- Stage 1 lexer.
 *
 * Splits nl_input into words, assigns POS tags, computes FNV-1a hash.
 * Returns the number of words extracted.
 */
static uint32_t r1_lex_tokenize(const char *nl_input, uint32_t nl_len,
                                r1_word_t *words, uint32_t max_words)
{
    uint32_t word_count = 0;
    uint32_t i = 0;

    while (i < nl_len && word_count < max_words) {
        /* Skip non-alphanumeric (whitespace, punctuation) */
        while (i < nl_len && !r1_is_alnum((uint8_t)nl_input[i]))
            i++;
        if (i >= nl_len) break;

        /* Collect word characters */
        uint32_t start = i;
        while (i < nl_len && (r1_is_alnum((uint8_t)nl_input[i]) ||
               nl_input[i] == '\'' || nl_input[i] == '-'))
            i++;

        uint32_t wlen = i - start;
        if (wlen == 0) continue;
        if (wlen >= R1_MAX_WORD_LEN) wlen = R1_MAX_WORD_LEN - 1;

        r1_word_t *w = &words[word_count];

        /* Copy and lowercase */
        for (uint32_t j = 0; j < wlen; j++)
            w->text[j] = (char)r1_tolower((uint8_t)nl_input[start + j]);
        w->text[wlen] = '\0';
        w->len = wlen;

        /* Strip leading/trailing apostrophes and hyphens */
        /* (left as-is for Phase 1 -- the FSM handles contractions) */

        /* POS tag: lookup table first, then suffix heuristic */
        w->pos = r1_pos_lookup(w->text);
        if (w->pos == POS_UNKNOWN)
            w->pos = r1_pos_suffix_heuristic(w->text, w->len);

        /* FNV-1a hash */
        w->hash = r1_fnv1a(w->text, w->len);

        word_count++;
    }

    return word_count;
}

/* ═══════════════════════════════════════════════════════════════════════
 * S10  STAGE 2: SEMANTIC ANALYSIS
 *
 * (a) Classify intent via decision tree
 * (b) Extract entities by matching against registry
 * (c) Extract predicates from verb-object pairs
 * ═══════════════════════════════════════════════════════════════════════ */

/* ── 2a: Intent classification ─────────────────────────────────────── */

typedef struct {
    uint8_t  intent_subtype;      /* XCOG_INTENT_* value      */
    uint8_t  confidence;          /* 0..255                    */
    uint32_t trigger_word_idx;    /* index of word that fired  */
} r1_intent_result_t;

static r1_intent_result_t r1_classify_intent(const r1_word_t *words,
                                              uint32_t word_count)
{
    r1_intent_result_t result;
    result.intent_subtype = XCOG_INTENT_CONVERSE;
    result.confidence = 0;
    result.trigger_word_idx = 0;

    if (word_count == 0) return result;

    /* Rule 1: WH-word at position 0 or 1 -> QUERY */
    for (uint32_t i = 0; i < word_count && i < 2; i++) {
        if (words[i].pos == POS_WH) {
            result.intent_subtype = XCOG_INTENT_QUERY;
            result.confidence = R1_CONF_FULL;
            result.trigger_word_idx = i;
            return result;
        }
    }

    /* Rule 2-7: Match first verb against verb_intent_map */
    for (uint32_t i = 0; i < word_count; i++) {
        if (words[i].pos != POS_VERB) continue;

        for (size_t j = 0; j < R1_VERB_INTENT_COUNT; j++) {
            if (r1_strcasecmp(words[i].text, s_verb_intent_map[j].verb) == 0) {
                r1_intent_rule_t rule = s_verb_intent_map[j].rule;
                result.intent_subtype = s_rule_to_intent[rule];
                result.confidence = s_rule_confidence[rule];

                /* Boost confidence if verb is at sentence start (imperative) */
                if (i == 0 && result.confidence < R1_CONF_FULL)
                    result.confidence += 25;

                result.trigger_word_idx = i;
                return result;
            }
        }

        /* Generic imperative verb at position 0 -> COMMAND */
        if (i == 0) {
            result.intent_subtype = XCOG_INTENT_COMMAND;
            result.confidence = R1_CONF_MED;
            result.trigger_word_idx = 0;
            return result;
        }
    }

    /* Check if input ends with '?' -> QUERY */
    /* (Already handled by WH, but catches "is X available?") */
    /* We do not have access to the original punctuation in words,
     * but we can check via a separate flag passed in.  For Phase 1,
     * rely on WH-word detection. */

    return result;  /* CONVERSE fallback */
}

/* ── 2b: Entity extraction ─────────────────────────────────────────── */

typedef struct {
    uint8_t  entity_subtype;
    uint16_t ref;              /* FNV-1a low 16 bits of entity keyword */
    uint32_t payload;          /* FNV-1a high 32 bits of entity keyword */
    uint32_t word_idx;         /* index into word array                 */
} r1_entity_result_t;

static uint32_t r1_extract_entities(const r1_word_t *words, uint32_t word_count,
                                     r1_entity_result_t *out, uint32_t max_ent)
{
    uint32_t ent_count = 0;

    for (uint32_t i = 0; i < word_count && ent_count < max_ent; i++) {
        /* Only match nouns (content words) against entity registry */
        if (words[i].pos != POS_NOUN && words[i].pos != POS_UNKNOWN)
            continue;

        for (size_t j = 0; j < R1_ENTITY_REGISTRY_COUNT; j++) {
            if (r1_strcasecmp(words[i].text, s_entity_registry[j].keyword) == 0) {
                r1_entity_result_t *e = &out[ent_count];
                e->entity_subtype = s_entity_registry[j].entity_subtype;
                e->ref = (uint16_t)(words[i].hash & 0xFFFF);
                e->payload = words[i].hash;
                e->word_idx = i;
                ent_count++;
                break;
            }
        }
    }

    /* Also check verb-tagged words that are in the entity registry
     * (e.g., "calendar" is both entity and might be verb-tagged via
     *  suffix heuristic).  Only if not already found. */
    for (uint32_t i = 0; i < word_count && ent_count < max_ent; i++) {
        if (words[i].pos == POS_NOUN || words[i].pos == POS_UNKNOWN)
            continue;  /* Already checked above */

        /* Check if this word appears in entity registry regardless of POS */
        for (size_t j = 0; j < R1_ENTITY_REGISTRY_COUNT; j++) {
            if (r1_strcasecmp(words[i].text, s_entity_registry[j].keyword) == 0) {
                /* Check for duplicate */
                int dup = 0;
                for (uint32_t k = 0; k < ent_count; k++) {
                    if (out[k].word_idx == i) { dup = 1; break; }
                }
                if (!dup) {
                    r1_entity_result_t *e = &out[ent_count];
                    e->entity_subtype = s_entity_registry[j].entity_subtype;
                    e->ref = (uint16_t)(words[i].hash & 0xFFFF);
                    e->payload = words[i].hash;
                    e->word_idx = i;
                    ent_count++;
                }
                break;
            }
        }
    }

    return ent_count;
}

/* Count nouns in word array (for confidence denominator) */
static uint32_t r1_count_nouns(const r1_word_t *words, uint32_t word_count)
{
    uint32_t n = 0;
    for (uint32_t i = 0; i < word_count; i++) {
        if (words[i].pos == POS_NOUN) n++;
    }
    return n;
}

/* ── 2c: Predicate extraction (verb-object pairs) ─────────────────── */

typedef struct {
    uint32_t verb_idx;
    uint32_t object_idx;
} r1_predicate_result_t;

static uint32_t r1_extract_predicates(const r1_word_t *words, uint32_t word_count,
                                       r1_predicate_result_t *out, uint32_t max_pred)
{
    uint32_t pred_count = 0;

    /* Simple heuristic: for each verb, find the next noun as object. */
    for (uint32_t i = 0; i < word_count && pred_count < max_pred; i++) {
        if (words[i].pos != POS_VERB) continue;

        /* Scan forward for the nearest noun (skipping determiners/preps) */
        for (uint32_t j = i + 1; j < word_count; j++) {
            if (words[j].pos == POS_NOUN) {
                out[pred_count].verb_idx = i;
                out[pred_count].object_idx = j;
                pred_count++;
                break;
            }
            /* Stop scanning if we hit another verb */
            if (words[j].pos == POS_VERB) break;
        }
    }

    return pred_count;
}

/* ── 2d: Temporal extraction ──────────────────────────────────────── */

typedef struct {
    int32_t  relative_seconds;
    uint32_t word_idx;
} r1_temporal_result_t;

static uint32_t r1_extract_temporal(const r1_word_t *words, uint32_t word_count,
                                     r1_temporal_result_t *out, uint32_t max_temp)
{
    uint32_t temp_count = 0;

    for (uint32_t i = 0; i < word_count && temp_count < max_temp; i++) {
        for (size_t j = 0; j < R1_TEMPORAL_TABLE_COUNT; j++) {
            if (r1_strcasecmp(words[i].text, s_temporal_table[j].keyword) == 0) {
                int32_t seconds = s_temporal_table[j].relative_seconds;

                /* Check for "ago" modifier: negate the preceding temporal */
                if (r1_strcasecmp(words[i].text, "ago") == 0 && temp_count > 0) {
                    /* Negate the previous temporal entry */
                    if (out[temp_count - 1].relative_seconds > 0) {
                        out[temp_count - 1].relative_seconds =
                            -out[temp_count - 1].relative_seconds;
                    }
                    break;  /* "ago" itself does not emit a new temporal */
                }

                out[temp_count].relative_seconds = seconds;
                out[temp_count].word_idx = i;
                temp_count++;
                break;
            }
        }
    }

    return temp_count;
}

/* ── 2e: Negation detection ───────────────────────────────────────── */

static int r1_has_negation(const r1_word_t *words, uint32_t word_count)
{
    for (uint32_t i = 0; i < word_count; i++) {
        if (words[i].pos == POS_NEG) return 1;
        /* Handle contractions: "don't", "can't", "won't", "isn't" etc. */
        if (words[i].len >= 3) {
            const char *t = words[i].text;
            uint32_t n = words[i].len;
            if (n >= 4 && t[n-3] == 'n' && t[n-2] == '\'' && t[n-1] == 't')
                return 1;
            if (n >= 3 && t[n-2] == 'n' && t[n-1] == 't' && t[n-3] == '\'')
                return 1;
        }
    }
    return 0;
}

/* ── 2f: Quantifier detection ─────────────────────────────────────── */

typedef struct {
    uint8_t  type;      /* 0=all, 1=some, 2=none, 3=specific */
    uint32_t word_idx;
} r1_quantifier_result_t;

static int r1_extract_quantifier(const r1_word_t *words, uint32_t word_count,
                                  r1_quantifier_result_t *out)
{
    for (uint32_t i = 0; i < word_count; i++) {
        if (words[i].pos == POS_QUANT) {
            if (r1_strcasecmp(words[i].text, "all") == 0 ||
                r1_strcasecmp(words[i].text, "every") == 0) {
                out->type = 0; out->word_idx = i; return 1;
            }
            if (r1_strcasecmp(words[i].text, "some") == 0 ||
                r1_strcasecmp(words[i].text, "few") == 0 ||
                r1_strcasecmp(words[i].text, "several") == 0 ||
                r1_strcasecmp(words[i].text, "many") == 0) {
                out->type = 1; out->word_idx = i; return 1;
            }
            /* "first", "last", "latest", etc. -> specific */
            out->type = 3; out->word_idx = i; return 1;
        }
        if (words[i].pos == POS_NEG && r1_strcasecmp(words[i].text, "none") == 0) {
            out->type = 2; out->word_idx = i; return 1;
        }
    }
    return 0;
}

/* ── 2g: Filter extraction (adjective-noun pairs for filtering) ──── */

typedef struct {
    uint32_t adj_idx;
    uint32_t noun_idx;
    uint8_t  op;       /* XCOG_OP_* */
} r1_filter_result_t;

static uint32_t r1_extract_filters(const r1_word_t *words, uint32_t word_count,
                                    r1_filter_result_t *out, uint32_t max_filt)
{
    uint32_t filt_count = 0;

    for (uint32_t i = 0; i + 1 < word_count && filt_count < max_filt; i++) {
        if (words[i].pos == POS_ADJ) {
            /* Find next noun */
            for (uint32_t j = i + 1; j < word_count; j++) {
                if (words[j].pos == POS_NOUN) {
                    out[filt_count].adj_idx = i;
                    out[filt_count].noun_idx = j;
                    out[filt_count].op = XCOG_OP_EQ;
                    filt_count++;
                    break;
                }
                if (words[j].pos == POS_VERB) break;
            }
        }
    }

    return filt_count;
}

/* ═══════════════════════════════════════════════════════════════════════
 * S11  STAGE 3: XCOG COMPILATION
 *
 * Emit XCOG instruction stream in canonical order:
 *   1. INTENT
 *   2. ENTITY (one per extracted entity)
 *   3. PREDICATE (one per verb-object pair)
 *   4. NEGATE (if negation detected)
 *   5. QUANTIFY (if quantifier detected)
 *   6. FILTER (one per adjective-noun pair)
 *   7. TEMPORAL (one per temporal reference)
 *   8. EMIT (output directive)
 * ═══════════════════════════════════════════════════════════════════════ */

static uint16_t r1_compile_xcog(
    const r1_intent_result_t     *intent,
    const r1_entity_result_t     *entities,    uint32_t ent_count,
    const r1_predicate_result_t  *predicates,  uint32_t pred_count,
    const r1_word_t              *words,       uint32_t word_count __attribute__((unused)),
    int                           has_negation,
    const r1_quantifier_result_t *quantifier,  int has_quantifier,
    const r1_filter_result_t     *filters,     uint32_t filt_count,
    const r1_temporal_result_t   *temporals,   uint32_t temp_count,
    xcog_instr_t                 *out_instrs,
    uint16_t                     *out_salience,
    uint16_t                      max_instrs)
{
    uint16_t ic = 0;  /* instruction count */

    if (max_instrs == 0) return 0;

    /* ── 1. INTENT instruction ────────────────────────────────────── */
    out_instrs[ic] = XCOG_INSTR(XCOG_INTENT, intent->intent_subtype,
                                 (uint16_t)intent->trigger_word_idx,
                                 (uint32_t)intent->confidence);
    out_salience[ic] = 65535u;  /* intent always max salience */
    ic++;

    /* ── 2. ENTITY instructions ───────────────────────────────────── */
    for (uint32_t i = 0; i < ent_count && ic < max_instrs; i++) {
        out_instrs[ic] = XCOG_INSTR(XCOG_ENTITY,
                                     entities[i].entity_subtype,
                                     entities[i].ref,
                                     entities[i].payload);
        /* Salience decays with distance from start of sentence */
        out_salience[ic] = (uint16_t)(65535u - (entities[i].word_idx * 512u));
        ic++;
    }

    /* ── 3. PREDICATE instructions ────────────────────────────────── */
    for (uint32_t i = 0; i < pred_count && ic < max_instrs; i++) {
        uint32_t verb_hash = words[predicates[i].verb_idx].hash;
        uint32_t obj_hash  = words[predicates[i].object_idx].hash;
        out_instrs[ic] = XCOG_INSTR(XCOG_PREDICATE,
                                     0,  /* subtype: generic relation */
                                     (uint16_t)(verb_hash & 0xFFFF),
                                     obj_hash);
        out_salience[ic] = 50000u;
        ic++;
    }

    /* ── 4. NEGATE instruction ────────────────────────────────────── */
    if (has_negation && ic < max_instrs) {
        out_instrs[ic] = XCOG_INSTR(XCOG_NEGATE, 0, 0, 0);
        out_salience[ic] = 60000u;  /* negation is high-salience */
        ic++;
    }

    /* ── 5. QUANTIFY instruction ──────────────────────────────────── */
    if (has_quantifier && ic < max_instrs) {
        out_instrs[ic] = XCOG_INSTR(XCOG_QUANTIFY,
                                     quantifier->type,
                                     (uint16_t)quantifier->word_idx,
                                     0);
        out_salience[ic] = 45000u;
        ic++;
    }

    /* ── 6. FILTER instructions ───────────────────────────────────── */
    for (uint32_t i = 0; i < filt_count && ic < max_instrs; i++) {
        uint32_t adj_hash = words[filters[i].adj_idx].hash;
        out_instrs[ic] = XCOG_INSTR(XCOG_FILTER,
                                     filters[i].op,
                                     (uint16_t)(adj_hash & 0xFFFF),
                                     adj_hash);
        out_salience[ic] = 40000u;
        ic++;
    }

    /* ── 7. TEMPORAL instructions ─────────────────────────────────── */
    for (uint32_t i = 0; i < temp_count && ic < max_instrs; i++) {
        uint32_t rel_sec;
        r1_memcpy(&rel_sec, &temporals[i].relative_seconds, sizeof(rel_sec));
        out_instrs[ic] = XCOG_INSTR(XCOG_TEMPORAL,
                                     0,  /* subtype: relative */
                                     (uint16_t)temporals[i].word_idx,
                                     rel_sec);
        out_salience[ic] = 35000u;
        ic++;
    }

    /* ── 8. EMIT directive ────────────────────────────────────────── */
    if (ic < max_instrs) {
        /* Emit type: 0=text, 1=structured, 2=action */
        uint8_t emit_type = 0;
        if (intent->intent_subtype == XCOG_INTENT_COMMAND ||
            intent->intent_subtype == XCOG_INTENT_CREATE  ||
            intent->intent_subtype == XCOG_INTENT_DELETE  ||
            intent->intent_subtype == XCOG_INTENT_MODIFY  ||
            intent->intent_subtype == XCOG_INTENT_CONFIGURE) {
            emit_type = 2;  /* action */
        } else if (intent->intent_subtype == XCOG_INTENT_QUERY ||
                   intent->intent_subtype == XCOG_INTENT_ANALYZE) {
            emit_type = 1;  /* structured */
        }
        out_instrs[ic] = XCOG_INSTR(XCOG_EMIT, emit_type, 0, ic);
        out_salience[ic] = 30000u;
        ic++;
    }

    return ic;
}

/* ═══════════════════════════════════════════════════════════════════════
 * S12  SHA-256 HELPERS
 * ═══════════════════════════════════════════════════════════════════════ */

static void r1_sha256_input(const char *nl_input, uint32_t nl_len,
                             uint8_t out_hash[32])
{
    xsec_sha256_ctx_t ctx;
    xsec_sha256_init(&ctx);
    xsec_sha256_update(&ctx, nl_input, (size_t)nl_len);
    xsec_sha256_final(&ctx, out_hash);
}

static void r1_sha256_instructions(const xcog_instr_t *instrs, uint16_t count,
                                    uint8_t out_hash[32])
{
    xsec_sha256_ctx_t ctx;
    xsec_sha256_init(&ctx);
    xsec_sha256_update(&ctx, instrs, (size_t)count * sizeof(xcog_instr_t));
    xsec_sha256_final(&ctx, out_hash);
}

/* ═══════════════════════════════════════════════════════════════════════
 * S13  XCOG-TO-TEXT HELPERS (for r1_per_translate_to_tokens)
 * ═══════════════════════════════════════════════════════════════════════ */

/* Append a string to a buffer with bounds checking.  Returns new offset. */
static uint32_t r1_buf_append(char *buf, uint32_t offset, uint32_t max,
                               const char *s)
{
    while (*s && offset + 1 < max) {
        buf[offset++] = *s++;
    }
    return offset;
}

/* Append uint32 as decimal to buffer.  Returns new offset. */
static uint32_t r1_buf_append_u32(char *buf, uint32_t offset, uint32_t max,
                                   uint32_t val)
{
    char tmp[12];
    int pos = 0;
    if (val == 0) {
        tmp[pos++] = '0';
    } else {
        while (val > 0 && pos < 10) {
            tmp[pos++] = (char)('0' + (val % 10));
            val /= 10;
        }
    }
    /* Reverse */
    for (int i = pos - 1; i >= 0 && offset + 1 < max; i--)
        buf[offset++] = tmp[i];
    return offset;
}

/* Intent subtype to string */
static const char *r1_intent_name(uint8_t subtype)
{
    switch (subtype) {
    case XCOG_INTENT_QUERY:     return "QUERY";
    case XCOG_INTENT_COMMAND:   return "COMMAND";
    case XCOG_INTENT_CREATE:    return "CREATE";
    case XCOG_INTENT_MODIFY:    return "MODIFY";
    case XCOG_INTENT_DELETE:    return "DELETE";
    case XCOG_INTENT_NAVIGATE:  return "NAVIGATE";
    case XCOG_INTENT_CONFIGURE: return "CONFIGURE";
    case XCOG_INTENT_ANALYZE:   return "ANALYZE";
    case XCOG_INTENT_CONVERSE:  return "CONVERSE";
    default:                    return "UNKNOWN";
    }
}

/* Entity subtype to string */
static const char *r1_entity_name(uint8_t subtype)
{
    switch (subtype) {
    case XCOG_ENT_FILE:         return "file";
    case XCOG_ENT_DIRECTORY:    return "dir";
    case XCOG_ENT_APP:          return "app";
    case XCOG_ENT_CONTACT:      return "contact";
    case XCOG_ENT_EMAIL:        return "email";
    case XCOG_ENT_EVENT:        return "event";
    case XCOG_ENT_SETTING:      return "setting";
    case XCOG_ENT_DEVICE:       return "device";
    case XCOG_ENT_PROCESS:      return "process";
    case XCOG_ENT_TEXT_FRAGMENT: return "text";
    case XCOG_ENT_NUMBER:       return "num";
    case XCOG_ENT_DATE:         return "date";
    case XCOG_ENT_TIME:         return "time";
    case XCOG_ENT_DURATION:     return "dur";
    case XCOG_ENT_USER_SELF:    return "self";
    case XCOG_ENT_USER_OTHER:   return "other";
    case XCOG_ENT_PASSTHROUGH:  return "raw";
    default:                    return "unk";
    }
}

/* ═══════════════════════════════════════════════════════════════════════
 * PUBLIC API: r1_per_init
 * ═══════════════════════════════════════════════════════════════════════ */

void r1_per_init(void)
{
    /*
     * Phase 1: All data structures are static const.
     * No dynamic allocation needed.
     *
     * This function validates the static tables and sets the
     * initialized flag.  Future phases will load dynamic entity
     * registries from XSTORE here.
     */

    /* Validate entity registry is non-empty */
    if (R1_ENTITY_REGISTRY_COUNT == 0) {
        pal_console_puts("[R1_PER] FATAL: entity registry empty\n");
        return;
    }

    /* Validate POS table is non-empty */
    if (R1_POS_TABLE_COUNT == 0) {
        pal_console_puts("[R1_PER] FATAL: POS table empty\n");
        return;
    }

    /* Validate verb-intent map is non-empty */
    if (R1_VERB_INTENT_COUNT == 0) {
        pal_console_puts("[R1_PER] FATAL: verb-intent map empty\n");
        return;
    }

    /* Validate XCOG instruction size contract */
    _Static_assert(sizeof(xcog_instr_t) == 8,
                   "XCOG instruction must be 8 bytes");

    /* Validate signal structure fits contract */
    _Static_assert(sizeof(r1_per_signal_t) < 1024,
                   "r1_per_signal_t must be < 1024 bytes");

    s_initialized = 1;

    pal_console_puts("[R1_PER] Phase 1 perception pipeline initialized\n");
    pal_console_puts("[R1_PER]   Entity registry: ");
    pal_console_printf("%u entries\n", (uint32_t)R1_ENTITY_REGISTRY_COUNT);
    pal_console_puts("[R1_PER]   POS table: ");
    pal_console_printf("%u entries\n", (uint32_t)R1_POS_TABLE_COUNT);
    pal_console_puts("[R1_PER]   Verb-intent map: ");
    pal_console_printf("%u entries\n", (uint32_t)R1_VERB_INTENT_COUNT);
    pal_console_puts("[R1_PER]   Temporal table: ");
    pal_console_printf("%u entries\n", (uint32_t)R1_TEMPORAL_TABLE_COUNT);
}

/* ═══════════════════════════════════════════════════════════════════════
 * PUBLIC API: r1_per_encode
 * ═══════════════════════════════════════════════════════════════════════ */

int r1_per_encode(const char *nl_input, uint32_t nl_len,
                  r1_per_signal_t *out)
{
    /* ── Validate inputs ──────────────────────────────────────────── */
    if (!nl_input || nl_len == 0 || !out)
        return -1;
    if (!s_initialized)
        return -2;

    /* ── Zero output structure ────────────────────────────────────── */
    r1_memset(out, 0, sizeof(r1_per_signal_t));

    /* ── Set header ───────────────────────────────────────────────── */
    out->magic   = R1_PER_MAGIC;
    out->version = R1_PER_VERSION;
    out->source_channel = R1_SOURCE_KEYBOARD;
    out->timestamp_ns   = pal_time_now_ns();

    /* ── Stage 1: Lexical analysis ────────────────────────────────── */
    r1_word_t words[R1_MAX_WORDS];
    r1_memset(words, 0, sizeof(words));

    uint32_t word_count = r1_lex_tokenize(nl_input, nl_len,
                                           words, R1_MAX_WORDS);
    if (word_count == 0) {
        /* Empty input after tokenization -> CONVERSE fallback */
        out->stage_flags = R1_STAGE_LEXICAL;
        out->fallback_flag = 1;
        out->instruction_count = 1;
        out->instructions[0] = XCOG_INSTR(XCOG_INTENT,
                                           XCOG_INTENT_CONVERSE, 0, 0);
        out->salience_scores[0] = 65535u;
        r1_sha256_input(nl_input, nl_len, out->input_hash);
        r1_sha256_instructions(out->instructions, 1, out->output_hash);
        return 0;
    }

    out->stage_flags |= R1_STAGE_LEXICAL;

    /* ── Stage 2: Semantic analysis ───────────────────────────────── */

    /* 2a: Intent classification */
    r1_intent_result_t intent = r1_classify_intent(words, word_count);

    /* 2b: Entity extraction */
    r1_entity_result_t entities[R1_PER_MAX_INSTRUCTIONS];
    uint32_t ent_count = r1_extract_entities(words, word_count,
                                              entities,
                                              R1_PER_MAX_INSTRUCTIONS / 2);

    /* 2c: Predicate extraction */
    r1_predicate_result_t predicates[16];
    uint32_t pred_count = r1_extract_predicates(words, word_count,
                                                 predicates, 16);

    /* 2d: Temporal extraction */
    r1_temporal_result_t temporals[8];
    uint32_t temp_count = r1_extract_temporal(words, word_count,
                                              temporals, 8);

    /* 2e: Negation detection */
    int has_neg = r1_has_negation(words, word_count);

    /* 2f: Quantifier detection */
    r1_quantifier_result_t quantifier;
    r1_memset(&quantifier, 0, sizeof(quantifier));
    int has_quant = r1_extract_quantifier(words, word_count, &quantifier);

    /* 2g: Filter extraction */
    r1_filter_result_t filt_results[16];
    uint32_t filt_count = r1_extract_filters(words, word_count,
                                              filt_results, 16);

    out->stage_flags |= R1_STAGE_SEMANTIC;

    /* ── Confidence computation ───────────────────────────────────── */
    /*
     * Confidence = (matched_entities / total_nouns) * (intent_match / 255)
     *
     * Both factors are in [0..255] range.  Combined as:
     *   combined = (entity_ratio_255 * intent_confidence) / 255
     *
     * Special case: if there are no nouns, entity_ratio = 255 (vacuously true)
     */
    uint32_t total_nouns = r1_count_nouns(words, word_count);
    uint32_t entity_ratio_255;
    if (total_nouns == 0) {
        entity_ratio_255 = R1_CONF_FULL;
    } else {
        entity_ratio_255 = (ent_count * 255u) / total_nouns;
        if (entity_ratio_255 > 255u) entity_ratio_255 = 255u;
    }

    uint32_t combined_confidence = (entity_ratio_255 * (uint32_t)intent.confidence) / 255u;
    if (combined_confidence > 255u) combined_confidence = 255u;

    /* ── Fallback check ───────────────────────────────────────────── */
    if (combined_confidence < R1_FALLBACK_THRESHOLD) {
        out->fallback_flag = 1;
        out->instruction_count = 1;
        out->instructions[0] = XCOG_INSTR(XCOG_INTENT,
                                           XCOG_INTENT_CONVERSE, 0,
                                           combined_confidence);
        out->salience_scores[0] = 65535u;
        out->stage_flags |= R1_STAGE_COMPILED;
        r1_sha256_input(nl_input, nl_len, out->input_hash);
        r1_sha256_instructions(out->instructions, 1, out->output_hash);
        return 0;
    }

    /* Update intent confidence with combined value */
    intent.confidence = (uint8_t)combined_confidence;

    /* ── Stage 3: XCOG compilation ────────────────────────────────── */
    uint16_t ic = r1_compile_xcog(
        &intent,
        entities,    ent_count,
        predicates,  pred_count,
        words,       word_count,
        has_neg,
        &quantifier, has_quant,
        filt_results, filt_count,
        temporals,   temp_count,
        out->instructions,
        out->salience_scores,
        R1_PER_MAX_INSTRUCTIONS
    );

    out->instruction_count = ic;
    out->stage_flags |= R1_STAGE_COMPILED;

    /* ── Dual SHA-256 hashing ─────────────────────────────────────── */
    r1_sha256_input(nl_input, nl_len, out->input_hash);
    r1_sha256_instructions(out->instructions, ic, out->output_hash);

    /* ── Context shards (Phase 1: none) ───────────────────────────── */
    out->context_shard_count = 0;
    out->context_total_size  = 0;

    return 0;
}

/* ═══════════════════════════════════════════════════════════════════════
 * PUBLIC API: r1_per_translate_to_tokens
 * ═══════════════════════════════════════════════════════════════════════ */

int r1_per_translate_to_tokens(const r1_per_signal_t *signal,
                                const void *model_config,
                                uint32_t *token_ids, uint32_t max_tokens,
                                uint32_t *out_count)
{
    if (!signal || !token_ids || !out_count || max_tokens == 0)
        return -1;

    *out_count = 0;

    /* Validate magic */
    if (signal->magic != R1_PER_MAGIC)
        return -3;

    /*
     * Build a structured text representation of the XCOG instructions.
     * Each instruction maps to a bracket-delimited tag:
     *   XCOG_INTENT(QUERY)    -> "[QUERY]"
     *   XCOG_ENTITY(FILE)     -> "[ENT:file]"
     *   XCOG_PREDICATE        -> "[PRED:XXXX]"
     *   XCOG_FILTER           -> "[FILT:XXXX]"
     *   XCOG_TEMPORAL         -> "[TIME:XXXX]"
     *   XCOG_NEGATE           -> "[NOT]"
     *   XCOG_QUANTIFY         -> "[QUANT:X]"
     *   XCOG_EMIT             -> "[EMIT]"
     *
     * The structured text is then fed to xmind_tokenize() if the
     * BPE tokenizer is loaded, otherwise byte-level tokenization.
     */

    /* If fallback, pass original NL through directly.
     * Since we don't have the original NL text in the signal struct,
     * the caller must have set fallback_flag=1.  In that case we emit
     * a structured fallback prompt. */
    if (signal->fallback_flag) {
        /* Emit structured prefix: "[CONVERSE] " then let model handle it.
         * The caller should prepend the original NL text separately. */
        const char *fallback_text = "[CONVERSE] ";
        uint32_t tok_count = 0;
        xmind_status_t rc = xmind_tokenize(fallback_text, token_ids,
                                            &tok_count, max_tokens);
        if (rc == 0) {
            *out_count = tok_count;
            return 0;
        }
        /* If tokenizer not loaded, emit byte-level */
        uint32_t fb_len = (uint32_t)r1_strlen(fallback_text);
        uint32_t n = (fb_len < max_tokens) ? fb_len : max_tokens;
        for (uint32_t i = 0; i < n; i++)
            token_ids[i] = (uint32_t)(uint8_t)fallback_text[i];
        *out_count = n;
        return 0;
    }

    /* Build structured text buffer (stack-allocated, bounded) */
    char text_buf[2048];
    uint32_t off = 0;
    const uint32_t text_max = sizeof(text_buf) - 1;

    for (uint16_t i = 0; i < signal->instruction_count; i++) {
        const xcog_instr_t *instr = &signal->instructions[i];

        if (i > 0) {
            off = r1_buf_append(text_buf, off, text_max, " ");
        }

        switch (instr->opcode) {
        case XCOG_INTENT:
            off = r1_buf_append(text_buf, off, text_max, "[");
            off = r1_buf_append(text_buf, off, text_max,
                                r1_intent_name(instr->subtype));
            off = r1_buf_append(text_buf, off, text_max, "]");
            break;

        case XCOG_ENTITY:
            off = r1_buf_append(text_buf, off, text_max, "[ENT:");
            off = r1_buf_append(text_buf, off, text_max,
                                r1_entity_name(instr->subtype));
            off = r1_buf_append(text_buf, off, text_max, "]");
            break;

        case XCOG_PREDICATE:
            off = r1_buf_append(text_buf, off, text_max, "[PRED:");
            off = r1_buf_append_u32(text_buf, off, text_max, instr->payload);
            off = r1_buf_append(text_buf, off, text_max, "]");
            break;

        case XCOG_FILTER:
            off = r1_buf_append(text_buf, off, text_max, "[FILT:");
            off = r1_buf_append_u32(text_buf, off, text_max, instr->payload);
            off = r1_buf_append(text_buf, off, text_max, "]");
            break;

        case XCOG_TEMPORAL:
            off = r1_buf_append(text_buf, off, text_max, "[TIME:");
            off = r1_buf_append_u32(text_buf, off, text_max, instr->payload);
            off = r1_buf_append(text_buf, off, text_max, "]");
            break;

        case XCOG_NEGATE:
            off = r1_buf_append(text_buf, off, text_max, "[NOT]");
            break;

        case XCOG_QUANTIFY: {
            const char *qnames[] = { "ALL", "SOME", "NONE", "SPEC" };
            uint8_t qi = instr->subtype;
            if (qi > 3) qi = 3;
            off = r1_buf_append(text_buf, off, text_max, "[QUANT:");
            off = r1_buf_append(text_buf, off, text_max, qnames[qi]);
            off = r1_buf_append(text_buf, off, text_max, "]");
            break;
        }

        case XCOG_EMIT:
            off = r1_buf_append(text_buf, off, text_max, "[EMIT]");
            break;

        case XCOG_SALIENCE:
            off = r1_buf_append(text_buf, off, text_max, "[SAL:");
            off = r1_buf_append_u32(text_buf, off, text_max, instr->payload);
            off = r1_buf_append(text_buf, off, text_max, "]");
            break;

        case XCOG_CONTEXT:
            off = r1_buf_append(text_buf, off, text_max, "[CTX]");
            break;

        case XCOG_REFERENCE:
            off = r1_buf_append(text_buf, off, text_max, "[REF]");
            break;

        case XCOG_SEQUENCE:
            off = r1_buf_append(text_buf, off, text_max, "[SEQ]");
            break;

        case XCOG_COMPOUND:
            off = r1_buf_append(text_buf, off, text_max, "[COMP]");
            break;

        case XCOG_MODALITY:
            off = r1_buf_append(text_buf, off, text_max, "[MOD]");
            break;

        default:
            /* Routing or unknown opcode -> generic tag */
            if (XCOG_IS_ROUTING(instr->opcode)) {
                off = r1_buf_append(text_buf, off, text_max, "[RT:");
                off = r1_buf_append_u32(text_buf, off, text_max,
                                        (uint32_t)instr->opcode);
                off = r1_buf_append(text_buf, off, text_max, "]");
            } else {
                off = r1_buf_append(text_buf, off, text_max, "[OPC:");
                off = r1_buf_append_u32(text_buf, off, text_max,
                                        (uint32_t)instr->opcode);
                off = r1_buf_append(text_buf, off, text_max, "]");
            }
            break;
        }
    }

    text_buf[off] = '\0';

    /* Tokenize the structured text via XMIND BPE tokenizer */
    uint32_t tok_count = 0;
    xmind_status_t rc = xmind_tokenize(text_buf, token_ids,
                                        &tok_count, max_tokens);
    if (rc == 0) {
        *out_count = tok_count;
        return 0;
    }

    /*
     * Fallback: byte-level tokenization.
     * Each byte of the structured text becomes one token ID.
     * This works with any model vocabulary since byte tokens (0-255)
     * are present in all modern BPE vocabularies.
     */
    uint32_t n = (off < max_tokens) ? off : max_tokens;
    for (uint32_t i = 0; i < n; i++)
        token_ids[i] = (uint32_t)(uint8_t)text_buf[i];
    *out_count = n;

    (void)model_config;  /* Phase 1: model-agnostic, config unused */

    return 0;
}

/* ═══════════════════════════════════════════════════════════════════════
 * PUBLIC API: r1_per_verify
 * ═══════════════════════════════════════════════════════════════════════ */

int r1_per_verify(const r1_per_signal_t *signal)
{
    if (!signal)
        return -1;

    /* Validate magic */
    if (signal->magic != R1_PER_MAGIC)
        return -1;

    /* Validate version */
    if (signal->version != R1_PER_VERSION)
        return -1;

    /* Validate instruction count */
    if (signal->instruction_count > R1_PER_MAX_INSTRUCTIONS)
        return -1;

    /* Recompute SHA-256 of instruction stream */
    uint8_t recomputed[32];
    r1_sha256_instructions(signal->instructions,
                            signal->instruction_count,
                            recomputed);

    /* Constant-time comparison to prevent timing side-channels */
    uint8_t diff = 0;
    for (uint32_t i = 0; i < 32; i++) {
        diff |= recomputed[i] ^ signal->output_hash[i];
    }

    if (diff != 0)
        return -1;  /* Tampered */

    return 0;  /* Valid */
}
