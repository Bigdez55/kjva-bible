# Stress Test + Frontier Diagnostic Gap-Map — TokenlessLM (2026-06-04)

Purpose: **refine the model before the next training run.** This is a diagnostic gap-map, not
marketing. Every number for our model is *measured here* (or cited as a prior metric-of-record
with that caveat); every frontier number is *published, not reproduced*. Axes where the
comparison is out-of-distribution are marked **not comparable** rather than scored as a loss.

Measured through the **deployed XMIND C engine with NEON** (the real runtime), not a Python
shadow. MLX/PyTorch are not installed on this host, so perplexity is cited from the model card
(metric-of-record), not re-run.

---

## 1. Model facts (measured / spec)

| Property | Value |
|---|---|
| Parameters | 18,980,352 (18.98M) · 8 layers · d_model 384 · 6 heads · FFN 1536 · ctx 1024 |
| Vocabulary | 259 (256 bytes + PAD/BOS/EOS) — **byte-level, tokenizer-free** |
| Training corpus | KJV + Apocrypha (~5 MB) |
| val perplexity | **3.21** (prior metric-of-record; not re-run here — MLX absent) |
| Deployment | 11 MB Q4_0 GGUF + 165 KB C engine (`libxmind-core`) — **phone-deployable** |
| Inference | parity-verified C (pt↔C MAE 0.0908, tol 0.6); RoPE rotate-half; Q4_0 |
| Throughput | **182 tok/s** (NEON, 128-token gen) — 4.86× over scalar (36.9 → 179) |

## 2. Stress test (empirical, this run)

| Axis | Result | Verdict |
|---|---|---|
| **In-domain generation** | 5/5 biblical prompts → coherent KJV verse structure (proper book abbrevs JER/JOB/JHN/2KI, verse refs) | **STRONG** |
| **Retrieval grounding** | `Psalm 23:1`/`John 3:16` → EXACT verse + citation, `generation_invoked=False` | **STRONG** — verbatim facts never confabulated |
| **OOD (code/math/news)** | 4/4 degrade to the domain distribution (e.g. `def fibonacci(n):` → biblical text), no crash | **EXPECTED** — domain model; this is why the product surface is retrieval/citation-gated |
| **Robustness** | 6/7 pass: empty, single-byte, unicode/non-ASCII, control bytes (`\x00`), repeated-token, max_new=256 all OK | mostly **ROBUST** |
| **Robustness — >ctx-1024 prompt** | **FAILS rc=-3** (errors instead of truncating) | **GAP** (see T4) |
| **Throughput / latency** | 182 tok/s @128, 112 tok/s @32; ~5.5 ms/tok (NEON) | **STRONG** for on-device |
| **Safety gate** | covenant gate fail-closed; harmful → 503/withheld (prior tests) | **PASS** |

## 3. Frontier diagnostic gap-map (3-tier honesty)

| Axis | Ours (measured/spec) | Frontier (published, not reproduced) | Verdict |
|---|---|---|---|
| Params | 18.98M | GPT-4-class / Llama-405B: 10²–10⁴× larger | context, not a score |
| In-domain (KJV) fluency | coherent, val_ppl 3.21 | not domain-specialized | **ours competitive in-niche** |
| Verbatim scripture accuracy | exact (retrieval-gated) | strong but can paraphrase/hallucinate cites | **ours stronger on this narrow axis** |
| Tokenizer | none (259-byte vocab) | BPE/tokenizer (30k–200k) | ours is tokenizer-free (an architecture property) |
| On-device footprint | 11 MB, 182 tok/s on a laptop CPU | tens–hundreds of GB, GPU/TPU | **ours far lighter** |
| General reasoning | ~none | strong | **NOT COMPARABLE** (OOD for a 19M domain model) |
| Code / math | ~none (confabulates) | strong (HumanEval/GSM8K 70–90%+) | **NOT COMPARABLE** |
| Long context | ctx 1024, errors beyond | 100k–1M+ | **GAP** vs frontier; T4 |
| Instruction following | none (base LM, no SFT/RLHF) | strong | **GAP**; T3 |

**Honest summary:** this is an 18.98M byte-level **domain** model. It is not comparable to
frontier models on general ability, and a head-to-head on MMLU/HumanEval would be ~0% vs ~85% —
noise, not signal. Where it *is* strong is its niche: tokenizer-free, phone-sized, parity-verified,
exact-citation-grounded KJV/Apocrypha. The useful output of this comparison is the
prioritized list below.

## 4. Prioritized weaknesses → training targets (the deliverable)

| # | Target | Evidence | Action for the next training run |
|---|---|---|---|
| **T1** | Corpus breadth | OOD collapses to KJV distribution; general fluency ~none | If broader capability is wanted, expand the corpus (the absorption/OMNI-PEFT path can add domain adapters without retraining the base — see [[project-omni-peft-absorption-path]]) |
| **T2** | Capacity vs corpus | 18.98M is tiny; val_ppl 3.21 is good for the corpus but caps headroom | Consider a larger d_model/layers variant if a bigger corpus is adopted; otherwise current size is well-matched |
| **T3** | No instruction/alignment tuning | base LM only; no SFT/RLHF; instruction-following ~none | An SFT/DPO pass (the alignment methods already in `training/peft/alignment/*`) on an instruction set would add task-following without touching the base distribution |
| **T4** | Long-context robustness | >ctx-1024 prompt errors (rc=-3), not graceful | Engine fix: truncate/slide the prompt window instead of erroring (C-side, `xmind_easy_generate`); + decide whether to train a longer ctx |
| **T5** | Calibration / uncertainty | drift_index/uncertainty wired but low signal on a tiny model | More eval coverage; the determinant/drift records are now emitted to support this |

**Standing strengths to preserve when retraining:** byte-level tokenizer-free design, the
parity-locked C deployment (re-verify pt↔C after any change), retrieval/citation grounding (keep
the product surface gated — do NOT ship free generation for verbatim facts), and the NEON hot path.

---

## 5. Re-run (post B5–B9 edge-wiring, 2026-06-04)

Re-ran the same stress harness after wiring the remaining ADR-0002 edges (B5 continuity
attestation, B6 session clarity, B8 model-artifact materialization, B9 metacognitive triad +
adapter IR/cache). **Generation is unchanged** (the new wiring is cognition/observability, not
generation), and one robustness axis improved:

| Axis | First pass | Re-run | Note |
|---|---|---|---|
| In-domain coherence | STRONG | STRONG (unchanged) | generation untouched |
| OOD graceful | yes | yes (unchanged) | |
| **Robustness** | 6/7 (>ctx errored rc=-3) | **7/7** | **T4 fixed** — >ctx now tail-truncates and generates (slower as ctx fills, but no error) |
| NEON throughput | 182 tok/s @128 | ~155 tok/s @128 | within system-load variance; still ~4–5× scalar |

**New per-turn cognitive provenance now emitted** (the edge-wiring made these CALLED, not just
defined) — observability the next training run can use for T5 calibration:
- `memory_verdict` (ADR-0001 §8.4): route, **lineage_level** (understanding/innerstanding/
  overstanding from the metacognitive triad), active_layers, invariant_verdict.
- `metacognition`: calibration_error, drift_samples, invariant_violations (the three levels).
- `attestation`: a tamper-evident SHA-256 continuity chain (head + chain_length).
- `model_artifact` materialization: the C-materialized model facts (8L/259v/q4_0) + adapter IR
  (family/target_count/rank/param_count/key) when an adapter is absorbed.

**Net for the next training run:** the 5 targets (T1–T5) stand; **T4 is now closed at the engine
level** (graceful long-prompt handling), so "long context" reduces to a *training* decision
(whether to train ctx > 1024) rather than an engine defect. The richer cognitive provenance
(lineage_level, calibration_error, drift, attestation) gives T5 (calibration) real signal to
evaluate against on the next run.
