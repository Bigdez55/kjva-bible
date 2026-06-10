/* adapter_runtime.c — XMIND-native adapter runtime dispatch (§11.1 Add).
 *
 * Holds the active adapter (borrowed pointer) and applies its delta at the
 * transformer hot path. NO-OP when no adapter is active → a model without an
 * adapter is byte-identical to the pre-adapter engine (acceptance-safe).
 */
#include "xmind_adapter_runtime.h"
#include "xmind_adapter_telemetry.h"

#include <stdio.h>
#include <string.h>

static const xmind_lora_t *s_active = (const xmind_lora_t *)0;
static char     s_id[64] = {0};
static uint64_t s_apply  = 0u;
static char     s_expected_base[80] = {0};  /* §9.2: the running model's base sha (set by the host) */

void xmind_adapter_runtime_set_expected_base(const char *sha256) {
    if (!sha256) { s_expected_base[0] = '\0'; return; }
    strncpy(s_expected_base, sha256, sizeof(s_expected_base) - 1);
    s_expected_base[sizeof(s_expected_base) - 1] = '\0';
}

void xmind_adapter_runtime_init(void) {
    s_active = (const xmind_lora_t *)0;
    s_id[0] = '\0';
    s_apply = 0u;
    xmind_adapter_telemetry_reset();
}

/* D36 — Adapter admission governance.
 *
 * Before an adapter is allowed to apply at the transformer hot path, it must
 * pass admission. Admission is a ONE-TIME decision made here (at activation),
 * NOT per-token in xmind_adapter_runtime_apply() — keeping the parity-sensitive
 * forward path byte-identical. On refusal we leave s_active untouched (so the
 * existing apply() null-guard yields a clean no-op) and record a telemetry line.
 *
 * Three governance intents the genome (training/peft/v2/adapter_genome_v2.py)
 * defines, mapped to the fields that ACTUALLY exist on the loaded runtime
 * struct (xmind_lora_t in lora.h):
 *
 *   (1) base-model-hash match  — genome: `base_checkpoint` + `content_hash`.
 *       NOT present on xmind_lora_t today. See TODO below; the honest runtime
 *       proxy we CAN enforce is structural payload integrity (mmap'd raw_data
 *       and entry tensors are well-formed and non-degenerate).
 *   (2) authority scope        — genome: `scope`. NOW surfaced onto xmind_lora_t.scope
 *       from the adapter __metadata__ (parse in lora.c). Enforced REALLY: every entry
 *       must fall inside the declared scope (gov_scope_admit), plus the engine-capacity
 *       bound (n_entries in (0, XMIND_LORA_MAX_TENSORS]). Absent scope = admitted.
 *   (3) conflict threshold     — genome: `parents` overlap / `signature`. NOT
 *       present on xmind_lora_t. See TODO; the runtime conflict we CAN reject is
 *       a self-inconsistent adapter (zero-rank / zero-dim / null A|B operators).
 *
 * Any refusal is a CLEAN no-op: the prior active adapter (if any) is unchanged.
 */
static void gov_refuse(const char *id, const char *reason) {
    /* Telemetry line records the refusal. Use the adapter-contribution
     * telemetry channel (no raw user content, just the decision + label). */
    char line[160];
    (void)snprintf(line, sizeof(line),
                   "adapter_refused id=%s reason=%s",
                   (id != (const char *)0) ? id : "(none)", reason);
    xmind_adapter_telemetry_record(line);
    /* Also surface to the console diagnostics path used by the easy layer. */
    (void)fprintf(stderr, "[xmind_adapter_gov] REFUSE %s\n", line);
}

/* §9.2 authority-scope check.
 *
 * The adapter MAY declare `scope` in its __metadata__ (surfaced onto xmind_lora_t.scope
 * by lora.c): a comma/space-separated list of permitted tensor-name prefixes/roles it is
 * authorized to touch (e.g. "blk.0.attn_q, blk.0.attn_v" or "attn_q,attn_v"). Every adapter
 * entry's canonical target name (blk.N.<role>.weight) must be covered by at least one token.
 * A token matches when it appears in the name at a '.'-delimited COMPONENT boundary — so a
 * layer-prefix token ("blk.0", "blk.0.attn_q") and a bare-role token ("attn_q", matching the
 * "...attn_q.weight" component) both admit, while "blk.1" does NOT false-admit
 * "blk.10.attn_q.weight". If ANY entry falls outside the declared scope, the adapter is
 * out-of-declared-scope and refused. Absent scope ("") = unverifiable = admitted.
 *
 * Returns 1 if in-scope (or no scope declared), 0 (caller refuses) if out of scope. */
static int gov_scope_admit(const xmind_lora_t *adapter) {
    if (adapter->scope[0] == '\0') {
        return 1;  /* no declared scope: unverifiable -> admitted (backward-compatible) */
    }
    for (uint32_t i = 0u; i < adapter->n_entries; i++) {
        const char *name = adapter->entries[i].name;
        int covered = 0;
        /* Walk the scope list, splitting on ',', ' ', '\t'. We copy each token into a
         * local buffer so we never mutate the const adapter struct (no strtok). */
        const char *p = adapter->scope;
        while (*p) {
            while (*p == ',' || *p == ' ' || *p == '\t') p++;  /* skip separators */
            if (*p == '\0') break;
            char tok[128];
            size_t t = 0u;
            while (*p && *p != ',' && *p != ' ' && *p != '\t' && t < sizeof(tok) - 1u) {
                tok[t++] = *p++;
            }
            tok[t] = '\0';
            /* advance past any trailing token chars that overflowed the buffer */
            while (*p && *p != ',' && *p != ' ' && *p != '\t') p++;
            if (t == 0u) continue;
            /* Match the token against the canonical name at a '.'-component boundary.
             * A token matches if it appears in `name` followed by '.' or end-of-string,
             * AND is preceded by start-of-string or '.'. This admits a layer-prefix token
             * ("blk.0", "blk.0.attn_q") and a bare-role token ("attn_q", which matches the
             * "...attn_q.weight" component), while NOT false-admitting "blk.1" against
             * "blk.10.attn_q.weight" (the char after the prefix is '0', not '.'). */
            for (const char *m = name; (m = strstr(m, tok)) != (const char *)0; m++) {
                char before = (m == name) ? '.' : m[-1];
                char after  = m[t];
                if ((before == '.' ) && (after == '.' || after == '\0')) {
                    covered = 1;
                    break;
                }
            }
            if (covered) break;
        }
        if (!covered) {
            return 0;  /* this entry targets a tensor outside the declared scope */
        }
    }
    return 1;
}

/* Returns 1 if the loaded adapter passes admission, 0 (and logs) if refused. */
static int gov_admit(const xmind_lora_t *adapter, const char *id) {
    uint32_t i;

    /* Gate (1) base-model / integrity proxy: the mmap'd payload must be live.
     *
     * TODO(genome:base_checkpoint, content_hash): xmind_lora_t carries no
     * base_checkpoint string nor a content_hash to compare against the running
     * model's identity. When lora.h is extended to surface those (loaded from
     * the adapter_genome_v2 block), assert content_hash == expected and
     * base_checkpoint == active model id here BEFORE admission. Until then we
     * enforce the strongest honest runtime invariant: a non-empty, mmap-backed
     * payload (a forged/empty adapter cannot apply a delta from nothing). */
    if (adapter->raw_data == (void *)0 || adapter->raw_size == 0u) {
        gov_refuse(id, "base_integrity:empty_payload");
        return 0;
    }

    /* §9.2 "No adapter activates against a mismatched base hash": if the adapter declares the base
     * sha it was trained on (base_sha256 from __metadata__) AND the host set the running model's
     * base, they MUST match. Absent on either side = unverifiable = admitted (the substrate's own
     * unsigned adapters keep working); a DECLARED mismatch is refused. */
    if (adapter->base_sha256[0] != '\0' && s_expected_base[0] != '\0' &&
        strcmp(adapter->base_sha256, s_expected_base) != 0) {
        gov_refuse(id, "base_hash:mismatch");
        return 0;
    }

    /* Gate (2a) authority scope — engine-capacity bound. An adapter claiming zero
     * or more-than-capacity entries is structurally out of scope for this engine. */
    if (adapter->n_entries == 0u || adapter->n_entries > XMIND_LORA_MAX_TENSORS) {
        gov_refuse(id, "authority_scope:entry_count_out_of_bounds");
        return 0;
    }

    /* Gate (2b) §9.2 authority scope — DECLARED scope (no longer a proxy).
     * The genome `scope` (which tensors/roles an adapter is permitted to touch) is now
     * surfaced onto xmind_lora_t.scope from the adapter __metadata__ (parse in lora.c). If
     * the adapter declares a scope, every entry it adapts MUST fall inside it; an entry
     * targeting a tensor outside the declared scope is refused. Absent scope = unverifiable
     * = admitted (backward-compatible). */
    if (!gov_scope_admit(adapter)) {
        gov_refuse(id, "authority_scope:out_of_declared_scope");
        return 0;
    }

    /* Gate (3) conflict threshold proxy: per-entry self-consistency.
     *
     * TODO(genome:parents, signature): cross-adapter conflict (overlapping
     * `parents` lineage) and tamper detection (`signature` HMAC) are genome
     * concerns absent from xmind_lora_t. When surfaced, verify the HMAC and
     * reject if a conflicting lineage is already active. Until then we reject a
     * self-conflicting adapter: an entry that claims to adapt a tensor but has a
     * degenerate rank/dim or a null low-rank operator would corrupt the forward
     * pass (silently or via OOB), so it is refused rather than applied. */
    for (i = 0u; i < adapter->n_entries; i++) {
        const xmind_lora_entry_t *e = &adapter->entries[i];
        if (e->rank == 0u || e->d_in == 0u || e->d_out == 0u ||
            e->A == (const float *)0 || e->B == (const float *)0) {
            gov_refuse(id, "conflict:degenerate_entry");
            return 0;
        }
    }

    return 1;
}

int xmind_adapter_runtime_activate(const xmind_lora_t *adapter, const char *id) {
    if (adapter == (const xmind_lora_t *)0) {
        return -1;
    }
    /* D36: enforce admission governance before binding into the hot path.
     * Refusal is a clean no-op — s_active is left as-is, so apply() stays a
     * no-op for the refused adapter (or keeps the prior adapter if one was
     * active). The refusal is recorded to telemetry inside gov_admit(). */
    if (!gov_admit(adapter, id)) {
        return -2;
    }
    s_active = adapter;
    if (id != (const char *)0) {
        strncpy(s_id, id, sizeof(s_id) - 1u);
        s_id[sizeof(s_id) - 1u] = '\0';
    } else {
        s_id[0] = '\0';
    }
    return 0;
}

void xmind_adapter_runtime_deactivate(void) {
    s_active = (const xmind_lora_t *)0;
    s_id[0] = '\0';
}

int xmind_adapter_runtime_active(void) { return s_active != (const xmind_lora_t *)0; }

const char *xmind_adapter_runtime_id(void) { return s_id; }

void xmind_adapter_runtime_apply(uint32_t layer, const char *role,
                                 const float *x, float *out) {
    const xmind_lora_entry_t *e;
    char name[XMIND_LORA_MAX_NAMELEN];

    if ((s_active == (const xmind_lora_t *)0) ||
        (role == (const char *)0) || (x == (const float *)0) || (out == (float *)0)) {
        return;  /* no-op: no adapter active or invalid args */
    }
    (void)snprintf(name, sizeof(name), "blk.%u.%s.weight", (unsigned)layer, role);
    e = xmind_lora_find(s_active, name);
    if (e == (const xmind_lora_entry_t *)0) {
        return;  /* this adapter does not adapt this tensor */
    }
    if (xmind_lora_apply_delta(e, x, out) == 0) {
        s_apply++;
        xmind_adapter_telemetry_record(name);
    }
}

uint64_t xmind_adapter_runtime_apply_count(void) { return s_apply; }
