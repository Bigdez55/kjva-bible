/*
 * parity_logits.c — load a GGUF, forward a raw-byte prompt (token = byte+3, no
 * BOS, matching the trainer/eval_clean_ppl convention), and print the
 * last-position logits (one float per line) to stdout.
 *
 * Used by tests/test_pt_xmind_parity.py to compare the XMIND C forward pass
 * against training/pt/model.py on identical weights+input. This is the
 * numerical parity gate that test_pt_parity.py never had (it only checked
 * tensor names/shapes, never logits).
 *
 * Build (mirrors the xmind-cli link rule):
 *   clang -std=c11 -Iinclude tests/parity_logits.c build/libxmind-core.a -lm -o build/parity_logits
 */
#include "xmind.h"
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s <model.gguf> <prompt>\n", argv[0]);
        return 1;
    }
    const char *model_path = argv[1];
    const char *prompt     = argv[2];

    xmind_model_t *m = xmind_get_global();
    memset(m, 0, sizeof(*m));

    if (xmind_weights_load_file(m, model_path) != XMIND_OK) {
        fprintf(stderr, "[parity] weights_load_file FAILED for %s\n", model_path);
        return 2;
    }
    if (xmind_rope_precompute(m) != XMIND_OK) {
        fprintf(stderr, "[parity] rope_precompute FAILED\n");
        return 3;
    }
    if (xmind_preflight_check(m) != XMIND_OK) {
        fprintf(stderr, "[parity] preflight_check FAILED\n");
        return 4;
    }

    uint32_t vocab = m->cfg.vocab_size;
    uint32_t T     = (uint32_t)strlen(prompt);
    if (T == 0u) { fprintf(stderr, "[parity] empty prompt\n"); return 5; }

    /* Feed tokens sequentially, building the KV cache; logits after the last
     * token are the next-byte distribution for the full prompt. */
    for (uint32_t pos = 0u; pos < T; pos++) {
        uint32_t tok = (uint32_t)(unsigned char)prompt[pos] + 3u;
        xmind_forward(m, tok, pos);
    }

    for (uint32_t i = 0u; i < vocab; i++) {
        printf("%.7e\n", (double)m->state.logits[i]);
    }
    return 0;
}
