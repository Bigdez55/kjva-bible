# XMIND-1 Benchmark Results — 2026-06-05T012121Z

**Spec:** XMIND_BENCHMARK_AND_EVAL_SUITE_2026-06-04.md
**Model:** `models v7/training/gguf/clean_base_soup_v1.gguf`  (11,046,112 B)
**Model SHA-256:** `e59c69091a1772a347098efd68d74944…`
**Dylib SHA-256:** `9b1eb4013aad28415a27c86bb62b68ee…`
**Engine version:** `xmind-easy/1.0 consumer-build`
**Init time:** 308.8 ms

## Honest scope
This run executes the SUBSET of the spec that can run against the on-disk GGUF + dylib without external eval sets, frontier API, NLI judge, R1_PER pipeline, or alternate-quantization variants. Skipped sections are listed in results['skipped'] with reasons. No claim about overall benchmark completeness is being made.

## Sections SKIPPED (with reason)
- **§2 Axis A (MMLU/GSM8K/ARC/HellaSwag/BBH/HumanEval/DROP/SQuAD)** — eval sets not in repo
- **§3.1 Grounding fidelity** — retriever not wired
- **§3.2 Hallucination IC/NC/OOC** — labeled strata not in repo
- **§3.3 Calibration ECE / risk-coverage** — requires per-position logits aligned to labels
- **§3.4 Faithfulness / NLI entailment** — NLI judge not in repo
- **§3.6 R1_PER injection battery** — R1_PER opcode pipeline not wired in current build
- **§4.4 Joules/query** — requires powermetrics root + per-query energy probe
- **§4.7 Quantization sensitivity** — only Q4_0 variant present; need f32/q8 to compare
- **§4.8 Capacity scaling curves** — only 18M tier present
- **§6   Long-context NIAH/RULER** — sets not in repo
- **§7   SFT / R1_PER round-trip** — no SFT checkpoint, no R1_PER decoder
- **§8   Adversarial / corpus poisoning** — adversarial corpus not in repo
- **§10  Frontier head-to-head** — no frontier model access from this environment
- **§11  Contamination audit** — no eval sets to audit against

## Sections EXECUTED

### §3.5 Determinism
- Byte-identical across 5 runs: **True**
- Distinct outputs: 1
- Wall-time mean: 209.2 ms (σ=1.6)

### §3.7 Byte-level perturbation robustness
- Variants tested: 8
- Distinct output hashes: 6
- Interpretation: Lower distinct count = more robust (semantically-similar inputs → similar outputs). Higher = more brittle. For a healthy byte-LM we expect distinct < n_variants but > 1.

| Variant | Out preview | Wall ms |
|---|---|---|
| clean | `. JOB 11:11 And the LORD` | 341.3 |
| lowercase | `. PSA 105:1 The LORD sha` | 342.6 |
| uppercase | ` 2:2 The LORD said unto ` | 331.7 |
| extra_spaces | `. JOB 11:1 And the LORD ` | 367.5 |
| typo_swap | `. JOB 11:10 And the LORD` | 346.1 |
| leading_ws | `. JOB 11:1 And the LORD ` | 347.1 |
| trailing_ws | `will send the heavens an` | 344.9 |
| punct_dropped | `. JOB 11:11 And the LORD` | 334.2 |

### §4.1 Decode throughput
| max_tokens | tok/s mean | tok/s stdev | min | max |
|---|---|---|---|---|
| 16 | 58.9 | 1.3 | 57.8 | 60.8 |
| 32 | 89.9 | 1.1 | 88.0 | 90.8 |
| 64 | 123.0 | 1.6 | 121.2 | 125.3 |
| 128 | 146.7 | 3.2 | 141.3 | 149.5 |

### §4.2 Time-to-first-token (TTFT)
| Prompt | Bytes | TTFT mean ms | p50 | min | max |
|---|---|---|---|---|---|
| short_8b | 9 | 52.0 | 51.6 | 51.2 | 53.8 |
| med_64b | 63 | 332.5 | 330.8 | 328.0 | 339.2 |
| long_256b | 256 | 1397.0 | 1402.1 | 1352.3 | 1433.2 |

### §4.3 Memory
- Model footprint on disk: **10.53 MB**
- Process RSS before inference: 43.58 MB
- Process RSS after inference: 44.66 MB
- RSS delta: 1.08 MB

### §4.5 Cold-start latency (true cold, fresh subprocess)
- N runs: 3
- Mean: 393.7 ms (σ=5.7)
- Min/Max: 388.3 / 399.6 ms

### §4.6 Concurrency
- Implementation note: xmind_easy_* is per-process singleton; in-process threads serialize on a spinlock. True parallelism needs multi-process.
- Sequential per-call: 69.5 ms
- Threaded per-call: 319.8 ms
- Threaded total wall (8 calls): 562.5 ms
- Ideal-parallel wall if truly concurrent: 69.5 ms

### §5 Bits-per-byte (BPB)
- Bytes scored: 64
- Avg NLL (nats): 0.8980
- **BPB: 1.2955**
- Held-out preview: `And God said, Let there be light: and there was light. And God saw the light, th`
- Interpretation: BPB on this held-out byte stream. Lower is better. Frontier BPB on English ≈ 0.6–1.0. KJV-trained 18M base will be higher off-domain and lower in-domain. Use as a CROSS-ARCHITECTURE comparable, not as a pass/fail.

---
## Spec coverage tally

- Sections executed: **8**
- Sections skipped (with reason): **14**

This is honest partial coverage. Do not interpret as a complete benchmark of the spec.