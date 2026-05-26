/*
 * xmind_materialize.h — Role-Based Materialization Layer (ADR-S49-01 Phase 2)
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Implements the three-way split from ADR Section 7 — Materialization
 *   Doctrine:
 *
 *     Artifact   = exact truth (GGUF on disk)
 *     Codec      = lossless compression (Q4_0, Q4_K_M)
 *     Materialization = runtime embodiment (what lives in memory)
 *
 *   This header defines materialization kinds, plans, and results.
 *   Classical mode wraps existing full-dense allocation.  Sparse mode
 *   selectively allocates only layers in the active mask.  Paged mode
 *   supports page-in/page-out of individual layers for memory-constrained
 *   devices (e.g. HP EliteBook x360 with 16 GB RAM).
 *
 * MEMORY BUDGET:
 *   Llama 3.2 3B Q4_0: ~1.7 GB fully dense.  Sparse at 50% active layers
 *   cuts to ~0.9 GB.  Paged mode can operate with as low as 4 resident
 *   layers (~0.2 GB) plus page-in latency on demand.
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef XMIND_MATERIALIZE_H
#define XMIND_MATERIALIZE_H

#ifdef PAL_FREESTANDING
#include "../../../pal/include/pal.h"
#else
#include <stdint.h>
#include <stddef.h>
#endif

/* ===================================================================
 * S1  MATERIALIZATION KIND ENUM — per ADR Section 7.3
 * =================================================================== */

typedef enum {
    XM_MAT_CLASSICAL  = 0,   /* Exact classical: full dense embodiment       */
    XM_MAT_SPARSE     = 1,   /* Sparse role: only active subgraph            */
    XM_MAT_PAGED      = 2,   /* Paged: page-in/page-out on demand           */
    XM_MAT_EXTERNAL   = 3,   /* External: routed co-processing only          */
    XM_MAT_QUDIT_SIM  = 99   /* END-STATE: experimental research only        */
} xmind_materialization_kind_t;

/* ===================================================================
 * S2  MATERIALIZATION PLAN — What to embody at runtime
 *
 * The plan is computed by xmind_materialize_plan_init() from the
 * model config + memory budget.  The orchestrator then calls the
 * appropriate materialization function to allocate weight buffers.
 * =================================================================== */

#define XM_MAT_MAX_LAYERS  32u  /* matches XMIND_MAX_LAYERS */

typedef struct {
    xmind_materialization_kind_t kind;
    uint32_t active_layer_mask;     /* Bitmask: which layers are embodied    */
    uint32_t total_layers;          /* Total layers in the model             */
    uint64_t budget_bytes;          /* Max runtime memory budget             */
    uint64_t embodied_bytes;        /* Actual bytes materialized             */
    float    sparsity_ratio;        /* 0.0=fully dense, 1.0=fully sparse    */
    uint8_t  page_resident[XM_MAT_MAX_LAYERS]; /* 1=resident, 0=paged out  */
} xmind_materialize_plan_t;

_Static_assert(sizeof(((xmind_materialize_plan_t *)0)->page_resident) ==
               XM_MAT_MAX_LAYERS,
               "page_resident must cover XM_MAT_MAX_LAYERS entries");

/* ===================================================================
 * S3  MATERIALIZATION RESULT
 * =================================================================== */

typedef struct {
    xmind_materialization_kind_t realized_kind;
    uint32_t layers_embodied;       /* Count of layers actually in memory    */
    uint64_t bytes_used;            /* Total bytes allocated                 */
    uint64_t bytes_saved;           /* vs fully dense (budget - bytes_used)  */
    float    realized_sparsity;     /* Actual sparsity achieved              */
} xmind_materialize_result_t;

/* ===================================================================
 * S4  LAYER BUFFER — Per-layer weight storage handle
 *
 * Each layer's weight data is represented by a pointer + size.
 * Paged mode uses this to track which layers are resident.
 * =================================================================== */

typedef struct {
    void    *data;                  /* Pointer to weight data (NULL=evicted) */
    uint64_t size_bytes;            /* Allocated size when resident          */
    uint32_t layer_index;           /* Which layer this buffer belongs to    */
    uint8_t  resident;              /* 1=in memory, 0=evicted               */
    uint8_t  dirty;                 /* 1=modified since load (future use)    */
    uint8_t  _pad[2];
} xm_layer_buffer_t;

/* ===================================================================
 * S5  MATERIALIZATION STATE — Global state for the materializer
 *
 * Tracks all layer buffers, the active plan, and cumulative stats.
 * Singleton per xmind_model_t instance.
 * =================================================================== */

typedef struct {
    xmind_materialize_plan_t   plan;
    xm_layer_buffer_t          layers[XM_MAT_MAX_LAYERS];
    uint32_t                   layer_count;
    uint64_t                   total_allocated;
    uint64_t                   peak_allocated;
    uint32_t                   page_in_count;   /* Lifetime page-in ops    */
    uint32_t                   page_out_count;  /* Lifetime page-out ops   */
} xmind_materialize_state_t;

/* ===================================================================
 * S6  PUBLIC API
 * =================================================================== */

/*
 * xmind_materialize_plan_init — Initialize a materialization plan.
 *
 * Computes which layers to embody based on the requested kind,
 * total layer count, active mask, and memory budget.
 *
 * @param plan          Plan to initialize (caller-allocated)
 * @param kind          Materialization kind
 * @param total_layers  Total layers in the model (max XM_MAT_MAX_LAYERS)
 * @param active_mask   Bitmask of layers to embody (0xFFFFFFFF = all)
 * @param budget_bytes  Maximum memory budget for weights
 * @return              XMIND_OK on success, XMIND_ERR_INVAL on bad params
 */
int32_t xmind_materialize_plan_init(xmind_materialize_plan_t *plan,
                                     xmind_materialization_kind_t kind,
                                     uint32_t total_layers,
                                     uint32_t active_mask,
                                     uint64_t budget_bytes);

/*
 * xmind_materialize_classical — Full dense materialization.
 *
 * Allocates weight buffers for ALL layers.  This is the existing
 * behavior wrapped in the materialization framework.
 *
 * @param state         Materialization state (caller-allocated)
 * @param plan          Initialized plan (kind must be XM_MAT_CLASSICAL)
 * @param bytes_per_layer  Bytes required per layer (from catalog)
 * @param result        Output result
 * @return              XMIND_OK on success, XMIND_ERR_NOMEM on OOM
 */
int32_t xmind_materialize_classical(xmind_materialize_state_t *state,
                                     const xmind_materialize_plan_t *plan,
                                     uint64_t bytes_per_layer,
                                     xmind_materialize_result_t *result);

/*
 * xmind_materialize_sparse — Sparse role-based materialization.
 *
 * Allocates weight buffers only for layers in active_layer_mask.
 * Layers not in the mask get NULL data pointers.
 *
 * @param state         Materialization state
 * @param plan          Initialized plan (kind must be XM_MAT_SPARSE)
 * @param bytes_per_layer  Bytes required per layer
 * @param result        Output result
 * @return              XMIND_OK on success, XMIND_ERR_NOMEM on OOM
 */
int32_t xmind_materialize_sparse(xmind_materialize_state_t *state,
                                  const xmind_materialize_plan_t *plan,
                                  uint64_t bytes_per_layer,
                                  xmind_materialize_result_t *result);

/*
 * xmind_materialize_page_in — Bring a layer into residence.
 *
 * Allocates memory for the layer and marks it resident.
 * Caller must load actual weight data after this call returns.
 *
 * @param state         Materialization state
 * @param layer_index   Layer to page in (0-based)
 * @param bytes         Byte size of the layer
 * @return              XMIND_OK on success, XMIND_ERR_NOMEM/INVAL on error
 */
int32_t xmind_materialize_page_in(xmind_materialize_state_t *state,
                                   uint32_t layer_index,
                                   uint64_t bytes);

/*
 * xmind_materialize_page_out — Evict a layer from residence.
 *
 * Frees the memory for the layer and marks it non-resident.
 *
 * @param state         Materialization state
 * @param layer_index   Layer to page out (0-based)
 * @return              XMIND_OK on success, XMIND_ERR_INVAL on bad index
 */
int32_t xmind_materialize_page_out(xmind_materialize_state_t *state,
                                    uint32_t layer_index);

/*
 * xmind_materialize_report — Report current materialization state.
 *
 * Fills result with a snapshot of what is currently embodied.
 *
 * @param state   Materialization state
 * @param result  Output result
 * @return        XMIND_OK on success, XMIND_ERR_INVAL if state is NULL
 */
int32_t xmind_materialize_report(const xmind_materialize_state_t *state,
                                  xmind_materialize_result_t *result);

/*
 * xmind_materialize_teardown — Free all materialized buffers.
 *
 * @param state   Materialization state to tear down
 */
void xmind_materialize_teardown(xmind_materialize_state_t *state);

#endif /* XMIND_MATERIALIZE_H */
