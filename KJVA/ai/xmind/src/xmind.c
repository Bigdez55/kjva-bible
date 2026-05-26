/*
 * xmind.c — XMIND Main API: Init / Alloc / Shutdown / Global Singleton
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * This translation unit owns:
 *   - xmind_init()        — validate config, zero-init model
 *   - xmind_alloc_state() — allocate inference scratch buffers + KV cache
 *   - xmind_shutdown()    — free all state buffers
 *   - xmind_dump_config() — print model config to debug console
 *   - s_xmind_model       — process-wide singleton
 *   - xmind_get_global()  — accessor for the singleton
 *
 * Memory management:
 *   XMIND uses xm_heap_alloc() / xm_heap_free() (defined in xmind.h)
 *   which are backed by pal_pages_alloc() + pal_map_pages().
 *
 *   State buffers (scratch + KV cache) are allocated here and freed
 *   by xmind_shutdown().  Weight buffers (wq, wk, …, token_emb, rope_*)
 *   are owned by the caller (memory-mapped model file) and are NOT freed.
 *
 * Allocation strategy:
 *   xmind_alloc_state() allocates each buffer individually.  If any
 *   allocation fails, all previously allocated buffers for this call
 *   are freed and XMIND_ERR_NOMEM is returned (partial-state safety).
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "xmind.h"

/* ═══════════════════════════════════════════════════════════════════
 * §0  HEAP SLAB — PAL handle tracking for xm_heap_alloc/free
 *
 * Sprint 10 (RA-XMIND-02 fix): replaces the Sprint 6 no-op xm_heap_free.
 * Each successful allocation stores (va, ph, mh) in a fixed-size slab.
 * xm_heap_free() looks up the virtual address and releases the PAL handles.
 *
 * Slab capacity: 128 slots covers the maximum inference state allocation
 * count (7 scratch buffers + 2 × XMIND_MAX_LAYERS KV entries = 71 max).
 * ═══════════════════════════════════════════════════════════════════ */

#define XM_HEAP_SLAB_SLOTS 128U

typedef struct {
    uintptr_t    va;
    pal_handle_t ph;
    pal_handle_t mh;
} xm_slab_entry_t;

static xm_slab_entry_t s_xm_slab[XM_HEAP_SLAB_SLOTS];
static uint32_t        s_xm_slab_n = 0u;

void *xm_heap_alloc(uint64_t sz) {
    if (sz == 0u) { return (void *)0; }
    uint64_t pages = (sz + PAL_PAGE_SIZE_4K - 1u) / PAL_PAGE_SIZE_4K;
    pal_handle_t ph = PAL_HANDLE_INVALID;
    pal_handle_t mh = PAL_HANDLE_INVALID;
    uintptr_t    va = 0u;
    if (pal_pages_alloc(pages, PAL_PAGE_SIZE_4K,
                        (uint32_t)PAL_MEM_ZEROED, PAL_NUMA_ANY, &ph) != PAL_OK) {
        return (void *)0;
    }
    if (pal_map_pages(ph, 0u, 0u, pages,
                      (uint32_t)(PAL_MAP_READ | PAL_MAP_WRITE),
                      &mh, &va) != PAL_OK) {
        (void)pal_pages_free(ph);
        return (void *)0;
    }
    if (s_xm_slab_n < XM_HEAP_SLAB_SLOTS) {
        s_xm_slab[s_xm_slab_n].va = va;
        s_xm_slab[s_xm_slab_n].ph = ph;
        s_xm_slab[s_xm_slab_n].mh = mh;
        s_xm_slab_n++;
    } else {
        /* Slab full — allocation succeeds but handle is untracked.
         * Emit a console warning; consider increasing XM_HEAP_SLAB_SLOTS. */
        pal_console_puts("[XMIND] WARN: heap slab full — handle untracked\n");
    }
    return (void *)va;
}

void xm_heap_free(void *ptr) {
    if (!ptr) { return; }
    uintptr_t target = (uintptr_t)ptr;
    uint32_t i;
    for (i = 0u; i < s_xm_slab_n; i++) {
        if (s_xm_slab[i].va == target) {
            /* Sprint 38 fix (H15/F-08): unmap BEFORE freeing pages.
             * Previously only pal_pages_free(ph) was called — mh leaked.
             * Each XMIND restart leaked ~336MB of virtual mappings. */
            (void)pal_unmap(s_xm_slab[i].mh);
            (void)pal_pages_free(s_xm_slab[i].ph);
            /* Compact slab: replace this slot with the last entry. */
            s_xm_slab_n--;
            s_xm_slab[i] = s_xm_slab[s_xm_slab_n];
            return;
        }
    }
    /* Pointer not in slab — may be an allocation that overflowed the slab
     * or a double-free; log and ignore to avoid undefined behaviour. */
    pal_console_puts("[XMIND] WARN: xm_heap_free: ptr not in slab\n");
}

/* ═══════════════════════════════════════════════════════════════════
 * §1  GLOBAL SINGLETON
 * ═══════════════════════════════════════════════════════════════════ */

static xmind_model_t s_xmind_model;

xmind_model_t *xmind_get_global(void) {
    return &s_xmind_model;
}

/* ═══════════════════════════════════════════════════════════════════
 * §2  INTERNAL ZERO-INIT HELPER
 * ═══════════════════════════════════════════════════════════════════ */

static void xm_zero_model(xmind_model_t *m) {
    /*
     * Zero-init the entire model struct using byte-write loop.
     * This clears all pointers to NULL (0), all counters to 0,
     * and initialized flag to 0.
     */
    uint8_t  *p   = (uint8_t *)m;
    uint64_t  sz  = (uint64_t)sizeof(xmind_model_t);
    uint64_t  i;
    for (i = 0u; i < sz; i++) {
        p[i] = 0u;
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * §3  xmind_init — VALIDATE CONFIG, ZERO MODEL, STORE CONFIG
 * ═══════════════════════════════════════════════════════════════════
 *
 * Validation rules:
 *   - m and cfg must be non-NULL
 *   - All dimension fields must be > 0
 *   - n_layers   <= XMIND_MAX_LAYERS
 *   - n_heads    <= XMIND_MAX_HEADS
 *   - n_kv_heads <= n_heads (GQA constraint)
 *   - n_heads * head_dim == hidden_dim
 *   - ctx_len    <= XMIND_MAX_SEQ
 *   - vocab_size <= XMIND_VOCAB_SIZE
 *
 * On success: m->initialized is set to 1.
 * On failure: returns XMIND_ERR_INVAL; m is left zero-initialised.
 */
xmind_status_t xmind_init(xmind_model_t *m, const xmind_config_t *cfg) {
    if (m   == (void *)0) { return XMIND_ERR_INVAL; }
    if (cfg == (void *)0) { return XMIND_ERR_INVAL; }

    xm_zero_model(m);

    /* Dimension presence checks */
    if (cfg->n_layers   == 0u) { return XMIND_ERR_INVAL; }
    if (cfg->n_heads    == 0u) { return XMIND_ERR_INVAL; }
    if (cfg->n_kv_heads == 0u) { return XMIND_ERR_INVAL; }
    if (cfg->head_dim   == 0u) { return XMIND_ERR_INVAL; }
    if (cfg->hidden_dim == 0u) { return XMIND_ERR_INVAL; }
    if (cfg->ffn_dim    == 0u) { return XMIND_ERR_INVAL; }
    if (cfg->vocab_size == 0u) { return XMIND_ERR_INVAL; }
    if (cfg->ctx_len    == 0u) { return XMIND_ERR_INVAL; }

    /* Bounds checks */
    if (cfg->n_layers   > XMIND_MAX_LAYERS) { return XMIND_ERR_INVAL; }
    if (cfg->n_heads    > XMIND_MAX_HEADS)  { return XMIND_ERR_INVAL; }
    if (cfg->n_kv_heads > cfg->n_heads)     { return XMIND_ERR_INVAL; }
    if (cfg->ctx_len    > XMIND_MAX_SEQ)    { return XMIND_ERR_INVAL; }
    if (cfg->vocab_size > XMIND_VOCAB_SIZE) { return XMIND_ERR_INVAL; }

    /* Structural consistency: n_heads × head_dim must equal hidden_dim */
    if ((uint64_t)cfg->n_heads * cfg->head_dim != (uint64_t)cfg->hidden_dim) {
        return XMIND_ERR_INVAL;
    }

    /* Store config */
    m->cfg = *cfg;

    /* B-PHASE1: Backfill special token IDs with compile-time defaults when
     * the caller left them zero.  This preserves backward compatibility —
     * existing callers that only fill dimension fields still get correct
     * Llama 3.2 token IDs; callers that are running a different model can
     * override them before calling xmind_init(). */
    if (m->cfg.bos_id == 0u) {
        m->cfg.bos_id = XMIND_DEFAULT_BOS_ID;
    }
    if (m->cfg.eos_id == 0u) {
        m->cfg.eos_id = XMIND_DEFAULT_EOS_ID;
    }
    /* eog_ids[0] = end-of-text, [1] = eom, [2] = eot_turn, [3] = reserved */
    if (m->cfg.eog_ids[0] == 0u) {
        m->cfg.eog_ids[0] = XMIND_DEFAULT_EOT_ID;
    }
    if (m->cfg.eog_ids[1] == 0u) {
        m->cfg.eog_ids[1] = XMIND_DEFAULT_EOM_ID;
    }
    if (m->cfg.eog_ids[2] == 0u) {
        m->cfg.eog_ids[2] = XMIND_DEFAULT_EOTURN_ID;
    }
    /* eog_ids[3] is reserved; leave as zero unless caller sets it */

    /* Mark as initialized */
    m->initialized = 1u;

    pal_console_printf("[XMIND] init OK: layers=%u heads=%u kv_heads=%u "
                       "head_dim=%u hidden=%u ffn=%u vocab=%u ctx=%u\n",
                       cfg->n_layers, cfg->n_heads, cfg->n_kv_heads,
                       cfg->head_dim, cfg->hidden_dim, cfg->ffn_dim,
                       cfg->vocab_size, cfg->ctx_len);

    return XMIND_OK;
}

/* ═══════════════════════════════════════════════════════════════════
 * §4  xmind_alloc_state — ALLOCATE INFERENCE BUFFERS + KV CACHE
 * ═══════════════════════════════════════════════════════════════════
 *
 * Allocates all scratch buffers and KV cache.
 * On partial failure (any allocation returns NULL), all previously
 * allocated buffers from THIS call are freed, then XMIND_ERR_NOMEM
 * is returned.
 *
 * Buffer sizes:
 *   logits : vocab_size × 4 bytes
 *   x      : hidden_dim × 4 bytes
 *   xb     : hidden_dim × 4 bytes
 *   q      : n_heads × head_dim × 4 bytes
 *   k      : n_kv_heads × head_dim × 4 bytes
 *   v      : n_kv_heads × head_dim × 4 bytes
 *   attn   : n_heads × ctx_len × 4 bytes
 *   kv.k[l]: ctx_len × n_kv_heads × head_dim × 4 bytes  (per layer)
 *   kv.v[l]: same
 */
xmind_status_t xmind_alloc_state(xmind_model_t *m) {
    if (m == (void *)0)     { return XMIND_ERR_INVAL; }
    if (!m->initialized)    { return XMIND_ERR_INVAL; }

    const xmind_config_t *c = &m->cfg;
    uint64_t f = (uint64_t)sizeof(float);

    /* Helper macro: alloc or goto cleanup */
#define XM_ALLOC(ptr, count) \
    do { \
        (ptr) = (float *)xm_heap_alloc((count) * f); \
        if ((ptr) == (void *)0) { goto oom; } \
    } while (0)

    XM_ALLOC(m->state.logits, (uint64_t)c->vocab_size);
    XM_ALLOC(m->state.x,      (uint64_t)c->hidden_dim);
    XM_ALLOC(m->state.xb,     (uint64_t)c->hidden_dim);
    XM_ALLOC(m->state.q,      (uint64_t)c->n_heads    * c->head_dim);
    XM_ALLOC(m->state.k,      (uint64_t)c->n_kv_heads * c->head_dim);
    XM_ALLOC(m->state.v,      (uint64_t)c->n_kv_heads * c->head_dim);
    XM_ALLOC(m->state.attn,   (uint64_t)c->n_heads    * c->ctx_len);

    /* KV cache: one pair per layer */
    {
        uint64_t kv_sz = (uint64_t)c->ctx_len * c->n_kv_heads * c->head_dim;
        uint32_t l;
        for (l = 0u; l < c->n_layers; l++) {
            XM_ALLOC(m->kv.k[l], kv_sz);
            XM_ALLOC(m->kv.v[l], kv_sz);
        }
    }

#undef XM_ALLOC

    m->state.pos     = 0u;
    m->kv.n_cached   = 0u;

    pal_console_printf("[XMIND] alloc_state OK\n");
    return XMIND_OK;

oom:
    /*
     * Free whatever was allocated in this call before the failure.
     * Sprint 38 fix (H14): xm_heap_free() is fully wired via the slab
     * tracker — calls pal_unmap() + pal_pages_free() for each allocation.
     */
    xm_heap_free(m->state.logits); m->state.logits = (void *)0;
    xm_heap_free(m->state.x);      m->state.x      = (void *)0;
    xm_heap_free(m->state.xb);     m->state.xb     = (void *)0;
    xm_heap_free(m->state.q);      m->state.q      = (void *)0;
    xm_heap_free(m->state.k);      m->state.k      = (void *)0;
    xm_heap_free(m->state.v);      m->state.v      = (void *)0;
    xm_heap_free(m->state.attn);   m->state.attn   = (void *)0;
    {
        uint32_t l;
        for (l = 0u; l < c->n_layers; l++) {
            xm_heap_free(m->kv.k[l]); m->kv.k[l] = (void *)0;
            xm_heap_free(m->kv.v[l]); m->kv.v[l] = (void *)0;
        }
    }
    pal_console_printf("[XMIND] alloc_state FAILED: out of memory\n");
    return XMIND_ERR_NOMEM;
}

/* ═══════════════════════════════════════════════════════════════════
 * §5  xmind_shutdown — FREE STATE BUFFERS
 * ═══════════════════════════════════════════════════════════════════
 *
 * Frees all state buffers allocated by xmind_alloc_state().
 * Weight pointers (wq, wk, …, token_emb, rope_*) are NOT freed.
 * After shutdown, m->initialized is cleared to 0.
 */
void xmind_shutdown(xmind_model_t *m) {
    if (m == (void *)0) { return; }

    xm_heap_free(m->state.logits); m->state.logits = (void *)0;
    xm_heap_free(m->state.x);      m->state.x      = (void *)0;
    xm_heap_free(m->state.xb);     m->state.xb     = (void *)0;
    xm_heap_free(m->state.q);      m->state.q      = (void *)0;
    xm_heap_free(m->state.k);      m->state.k      = (void *)0;
    xm_heap_free(m->state.v);      m->state.v      = (void *)0;
    xm_heap_free(m->state.attn);   m->state.attn   = (void *)0;

    {
        uint32_t l;
        for (l = 0u; l < m->cfg.n_layers; l++) {
            xm_heap_free(m->kv.k[l]); m->kv.k[l] = (void *)0;
            xm_heap_free(m->kv.v[l]); m->kv.v[l] = (void *)0;
        }
    }

    m->state.pos   = 0u;
    m->kv.n_cached = 0u;
    m->initialized = 0u;

    pal_console_printf("[XMIND] shutdown complete\n");
}

/* ═══════════════════════════════════════════════════════════════════
 * §6  xmind_dump_config — PRINT CONFIG TO DEBUG CONSOLE
 * ═══════════════════════════════════════════════════════════════════ */

void xmind_dump_config(const xmind_model_t *m) {
    if (m == (void *)0) {
        pal_console_printf("[XMIND] dump_config: NULL model\n");
        return;
    }
    const xmind_config_t *c = &m->cfg;
    pal_console_printf("[XMIND] version    : %s\n", XMIND_VERSION);
    pal_console_printf("[XMIND] initialized: %u\n", (uint32_t)m->initialized);
    pal_console_printf("[XMIND] n_layers   : %u\n", c->n_layers);
    pal_console_printf("[XMIND] n_heads    : %u\n", c->n_heads);
    pal_console_printf("[XMIND] n_kv_heads : %u\n", c->n_kv_heads);
    pal_console_printf("[XMIND] head_dim   : %u\n", c->head_dim);
    pal_console_printf("[XMIND] hidden_dim : %u\n", c->hidden_dim);
    pal_console_printf("[XMIND] ffn_dim    : %u\n", c->ffn_dim);
    pal_console_printf("[XMIND] vocab_size : %u\n", c->vocab_size);
    pal_console_printf("[XMIND] ctx_len    : %u\n", c->ctx_len);
    pal_console_printf("[XMIND] n_cached   : %u\n", m->kv.n_cached);
    pal_console_printf("[XMIND] state.pos  : %u\n", m->state.pos);
}
