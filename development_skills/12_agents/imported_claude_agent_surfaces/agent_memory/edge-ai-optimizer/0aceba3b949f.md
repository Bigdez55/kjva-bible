# XMIND Sprint 15 Inference Correctness & Completeness Audit

**Date:** 2026-03-07
**Agent:** Apex Edge AI Optimizer
**Sprint:** 15
**Files Audited:** inference.c (NEW), weights_loader.c (FIXED), xmind.h, transformer.c, tokenizer.c, xmind.c, tensor.c, quantize.c, sampler.c

---

## Key Findings

### inference.c (Sprint 15 NEW) -- CORRECT, WELL-DESIGNED
- xmind_rope_precompute: REAL (not stub). Taylor series cos/sin, xm_powf for theta.
- xmind_preflight_check: Validates state + weight + KV pointers (layer 0 only -- P2 gap)
- xmind_session_create/destroy: Correct heap-tracked allocation
- xmind_infer_step: Correct forward + sample + position advance
- xmind_generate: Correct 2-phase (prefill + autoregressive), EOS stop, context budget

### weights_loader.c -- ALLOCATION SIZES CORRECT
- wq_size = 3072 * (3072/32) * 20 = 5,898,240 -- CORRECT
- wkv_size = 3072 * (768/32) * 20 = 1,474,560 -- CORRECT
- wup_size = 3072 * (8192/32) * 20 = 15,728,640 -- CORRECT (same bytes as 8192*96*20)
- wdn_size = 8192 * (3072/32) * 20 = 15,728,640 -- CORRECT
- cfg.n_kv_heads IS a real field (xmind.h line 120)
- BUG: No NULL check on per-layer wl_alloc_pages returns (P1)
- BUG: Comments describe transposed matrix shapes (doc bug, not runtime bug)

### Q4_0 Dequantization -- CORRECT
- (nibble - 8) * scale matches GGML Q4_0 spec
- Consistent between quantize.c and tensor.c matmul

### transformer.c -- CORRECT
- Full GQA attention with KV cache
- RoPE applied correctly using precomputed tables
- SwiGLU FFN (gate * sigmoid(gate) * up, then down proj)
- Weight-tied logit projection (fp32, P2 performance finding)
- Stack scratch 64KB in xm_ffn (P1-02 still unfixed)

### tokenizer.c -- BROKEN for real models
- Byte-level mode produces IDs 3-258 (not Llama BPE IDs)
- BPE dispatch function exists but is never called (dead code)
- Need GGUF vocab loading for real inference

---

## P0 Blockers for Functional Inference

1. **Zero weights** -- GGUF tensor data not loaded (buffers allocated but zero-filled)
2. **Tokenizer mismatch** -- byte-level IDs != Llama SentencePiece/BPE IDs

## P1 Issues

1. Weight loader: no NULL check on per-layer allocations
2. Preflight check: only validates layer 0 (layers 1-27 unchecked)
3. Stack overflow: 64KB in xm_ffn (gate[] + up[])
4. No streaming callback API
5. No concurrency protection

## Sprint 16 Minimum for First Inference Demo (~500 LOC)

1. GGUF tensor data loader (~200 LOC) -- parse tensor info, seek+read data
2. Minimal tokenizer fix (~300 LOC) -- GGUF vocab load or hard-coded test prompt
3. Weight alloc error checking (~30 LOC)

## Pipeline Status: STRUCTURALLY COMPLETE

load -> init -> alloc_state -> load_weights -> rope_precompute -> preflight ->
session_create -> generate (prefill + autoregressive) -> sample -> destroy

Broken only by zero weights and wrong token IDs. Math is correct throughout.
