/*
 * lora.c — LoRA adapter loader + delta application.
 *
 * SAFETENSORS FORMAT (the open-standard adapter container):
 *
 *   [8 bytes]   header_size (uint64 little-endian)
 *   [N bytes]   header — JSON object describing each tensor:
 *                 { "tensor_name": {
 *                     "dtype":  "F32",
 *                     "shape":  [d0, d1, ...],
 *                     "data_offsets": [start, end]
 *                   },
 *                   ... }
 *   [...]       raw tensor data, packed per offsets
 *
 * The parser here is minimal — it scans the JSON header looking for the
 * specific keys we need (dtype, shape, data_offsets) and the LoRA naming
 * convention "<base_tensor>.lora_A" / "<base_tensor>.lora_B".
 *
 * The same file format is what HuggingFace `safetensors`, `peft`, `mlx`,
 * and Apple's MLX-LM all read/write. There is NO MLX runtime dependency
 * in this loader — pure libc parsing.
 *
 * EXTENSION POINT — Omni PEFT composition:
 *   The xmind_lora_t structure currently holds one entry per target tensor.
 *   For composed/routed delta systems (your Omni PEFT hypothesis), extend
 *   the entry to hold a list of operators with a router function pointer.
 *   The apply_delta function dispatches on kind and can sum / route across
 *   multiple operators per tensor. This file is the scaffold; the Omni
 *   composition layer is left as a follow-up.
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif

#include "lora.h"
#include "pal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

/* ═══════════════════════════════════════════════════════════════════
 * §1  MINIMAL JSON PARSER (tailored to safetensors header structure)
 * ═══════════════════════════════════════════════════════════════════ */

/* Find next '"key":' occurrence within [p, end), returns ptr after the colon
 * (positioned at the value). Returns NULL if not found. */
static const char *find_key(const char *p, const char *end, const char *key) {
    size_t klen = strlen(key);
    while (p < end - klen - 3) {
        if (*p == '"' && (size_t)(end - p) > klen + 2 &&
            memcmp(p + 1, key, klen) == 0 && p[1 + klen] == '"') {
            const char *q = p + klen + 2;
            while (q < end && (*q == ' ' || *q == '\t')) q++;
            if (q < end && *q == ':') return q + 1;
        }
        p++;
    }
    return NULL;
}

/* Parse a quoted JSON string starting at p (must point to opening quote).
 * Writes the unescaped value into buf (max len-1 chars). Returns ptr after
 * closing quote, or NULL on parse error. */
static const char *parse_str(const char *p, const char *end,
                              char *buf, size_t buflen) {
    if (p >= end || *p != '"') return NULL;
    p++;
    size_t i = 0;
    while (p < end && *p != '"') {
        if (*p == '\\' && p + 1 < end) {
            p++;
            if (i < buflen - 1) buf[i++] = *p;
            p++;
        } else {
            if (i < buflen - 1) buf[i++] = *p;
            p++;
        }
    }
    buf[i] = '\0';
    return (p < end) ? p + 1 : NULL;
}

/* Skip whitespace */
static const char *skip_ws(const char *p, const char *end) {
    while (p < end && (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r' || *p == ',')) p++;
    return p;
}

/* Parse a JSON array of uint64 — returns count parsed, fills out[] up to max */
static int parse_uint64_array(const char *p, const char *end,
                                uint64_t *out, int max) {
    p = skip_ws(p, end);
    if (p >= end || *p != '[') return -1;
    p++;
    int n = 0;
    while (p < end && *p != ']' && n < max) {
        p = skip_ws(p, end);
        if (p >= end || *p == ']') break;
        char *endp;
        uint64_t v = strtoull(p, &endp, 10);
        if (endp == p) return n;
        out[n++] = v;
        p = endp;
        p = skip_ws(p, end);
    }
    return n;
}

/* ═══════════════════════════════════════════════════════════════════
 * §2  Iterate entries in safetensors header
 *
 * Format invariant: top-level is an object whose keys are tensor names.
 * We scan for top-level keys (string at depth 0) that are NOT "__metadata__".
 * ═══════════════════════════════════════════════════════════════════ */

typedef struct {
    char     name[XMIND_LORA_MAX_NAMELEN];
    char     dtype[16];
    uint64_t shape[8];
    int      n_dims;
    uint64_t off_start;
    uint64_t off_end;
} st_entry_t;

/* Returns next entry start (advances past current entry). */
static const char *parse_one_entry(const char *p, const char *end, st_entry_t *out) {
    p = skip_ws(p, end);
    if (p >= end || *p != '"') return NULL;

    /* Tensor name */
    const char *q = parse_str(p, end, out->name, sizeof(out->name));
    if (!q) return NULL;
    p = skip_ws(q, end);
    if (p >= end || *p != ':') return NULL;
    p++;
    p = skip_ws(p, end);
    if (p >= end || *p != '{') return NULL;
    p++;

    /* Find object end (matching brace) */
    int depth = 1;
    const char *obj_start = p;
    while (p < end && depth > 0) {
        if (*p == '{') depth++;
        else if (*p == '}') depth--;
        if (depth > 0) p++;
    }
    if (p >= end) return NULL;
    const char *obj_end = p;

    /* dtype */
    const char *v = find_key(obj_start, obj_end, "dtype");
    out->dtype[0] = '\0';
    if (v) {
        v = skip_ws(v, obj_end);
        parse_str(v, obj_end, out->dtype, sizeof(out->dtype));
    }

    /* shape */
    out->n_dims = 0;
    v = find_key(obj_start, obj_end, "shape");
    if (v) {
        int n = parse_uint64_array(v, obj_end, out->shape, 8);
        out->n_dims = (n >= 0) ? n : 0;
    }

    /* data_offsets */
    uint64_t offs[2] = {0, 0};
    v = find_key(obj_start, obj_end, "data_offsets");
    if (v) {
        parse_uint64_array(v, obj_end, offs, 2);
    }
    out->off_start = offs[0];
    out->off_end   = offs[1];

    return p + 1;  /* past closing brace */
}

/* ═══════════════════════════════════════════════════════════════════
 * §3  Load adapter
 * ═══════════════════════════════════════════════════════════════════ */

/* D09 fix — canonicalize the LoRA base-module path to the GGUF tensor name the
 * runtime hot path looks up.  The transformer calls
 *   xmind_adapter_runtime_apply(layer, "<role>", ...)
 * which builds the lookup key "blk.<layer>.<role>.weight" (adapter_runtime.c).
 * For an applied delta to be found, get_or_create_entry() MUST store under that
 * SAME canonical key.  The training stack exports adapters under different
 * conventions (blocks.N.attn.q / layers.N.attn.wq / PEFT self_attn.q_proj), so
 * without canonicalization the lookup was always NULL and the adapter was a
 * silent no-op.
 *
 * Canonical role names (must match transformer.c's role strings exactly):
 *   attn_q  attn_k  attn_v  attn_output   (note: o -> attn_output, not attn_o)
 *   ffn_gate  ffn_up  ffn_down
 *
 * The map mirrors training/pt/model.py and training/scripts/convert_to_gguf.py:
 *   blocks|layers . N . attn.{q,k,v,o}        -> blk.N.attn_{q,k,v,output}.weight
 *   blocks|layers . N . mlp.{gate,up,down}    -> blk.N.ffn_{gate,up,down}.weight
 *   blocks|layers . N . attn.{wq,wk,wv,wo}    -> blk.N.attn_{q,k,v,output}.weight
 *   blocks|layers . N . self_attn.{q,k,v,o}_proj -> blk.N.attn_{q,k,v,output}.weight
 *   blocks|layers . N . mlp.{gate,up,down}_proj  -> blk.N.ffn_{gate,up,down}.weight
 */

/* Return the canonical role for a module suffix, or NULL if unrecognized. */
static const char *lora_canonical_role(const char *mod) {
    /* attention projections */
    if (strcmp(mod, "attn.q") == 0 || strcmp(mod, "attn.wq") == 0 ||
        strcmp(mod, "self_attn.q_proj") == 0 || strcmp(mod, "q_proj") == 0) return "attn_q";
    if (strcmp(mod, "attn.k") == 0 || strcmp(mod, "attn.wk") == 0 ||
        strcmp(mod, "self_attn.k_proj") == 0 || strcmp(mod, "k_proj") == 0) return "attn_k";
    if (strcmp(mod, "attn.v") == 0 || strcmp(mod, "attn.wv") == 0 ||
        strcmp(mod, "self_attn.v_proj") == 0 || strcmp(mod, "v_proj") == 0) return "attn_v";
    if (strcmp(mod, "attn.o") == 0 || strcmp(mod, "attn.wo") == 0 ||
        strcmp(mod, "self_attn.o_proj") == 0 || strcmp(mod, "o_proj") == 0) return "attn_output";
    /* FFN / MLP projections */
    if (strcmp(mod, "mlp.gate") == 0 || strcmp(mod, "mlp.gate_proj") == 0 ||
        strcmp(mod, "ffn.gate") == 0) return "ffn_gate";
    if (strcmp(mod, "mlp.up") == 0 || strcmp(mod, "mlp.up_proj") == 0 ||
        strcmp(mod, "ffn.up") == 0) return "ffn_up";
    if (strcmp(mod, "mlp.down") == 0 || strcmp(mod, "mlp.down_proj") == 0 ||
        strcmp(mod, "ffn.down") == 0) return "ffn_down";
    return (const char *)0;
}

/* Try to canonicalize a stripped base path (e.g. "blocks.0.attn.q",
 * "base_model.model.layers.3.self_attn.v_proj") into the runtime lookup key
 * "blk.<N>.<role>.weight".  Returns 0 and fills target_out on success; returns
 * -1 if the path does not match a known layer/module pattern (caller falls back
 * to storing the stripped path verbatim, so already-canonical adapters whose
 * base IS "blk.N.<role>.weight" still join correctly). */
static int lora_canonicalize_target(const char *base, char *target_out, size_t target_max) {
    /* Find the layer-index marker: "blocks." or "layers." followed by digits. */
    const char *marker = strstr(base, "blocks.");
    const char *after  = (const char *)0;
    if (marker) {
        after = marker + 7; /* strlen("blocks.") */
    } else {
        marker = strstr(base, "layers.");
        if (marker) after = marker + 7; /* strlen("layers.") */
    }
    if (!after || *after < '0' || *after > '9') return -1;

    /* Parse the layer index. */
    unsigned layer = 0u;
    const char *q = after;
    while (*q >= '0' && *q <= '9') { layer = layer * 10u + (unsigned)(*q - '0'); q++; }
    if (*q != '.') return -1;
    q++; /* skip the dot after the index -> q now points at the module path */

    const char *role = lora_canonical_role(q);
    if (!role) return -1;

    int n = snprintf(target_out, target_max, "blk.%u.%s.weight", layer, role);
    if (n < 0 || (size_t)n >= target_max) return -1;
    return 0;
}

/* LoRA naming conventions we accept (side suffixes):
 *   <base>.lora_A    / <base>.lora_B          (HF/PEFT short)
 *   <base>.lora_A.weight / <base>.lora_B.weight  (PEFT style)
 *   <base>.A.weight  / <base>.B.weight         (MLX low_rank export — the
 *                                               convention the repo's proof
 *                                               adapter actually uses)
 *
 * After stripping the side suffix, <base> is canonicalized to the GGUF runtime
 * key "blk.<N>.<role>.weight" (D09).  If <base> does not match a known module
 * pattern it is stored verbatim — this preserves already-canonical adapters and
 * keeps the path a clean no-op for unknown tensors. */
static int parse_lora_name(const char *name, char *target_out, size_t target_max, char *side_out) {
    const char *p = (const char *)0;

    /* Locate the side marker.  ".lora_A"/".lora_B" take precedence; otherwise
     * accept the ".A.weight"/".B.weight" MLX export form. */
    if ((p = strstr(name, ".lora_A")) != (const char *)0) {
        *side_out = 'A';
    } else if ((p = strstr(name, ".lora_B")) != (const char *)0) {
        *side_out = 'B';
    } else if ((p = strstr(name, ".A.weight")) != (const char *)0) {
        *side_out = 'A';
    } else if ((p = strstr(name, ".B.weight")) != (const char *)0) {
        *side_out = 'B';
    } else {
        return -1;
    }

    /* base = everything before the side marker. */
    size_t base_len = (size_t)(p - name);
    char base[XMIND_LORA_MAX_NAMELEN];
    if (base_len >= sizeof(base)) base_len = sizeof(base) - 1u;
    memcpy(base, name, base_len);
    base[base_len] = '\0';

    /* Canonicalize to the runtime lookup key; fall back to verbatim base. */
    if (lora_canonicalize_target(base, target_out, target_max) != 0) {
        size_t n = base_len;
        if (n >= target_max) n = target_max - 1u;
        memcpy(target_out, base, n);
        target_out[n] = '\0';
    }
    return 0;
}

/* Find or create an entry for a target tensor. Returns NULL if full. */
static xmind_lora_entry_t *get_or_create_entry(xmind_lora_t *lora, const char *target) {
    for (uint32_t i = 0; i < lora->n_entries; i++) {
        if (strcmp(lora->entries[i].name, target) == 0) return &lora->entries[i];
    }
    if (lora->n_entries >= XMIND_LORA_MAX_TENSORS) return NULL;
    xmind_lora_entry_t *e = &lora->entries[lora->n_entries++];
    memset(e, 0, sizeof(*e));
    strncpy(e->name, target, XMIND_LORA_MAX_NAMELEN - 1);
    e->name[XMIND_LORA_MAX_NAMELEN - 1] = '\0';
    e->kind  = XMIND_LORA_OP_LORA;
    e->alpha = 16.0f;  /* sensible default; override via __metadata__ if present */
    return e;
}

int xmind_lora_load_safetensors(const char *path, xmind_lora_t *out) {
    if (!path || !out) return -1;
    memset(out, 0, sizeof(*out));

    int fd = open(path, O_RDONLY);
    if (fd < 0) return -2;

    struct stat st;
    if (fstat(fd, &st) != 0) { close(fd); return -3; }
    if (st.st_size < 8) { close(fd); return -4; }

    void *map = mmap(NULL, (size_t)st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
    close(fd);
    if (map == MAP_FAILED) return -5;

    /* Parse header length */
    uint64_t header_size = 0;
    memcpy(&header_size, map, 8);
    if (header_size > (uint64_t)st.st_size - 8) {
        munmap(map, (size_t)st.st_size);
        return -6;
    }

    const char *header_start = (const char *)map + 8;
    const char *header_end   = header_start + header_size;
    const char *payload      = header_end;

    /* Walk entries */
    const char *p = header_start;
    p = skip_ws(p, header_end);
    if (p < header_end && *p == '{') p++;

    /* Read alpha from __metadata__ if present */
    const char *meta = find_key(header_start, header_end, "__metadata__");
    float metadata_alpha = 16.0f;
    if (meta) {
        const char *av = find_key(meta, header_end, "lora_alpha");
        if (av) {
            av = skip_ws(av, header_end);
            char buf[32];
            if (av < header_end && *av == '"') {
                parse_str(av, header_end, buf, sizeof(buf));
            } else {
                size_t i = 0;
                while (av < header_end && (*av == '-' || *av == '.' || (*av >= '0' && *av <= '9')) && i < sizeof(buf)-1)
                    buf[i++] = *av++;
                buf[i] = '\0';
            }
            metadata_alpha = (float)strtod(buf, NULL);
            if (metadata_alpha == 0) metadata_alpha = 16.0f;
        }
        /* §9.2: read the base-model sha the adapter was trained on, if declared. gov_admit refuses
         * an adapter whose base_sha256 mismatches the running model (no adapter against a mismatched
         * base). Absent ("") = unverifiable = admitted (the substrate's own unsigned adapters). */
        const char *bv = find_key(meta, header_end, "base_sha256");
        if (bv) {
            bv = skip_ws(bv, header_end);
            if (bv < header_end && *bv == '"')
                parse_str(bv, header_end, out->base_sha256, sizeof(out->base_sha256));
        }
        /* §9.2 authority-scope: read the comma/space-separated list of permitted tensor-name
         * prefixes the adapter declares it is authorized to touch. gov_admit refuses any entry
         * targeting a tensor OUTSIDE this declared scope. Absent ("") = unverifiable = admitted
         * (backward-compatible with the substrate's own unscoped adapters). */
        const char *sv = find_key(meta, header_end, "scope");
        if (sv) {
            sv = skip_ws(sv, header_end);
            if (sv < header_end && *sv == '"')
                parse_str(sv, header_end, out->scope, sizeof(out->scope));
        }
    }

    while (p < header_end) {
        p = skip_ws(p, header_end);
        if (p >= header_end || *p == '}') break;

        st_entry_t st_entry;
        const char *next = parse_one_entry(p, header_end, &st_entry);
        if (!next || next <= p) break;
        p = next;

        /* Skip __metadata__ pseudo-entry */
        if (strcmp(st_entry.name, "__metadata__") == 0) continue;
        /* Skip non-LoRA tensors */
        char target[XMIND_LORA_MAX_NAMELEN];
        char side;
        if (parse_lora_name(st_entry.name, target, sizeof(target), &side) != 0) continue;
        /* Skip non-fp32 (for scaffold; extend with bf16/fp16 later) */
        if (strcmp(st_entry.dtype, "F32") != 0) continue;
        if (st_entry.n_dims != 2) continue;

        xmind_lora_entry_t *e = get_or_create_entry(out, target);
        if (!e) break;
        e->alpha = metadata_alpha;
        const float *data = (const float *)(payload + st_entry.off_start);
        if (side == 'A') {
            e->rank = (uint32_t)st_entry.shape[0];
            e->d_in = (uint32_t)st_entry.shape[1];
            e->A = data;
        } else {
            e->d_out = (uint32_t)st_entry.shape[0];
            /* shape[1] is rank — confirm */
            if (e->rank == 0) e->rank = (uint32_t)st_entry.shape[1];
            e->B = data;
        }
    }

    /* Validate: each entry must have both A and B. Drop incomplete ones. */
    uint32_t valid = 0;
    for (uint32_t i = 0; i < out->n_entries; i++) {
        if (out->entries[i].A && out->entries[i].B &&
            out->entries[i].rank > 0 && out->entries[i].d_in > 0 && out->entries[i].d_out > 0) {
            if (valid != i) out->entries[valid] = out->entries[i];
            valid++;
        }
    }
    out->n_entries = valid;

    out->raw_data = map;
    out->raw_size = (uint64_t)st.st_size;

    pal_console_printf("[lora] loaded %s — %u tensors, alpha=%.1f\n",
                       path, out->n_entries, (double)metadata_alpha);
    return 0;
}

const xmind_lora_entry_t *xmind_lora_find(const xmind_lora_t *lora, const char *name) {
    if (!lora || !name) return NULL;
    for (uint32_t i = 0; i < lora->n_entries; i++) {
        if (strcmp(lora->entries[i].name, name) == 0) return &lora->entries[i];
    }
    return NULL;
}

/* ═══════════════════════════════════════════════════════════════════
 * §4  Apply delta (scalar implementation)
 *
 *   out[i] += (alpha/r) * sum_k (B[i,k] * sum_j (A[k,j] * x[j]))
 *
 *   Step 1: tmp[k] = sum_j A[k,j] * x[j]    (k=0..r-1)
 *   Step 2: out[i] += scale * sum_k B[i,k] * tmp[k]
 * ═══════════════════════════════════════════════════════════════════ */

int xmind_lora_apply_delta(const xmind_lora_entry_t *e,
                            const float *x,
                            float *out) {
    if (!e || !x || !out) return -1;
    if (e->kind != XMIND_LORA_OP_LORA) {
        /* DoRA / IA3 / OMNI not yet implemented in this scaffold */
        return -2;
    }
    if (!e->A || !e->B || e->rank == 0) return -3;

    const uint32_t r     = e->rank;
    const uint32_t d_in  = e->d_in;
    const uint32_t d_out = e->d_out;
    const float    scale = e->alpha / (float)r;

    /* Stack-alloc tmp[r] if r is small; heap fallback for safety. */
    float  tmp_stack[64];
    float *tmp = (r <= 64) ? tmp_stack : (float *)malloc(r * sizeof(float));
    if (!tmp) return -4;

    /* Step 1: tmp = A * x  (r × d_in matmul) */
    for (uint32_t k = 0; k < r; k++) {
        float acc = 0.0f;
        const float *row = e->A + (size_t)k * d_in;
        for (uint32_t j = 0; j < d_in; j++) acc += row[j] * x[j];
        tmp[k] = acc;
    }

    /* Step 2: out += scale * B * tmp  (d_out × r matmul) */
    for (uint32_t i = 0; i < d_out; i++) {
        float acc = 0.0f;
        const float *row = e->B + (size_t)i * r;
        for (uint32_t k = 0; k < r; k++) acc += row[k] * tmp[k];
        out[i] += scale * acc;
    }

    if (tmp != tmp_stack) free(tmp);
    return 0;
}

void xmind_lora_free(xmind_lora_t *lora) {
    if (!lora) return;
    if (lora->raw_data && lora->raw_size > 0) {
        munmap(lora->raw_data, (size_t)lora->raw_size);
    }
    memset(lora, 0, sizeof(*lora));
}

void xmind_lora_dump(const xmind_lora_t *lora) {
    if (!lora) { pal_console_puts("[lora] (null)\n"); return; }
    pal_console_printf("[lora] %u entries:\n", lora->n_entries);
    for (uint32_t i = 0; i < lora->n_entries; i++) {
        const xmind_lora_entry_t *e = &lora->entries[i];
        pal_console_printf("  %-50s  rank=%u  d_in=%u  d_out=%u  alpha=%.1f\n",
                           e->name, e->rank, e->d_in, e->d_out, (double)e->alpha);
    }
}
