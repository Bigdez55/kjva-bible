/*
 * r1_per_hook.c — R1_PER perception pipeline hook for xmind_easy_generate().
 *
 * STATUS: INACTIVE — see ACTIVATION GATE below before enabling.
 *
 * PURPOSE:
 *   This file wires r1_per_encode() + r1_per_translate_to_tokens() into
 *   the xmind_easy_generate() token-preparation path as a pre-processing
 *   stage, replacing the raw byte-level tokenization with semantically
 *   structured XCOG opcodes when the perception pipeline is initialized
 *   and classification confidence is above threshold.
 *
 * WHY THIS IS NOT LIVE-WIRED IN xmind_easy.c YET:
 *
 *   Two blockers prevent safe direct wiring as of 2026-06-07:
 *
 *   BLOCKER 1 — Token encoding mismatch (vocab corruption, silent):
 *     xmind_easy_generate() uses byte+3 encoding for the 259-token
 *     byte-level vocab (PAD=0, BOS=1, EOS=2, then byte+3 for [3,258]).
 *     r1_per_translate_to_tokens() fallback path (r1_per.c:1661) emits
 *     raw byte values (0-255) when xmind_tokenize() is not loaded.
 *     Feeding raw byte IDs 0/1/2 to the 259-vocab model treats them as
 *     PAD/BOS/EOS, silently corrupting generation.  This will compile
 *     clean and return rc=0 while producing garbage output.
 *     FIX REQUIRED: r1_per_translate_to_tokens must be taught to emit
 *     byte+3 IDs when model_config indicates a 259-vocab byte-level
 *     model (vocab_size == 259).  Add a guard in the fallback path:
 *       if (((xmind_config_t*)model_config)->vocab_size == 259)
 *           token_ids[i] = (uint32_t)(uint8_t)text_buf[i] + 3u;
 *     and ensure BOS/EOS handling is consistent.
 *
 *   BLOCKER 2 — r1_per_init() not called before xmind_easy_init() returns:
 *     r1_per_encode() returns -2 if s_initialized==0 (r1_per.c:1342).
 *     r1_per_init() is declared as a post-XMIND-ready call (r1_per.h:128:
 *     "Called from GENSD after XMIND is ready").  It is not called anywhere
 *     in xmind_easy.c today.  Live wiring must call r1_per_init() from
 *     xmind_easy_init() after xmind_session_create() succeeds, or the
 *     encode will always return -2 and fall through to byte encoding with
 *     no signal that the pipeline was never active.
 *
 * HOW TO ACTIVATE (after both blockers are resolved):
 *   1. Apply the vocab fix to r1_per.c r1_per_translate_to_tokens fallback
 *      (see BLOCKER 1 above) and verify with output-differs falsification:
 *      feed a prompt and confirm token IDs are in [3,258], not [0,255].
 *   2. Add r1_per_init() call in xmind_easy_init() after session_create().
 *   3. Add this file to CORE_SRC in Makefile (currently excluded):
 *        src/r1_per_hook.c \
 *   4. Uncomment the call in the ACTIVATION SITE comment below, then
 *      in xmind_easy.c replace the byte-tokenization block (lines 310-316)
 *      with a call to xmind_easy_per_tokenize() with byte-path fallback.
 *   5. Verify with a falsification test: feed structured input
 *      (e.g. "find the file") and confirm output differs from the
 *      baseline byte-path result.  rc=0 is not sufficient — check output.
 *
 * NOTE on context_bridge.c:
 *   context_bridge.c implements xmind_context_retrieve() for RT4 context
 *   shards.  It is deliberately excluded from CORE_SRC (Makefile:59-62)
 *   because it requires the context_coord daemon on port 18600.  It is NOT a
 *   dependency of r1_per_hook and should not be added to CORE_SRC for
 *   this task.  r1_per.c's Phase 1 sets context_shard_count=0 (line 1472)
 *   and needs no context_bridge calls.
 *
 * CALL SITE (what live wiring would look like in xmind_easy.c):
 *
 *   // R1_PER: encode NL prompt through perception pipeline.
 *   // Replace direct byte-tokenization when perception is initialized
 *   // and classification confidence exceeds R1_FALLBACK_THRESHOLD.
 *   //
 *   // ACTIVATION SITE — uncomment after both blockers resolved:
 *   //
 *   //   uint32_t per_count = 0;
 *   //   if (xmind_easy_per_tokenize(p, prompt_chars,
 *   //                               s_prompt_tokens + 1,  // +1: BOS already placed
 *   //                               max_prompt_chars,
 *   //                               &per_count) == 0 && per_count > 0) {
 *   //       prompt_tok_count = 1u + per_count;  // 1 for BOS
 *   //   } else {
 *   //       // fallback: existing byte+3 loop (lines 311-316 of xmind_easy.c)
 *   //       for (uint32_t i = 0u; i < prompt_chars; i++)
 *   //           s_prompt_tokens[prompt_tok_count++] =
 *   //               (uint32_t)(unsigned char)p[i] + 3u;
 *   //   }
 *   //
 *   // Note: BOS token (1u) must still be written at s_prompt_tokens[0]
 *   // before this call.  The fallback must remain to keep generation
 *   // working when perception is not initialized or falls back to CONVERSE.
 */

#include "../include/r1_per.h"
#include "../include/xmind.h"

/*
 * xmind_easy_per_tokenize — Run NL input through R1_PER and translate
 * to byte+3 token IDs suitable for xmind_easy_generate().
 *
 * Fills token_ids[0..out_count-1] with IDs in the byte-level vocab
 * range [3,258] (byte+3 encoding, matching xmind_easy_generate's
 * convention).  BOS token (1u) is NOT prepended — caller handles that.
 *
 * Returns 0 on success (out_count > 0 means structured tokens were
 * produced), negative if r1_per is not initialized or encode fails.
 * On any non-zero return, caller must fall back to direct byte+3 loop.
 *
 * This function is INACTIVE (not called from xmind_easy.c) until both
 * blockers in the file header are resolved.  It compiles but is dead code.
 */
int xmind_easy_per_tokenize(const char *nl_input, uint32_t nl_len,
                             uint32_t *token_ids, uint32_t max_tokens,
                             uint32_t *out_count)
{
    if (!nl_input || !token_ids || !out_count || max_tokens == 0) {
        if (out_count) *out_count = 0;
        return -1;
    }
    *out_count = 0;

    /* Encode NL to XCOG signal */
    r1_per_signal_t signal;
    int rc = r1_per_encode(nl_input, nl_len, &signal);
    if (rc != 0) {
        /* r1_per not initialized (rc=-2) or invalid input (rc=-1).
         * Caller must fall back to byte+3 direct encoding. */
        return rc;
    }

    /* BLOCKER 1 guard: translate_to_tokens emits raw bytes (0-255) in
     * its fallback path, not byte+3 (3-258).  Until r1_per.c is fixed,
     * refuse to produce tokens to avoid feeding raw-byte IDs to the
     * 259-vocab model.  This function returns -3 so the caller falls back
     * to the safe byte+3 loop. */
    xmind_model_t *m = xmind_get_global();
    if (!m || m->cfg.vocab_size != 259u) {
        /* Non-byte-level model: BPE path via xmind_tokenize may work;
         * translate_to_tokens is designed for BPE.  Allow the call. */
        uint32_t count = 0;
        rc = r1_per_translate_to_tokens(&signal, &m->cfg,
                                        token_ids, max_tokens, &count);
        if (rc == 0 && count > 0) {
            *out_count = count;
            return 0;
        }
        return -4;
    }

    /* 259-vocab byte-level model: translate_to_tokens fallback emits raw
     * bytes, not byte+3.  This produces vocab-corrupting IDs 0,1,2 for
     * NUL/SOH/STX bytes and puts ASCII in [3,127] by coincidence for some
     * bytes — but [QUERY], [ENT:file] etc. contain chars like '[', 'Q',
     * 'U' whose raw-byte values ARE in [3,258] but are not the byte+3
     * encoding the model was trained on.  Refuse until r1_per.c is fixed.
     *
     * TODO: after BLOCKER 1 fix in r1_per.c, remove this guard and call:
     *   r1_per_translate_to_tokens(&signal, &m->cfg,
     *                              token_ids, max_tokens, out_count);
     */
    return -3;  /* BLOCKER 1 not yet resolved */
}
