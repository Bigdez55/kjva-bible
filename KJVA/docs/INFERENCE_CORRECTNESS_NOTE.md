# Implementation Note — XMIND Tokenless Inference Correctness

> This is an **implementation note**, not an ADR. The locked architecture authority is
> **ADR-0001** (neutral architecture) and **ADR-0002** (local path mapping). This note records
> bug fixes that make ADR-0002's **Inference Engine / Materialization Plane** (§3, §8) actually
> compute the trained model's function. It introduces no new architecture, taxonomy, pillar, layer,
> or authority.

## Why

The XMIND C inference engine (ADR-0002's Inference Engine) computed a *different function* than the
PyTorch trainer (`training/pt/model.py`). The prior `tests/test_pt_parity.py` only checked tensor
names/shapes, so it never caught it. Two silent bugs:

1. **RoPE convention.** `ai/xmind/src/tensor.c:xmind_rope` used llama-style **interleaved**
   `(q[2i], q[2i+1])`; the model trained **rotate-half** `(q[i], q[i+head_dim/2])`. No compensating
   permutation. → wrong attention (pt argmax `.`, xmind argmax `a`, logit MAE 1.68).
2. **Q4_0 scale.** `training/scripts/convert_to_gguf.py:quantize_q4_0` stored the block **max**
   (`absmax`) as the per-block scale, but the C decoder (`tensor.c:xmind_matmul_q4`) reconstructs
   `w = (nibble-8)·scale`, expecting the quantization **step** `absmax/7`. → every weight read 7× off
   (C logits ≈ −5.8 vs trainer ≈ −17, MAE 8.2).

## Fixes (bug fixes, not architecture)

- `tensor.c:xmind_rope` → rotate-half, matching `pt/model.py:apply_rope`.
- `convert_to_gguf.quantize_q4_0` → store `absmax/7`; `pt/eval_clean_ppl.py` dequant → `(nibble-8)·scale`.
- XMIND is tokenless-only: `interp_llama` removed from the registry/build (it does not conform to the
  tokenless rotate-half convention).
- `tests/test_pt_xmind_parity.py` — permanent numerical gate (pt forward == C forward logits, MAE<0.6).

## Evidence
Parity: T=1 `A` pt→xmind `n`→`n` MAE 0.098; full prompt `.`→`.` MAE 0.091. `pytest` → passed.
Deploy ppl via corrected GGUF = 2.7498 (unchanged; reconstruction-equivalent). GGUFs exported before
these fixes are broken on the C path and must be re-exported; the F32 safetensors are unaffected.

## Scripture grounding (product requirement, not architecture)
The model confabulates verbatim verses under free generation; accurate scripture is **retrieved exact**
from the corpus (`ai/tokenless-agent/src/retrieval/kjv_retrieval.py`, `generation_invoked=False`),
wired first in the agent. The LM never writes verse text. This realizes the retrieval/citation-gated
product surface; it adds no architecture beyond ADR-0001/0002.
