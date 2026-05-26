/*
 * xmind_tensor_roles.h — Canonical Tensor Role Vocabulary
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Defines a family-neutral vocabulary of tensor roles that any
 *   transformer model may use.  An artifact interpreter maps GGUF
 *   tensor names (e.g. "blk.0.attn_q.weight") to canonical roles
 *   (e.g. XMIND_ROLE_ATTN_Q, layer 0).
 *
 *   The weight plan (xmind_weight_plan_t) is the complete mapping
 *   from catalog tensor indices to roles + layer indices.  The
 *   orchestrator (weights_loader.c) uses the plan to allocate
 *   buffers at correct sizes and load data into the right slots.
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef XMIND_TENSOR_ROLES_H
#define XMIND_TENSOR_ROLES_H

#ifdef PAL_FREESTANDING
#include "../../../pal/include/pal.h"
#else
#include <stdint.h>
#include <stddef.h>
#endif

/* ===================================================================
 * S1  CANONICAL ROLE ENUM
 *
 * Every tensor in a transformer model maps to exactly one role.
 * Roles are architecture-neutral: "ATTN_Q" means the query projection
 * whether the model is Llama, Mistral, Phi, or future families.
 * =================================================================== */

typedef enum {
    XMIND_ROLE_TOKEN_EMB   =  0u,  /* token embedding table            */
    XMIND_ROLE_ATTN_Q      =  1u,  /* attention query projection       */
    XMIND_ROLE_ATTN_K      =  2u,  /* attention key projection         */
    XMIND_ROLE_ATTN_V      =  3u,  /* attention value projection       */
    XMIND_ROLE_ATTN_O      =  4u,  /* attention output projection      */
    XMIND_ROLE_FFN_GATE    =  5u,  /* FFN gate / SwiGLU w1             */
    XMIND_ROLE_FFN_DOWN    =  6u,  /* FFN down projection / w2         */
    XMIND_ROLE_FFN_UP      =  7u,  /* FFN up projection / w3           */
    XMIND_ROLE_NORM_ATTN   =  8u,  /* RMSNorm before attention         */
    XMIND_ROLE_NORM_FFN    =  9u,  /* RMSNorm before FFN               */
    XMIND_ROLE_NORM_FINAL  = 10u,  /* final RMSNorm (output_norm)      */
    XMIND_ROLE_OUTPUT      = 11u,  /* output / language model head      */
    XMIND_ROLE_ROPE_COS    = 12u,  /* RoPE cosine table (if in GGUF)   */
    XMIND_ROLE_ROPE_SIN    = 13u,  /* RoPE sine table (if in GGUF)     */
    XMIND_ROLE_UNKNOWN     = 255u, /* unrecognized tensor               */
} xmind_tensor_role_t;

/* Number of per-layer roles (ATTN_Q through NORM_FFN) */
#define XMIND_ROLES_PER_LAYER  9u

/* Number of global roles (TOKEN_EMB, NORM_FINAL, OUTPUT, ROPE_COS, ROPE_SIN) */
#define XMIND_ROLES_GLOBAL     5u

/* ===================================================================
 * S2  ROLE MAPPING — Links a catalog tensor to a role + layer
 * =================================================================== */

typedef struct {
    xmind_tensor_role_t role;          /* canonical role                 */
    uint32_t            layer_index;   /* layer number (0 for global)    */
    uint32_t            tensor_index;  /* index into gguf_catalog_t.tensors[] */
} xmind_role_mapping_t;

/* ===================================================================
 * S3  WEIGHT PLAN — Complete mapping for a model
 *
 * Built by the artifact interpreter, consumed by the orchestrator.
 * Max capacity: 32 layers * 9 per-layer + 5 global = 293 roles.
 * =================================================================== */

#define XMIND_WEIGHT_PLAN_MAX  512u

typedef struct {
    xmind_role_mapping_t mappings[XMIND_WEIGHT_PLAN_MAX];
    uint32_t             count;       /* number of valid entries         */
    uint8_t              validated;   /* 1 if interpreter validated plan */
    uint8_t              _pad[3];
} xmind_weight_plan_t;

/* ===================================================================
 * S4  PLAN QUERY HELPERS
 * =================================================================== */

/*
 * xmind_plan_find — Find the first mapping with the given role + layer.
 *
 * @param plan   Weight plan to search
 * @param role   Role to match
 * @param layer  Layer index to match
 * @return       Pointer to matching entry, or NULL if not found
 */
const xmind_role_mapping_t *xmind_plan_find(
    const xmind_weight_plan_t *plan,
    xmind_tensor_role_t role,
    uint32_t layer);

/*
 * xmind_plan_count_role — Count mappings for a given role across all layers.
 */
uint32_t xmind_plan_count_role(const xmind_weight_plan_t *plan,
                                 xmind_tensor_role_t role);

#endif /* XMIND_TENSOR_ROLES_H */
