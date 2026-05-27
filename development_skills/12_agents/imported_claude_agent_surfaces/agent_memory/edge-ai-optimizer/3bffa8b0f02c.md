---
name: P1 AI Performance Audit -- XJIT + XMIND (H13, H14, H15, M28)
description: Comprehensive audit of XMIND memory leaks (H13/H15), inference pipeline correctness (H14), and AVX2 SIMD implementation (M28). All four items verified complete with two critical findings.
type: project
---

## P1 AI Performance Audit Results (2026-03-24)

### H13 (336MB memory leak per restart): VERIFIED COMPLETE
- Sprint 38: xm_heap_free() calls pal_unmap(mh) before pal_pages_free(ph) [xmind.c:92-93]
- Sprint 41: wl_free_all_pages() calls pal_unmap(mh) before pal_pages_free(ph) [weights_loader.c:533-536]
- xmind_weights_unload() orchestrates: NULL pointers -> xmind_shutdown -> wl_free_all_pages

### H14 (Zero real output): VERIFIED COMPLETE (with P1 vocab cap issue)
- Weights: Full GGUF tensor loader reads Q4_0 (f16->f32 scale conversion) and F32 tensors
- Forward pass: Complete Llama-style transformer (28 layers, GQA, SwiGLU, RoPE)
- Generation: Two-phase (prefill + autoregressive), real sampler with temperature/top-p
- **CRITICAL-01**: WL_TOK_MAX_VOCAB=32000 vs XMIND_VOCAB_SIZE=128256. Tokens >32K render as <UNK>.
- **CRITICAL-02**: bpe_token_str() is O(n) linear scan for detokenization. Needs hash table.

### H15 (heap_free is no-op): VERIFIED COMPLETE
- Real slab-tracked implementation since Sprint 10 (RA-XMIND-02)
- Sprint 38 added pal_unmap(mh) fix
- 128-slot slab covers max 63 inference state allocations

### M28 (No AVX2 vector support): VERIFIED COMPLETE
- avx2_dot.c: xjit_dot_f32_avx2 (YMM + VFMADD231PS), xjit_dot_q4_0_avx2 (fused dequant+dot)
- avx2_matmul.c: CPUID detection, JIT code emitter
- tensor.c: Runtime SIMD dispatch via function pointers (xmind_simd_init)
- Wired into: matmul_q4, dot, rmsnorm, attention scores, logit projection
- Predicted: ~8x speedup, ~14 TPS on i5-8250U

**Why:** These findings establish the baseline for XMIND inference performance going forward.

**How to apply:**
- H13/H15 are resolved. No further work needed.
- H14 requires WL_TOK_MAX_VOCAB increase to 128256 for Llama 3.2 compatibility.
- M28 needs real-hardware benchmark to validate predicted 14 TPS.
