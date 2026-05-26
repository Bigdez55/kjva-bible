/*
 * xmind_context.h — Memory Bridge Contract (Gap 3 Closure)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Closes Gap 3: the memory bridge between Bookworm/SoulManager and
 *   r1_per_signal_t.context_shards.  This is the contract that connects:
 *
 *   Bookworm (archival library) → retrieves by semantic similarity
 *   SoulManager (episodic memory) → retrieves by session continuity
 *   RT4 salience filter → scores and ranks shards
 *   r1_per_signal_t.context_shard_count → populated by this bridge
 *
 *   Max 7 shards per signal (law of seven, matches FROZEN r1_per.h).
 *
 * DATA FLOW:
 *   XMIND inference request arrives
 *     → R1_PER encodes input → r1_per_signal_t
 *     → xmind_context_retrieve(signal, shards, 7)
 *         → sends context request over XNET to Ahki (port 18600)
 *         → Ahki dispatches to Bookworm + SoulManager
 *         → RT4 salience filter scores each candidate
 *         → Top 7 shards returned
 *     → Heptagon pre_inference runs with populated signal
 *     → xmind_forward() with context in KV cache
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef XMIND_CONTEXT_H
#define XMIND_CONTEXT_H

#ifdef PAL_FREESTANDING
#include "../../pal/include/pal.h"
#else
#include <stdint.h>
#endif

#include "../../xisc/include/xcog.h"
#include "r1_per.h"

/* ═══════════════════════════════════════════════════════════════════════
 * §1  CONSTANTS
 * ═══════════════════════════════════════════════════════════════════════ */

#define XMIND_MAX_CONTEXT_SHARDS  7u  /* Law of seven, matches r1_per.h */

/* Memory types (Heptagon L1 five-layer memory model) */
#define XMIND_MEM_REGISTER  0u  /* L1: immediate transient working contents  */
#define XMIND_MEM_SESSION   1u  /* L2: current task continuity               */
#define XMIND_MEM_EPISODIC  2u  /* L3: bound experiences with time/context   */
#define XMIND_MEM_SEMANTIC  3u  /* L4: distilled facts, rules, patterns      */
#define XMIND_MEM_ARCHIVAL  4u  /* L5: long-horizon compressed records       */

/* ═══════════════════════════════════════════════════════════════════════
 * §2  CONTEXT SHARD — A single piece of retrieved context
 * ═══════════════════════════════════════════════════════════════════════ */

typedef struct __attribute__((packed)) {
    uint32_t  shard_id;            /* Unique identifier for this shard    */
    uint16_t  memory_type;         /* XMIND_MEM_* (which memory layer)   */
    uint16_t  salience;            /* RT4 score: fixed-point 0..65535    */
    uint32_t  compressed_size;     /* Bytes after AIT compression (0=raw) */
    uint32_t  raw_size;            /* Original bytes before compression   */
    /* Shard payload is NOT inline — lives in separate buffer.
     * Referenced by offset into xmind_context_result_t.shard_data.     */
} xmind_context_shard_t;

/* ═══════════════════════════════════════════════════════════════════════
 * §3  CONTEXT REQUEST — What XMIND asks for
 * ═══════════════════════════════════════════════════════════════════════ */

typedef struct {
    const xcog_instr_t *query_instructions; /* XCOG stream to match against   */
    uint32_t            query_count;        /* Number of XCOG instructions    */
    uint16_t            salience_threshold; /* Minimum salience to include    */
    uint16_t            max_shards;         /* Up to XMIND_MAX_CONTEXT_SHARDS */
} xmind_context_request_t;

/* ═══════════════════════════════════════════════════════════════════════
 * §4  CONTEXT RESULT — What the bridge returns
 * ═══════════════════════════════════════════════════════════════════════ */

typedef struct {
    xmind_context_shard_t shards[XMIND_MAX_CONTEXT_SHARDS];
    uint32_t              shard_count;      /* Actual shards returned (≤ 7)  */
    uint8_t              *shard_data;       /* Packed shard payloads          */
    uint32_t              total_data_size;  /* Total bytes in shard_data      */
} xmind_context_result_t;

/* ═══════════════════════════════════════════════════════════════════════
 * §5  MEMORY BRIDGE API
 *
 * Implemented by Citadel memory subsystem (Ahki → Bookworm + SoulManager).
 * Called from XMIND inference pipeline before xmind_heptagon_pre_inference().
 * ═══════════════════════════════════════════════════════════════════════ */

/*
 * xmind_context_retrieve — Fetch context shards for the given signal.
 *
 * Dispatcher: XMIND → (IPC) → Ahki → Bookworm + SoulManager → RT4 filter
 *
 * The RT4 salience formula:
 *   score = (salience × priority × relevance × policy_clearance) + novelty_bonus
 *
 * Shards are returned sorted by salience (highest first).
 *
 * @param req  Context request with XCOG query instructions + threshold
 * @param out  Result buffer (caller-allocated)
 * @return     0 on success, negative on error (-1 = IPC failure, -2 = no shards)
 */
int xmind_context_retrieve(const xmind_context_request_t *req,
                            xmind_context_result_t *out);

/*
 * xmind_context_release — Release shard data buffer.
 *
 * Frees the shard_data buffer allocated by xmind_context_retrieve().
 */
void xmind_context_release(xmind_context_result_t *result);

#endif /* XMIND_CONTEXT_H */
