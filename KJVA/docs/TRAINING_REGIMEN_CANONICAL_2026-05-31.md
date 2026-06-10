The advisor confirmed the approach and flagged the critical traps. Writing the canonical document now as my final response.

# Model Build & Training Regimen — Canonical Spec & Actual-State Reconciliation

**Source of truth:** `models v7/docs/UNIFIED_MASTER_TECH_PACK.md` (11,469 lines), v1.0.0 DRAFT, consolidation dated 2026-05-30.
**Verified runtime context:** operational runtime = XMIND (freestanding C) + GGUF + numpy. MLX is the *optional training-only* workspace (not importable in this environment).
**Canonical model:** §8.6 Byte-Level Substrate Model — an 18.98M-param byte-level transformer sourced from `kjva-bible`.

**Citation discipline:** `L####` = a line in UNIFIED_MASTER_TECH_PACK.md (spec). `file:line` = a code/artifact claim (actual state). Where they disagree, the spec's *definitional* sections (§8.6/§4) win by line precedence; realized-state divergences are numbered as gaps (G#) / defects (M#) in §8.

---

## 0. Decoy Models — DO NOT CONFLATE

The spec describes four distinct model specifications. Only one is the canonical trained artifact. Three decoys must never leak into the architecture table:

| # | Spec object | What it is | Why NOT this model | Line ref |
|---|-------------|------------|--------------------|----------|
| ✅ | **§8.6 Byte-Level Substrate** | The realized 18.98M byte model | **This IS the model** | L1168–1190 |
| ✗ D1 | §8.5 XMIND-1 Native | On-device GGUF *target* (24L, 16Q/4KV GQA, vocab 32768, d1024, ffn2816, seq4096, RoPE 100000, Q4_0) | Larger unrealized native target; true GQA + BPE vocab | L1150–1166 |
| ✗ D2 | §8.7 Llama 3.2 3B | Memory-budget *illustration* (~2.42 GB @ Q4_0) | Illustrative sizing table only | L1192–1204 |
| ✗ D3 | §14.4 XMIND_* engine ceilings | Engine *capacity limits* (MAX_LAYERS 32, MAX_HEADS 32, MAX_SEQ 8192, VOCAB_SIZE 128256) | Llama-class engine maxima, not a model config | L1624–1639 |

---

## 1. Model Architecture

Canonical = §8.6 (spec) triple-confirmed against `models v7/training/gguf/model.gguf.json`, `kjva-bible/KJVA/training/model_config.json`, and the parsed GGUF binary (74 tensors).

| Parameter | Spec value | Actual value (realized) | Source (spec / actual) | Divergence |
|-----------|------------|-------------------------|------------------------|------------|
| Model class | byte-level decoder-only transformer | tokenless_lm GGUF, slot 1 | L1170 / model.gguf.json:30 | — |
| Parameters | "18M" (rounded) | **18,980,352** (18.98M) | L1175 / model.gguf.json:28 | rounding only |
| Vocabulary | 259 (256 bytes + PAD/BOS/EOS) | 259 | L1177 / model.gguf.json:19 | — |
| Layers | 8 | 8 | L1178 / model.gguf.json:8 | — |
| d_model | 384 | 384 | L1179 / model.gguf.json:10 | — |
| FFN intermediate | 1,536 (SwiGLU) | 1,536 | L1180,L1091 / model.gguf.json:11 | — |
| Attention heads | **(silent)** | **6 (MHA; head_dim 64; head_count_kv == 6)** | §8.6 silent / model.gguf.json:9 | **G-arch-1: spec omits head count** |
| Max seq / context | **(silent)** | **1024** | §8.6 silent / model.gguf.json:13 | **G-arch-2: spec omits seq len** |
| RoPE base | 10,000 | 10,000.0 | L1181 / model.gguf.json:14 | — (≠ D1's 100,000) |
| Norm | RMSNorm, pre-norm, eps 1e-5 | RMSNorm eps 1e-5 | L1712 / model.gguf.json:16 | — |
| Activation | SiLU/SwiGLU | SiLU·gate × up → down | L1091,L1713 / model.py SwiGLU | — |
| Embeddings | weight-tied logits (no output.weight) | tie_embeddings=true | L1092,L3826 / model.gguf.json:15 | — |
| init_std | (silent) | 0.02; residual-proj scaled by 1/√(2·n_layers) | — / model.py init_weights | INTENDED (code only) |
| Causal mask | additive triu −1e9 (k=1) | same | — / model.py:173 | — |
| Attn scale | 1/√head_dim | same | — / model.py:109 | — |
| Weight precision | F32 ships; Q4_0/Q4_K_M engine paths | F32 (file_type 0); both matmul paths exist | L3831–3845 / model.gguf.json:6 | — |
| Tensor count | — | 74 | — / model.gguf.json:27 | — |
| File size | — | 10.53 MB (11,046,112 B) | — / model.gguf.json:29 | — |

**Exact param derivation (verifies 18,980,352):** emb(259·384) + 8·(4·384² + 3·384·1536 + 2·384) + 384, tied embeddings. Recomputed diff = 0.

**Template-default divergence (never realized):** `model.py ModelConfig` defaults `vocab_size=16000, n_layers=6, max_seq_len=512` (BPE-era substrate defaults); `train_byte.py` overrides to 259/8/1024. Only the seq 512 default is a real-but-overridden divergence; all else agrees (model.py:31–36).

---

## 2. Pretraining Regimen

**Critical honesty flag:** The spec specifies **ZERO byte-model training hyperparameters** — no optimizer, LR, schedule, batch, steps, seed. Every optimizer/schedule row below is **INTENDED (from `train_byte.py` defaults), NOT spec-mandated, and NOT verified against the producing run** (kjva-bible contains no `train_log.jsonl` or `*.meta.json`). They are the *canonical intended* regimen, corroborated only circumstantially (default `--iters 5000` matches spec's "step 5000").

| Aspect | Spec | INTENDED / actual (train_byte.py) | Source |
|--------|------|-----------------------------------|--------|
| Objective | next-byte LM (implied) | NLL over 259 vocab; logits − logsumexp | train_byte.py:55–80 |
| Tokenization | token = byte+3 (PAD0/BOS1/EOS2) | uint8 → uint16 +3 | L1184 / train_byte.py:55 |
| Init | — | random; no pretrained load | train_byte.py:159–167 |
| Optimizer | — | **AdamW, betas [0.9, 0.95], eps 1e-8, weight_decay 0.1** | train_byte.py:120–132,210 |
| LR schedule | — | **linear warmup 200 → cosine decay; lr_max 3e-4, lr_min 3e-5** | train_byte.py:83–89 |
| Grad clip | — | max_norm 1.0 | train_byte.py:131 |
| Batch / seq | — | batch 8 / seq 1024 | train_byte.py:122,134 |
| Steps | "step 5000" (artifact label) | iters 5000 | L1176 / train_byte.py:117 |
| Seed | — | 42 | train_byte.py:137 |
| Val split | — | 2% (min 4096 tokens) | train_byte.py:62–64 |
| Eval/save cadence | — | eval-every 200, save-every 500, log-every 10 | train_byte.py:129–131 |
| Checkpoint provenance | — | corpus_sha256, byte_vocab_sha256, checkpoint_sha256, config, random_init=true | train_byte.py:159–318 |
| Inline bench | ckpt_bench at every save (AGENTS.md) | wired | train_byte.py (ckpt_bench call) |
| **val_ppl target** | **3.21 (step 5000)** | observed **~3.05** for shipped model.gguf | L1176 vs L3796 → **M5 (conflict)** |

A second pretraining path exists for the BPE variant: `train.py` (omni `scratch.bpe_lm`, SentencePiece byte-fallback). No BPE run realized.

---

## 3. Training Styles / PEFT Catalog

### 3.1 Omni-PEFT OS baseline (realized)
- **44 registered / 42 implemented methods** (spec L6836, L8077); registry `omni_training_registry.json` status counts = **40 implemented / 2 planned / 2 extension_spec**; `train_peft.py` self-describes as **"37 PEFT/alignment/distillation methods"**; actual **43 DeltaOperator code modules**. *(Four numbers — see §8 M6 reconciliation; none silently picked.)*
- Components: registry/program layer, PEFT OS module, Task Fingerprinter, PEFT Compiler, Training Tournament, Hierarchical Runtime Router, Adapter Genome System, `--method omni` (L6838–6845).

### 3.2 Omni selection pipeline (realized v1)
`--method omni` = **Fingerprinter → Compiler → Tournament → Pareto** (L6848). Runtime router = **Task → Domain → Layer → Budget → Safety** (L6854; router.py top_k=2).

- **TaskFingerprinter** escalation by DomainShift: NONE→[ia3,bitfit]; LOW→[ia3,lora,bitfit]; MEDIUM→[lora,adalora,ia3]; HIGH→[lora,adalora,dora]; VERY_HIGH→[dora,adalora,houlsby] (fingerprint.py:163–195).
- **Compiler** "cheapest sufficient change": rank-by-shift {NONE(1,4),LOW(4,8),MED(8,16),HIGH(16,32),VHIGH(32,64)}, alpha=2·rank, budget gate max_trainable_params=10M, substrate=qlora if train_vram<12000 (compiler.py:110–203).
- **Tournament v1** (5-objective Pareto): domain_accuracy 0.35, base_retention 0.25, params 0.15, latency 0.15, merge_safe 0.10 (tournament.py:49–73). Constraints: retention_requirement 0.92, HardwareBudget 16GB M2 (base.py:244–260).

### 3.3 Method catalog (key hyperparams; targets = attn.{q,k,v,o} + mlp.{gate,up,down}; embeddings frozen; layernorm→bitfit only)

| Family | Methods (id) | Key defaults |
|--------|-------------|--------------|
| Low-rank | lora, dora, adalora, pissa, olora | rank 8, alpha 16, scaling α/r; A Kaiming / B zeros |
| Low-rank variants | rslora (α/√r), vera (rank 64, frozen A/B, train d&b), loha (r 4, α/r²), lokr (r 4, factor 4), rosa (r 4, sparsity 0.01) | per-method |
| Quantized | qlora | rank 8, bits 4 |
| Additive | houlsby (bottleneck 64, after attn+ffn), pfeiffer (after ffn) | 2·d·bottleneck params |
| Prompt | prompt_tuning (n=20), prefix_tuning (n=32 per-layer KV), p_tuning (encoder 512) | — |
| Activation | ia3 (l_k,l_v,l_ff vectors) | ~3k params |
| Selective | bitfit (bias only), diffpruning (L0 mask), fishmask (Fisher), far | sparsity ~0.01 |
| Hybrid | unipelt, mam_adapter, compacter (Kronecker), xlora (4 experts + router) | — |
| Structural | **oft, boft, fourier_ft** | **in code, ABSENT from registry → M7 drift** |
| Alignment | sft, dpo (β 0.1), ipo (β 0.1), kto (β 0.1, λd/λu), orpo (λ 0.1) | — |
| Alignment-RL | ppo_rlhf (clip 0.2, vc 0.5, ec 0.01), grpo (clip 0.2, β 0.04) | — |
| Distillation | distill_logit, distill_sequence | dispatched via SFTTrainer |

### 3.4 §8 Omni-PEFT++ upgrade (SPEC-MANDATED, mostly UNREALIZED)
- **AdapterIR**: every method compiles to op_kinds (16–18 variants: low_rank_delta, multiplicative_gate, additive_adapter, prompt_prefix, sparse_mask, quantized_delta, orthogonal_transform, fourier_transform, block_diagonal_delta, granular_block_delta, router_mixture, activation_scale, …) (L7778–7824). **Not in code → G3.**
- **AdapterGenome v2**: signed (ed25519 by model_training_authority), hashed (base/training/fingerprint/IR sha256), scoped (companion_layer/heptagon_region/sensory/authority/privacy), eval_results gate (domain_accuracy, base_retention, calibration_error, safety_retention, latency_overhead, conflict_score), deployment status=shadow + rollback (L7826–7878). **v1 genome implemented; v2 not → G4.**
- **Adapter algebra** (14 ops incl. compose/diff/distill(A,B→C)/conflict_detect/authority_bound/rollback) (L7884–7898). **adapter_algebra.py listed L8145 but absent → G5.**
- **Layer-bound plasticity map** (L1–L7): L1 trainable-tokens/prefix/aLoRA; L2 IA3/BitFit/LN; L3 LoRA/IA3/reranker; L4 DoRA/AdaLoRA/GraLoRA/PSOFT; L5 LoRA/AdaLoRA/Lily/Arrow; L6 aLoRA/IA3/TinyLoRA; **L7 conservative LoRA/IA3/BitFit only, proof-gated, no aggressive merges** (L7959–7967; L10430–10436). **layer_plasticity.py absent → G6.**
- Method ontology (family, adaptation_kind, injection_sites, merge/runtime_behavior, risk_profile, proof_obligations) — spec-only (L7740–7772).

### 3.5 Tournament v2 — TWO version-scoped specs (DO NOT MERGE)

These are different consolidated packs. Present version-scoped:

| | V3 §8 sovereign score (L7919–7935) | V4 §9 profile (L10463–10479) — **later** |
|---|---|---|
| Terms | 12 | 11 |
| domain_accuracy | 0.18 | 0.18 (domain/layer) |
| base_retention | 0.14 | 0.14 |
| calibration | 0.10 | 0.11 (Brier) |
| safety_retention | 0.10 | 0.11 (covenant) |
| source_grounding | 0.08 | — |
| memory_writeback_safety | 0.07 | 0.09 |
| sensory precision/recall | — | 0.08 |
| latency_efficiency | 0.08 | 0.07 |
| trainable_param_efficiency | 0.07 | 0.06 |
| out_of_domain_humility | 0.05 | 0.07 |
| merge_safety | 0.04 | 0.05 |
| conflict_resistance | 0.06 | 0.04 |
| deterministic_reproducibility | 0.03 | — |

Both sum to 1.00. V3 adds 12 lanes (incl. determinism/reproducibility); V4 adds 9 adversarial lanes (identity-drift, memory-injection, false-sensory, privacy, prompt-injection-in-OCR). **`tournament_v2.py` not present → G7.** Governing laws: "No training without tournament. No deployment without shadow. No evolution without rollback." (L8518).

---

## 4. Distillation & Alignment

| Method | Family | When used | Data requirement | Source |
|--------|--------|-----------|------------------|--------|
| SFT | alignment | base for distill | prompt/response, ignore_index −100 | sft.py:42 |
| DPO / IPO | preference | preference tuning | chosen/rejected pairs, β 0.1 | dpo.py/ipo.py |
| KTO | preference | binary-label prefs | desirable/undesirable, λu≈2λd | kto.py:56 |
| ORPO | SFT+pref | combined | odds-ratio, λ 0.1 | orpo.py:49 |
| PPO-RLHF | RL | reward-model RLHF | reward_model | ppo_rlhf.py:56 |
| GRPO | RL | group-relative | reward_signal, β 0.04 | grpo.py:55 |
| distill_logit | distillation | match teacher logits | teacher logit distributions | omni_registry:826 |
| distill_sequence | distillation | learn teacher outputs | teacher-generated sequences | omni_registry:826 |

Named training-data families (L10440–10461): sensory_event, memory_recall, world_model, planning, **self_correction (draft→flaw→correction→final)**, governance, companion_style. Both distillation methods dispatch through `SFTTrainer` (train_peft.py:120). All alignment methods operate over the base as objectives, not per-layer operators (train_peft.py).

---

## 5. Corpus

### 5.1 Canonical identity (what the model WAS built on)
**`eng_kjv_apocrypha_v1`** (KJV + Apocrypha). **Present in-tree** at `ml-training/corpus/eng_kjv_apocrypha_v1/` (verified): corpus.txt (5,464,844 chars / 5.46 MB / 46,355 lines), verses.jsonl (36,822 records / 23.9 MB), byte_vocab.json, manifest.json, retrieval_index.json (25 MB), validation_report.json.
- 80 books, 1,362 chapters, 36,822 verses (OT 23,145 / Apocrypha 5,720 / NT 7,957) (manifest.json:12–22).
- corpus.txt format: `<|source:kjv:<canon>:<BOOK>:<chapter>|>` + Book/Chapter/Canon headers + verse text.
- Built by `ml-training/scripts/build_kjv_corpus.py` from `eng-kjv_vpl.xml` (primary) + `.txt` (crosscheck); HTML/browserBible used ONLY for retrieval enrichment. Full SHA-256 input/output chain in manifest; validation pass=true (xml==vpl==36,822, 0 mismatches, 7/7 anchors).

### 5.2 Required format (the corpus SLOT)
The substrate ships **corpus-NEUTRAL**. Consuming project drops `corpus/<corpus-id>/corpus.txt` (required) + optional verses.jsonl, byte_vocab.json, manifest.json, retrieval_index.json, validation_report.json; `tokens_byte_uint16.npy` generated on first train (uint16 because vocab 259 > uint8 max 255).
- Spec default placeholder id = `domain_corpus_v1` (workspace_manifest `current_corpus_id`).
- Template-vs-actual split is encoded in two diverging `omni_training_programs.jsonl`: models v7 ships neutral `corpus.domain_builder` (extension_spec); ml-training ships concrete `corpus.kjv_apocrypha` (implemented).

### 5.3 Actual presence/absence
- **`models v7/training/corpus/` contains NO real corpus** — only README.md + programs/ (verified). No `domain_corpus_v1/`, no corpus.txt → **G1**.
- Corpus quality gates (retrain recipe, Bible_Tokenless_POC, DO-NOT-MODIFY): direct_citation_min 1.0, natural_top3_min 0.90, apocrypha_top3_min 0.90, byte_ppl_ratio_max 1.25.
- **NEGATIVE FINDINGS:** No corpus-level data sharding (all "shards" are RT4 memory-retrieval, MAX_SHARDS 7 / threshold 0.30). No MTD/SUM aggregation, no medallion/gold-silver-bronze tiers — those belong to an unrelated KPI domain skill (0 spec hits).

---

## 6. Tokenizer

Tokenizer-free UTF-8 byte scheme. **THREE vocab regimes — do not conflate:**

| Regime | Vocab | Use | Source |
|--------|-------|-----|--------|
| **(1) byte-level — THE model** | **259** (256 bytes + PAD0/BOS1/EOS2, byte_offset 3, kind utf8_byte, token=byte+3, zero OOV) | shipped model | L1177,L1184; byte_vocab.json |
| (2) SentencePiece BPE | 16,000 (`kjv_bpe_v1_20m`) | optional alt path; "byte model does NOT use this" | tokenizer/README; kjv_retrain.yaml:23 |
| (3) XMIND engine BPE | 128,256 (Llama-class; FNV-1a, HT 262,144) | C engine constant, bypassed by byte mode | L1631,L377 |

Special ids: PAD=0, BOS=1, EOS=2; byte tokens 3..258. Spec explicitly forbids SentencePiece/BPE for the byte model (L1182). Realized: `interp_tokenless.c` slot 1, native byte mode.

---

## 7. Evaluation & Gates

- **ckpt_bench** — runs at every checkpoint save (do not disable; AGENTS.md / train_byte.py).
- **benchmark_byte.py** — 8 sections → `eval/<run_id>/benchmark_final.json` (AGENTS.md). Dedup pre-pass keeps tokens >4 chars (L1280).
- **val_ppl** — target 3.21 (§8.6 L1176); observed ~3.05 on shipped gguf (§25 L3796) → **M5 conflict**.
- **Adapter validation 8-gate** — `validate_adapter.py check`. **DISCREPANCY M2:** docstring says 6, code emits 10 named GateResults (directory_exists, genome_exists, genome_parse, genome_fields, weights_exist, weights_load, weights_valid, method_known, size_gate, retention_score), AGENTS.md/manifest say 8. Promotion requires non-empty `genome.evaluation` (registry.py).
- **Apex §22 acceptance** (`tests/validate_apex.py`) — **9/9 PASS**: 5-tier SoulManager, Connection 1 covenant-block pre-inference, Connection 2 clean→XMIND (ai_powered), Connection 3 episodic persist + RT4 retrieve (top-7, ≤1800 chars) + restart survival, PII never persisted, writeback quality gate, bounded REVIEWING re-entry (L3866–3879).
- **XMIND unit suite** — 10 groups (struct asserts, BPE roundtrip, Q4_0/Q4_K_M roundtrip, SIMD dot, RoPE, softmax, RMSNorm, SiLU, pre-tokenizer) (L1703–1715). Init self-tests: q4/q4km roundtrip, r1_per dual-SHA (L1717–1723).
- **Verify-validate gates** — all PASS: Gate 1 Build, 2 Tests, 3C Anti-patterns, 4 IDs/wiring, 5B Gitignore, 7C Binaries (0 tracked weights), 7E Remote (L11397).
- **Latency plateau** — ~13 s/turn on 18M scalar-CPU F32; §22 P99 <5000 ms not met in absolute terms (throughput property, not defect). Root cause: KV reset + retrieval cap 12 + prefix 400 chars + episodic eviction 256 (L11244,L3897).
- **Runtime governance floors** (inference, not training): QUALITY_FLOOR 0.30, LATENCY_SLA 5000ms, ERROR_RATE 0.05, DRIFT_LIMIT 0.15, BUDGET 8192 (L1618–1622).

---

## 8. As-Built vs Should-Have-Been

### Gaps (G — spec mandates X, not realized)

| ID | Spec mandate | Realized | Source |
|----|--------------|----------|--------|
| G1 | corpus slot populated for training in models v7 | empty (README/programs only); actual corpus lives in ml-training | corpus/ dir |
| G2 | promoted base + staged weights (runs/bases/weights.safetensors) | runs/ bases/ README-only; no `training/weights.safetensors`; wire_base/promote have no input | runs/, bases/ |
| G3 | AdapterIR (16-op canonical IR) | not in code | L7778 |
| G4 | AdapterGenome v2 (signed/scoped/hashed) | v1 only | L7826 |
| G5 | adapter_algebra.py (14 ops + distill) | absent (only conflict.py v1) | L8145 |
| G6 | layer_plasticity.py / sensory_plasticity.py | absent | L8148 |
| G7 | tournament_v2.py (sovereign score + lanes) | absent (v1 tournament.py only) | L7919 |
| G8 | XMIND-native signed adapter C runtime | spec-only | L7969 |
| G-arch-1/2 | §8.6 to specify head count + seq len | omitted in spec (actual 6 / 1024) | §8.6 |

### Defects (M — realized but wrong/inconsistent)

| ID | Defect | Detail | Source |
|----|--------|--------|--------|
| M1 | PEFT loss disconnected | operators built in standalone dict never attached to base forward graph; `logits = base_model(tokens)` (frozen only) → adapter gradients cannot flow | train_peft.py:255–442 |
| M2 | PEFT base-load broken | `np.load()` expects .npz but base is .safetensors → silent except → random weights | train_peft.py:618 |
| M3 | PEFT config mismatch | bare `ModelConfig()` = vocab 16000 / 6L / seq 512 vs byte base 259/8L/1024 | train_peft.py:621 |
| M4 | PEFT byte-offset bug | `b + 1` (1-indexed) violates the +3 byte_offset contract | train_peft.py:219 |
| M5 | val_ppl conflict | 3.21 (L1176) vs ~3.05 (L3796), unreconciled in spec | spec |
| M6 | method-count drift | 44 reg/42 impl (spec) vs 37 (train_peft) vs 40-impl (registry) vs 43 modules | multiple |
| M7 | structural-family drift | oft/boft/fourier_ft dispatchable in code, absent from registry JSON | structural/*.py |
| M8 | adapter-gate-count drift | 6/8/10 three-way mismatch | validate_adapter.py:8 |

**Realized (as-built) summary:** the ONLY end-to-end artifact is `model.gguf` (inference). Pretraining script (`train_byte.py`) is contract-correct but non-runnable here (no corpus, MLX absent). PEFT path is a stub (M1–M4). No runs, bases, staged weights, or adapters exist in models v7.

---

## 9. Recommended Training Regimen Going Forward (runnable, spec-grounded)

**Prerequisite:** `pip install mlx` (absent in this env; training scripts import it). Fix M2–M4 in `train_peft.py` before any PEFT run.

### 9.1 Pretraining (from-scratch byte LM)
Override the nonexistent `DEFAULT_CORPUS` with the real corpus:

```bash
python3 ml-training/scripts/train_byte.py \
  --corpus ml-training/corpus/eng_kjv_apocrypha_v1/corpus.txt \
  --run-id byte_v1_20m \
  --n-layers 8 --d-model 384 --n-heads 6 --d-ffn 1536 --seq-len 1024 \
  --iters 5000 --batch 8 \
  --lr 3e-4 --lr-min 3e-5 --warmup 200 --weight-decay 0.1 --grad-clip 1.0 \
  --seed 42 --eval-every 200 --save-every 500
```
Objective next-byte NLL; AdamW(betas 0.9/0.95, eps 1e-8); cosine LR after warmup; ckpt_bench at every save. **Accept** at val_ppl ≤ 3.21 (step 5000). Then promote:
```bash
python3 ml-training/scripts/promote_base_model.py --run byte_v1_20m
bash models\ v7/training/scripts/wire_base.sh   # stages → training/weights.safetensors
```

### 9.2 PEFT (after M1–M4 fixed)
```bash
# auto-select
python3 ml-training/scripts/train_peft.py --method omni \
  --base-checkpoint <bases/byte_v1_20m/weights.safetensors> \
  --corpus ml-training/corpus/eng_kjv_apocrypha_v1/corpus.txt
# explicit, conservative for governance-class adapters
python3 ml-training/scripts/train_peft.py --method lora \
  --base-checkpoint <…> --corpus <…>   # rank 8, alpha 16
```
Pipeline: Fingerprinter→Compiler→Tournament→Pareto. Target modules attn.{q,k,v,o}+mlp.{gate,up,down}; embeddings frozen; respect retention_requirement 0.92.

### 9.3 Eval gates (every promotion)
1. `benchmark_byte.py` → 8 sections, byte_ppl_ratio ≤ 1.25.
2. `validate_adapter.py check <dir>` → all gates PASS (reconcile to the documented count first — M8).
3. Apex §22 `validate_apex.py` → 9/9.
4. Verify-validate → all gates green.
5. Tournament v2 (once G7 built) before any deployment; shadow before active; AdapterGenome v2 signed + rollback pointer.

---

## 10. Completeness Boundary

**Spec ranges read (12 extractions, full L1–L11469):** Part 0 + §1–§11 (1–1450); IPC/API/config/L7 + Apex Part II (1450–2900); Apex §10–§24 + Sovereignty + §25 Realization (2900–4350); Heptagon L1–L7 + runtime algo §5–§9 (4350–5800); Apex §9–§20 + V4 §0–§5.1 (5800–7250); Omni-PEFT++ §8 + gates §13–§20 (7250–8700); V2 four-pillar + materialization (8700–10100); V2 §6–§18 + Part V + Appendices (10100–11469). Thematic deep-dives: architecture/HPs, full PEFT catalog, corpus/tokenizer, actual training-state.

**Actual files inspected:** `models v7/training/gguf/model.gguf{,.json}` (parsed), `ml-training/corpus/eng_kjv_apocrypha_v1/*` (present/validated), `models v7/training/{corpus,runs,bases}/` (empty scaffold), `kjva-bible/KJVA/training/{weights.safetensors,model_config.json,byte_vocab.json}` (present); scripts `train_byte.py`, `train_peft.py`, `promote_base_model.py`, `wire_base.sh`, `wire_all.sh`, `validate_adapter.py`, `model.py`; `omni_training_registry.json`, `omni_training_programs.jsonl`, `workspace_manifest.json`.

**Run/verified:** GGUF config + corpus presence + scaffold emptiness confirmed via filesystem. MLX import confirmed failing (training non-runnable in this env).

**Unverified:** Exact producing-run hyperparameters (no train_log.jsonl in kjva-bible — §2 optimizer/schedule are INTENDED defaults). val_ppl 3.21 vs ~3.05 conflict unresolvable from artifacts (no val_ppl field in gguf/manifests). All §8 Omni-PEFT++ modules (AdapterIR, Genome v2, algebra, layer_plasticity, tournament_v2, XMIND adapter C runtime) are spec-only; their behavior could not be executed because they are not implemented (G3–G8).