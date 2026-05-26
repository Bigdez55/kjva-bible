/*
 * xmind_artifact_interp.h — Artifact Interpreter Interface
 *
 * Copyright (c) 2026 Tokenless Models Project. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-Proprietary
 *
 * PURPOSE:
 *   Defines the artifact interpreter vtable: a set of function pointers
 *   that a model-family module implements to translate a neutral GGUF
 *   catalog into an XMIND-ready model configuration.
 *
 *   The interpreter lifecycle:
 *     1. detect()       — Does this catalog belong to my family?
 *     2. build_config() — Extract xmind_config_t from catalog metadata
 *     3. map_tensor()   — Map each catalog tensor to a canonical role
 *     4. validate()     — Verify the weight plan is complete
 *
 *   Interpreters are registered via xmind_interp_register() and
 *   detected via xmind_interp_detect() (highest confidence wins).
 *
 * No libc.  Freestanding C11.  PAL types only.
 */

#ifndef XMIND_ARTIFACT_INTERP_H
#define XMIND_ARTIFACT_INTERP_H

#ifdef PAL_FREESTANDING
#include "../../../pal/include/pal.h"
#else
#include <stdint.h>
#include <stddef.h>
#endif

#include "xmind_gguf.h"
#include "xmind_tensor_roles.h"

/* xmind_config_t is defined in xmind.h.  The vtable uses void* for cfg_out
 * to avoid a circular include dependency.  Interpreter .c files include
 * xmind.h directly and cast from void* to xmind_config_t*. */

/* ===================================================================
 * S0  FFN LAYOUT TYPES
 *
 * Different model families use different FFN structures.  The layout
 * enum allows the orchestrator to handle allocation without assuming
 * a specific FFN shape (e.g., SwiGLU 3-matrix is Llama-specific).
 * =================================================================== */

typedef enum {
    XM_FFN_SWIGLU_3MAT = 0,  /* w1(gate) + w2(down) + w3(up) — Llama, Mistral */
    XM_FFN_GLU_FUSED   = 1,  /* gate_up_fused + down — Qwen2              */
    XM_FFN_2MAT        = 2,  /* up + down only — some Phi variants         */
} xmind_ffn_layout_t;

/* ===================================================================
 * S1  INTERPRETER VTABLE
 *
 * Each model family (Llama, Mistral, Phi, ...) implements one instance
 * of this struct with its detect/config/map/validate logic.
 * =================================================================== */

typedef struct xmind_artifact_interp_s {
    /*
     * family_name — Human-readable name (e.g. "llama", "mistral").
     * Used in diagnostics.  Must be a static string.
     */
    const char *family_name;

    /*
     * detect — Probe catalog metadata to determine if this file
     * belongs to the interpreter's model family.
     *
     * @param catalog  Parsed GGUF catalog
     * @return         Confidence 0..100 (0 = no match, 100 = certain)
     *
     * Multiple interpreters may return non-zero.  The registry picks
     * the highest confidence.  If two tie, the first registered wins.
     */
    uint32_t (*detect)(const gguf_catalog_t *catalog);

    /*
     * build_config — Extract model configuration from catalog metadata.
     *
     * Reads KV entries (e.g. "llama.block_count") and populates an
     * xmind_config_t.  The config must be fully populated — no zero
     * fields for required dimensions.
     *
     * @param catalog  Parsed GGUF catalog
     * @param cfg_out  Output config (caller-allocated, zeroed by callee)
     * @return         0 on success, negative on error
     */
    int32_t (*build_config)(const gguf_catalog_t *catalog, void *cfg_out);

    /*
     * map_tensor — Map a single catalog tensor to a canonical role.
     *
     * @param catalog       Parsed GGUF catalog
     * @param tensor_index  Index into catalog->tensors[]
     * @param role_out      Output role
     * @param layer_out     Output layer index (0 for global tensors)
     * @return              0 if mapped, -1 if unrecognized
     */
    int32_t (*map_tensor)(const gguf_catalog_t *catalog,
                           uint32_t tensor_index,
                           xmind_tensor_role_t *role_out,
                           uint32_t *layer_out);

    /*
     * validate — Verify the weight plan is complete for this family.
     *
     * Checks that all required roles are present for all layers,
     * dimensions are consistent, etc.
     *
     * @param catalog  Parsed GGUF catalog
     * @param plan     Populated weight plan
     * @param n_layers Number of layers expected
     * @return         0 if valid, negative error count
     */
    int32_t (*validate)(const gguf_catalog_t *catalog,
                         const xmind_weight_plan_t *plan,
                         uint32_t n_layers);

} xmind_artifact_interp_t;

/* ===================================================================
 * S2  REGISTRY API
 *
 * The registry is a static array of interpreter pointers.  Interpreters
 * are registered at init time (before any model load).
 * =================================================================== */

#define XMIND_MAX_INTERPS  16u

/*
 * xmind_interps_init — Register all built-in interpreters.
 * Must be called once before any model load.  Idempotent.
 */
void xmind_interps_init(void);

/*
 * xmind_interp_register — Register a custom artifact interpreter.
 *
 * @param interp  Pointer to interpreter vtable (must be static lifetime)
 * @return        0 on success, -1 if registry full
 */
int32_t xmind_interp_register(const xmind_artifact_interp_t *interp);

/*
 * xmind_interp_detect — Find the best interpreter for a catalog.
 *
 * Iterates all registered interpreters, calls detect() on each,
 * returns the one with highest confidence.
 *
 * @param catalog  Parsed GGUF catalog
 * @return         Pointer to best interpreter, or NULL if none matched
 */
const xmind_artifact_interp_t *xmind_interp_detect(
    const gguf_catalog_t *catalog);

/* ===================================================================
 * S3  BUILT-IN INTERPRETER EXTERNS
 *
 * Each built-in interpreter exports a registration function and a
 * static vtable pointer.  The registration functions are called by
 * xmind_interps_init().
 * =================================================================== */

/* Llama family interpreter (interp_llama.c) */
extern const xmind_artifact_interp_t xmind_interp_llama;

#endif /* XMIND_ARTIFACT_INTERP_H */
