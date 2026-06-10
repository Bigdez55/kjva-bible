# XMIND-1 — Complete Benchmark & Evaluation Suite
**Target artifact:** 18.98M-parameter, tokenizer-free, byte-level, retrieval-grounded domain LM
**Engine:** NEON (native; no external runtime)
**Baseline run:** STRESS_TEST_AND_FRONTIER_GAPMAP_2026-06-04
**Status of this doc:** v1 specification — implementation contract for all downstream eval work

---

## 0. The claim under test

> A local, tokenizer-free, retrieval-grounded byte-LM with an explicit governing law can **match or beat frontier models on the dimensions that define reliability** — grounding fidelity, hallucination rate, calibration, injection resistance, determinism, and joules-per-query — at 1/1000th the footprint, while *not* competing on broad parametric world-knowledge.

This suite exists to **prove or falsify that sentence**. Every benchmark below maps to either the claim or the diagnostic floor that bounds it. Nothing here is decoration; if a test does not move a decision, it is cut.

The design principle is two axes, never collapsed into one number:

- **Axis A — Frontier-parity diagnostics (the floor).** Standard public benchmarks. We *expect to lose* here at 18.98M, and that is fine. We measure them only to (a) locate the real gap honestly, (b) track it across capacity scaling, and (c) refuse to let "improve MMLU" silently become a training target. These are a thermometer, not a goal.
- **Axis B — Structural-advantage battery (the scoreboard).** The dimensions the architecture is actually built for. This is where the claim lives and where head-to-head frontier comparison is fair.

**Honesty rules (non-negotiable, apply to every number this suite emits):**
1. Report floor scores raw, with no spin. A 0% is reported as 0%.
2. Every eval set is dedup-audited against the training corpus before any score is trusted (Section 11). Contaminated scores are discarded, not footnoted.
3. Every reported metric carries a confidence interval and seed count. Single-run numbers are forbidden in any comparison.
4. Frontier head-to-head uses the *same corpus, same hardware-normalized protocol, same prompts*. No cherry-picked domains.
5. The structural-advantage claim is only stated in the exact form Section 10 permits.

---

## 1. Evaluation philosophy

The industry optimizes a single scalar (aggregate capability) by scaling parameters. This artifact is a deliberate departure: capability is *bounded by design* and reliability is *unbounded by design* (grounding + governing law + typed input). The eval suite must therefore be **structurally different from MMLU-style leaderboards**, in the same way the model is structurally different from a frontier transformer.

Concretely, that means three things most leaderboards omit:
- **Boundary-awareness is a first-class metric**, weighted above raw accuracy. A model that abstains correctly is worth more than one that guesses well.
- **Negative space is tested explicitly.** Most benchmarks only ask questions the model could answer. Here, out-of-corpus and adversarial queries are a majority of the structural battery, because not-confabulating is the product.
- **The substrate is measured, not just the output.** Determinism, energy, injection surface, and quantization robustness are properties of the engine and architecture, and frontier APIs cannot match several of them by construction.

---

## 2. Axis A — Frontier-parity diagnostics (the floor)

Run these once per capacity tier (Section 4.6 scaling curve), report as floor, never optimize directly.

| Suite | What it measures | Expected at 18.98M | Why we still run it |
|---|---|---|---|
| MMLU + MMLU-Pro | Broad knowledge + reasoning, 57 subjects | ~chance (noise) | Locates the parametric-knowledge gap; tracks whether capacity scaling buys anything |
| GSM8K, MATH | Multi-step arithmetic reasoning | very low | Reasoning is the clearest capacity-bound signal |
| ARC-Challenge, HellaSwag, WinoGrande | Commonsense + science reasoning | low | Cheap, standard, comparable to literature |
| BBH (BIG-Bench Hard) | Hard reasoning subset | low | Detects emergent reasoning if/when capacity rises |
| HumanEval, MBPP | Code generation | n/a unless code in corpus | Only if/when code domain is added |
| DROP, SQuAD v2 | Reading comprehension w/ unanswerable Qs | **watch SQuAD v2 abstention** | SQuAD v2's unanswerable split actually probes Axis B |

**Diagnostic rule:** record each as a point on a capability-vs-params curve. The decision these feed is *not* "is the score high" but "does the slope justify the footprint cost." A flat slope means scaling won't fix generality and the bet stays fully on Axis B.

---

## 3. Axis B — Structural-advantage battery (the real scoreboard)

This is the heart of the suite. Each block defines metric, dataset construction, and pass/fail intent.

### 3.1 Grounding fidelity
- **Verbatim retrieval exactness:** for in-corpus factual queries (e.g., KJV verse recall), measure exact-match character accuracy of the grounded span. Target: ≥ 0.999. Any drift from verbatim is a defect, not an approximation.
- **Citation correctness:** does the cited source span actually contain the answer? Precision/recall of the attribution pointer.
- **Span localization:** when retrieval returns a window, does the model attend to the correct sub-span (not just the right document)?

### 3.2 Hallucination / confabulation rate — the defining metric
Construct three query strata explicitly:
- **In-corpus (IC):** answer exists verbatim in corpus.
- **Near-corpus (NC):** plausibly adjacent, answer *not* in corpus (designed lures — paraphrased non-facts, fabricated cross-references).
- **Out-of-corpus (OOC):** clearly outside domain.

Metric per stratum: {correct, abstain, confabulate}. The single headline number is **OOC confabulation rate** — target ≈ 0%. A model that says "not in my corpus" on 100% of NC+OOC while answering IC correctly is the win condition. This is where the architecture should *dominate* frontier, which confabulates fluently on NC lures.

### 3.3 Calibration & boundary-awareness (weighted highest)
- **Selective prediction / risk-coverage curve:** plot accuracy vs coverage as the abstention threshold sweeps. Report area under the risk-coverage curve and accuracy@90%-coverage.
- **Expected Calibration Error (ECE)** and reliability diagrams on confidence vs correctness.
- **Abstention precision/recall:** of things it abstained on, how many were truly unknown (precision); of truly unknown things, how many did it abstain on (recall).
- **Known-unknown discrimination:** AUROC of confidence score separating answerable from unanswerable queries.

### 3.4 Faithfulness / attribution
- **Entailment of output from retrieved evidence:** NLI-style scoring — does the generated answer logically follow from the grounded span? (AIS-style attributable-to-identified-sources protocol.)
- **No-evidence-no-claim:** rate at which the model makes a factual assertion *without* a supporting retrieved span. Target ≈ 0.

### 3.5 Determinism & reproducibility (structural; frontier cannot match)
- Same input → byte-identical output across N runs and across cold restarts. Report determinism rate (target 100% at temperature 0).
- Cross-hardware determinism: same output on different phone SoCs given the same NEON build.
- This is a *property*, not a score to optimize — but it is a genuine frontier-comparison win and must be documented as such.

### 3.6 Injection & instruction-override resistance (R1_PER thesis)
This is the sharpest structural claim. Because R1_PER compiles natural language into typed XISC opcodes (0x70–0x8F) before inference, freeform instruction injection should be **structurally impossible**, not merely filtered.
- **Injection battery:** assemble an adversarial corpus — jailbreak prompts, "ignore previous instructions," role-override, smuggled-instruction-in-data, unicode/homoglyph attacks, payload-in-retrieved-document.
- **Metric:** instruction-override success rate. Target ≈ 0 *by construction*, and the eval must demonstrate the mechanism (show that the injected text never reaches an instruction-bearing channel because it was typed as data opcodes).
- **Falsification test:** actively try to construct an input that smuggles control through the opcode boundary. A single success here is a finding that touches the R1_PER binary contract and must be filed against it.

### 3.7 Byte-level robustness (tokenizer-free thesis)
Where BPE models degrade, this should not:
- **Perturbation robustness:** typos, casing, whitespace noise, character substitution — measure accuracy delta vs clean input.
- **OOV / novel-string handling:** rare names, IDs, numbers, code tokens, mixed scripts — no tokenizer means no OOV cliff; measure it.
- **Numerical fidelity:** digit-level manipulation tasks where BPE tokenization corrupts numbers.
- **Multilingual / mixed-script bytes:** even if out of domain, measure graceful behavior vs garbage.

---

## 4. Efficiency & systems benchmarks (the "local" thesis)

The footprint/latency story is a headline feature and must be measured with the same rigor as accuracy.

1. **Decode throughput:** tok/s (baseline 182) — p50/p95/p99, sustained vs burst.
2. **Time-to-first-token (TTFT):** the number that dominates perceived latency; measure under varying context length.
3. **Memory:** model footprint (11MB), peak RSS, KV-cache growth vs context length (note byte-level ~4× sequence expansion inflates this — measure it honestly).
4. **Energy:** **joules per query** and per token on target hardware. This is a true frontier-comparison win (frontier = datacenter round-trip + GPU) and belongs in Section 10.
5. **Cold-start:** boot-to-first-inference latency (AetherBoot → NEON ready).
6. **Concurrency:** throughput under N simultaneous sessions on-device.
7. **Quantization sensitivity:** re-run Sections 3.1–3.3 under int8/int4. Critical question: does quantization degrade *grounding/calibration* (not just perplexity)? A quantization that preserves capability but breaks abstention is a trap.
8. **Capability-vs-cost scaling curves:** the central planning artifact. Plot {grounding fidelity, OOC-confabulation, MMLU-floor} against {params, footprint MB, TTFT, J/query}. Output: **the largest model that still fits the phone box** (define the box: target ≤ X MB, ≤ Y ms TTFT, ≤ Z J/query). Optimize *within* that box; never treat capacity as free.

---

## 5. Byte-level native metric — the single most honest cross-architecture comparison

**Bits-per-byte (BPB)** on a held-out, contamination-audited domain corpus.

This is the one number that is *directly and fairly comparable* across model sizes and across architectures, including against any frontier model evaluated on the identical held-out bytes. It sidesteps tokenizer mismatch entirely (no normalization-by-token games). Report BPB:
- on in-domain held-out text (should be excellent),
- on near-domain text (graceful), and
- versus a frontier model scored on the same exact bytes.

If the 18.98M model achieves competitive BPB *on its domain* against a frontier model, that is a legitimate, publishable, structurally-grounded "matches frontier on our axis" result — at 1/1000th the size. This metric carries disproportionate weight in the suite.

---

## 6. Long-context evaluation

Lowest priority of the major axes, because retrieval should pre-narrow the window — but measured so that priority decision is data-backed, not assumed.
- **Needle-in-a-haystack (NIAH)** at byte scale, swept across depth and context length.
- **RULER** suite for multi-needle, variable-tracking, aggregation.
- **Effective context length:** the length at which accuracy crosses a degradation threshold (report this, not the nominal max).
- **Retrieval-vs-raw ablation:** same task with retrieval on vs forcing the model to hold context. If retrieval-on wins decisively, long-context training is formally deprioritized and that is recorded as a justified decision.

---

## 7. SFT / alignment / R1_PER encoding-fidelity evals

- **Instruction-following on the retrieval interface:** does it produce the grounded-answer format reliably? Format-adherence rate, structured-output validity (JSON/opcode envelope conformance).
- **R1_PER round-trip fidelity:** NL → XISC opcode → (decode) → semantic equivalence. Measure lossless-semantics rate. The doctrine is "equivalent meaning at higher density," so the test is *semantic* equivalence, not byte equivalence. Build a paired corpus and score round-trip meaning preservation.
- **Governing-law behavior:** refusals/denials must be *explicit, typed, logged* (per the internal-law doctrine). Eval: every denial produces a typed reason code; zero silent refusals. This is testable and should be 100%.
- **Alignment regression guard:** SFT must not degrade Section 3.2/3.3. Run the structural battery pre- and post-SFT; any grounding/calibration regression blocks the checkpoint.

---

## 8. Adversarial, OOD & stress (extends 3.6/3.7)

- **Red-team query generation:** auto-generate NC lures and OOC traps at scale (use a frontier model as an adversary to *generate* hard lures — fair use of frontier as a tool, not a baseline).
- **Corpus-poisoning resistance:** inject a false "fact" into a retrieved document and measure whether the model launders it as grounded truth. Faithfulness must catch this.
- **Distribution-shift sweep:** register-shift, dialect, archaic vs modern English (relevant given KJV corpus), domain-edge queries.
- **Failure-mode taxonomy:** every failure is classified (confabulation / mis-retrieval / mis-attribution / over-abstention / format-break / injection-leak). The taxonomy itself is a deliverable that drives the next training cycle.

---

## 9. Regression & continuous-evaluation infrastructure

The suite is worthless run once. It must be a standing harness.
- **Golden frozen baseline ("eval POINT ZERO"):** a sealed set + sealed scores. Every checkpoint is scored against it; any regression on grounding/calibration/injection is a hard gate.
- **Per-checkpoint scorecard:** Axis A floor + Axis B scoreboard + efficiency, emitted automatically per training run, diffed against the prior checkpoint.
- **Drift alarms:** thresholded alerts on the structural metrics specifically (those degrade silently under capability-focused training).
- **Provenance:** every score tagged with corpus hash, model hash, NEON build hash, seed set — replayable, in keeping with the system's replay doctrine.

---

## 10. Head-to-head frontier comparison protocol (how to claim "matches frontier" defensibly)

Pick 2–3 frontier baselines (one small, one large) and run them through the **same Axis B + efficiency battery on the same domain corpus and prompts.** Frontier wins Axis A by definition; that is conceded up front and not contested.

The **only** claim this suite authorizes has this exact shape:

> "On {grounding fidelity, OOC-confabulation rate, abstention AUROC, faithfulness, injection-override rate, determinism, J-per-query, domain BPB} measured over {named corpus} on {named hardware}, the 18.98M local model scores {X} versus frontier {model} at {Y}, at {footprint ratio} the size and {energy ratio} the energy per query."

That is a true, narrow, defensible frontier-comparison — and it is the strongest honest version of the goal. It says: *not "as smart as," but "more reliable, more private, more efficient, on the dimensions that decide whether you can trust and ship it locally."* That is the structurally-different-axis thesis, made measurable.

---

## 11. Statistical rigor & contamination control

- **Contamination audit (run before any score is trusted):** n-gram / substring / near-dup (MinHash) overlap between every eval set and the training corpus. Overlapping items removed; contaminated suites discarded.
- **Held-out discipline:** eval corpora sealed and never seen in training; rotate fresh held-out sets to detect overfitting-to-eval.
- **Statistics:** ≥ 3 seeds for any stochastic component; bootstrap confidence intervals on every reported metric; significance tests on every head-to-head delta. No bare point estimates in comparisons.
- **Inter-rater reliability** for any human-judged metric (faithfulness, abstention-correctness): report agreement (κ).

---

## 12. Gap-closure map → the five training targets

Each target gets the benchmark that gates it and an acceptance threshold. Thresholds are placeholders for you to set; the structure is the contract.

| Training target | Gating benchmarks | Acceptance criterion (set values) | Tension to watch |
|---|---|---|---|
| **Calibration** *(promote to #1)* | 3.3 risk-coverage, ECE, abstention P/R; 3.2 OOC rate | OOC-confab ≤ ε; abstention recall ≥ τ | Cheap; preserves strengths — do first |
| **SFT / alignment** | 7 format adherence, round-trip fidelity, typed-denial rate; 9 regression guard | 100% typed denials; no Axis-B regression | Must not trade grounding for fluency |
| **Capacity + Corpus breadth** *(coupled, not separate)* | 4.6 scaling curve; 5 BPB; 3.1 grounding under breadth | Stay in phone box; BPB↑ without grounding↓ | Breadth at fixed capacity *degrades* KJV coherence — move together or not at all |
| **Long-context** *(lowest)* | 6 NIAH/RULER + retrieval-vs-raw ablation | Only invest if ablation shows retrieval insufficient | Byte-level ~4× expansion makes this expensive; retrieval likely obviates |
| **Robustness (implicit 6th)** | 3.6 injection, 3.7 perturbation, 8 poisoning | Injection-override ≈ 0 (prove mechanism) | The R1_PER structural win — prove it, don't assume it |

---

## 13. Harness scaffolding (pseudocode, to implement against NEON)

```
# Each eval is a pure function: (model_handle, sealed_set) -> scorecard
# All scores carry provenance + CI; all sets pass contamination audit first.

run_suite(model, build_hash):
    audit = contamination_audit(EVAL_SETS, TRAIN_CORPUS_HASH)   # Sec 11; abort on overlap
    floor   = axisA_diagnostics(model, audit.clean)            # Sec 2 — report, don't optimize
    score   = axisB_battery(model, audit.clean)               # Sec 3 — the scoreboard
    systems = efficiency_bench(model, TARGET_HW)              # Sec 4 — TTFT, J/query, scaling pt
    bpb     = bits_per_byte(model, HELDOUT_DOMAIN)            # Sec 5 — cross-arch honest metric
    longc   = long_context(model, audit.clean)               # Sec 6 — incl retrieval ablation
    align   = sft_alignment(model, audit.clean)              # Sec 7 — incl R1_PER round-trip
    adv     = adversarial(model, REDTEAM_SET)               # Sec 8 — injection, poisoning
    card    = scorecard(floor, score, systems, bpb, longc, align, adv,
                        provenance={model, build_hash, seeds, corpus_hash})
    assert no_regression(card, GOLDEN_BASELINE)              # Sec 9 — hard gate
    return card

# Frontier head-to-head: identical sets/prompts/hw-normalized protocol
compare_frontier(model, frontier_models):
    return { f: axisB_battery(f, SHARED_SET) + efficiency_bench(f, NORMALIZED)
             for f in frontier_models }   # Sec 10 — authorizes the narrow claim only
```

---

## 14. Phased rollout (what to run first)

1. **Phase 0 — Instrument the floor.** Wire Sections 2, 4 (incl. the scaling-curve harness), and 5 (BPB). Establish the honest baseline and the phone box.
2. **Phase 1 — Build the scoreboard.** Sections 3.1–3.4 + 3.5 determinism. This is where the thesis first becomes measurable.
3. **Phase 2 — Prove the structural wins.** Section 3.6 injection + 3.7 byte robustness + Section 8 poisoning. These are the claims frontier cannot match.
4. **Phase 3 — Stand up regression infra.** Section 9 golden baseline + per-checkpoint scorecards. Now training can proceed without silent regression.
5. **Phase 4 — Frontier head-to-head.** Section 10, producing the first defensible comparison statement.
6. **Continuous.** Every checkpoint runs Phases 0–3 automatically; Phase 4 on milestones.

---

## 15. Parameters that need your input (do not block on these — defaults proposed)

- **Phone box definition:** max footprint (MB), max TTFT (ms), max J/query. *(Proposed: keep footprint < 100MB, TTFT < 500ms, to preserve the "phone-sized" story while buying capacity headroom.)*
- **Frontier baselines for Section 10:** which 2–3 models, and via what access (the eval treats them as black boxes on shared bytes).
- **Domain scope for breadth:** is breadth *adjacent* (more scripture/wisdom/translation corpora) or *cross-domain* (code, general)? This changes the capacity-vs-coherence tradeoff sharply.
- **Acceptance thresholds (ε, τ, etc.)** in Section 12 — these are sovereign decisions, not engineering ones.
- **Is code generation in scope yet?** Gates whether HumanEval/MBPP and a code domain enter the suite at all.
```
