# models v7 — Complete Build Report (Phases 0–9)

**Date:** 2026-05-31 · **Plan:** wire everything → train → benchmark → optimize
**Source of truth:** `docs/UNIFIED_MASTER_TECH_PACK.md` + the two audit reports.
**Verification discipline:** verify-validate + audit-assess-analyze + source-of-truth-reconciliation at every milestone.

## Headline

The complete build is wired and verified end-to-end. **42/42 tests pass** across all
subsystems (including the pre-existing Apex §22 acceptance **9/9 + latency** with **zero
regression** at every phase). The decisive proof: a **PyTorch-trained model → safetensors
→ GGUF → XMIND C engine loads + generates** — the training framework changed (MLX→PyTorch,
Docker-portable) while the GGUF/XMIND inference runtime is byte-for-byte unchanged.

## What was built, per phase (all committed)

| Phase | Deliverable | Gate | Commit |
|------|-------------|------|--------|
| 0 | Portable Docker training env (PyTorch CPU↔CUDA) | image builds | e98f17c |
| 1 core | PyTorch `TokenlessLM` port + train_byte + export + corpus G1 | parity 2/2; **18,980,352 params, 74-tensor contract** | e98f17c |
| 1 PEFT | PyTorch PEFT catalog (8 families) + train_peft + attach | gradflow 7/7 (grads flow, base frozen) | 7b8054e |
| 2 | Omni-PEFT++ v2 (IR/genome/algebra/plasticity/tournament/determinism/proofs) | 8/8, imports w/o torch+mlx, 6 proofs | 2891259 |
| 3 | Cognitive runtime fixes: covenant fail-closed + Heptagon L6 | covenant 2/2; acceptance 10/10 | c482042 |
| 4 | Sensory evidence + extended memory + §12 Level-1 wiring | 6/6; acceptance 10/10 | 8c45133 |
| 5 | XMIND adapter C-runtime + inference apply (no-op-safe) | `make` 0-err; acceptance 10/10 | 022cf4e |
| 6 | Companion provenance UI | `vite build`+`tsc` 0 errors | 3e519c7 |
| 7 | Doc drift reconciliation (M5–M8) + PyTorch/Docker README | docs | e5280ff |
| 8 | Train: pretrain→export→GGUF→PEFT→validate (end-to-end) | adapter validate 7/7 | c2e636b |

## Gap/defect ledger — final status

- **G1 corpus slot** — wired (eng_kjv_apocrypha_v1). ✅
- **G3–G8 Omni-PEFT v2** — built (8 modules + proofs, pure-python). ✅
- **G8 XMIND adapter runtime** — built + wired into transformer.c (no-op when inactive). ✅
- **M1–M4 PEFT defects** — resolved by construction in the PyTorch port (adapters are real
  submodules → gradients flow; safetensors load; config-from-checkpoint; byte+3). ✅
- **Covenant bypass (CRITICAL)** — fixed at the caller, fail-closed; contract test locks it. ✅
- **Heptagon L6 dead** — fixed (`ParameterCalibrator(entity_id=...)`). ✅
- **Sensory + experience_atom/recall_trail/lifespan_ledger ABSENT** — built. ✅
- **Companion provenance ABSENT** — built. ✅
- **M5–M8 doc drift** — reconciled (canonical values fixed). ✅
- **DO_NOT_MODIFY** — zero protected files modified across all phases. ✅

## End-to-end training loop (proven, local CPU, bounded)

```
pretrain byte_proof (120 steps)  loss 5.68 → 2.17   val_ppl 12.58 → 9.15
  → pt/export.py → GGUF (74 tensors, 18,980,352 params)
  → XMIND xmind_easy_init → LOADS (tokenless_lm conf=100, 8 layers validated) → GENERATES 24 tokens
  → pt/train_peft.py LoRA → adapter (loss 2.25 → 2.02)
  → validate_adapter.py check → PASS (7/7 gates)
```

## Final verification (this report)

- `pytest` (parity+gradflow+v2+sensory/memory+covenant+substrate+apex) → **42 passed**.
- `make -C ai/xmind test` → **PASS** (0-error build).
- Apex §22 acceptance **9/9 + latency** — unchanged from the start (no regression).
- `verify-validate`: build clean, mlx/torch separation clean, no tracked binaries, no DO_NOT_MODIFY edits.

## Remaining (Phase 8 full run + Phase 10 optimize)

1. **Full pretrain** — the 5000-iter run to `val_ppl ≤ 3.21` is CPU-bound (~hours) and is
   intended for the **cloud/GPU Docker host** (`run_train.sh full`, `--gpus all`). The portable
   image + pipeline are ready; only compute is pending. The 120-step proof confirms convergence behavior.
2. **pt-adapter → XMIND-adapter name bridge** — the XMIND adapter runtime is wired and no-op-safe;
   applying a *PyTorch-trained* adapter in XMIND needs a tensor-name mapping (pt `blocks.N.attn.q.A`
   → GGUF `blk.N.attn_q`). Tracked for Phase 10.
3. **Phase 10 optimize/prune** — driven by full-run benchmark numbers: framework cost/throughput,
   quantization, latency-plateau tuning, prune unused long-tail methods.

## How to run the full training (when GPU host is available)

```bash
# build the CUDA image and run the full pretrain on a Linux+GPU host
cd "models v7"
TORCH_VARIANT=cu121 docker build -t tokenless-train:cu121 -f training/docker/Dockerfile .
GPU=1 TORCH_VARIANT=cu121 training/docker/run_train.sh full
# then: pt/export.py → GGUF → promote_base_model.py → wire_base.sh → benchmark_byte / validate_apex
```
