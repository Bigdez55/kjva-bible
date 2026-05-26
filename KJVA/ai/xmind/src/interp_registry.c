/*
 * interp_registry.c — Artifact Interpreter Registry
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Manages the static array of registered artifact interpreters.
 *   Provides init (registers built-ins), register (custom), and
 *   detect (iterate all, return highest confidence).
 *
 *   Also implements xmind_plan_find() and xmind_plan_count_role()
 *   from xmind_tensor_roles.h, since these are small functions
 *   needed by both the registry and individual interpreters.
 *
 * No libc.  Freestanding C11.  PAL types only.
 *
 * S1  Registry state
 * S2  xmind_interps_init
 * S3  xmind_interp_register
 * S4  xmind_interp_detect
 * S5  Weight plan query helpers
 */

#ifndef PAL_FREESTANDING
#define PAL_FREESTANDING
#endif
#include "../include/xmind_artifact_interp.h"

/* ===================================================================
 * S1  REGISTRY STATE
 * =================================================================== */

static const xmind_artifact_interp_t *s_interps[XMIND_MAX_INTERPS];
static uint32_t s_interp_count = 0u;
static uint8_t  s_initialized  = 0u;

/* ===================================================================
 * S2  xmind_interps_init — Register all built-in interpreters
 *
 * Idempotent.  Safe to call multiple times.
 * Registers Llama first (the primary model family for Tokenless Models).
 * =================================================================== */

void xmind_interps_init(void) {
    if (s_initialized) return;
    s_initialized = 1u;
    s_interp_count = 0u;

    /* Register built-in interpreters */
    xmind_interp_register(&xmind_interp_llama);

    pal_console_printf("[INTERP-REG] initialized: %u interpreters\n",
                       s_interp_count);
}

/* ===================================================================
 * S3  xmind_interp_register — Add an interpreter to the registry
 * =================================================================== */

int32_t xmind_interp_register(const xmind_artifact_interp_t *interp) {
    if (!interp) return -1;
    if (s_interp_count >= XMIND_MAX_INTERPS) {
        pal_console_printf("[INTERP-REG] registry full (%u slots)\n",
                           XMIND_MAX_INTERPS);
        return -1;
    }
    s_interps[s_interp_count] = interp;
    s_interp_count++;
    return 0;
}

/* ===================================================================
 * S4  xmind_interp_detect — Find best interpreter for a catalog
 *
 * Iterates all registered interpreters.  Each calls detect() on the
 * catalog.  Highest confidence wins.  On tie, first registered wins.
 * =================================================================== */

const xmind_artifact_interp_t *xmind_interp_detect(
    const gguf_catalog_t *catalog) {
    if (!catalog) return (const xmind_artifact_interp_t *)0;

    /* Auto-init if not yet done */
    if (!s_initialized) { xmind_interps_init(); }

    const xmind_artifact_interp_t *best = (const xmind_artifact_interp_t *)0;
    uint32_t best_conf = 0u;

    uint32_t i;
    for (i = 0u; i < s_interp_count; i++) {
        if (!s_interps[i] || !s_interps[i]->detect) continue;
        uint32_t conf = s_interps[i]->detect(catalog);
        if (conf > best_conf) {
            best_conf = conf;
            best = s_interps[i];
        }
    }

    if (best) {
        pal_console_printf("[INTERP-REG] detected family: %s (conf=%u)\n",
                           best->family_name ? best->family_name : "?",
                           best_conf);
    } else {
        pal_console_printf("[INTERP-REG] no interpreter matched catalog "
                           "(arch=%s)\n",
                           catalog->arch_len > 0u ? catalog->arch : "<none>");
    }

    return best;
}

/* ===================================================================
 * S5  WEIGHT PLAN QUERY HELPERS
 *
 * Implemented here so both the registry and interpreters can use them
 * without circular dependencies.
 * =================================================================== */

const xmind_role_mapping_t *xmind_plan_find(
    const xmind_weight_plan_t *plan,
    xmind_tensor_role_t role,
    uint32_t layer) {
    if (!plan) return (const xmind_role_mapping_t *)0;
    uint32_t i;
    for (i = 0u; i < plan->count; i++) {
        if (plan->mappings[i].role == role &&
            plan->mappings[i].layer_index == layer) {
            return &plan->mappings[i];
        }
    }
    return (const xmind_role_mapping_t *)0;
}

uint32_t xmind_plan_count_role(const xmind_weight_plan_t *plan,
                                 xmind_tensor_role_t role) {
    if (!plan) return 0u;
    uint32_t count = 0u;
    uint32_t i;
    for (i = 0u; i < plan->count; i++) {
        if (plan->mappings[i].role == role) { count++; }
    }
    return count;
}
