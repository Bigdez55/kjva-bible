# Tokenless Neutral Byte Base — Model Card & Mass-Production Substrate

**Status:** TRAINED base **v1** — substrate + pipeline verified, and the shared base weights are
produced and benchmark-validated. Release tag: `models-v7-base-v1.0.0`.
**Identity:** intentionally **neutral** — no name, no persona, no domain. A domain model is
produced by forking this base, training on a domain corpus, and **naming it at derive time**.
This card is the canonical contract every derived project (database / transportation /
healthcare / …) starts from, so the substrate is built **once**.

## Base v1 — validated result

Trained on the **clean** KJV+Apocrypha verse corpus (`eng_kjv_clean_v1`, 36,822 verses, 0 markers),
then **model-souped** (uniform average of checkpoints 1500/2000/2500/3000). Scored against the prior
benchmark model on **identical held-out clean scripture** with a scorer validated to reproduce that
model's published 3.2125 to four decimals:

| Artifact | clean_val ppl | vs prior benchmark (3.2784) |
|---|---|---|
| `soup_best.safetensors` (F32, canonical) | **2.7258** | **−16.86%** (conservative floor) |
| `clean_base_soup_v1.gguf` (Q4_0, XMIND deploy) | **2.7498** | −16.1% (≈0.9% quant cost) |

The −16.86% is a floor: clean_val is fully held out from this model; every measured asymmetry favors
the older model. Independently re-verified by a 4-auditor adversarial workflow (soup reproduced twice;
harness sound; comparison fair; artifacts contract-correct). Full detail: `docs/CLEAN_BASE_v1_RESULT_2026-05-31.md`.
*(Note: open-ended generation verse-hops, as expected for an 18.98M byte-LM — the product surface is
retrieval/citation-gated, not free generation. Perplexity is the metric of record.)*

---

## 1. What is frozen here

This is the reusable **base**: a verified, identity-neutral byte-level transformer + its full
training/inference pipeline. Everything needed to mass-produce named domain models, minus the
domain corpus and the name (both applied per project).

| Component | State |
|---|---|
| Architecture (immutable spec §8.6) | **18,980,352 params** · 8 layers · d_model 384 · 6 heads · FFN 1536 · ctx 1024 · vocab 259 · RoPE 10k · RMSNorm · SwiGLU · tied embeddings |
| Tokenizer | UTF-8 byte-level, token = byte+3, vocab 259 (PAD 0 / BOS 1 / EOS 2) — **tokenizer-free** |
| Tensor contract | 74 tensors; PyTorch state_dict keys == `safetensors_to_gguf` GGUF mapping (parity-tested) |
| Training | PyTorch (`training/pt/`), portable Docker (CPU↔CUDA) |
| Inference | XMIND C engine + GGUF (loads the PyTorch-exported model unchanged — proven) |
| Adaptation | Omni-PEFT: 8 families, 23 resolvable methods + v2 layer (IR/genome/algebra/tournament/plasticity/determinism/proofs) |
| Adapter runtime | XMIND C adapter dispatch (no-op-safe) wired into inference |
| Cognitive runtime | covenant fail-closed, Heptagon L1–L7, §12 evidence pipeline, sensory + memory |

**Verification at freeze:** 42/42 tests pass; Apex §22 acceptance 9/9 + latency; XMIND `make test`
PASS; companion `vite build` clean; zero DO_NOT_MODIFY edits. See `docs/BUILD_v8_COMPLETE_REPORT_2026-05-31.md`.

## 2. Why neutral (the mass-production principle)

The base carries **no identity** so it can become **any** identity cheaply:
```
neutral base  +  domain corpus  +  NAME  =  named domain model
```
The name is **not a code feature** — it is a parameter applied at export/derive time
(`general.name` / `general.domain` in the GGUF). This is what lets one substrate spawn
TransitGPT, a healthcare model, a database model, etc., without rebuilding anything.

## 3. How the shared base weights were produced (base v1)

The **shared base weights** are the model soup above, produced on Apple-Silicon GPU (MPS) from the
clean corpus — the reproducible recipe:

```bash
# train on the CLEAN verse corpus (markerless), Apple GPU, crash-safe
python3 training/pt/train_byte.py --run-id byte_clean_v1 \
    --corpus training/corpus/eng_kjv_clean_v1/corpus.txt \
    --token-cache training/corpus/eng_kjv_clean_v1/tokens_byte_uint16.npy \
    --iters 5000 --batch 8 --seq-len 1024 --save-every 500 --device mps --resume
# pick best-val checkpoints by the deterministic full-pass scorer, then soup them:
#   uniform mean of ckpt_step_{1500,2000,2500,3000} -> soup_best.safetensors  (clean_val 2.7258)
python3 training/pt/export.py --checkpoint training/runs/byte_clean_v1/soup_best.safetensors \
    --config  training/runs/byte_clean_v1/model_config.json \
    --vocab   training/runs/byte_clean_v1/byte_vocab.json \
    --output  training/gguf/clean_base_soup_v1.gguf            # Q4_0 deploy, clean_val 2.7498
```
Measure any checkpoint/soup on the fixed held-out set with `training/pt/eval_clean_ppl.py`
(`score` / `compare` / `gate-a` / `gate-b`). **The corpus is `eng_kjv_clean_v1` (clean verses),
NOT the marker-polluted `eng_kjv_apocrypha_v1`** — training on markers was the defect this base fixes.

## 4. Mass-producing a NAMED domain model

One command per domain — no substrate work:
```bash
training/spawn_domain_model.sh \
    --name TransitGPT --domain transportation \
    --corpus path/to/transit_corpus.txt \
    --base-run training/runs/tokenless_base_v1 \
    --steps 500
```
Produces: a **named** GGUF (`general.name=TransitGPT`), a validated domain PEFT adapter, and a
domain model card. Deploy the GGUF in the XMIND runtime; the adapter applies via the adapter
runtime. Repeat with `--name HealthScribe --domain healthcare …`, etc.

## 5. Optimize / prune (per domain or for the base)

After a domain model trains, run benchmarks then optimize (Omni tournament-v2 Pareto, quantization
Q4_0/Q4_K_M, latency tuning, prune unused PEFT methods). This is the post-training loop; it does
not change the frozen substrate contract.

## 6. Reproducibility / provenance

- Frozen at git tag **`models-v7-base-v1.0.0`** (commit on `main`).
- Architecture is parity-locked: any export must yield 74 tensors / 18,980,352 params or it is
  not this base (`tests/test_pt_parity.py` enforces it).
- Weights/GGUF are gitignored in-repo. **As of 2026-06-01 the weights are kept LOCAL** (free-tier
  HF private-storage quota was exhausted); this private repo currently holds only this card + config +
  vocab. The weight LFS files will be pushed here once storage is resolved. The SHA256s below are for
  the **local** artifacts (the source of truth):
  - `soup_best.safetensors` (local) = `531966b642ec7abc376577dd3f09b43b6121f30491fe54cb1f87fbab539f8a45`
  - `clean_base_soup_v1.gguf` (local) = `d767788369aec90b7dfd61c70a90384033d4110d845e87733d4dee0116491bdf`
- Corpus: `eng_kjv_clean_v1/corpus.txt` (36,822 verses, 0 markers, 0 dupes). Soup = uniform mean of
  byte_clean_v1 checkpoints {1500,2000,2500,3000}. Scorer/gates: `training/pt/eval_clean_ppl.py`.
