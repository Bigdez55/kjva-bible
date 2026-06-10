/*
 * adapter_apply_check.c — D09 verification harness (Track B).
 *
 * The numerical parity gate (tests/parity_logits.c + tests/test_pt_xmind_parity.py)
 * runs with NO adapter active, so it can prove the no-adapter forward path is
 * intact but CANNOT prove that a *loaded* adapter actually applies. This harness
 * supplies that missing evidence for the D09 fix (lora.c canonical-name join):
 *
 *   1. Load the proof adapter (training-stack naming: blocks.N.attn.q.A.weight).
 *      Assert n_entries == 56 (8 layers x 7 modules) — proves the extended
 *      parser accepts the ".A.weight"/".B.weight" convention.
 *   2. Assert xmind_lora_find(&a, "blk.0.attn_q.weight") != NULL — proves the
 *      stored key was canonicalized to the runtime lookup key (the D09 join).
 *   3. Forward once WITHOUT the adapter, capture last-position logits.
 *   4. Activate the adapter, forward again, capture logits.
 *      Assert apply_count > 0 and the logits differ — proves the delta is no
 *      longer a silent no-op.
 *
 * Exit 0 = all checks pass. Non-zero = first failing check (stderr message).
 *
 * Build (mirrors parity_logits link rule):
 *   clang -std=c11 -Iinclude -Ishim tests/adapter_apply_check.c \
 *         build/libxmind-core.a -lm -o build/adapter_apply_check
 * Run:
 *   ./build/adapter_apply_check <model.gguf> <adapter.safetensors> <prompt>
 */
#include "xmind.h"
#include "lora.h"
#include "xmind_adapter_runtime.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define EXPECTED_ENTRIES 56u

static void run_forward(xmind_model_t *m, const char *prompt) {
    uint32_t T = (uint32_t)strlen(prompt);
    for (uint32_t pos = 0u; pos < T; pos++) {
        uint32_t tok = (uint32_t)(unsigned char)prompt[pos] + 3u;
        xmind_forward(m, tok, pos);
    }
}

int main(int argc, char **argv) {
    if (argc < 4) {
        fprintf(stderr, "usage: %s <model.gguf> <adapter.safetensors> <prompt>\n", argv[0]);
        return 1;
    }
    const char *model_path   = argv[1];
    const char *adapter_path = argv[2];
    const char *prompt       = argv[3];

    xmind_model_t *m = xmind_get_global();
    memset(m, 0, sizeof(*m));

    if (xmind_weights_load_file(m, model_path) != XMIND_OK) {
        fprintf(stderr, "[adapter-check] weights_load_file FAILED for %s\n", model_path);
        return 2;
    }
    if (xmind_rope_precompute(m) != XMIND_OK) {
        fprintf(stderr, "[adapter-check] rope_precompute FAILED\n");
        return 3;
    }
    if (xmind_preflight_check(m) != XMIND_OK) {
        fprintf(stderr, "[adapter-check] preflight_check FAILED\n");
        return 4;
    }

    uint32_t vocab = m->cfg.vocab_size;
    if ((uint32_t)strlen(prompt) == 0u) { fprintf(stderr, "[adapter-check] empty prompt\n"); return 5; }

    xmind_adapter_runtime_init();

    /* ── Pass 1: forward WITHOUT adapter, snapshot logits ─────────────── */
    run_forward(m, prompt);
    float *base = (float *)malloc((size_t)vocab * sizeof(float));
    if (!base) { fprintf(stderr, "[adapter-check] OOM\n"); return 6; }
    memcpy(base, m->state.logits, (size_t)vocab * sizeof(float));

    /* ── Load the adapter (training-stack naming) ─────────────────────── */
    xmind_lora_t adapter;
    int rc = xmind_lora_load_safetensors(adapter_path, &adapter);
    if (rc != 0) {
        fprintf(stderr, "[adapter-check] FAIL: lora_load rc=%d path=%s\n", rc, adapter_path);
        free(base);
        return 7;
    }

    /* CHECK 1 — parser accepted .A.weight/.B.weight and merged A+B per module. */
    if (adapter.n_entries != EXPECTED_ENTRIES) {
        fprintf(stderr, "[adapter-check] FAIL CHECK1: n_entries=%u expected=%u\n",
                (unsigned)adapter.n_entries, (unsigned)EXPECTED_ENTRIES);
        xmind_lora_free(&adapter);
        free(base);
        return 8;
    }

    /* CHECK 2 — D09 join: stored key canonicalized to runtime lookup key. */
    const char *probe = "blk.0.attn_q.weight";
    const xmind_lora_entry_t *e = xmind_lora_find(&adapter, probe);
    if (e == (const xmind_lora_entry_t *)0) {
        fprintf(stderr, "[adapter-check] FAIL CHECK2: lora_find(\"%s\") == NULL "
                        "(canonical key mismatch — D09 not fixed)\n", probe);
        xmind_lora_free(&adapter);
        free(base);
        return 9;
    }

    /* ── Pass 2: forward WITH adapter active ──────────────────────────── */
    if (xmind_adapter_runtime_activate(&adapter, "d09-check") != 0) {
        fprintf(stderr, "[adapter-check] FAIL: runtime_activate\n");
        xmind_lora_free(&adapter);
        free(base);
        return 10;
    }
    run_forward(m, prompt);

    /* CHECK 3 — the delta actually applied (count > 0). */
    uint64_t applies = xmind_adapter_runtime_apply_count();
    if (applies == 0u) {
        fprintf(stderr, "[adapter-check] FAIL CHECK3: apply_count==0 (silent no-op)\n");
        xmind_adapter_runtime_deactivate();
        xmind_lora_free(&adapter);
        free(base);
        return 11;
    }

    /* CHECK 4 — logits moved (the delta has a numerical effect). */
    double mae = 0.0;
    for (uint32_t i = 0u; i < vocab; i++) {
        double d = (double)m->state.logits[i] - (double)base[i];
        mae += (d < 0.0) ? -d : d;
    }
    mae /= (double)vocab;
    if (mae == 0.0) {
        fprintf(stderr, "[adapter-check] FAIL CHECK4: logits identical (delta had no effect)\n");
        xmind_adapter_runtime_deactivate();
        xmind_lora_free(&adapter);
        free(base);
        return 12;
    }

    printf("[adapter-check] PASS n_entries=%u find(\"%s\")=ok apply_count=%llu logit_MAE=%.6f\n",
           (unsigned)adapter.n_entries, probe,
           (unsigned long long)applies, mae);

    xmind_adapter_runtime_deactivate();
    xmind_lora_free(&adapter);
    free(base);
    return 0;
}
