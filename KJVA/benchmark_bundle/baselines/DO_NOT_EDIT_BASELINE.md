# BASELINE LOCK — DO NOT EDIT

Files in this directory are the **sealed golden baseline** for KJVA-1 / XMIND-1 as of 2026-06-08.

## Contents

- `KJVA1_XMIND1_BASELINE_2026-06-08.json` — machine-readable baseline thresholds
- `BENCHMARK_COMPILATION_2026-06-08.md` — human-readable full benchmark compilation (sealed copy)
- `regression_gate.py` — script to check any future benchmark run against these thresholds

## Rules

1. **DO NOT EDIT** these files. They are the reference point.
2. Append-only corrections: if a value was measured incorrectly, add a `_correction` key to the JSON with an explanation. Do not remove or overwrite.
3. Future benchmark runs must pass `regression_gate.py` before promotion is considered.
4. If the model architecture changes, create a NEW baseline file (`KJVA2_XMIND2_BASELINE_<date>.json`) — do not replace this one.

## What a regression means

Any future run that fails `regression_gate.py` means one or more of:
- Governance weakened (below 25/25)
- Test suite broke (failed > 0)
- Scripture grounding disabled (below 14/14)
- BPB worsened beyond threshold
- Determinism dropped below 100% at T=0
- Archived candidate accidentally becoming runtime-authoritative
- Footprint grew (quantization format changed)

A regression must be investigated before any commit or promotion.
