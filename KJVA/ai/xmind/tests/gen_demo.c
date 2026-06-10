/* gen_demo.c — end-to-end generation through the corrected XMIND C engine.
 * Proves the deployed model produces coherent bytes after the docs/INFERENCE_CORRECTNESS_NOTE.md fixes
 * (rotate-half RoPE + Q4_0 scale). Build like the cli; run: gen_demo <gguf> <prompt> */
#include "xmind_easy.h"
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: %s <gguf> <prompt>\n", argv[0]); return 1; }
    if (xmind_easy_init(argv[1], 1024) != 0) { fprintf(stderr, "init failed\n"); return 2; }
    char out[512];
    int n = xmind_easy_generate(argv[2], out, sizeof(out),
                                0.2f /*temp*/, 0.95f /*top_p*/, 80 /*max_new*/);
    if (n < 0) { fprintf(stderr, "generate failed rc=%d\n", n); return 3; }
    printf("PROMPT: %s\nGEN   : %s\n", argv[2], out);
    xmind_easy_shutdown();
    return 0;
}
