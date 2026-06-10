# Documentation Drift Reconciliation (M5–M8)

**Date:** 2026-05-31 · **Phase 7** · source-of-truth order: running code > tests > manifests/registry > prose.

The audit found four documentation drifts. Canonical values are fixed here.

## M5 — val_ppl: 3.21 vs 3.05

Both are real and not in conflict once labeled:
- **3.21** = the spec §8.6 **acceptance target** (the gate: a base passes at `val_ppl ≤ 3.21`).
- **3.05** = the **observed** val_ppl on the shipped `model.gguf` (§25), i.e. *better* than target.

**Canonical:** target = **3.21** (gate); observed-on-shipped = **3.05**. `kjv_omni_program.yaml`
records `val_ppl_target: 3.21`. No code change — labeling only.

## M6 — PEFT method count: 37 / 40 / 42 / 44

Different granularities, all valid:
- **44** = total methods declared in `omni_training_registry.json` (the registry — source of truth).
- **40 implemented / 2 extension_spec / 2 planned** = the registry status breakdown (sums to 44).
- **37** = the MLX `train_peft.py` docstring's operator count (reference script).
- **23** = the PyTorch `pt/peft` catalog's resolvable methods (6 bespoke + 17 documented aliases;
  `operators.catalog_status()` reports them — no silent gaps).

**Canonical:** the **registry's 44** (40 implemented). The PyTorch catalog resolves **23** methods to
concrete operators today; the remaining registry methods are reference/long-tail (Phase 10).

## M7 — structural family registry drift (oft/boft/fourier_ft)

`oft`/`boft`/`fourier_ft` were dispatchable in code but absent from the registry JSON.
**Resolved:** `programs/method_ontology_v2.json` now lists them — `oft` bespoke (STRUCTURAL),
`boft`/`fourier_ft` as documented aliases of `oft`. The PyTorch catalog implements `OFTLinear`
(bespoke) + boft/fourier_ft aliases.

## M8 — adapter-gate count: 6 / 8 / 10

`validate_adapter.py` **emits 10 named GateResults** (directory_exists, genome_exists, genome_parse,
genome_fields, weights_exist, weights_load, weights_valid, method_known, size_gate, retention_score).
The docstring said 6; AGENTS.md/manifest say 8.

**Canonical (code > docs):** **10** code-emitted gates. AGENTS.md's "8 gates" is the headline count;
the authoritative set is the 10 the validator actually emits. Promotion still requires a non-empty
`genome.evaluation`.

## Path naming (informational)

Spec prose cites `ai/genesys-ai/src/...`; the realized code is `ai/tokenless-agent/src/...`
(reconciled by the `GenesysAgentWithHeptagon = TokenlessAgentWithHeptagon` alias, ADR-S49-02).
Code is correct; spec prose paths are legacy.
