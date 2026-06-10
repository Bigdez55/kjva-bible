# Canonical Base Promotion Record

**Date promoted:** 2026-06-07
**Promoted weight:** `clean_base_soup_v1.source.gguf` → `training/gguf/canonical.gguf`
**Promoted SHA-256:** `e59c69091a1772a347098efd68d7494419d5e82a75a3e064d95370d1d3f8fb93`
**Architecture:** byte-level decoder-only transformer, `tokenless_lm` (interpreter slot 1), 18,980,352 params, vocab 259, 8 layers, 6 heads, d_model 384, d_ffn 1536, ctx_len 1024, rope_base 10000.0, tied embeddings.

## Doctrine

**Identity is singular. Engineering surfaces remain auditable. Cognitive flow remains fused.**

Short form: **One cognitive identity. Auditable engineering surfaces. Fluid depth-scaled cognition.**

The runtime embodiment loaded by XMindClient is `training/gguf/canonical.gguf` — a single canonical weight file. The previous practice of leaving three peer `.gguf` files in `training/gguf/` without an authority gradient invited taxonomy drift and was the cause of the "are these three models?" confusion on 2026-06-04.

`canonical.gguf` is the **current promoted runtime embodiment** of the singular cognitive identity, selected from a soup of checkpoints in the `byte_clean_v1` training run. Historical embodiments remain in `training/gguf/archive/` as lineage evidence — they are NOT auto-loaded by the runtime, are NOT separate identities or separate minds, and should NOT be referenced as alternative model designs.

**Promotion is a runtime authority decision**, not merely a training-stage label. Training creates candidate embodiments; promotion is a canonical runtime attestation grounded in benchmark evidence, provenance, SHA integrity, runtime compatibility, regression standing, and doctrine alignment. See `training/gguf/CANONICAL_BASE_DOCTRINE.md` for the full Unified Cognitive Identity Contract.

## Promotion candidates (ranked by §5 BPB on KJV held-out, lower is better)

| Candidate (archived as) | §5 BPB (KJV) | §4.1 Throughput @128 | Init ms | Provenance |
|---|---|---|---|---|
| **`archive/clean_base_soup_v1.source.gguf`** ← promoted | **1.2955** | 146.7 c/s | 308.8 | Weight-soup of best checkpoints in `runs/byte_clean_v1` |
| `archive/clean_base_v1.step2500.gguf` | 7.3999 | 146.5 c/s | 347.5 | Single checkpoint at step 2,500 of the same `byte_clean_v1` run |
| `archive/model.kjva_base.gguf` | 8.6848 | 126.0 c/s | 402.4 | External KJVA base weights (`../../kjva-bible/KJVA/training/weights.safetensors`); first weight imported into this repo on 2026-05-30 |

The 5.7× BPB advantage of `clean_base_soup_v1` over `clean_base_v1.step2500` came from soup averaging across the same training run, not from a different model design.

## Justification

1. **Best BPB on in-domain held-out** (the most architecture-fair number per spec §5).
2. **Same architecture, same params, same vocab** as the alternates — the promotion is a **canonical runtime attestation** decision, grounded in evidence rather than in any change of architecture or identity. The alternates are historical embodiments of the same singular cognitive identity.
3. **Determinism holds at T=0** (5-run identity check, all byte-identical) — see `benchmark_bundle/benchmark_results/clean_base_soup_v1/results_2026-06-05T012121Z.md`.
4. **Throughput and TTFT** are within noise of the next candidate — promotion does not cost runtime performance.

## Authority gradient (read this before adding new GGUFs)

```
canonical.gguf            ← THE runtime base. ONE file. The XMindClient default.
canonical.gguf.json       ← metadata for the runtime base
archive/*.gguf            ← historical evidence. DO NOT load at runtime.
archive/*.gguf.json       ← lineage of historical weights
promotion/                ← this folder: PROMOTION_RECORD.md + manifests
```

**Forbidden patterns:**
- Adding a new `.gguf` alongside `canonical.gguf` (always archive first, then promote a new canonical with a new record entry).
- Loading any `archive/*.gguf` directly in production code paths.
- Treating `model.kjva_base`, `clean_base_v1`, `clean_base_soup_v1` as separate model designs in code, prompts, naming, or documentation.

## Promotion ceremony (for future promotions)

1. Train a candidate; place its `.gguf` (with `.gguf.json` sidecar) at `training/gguf/candidate.gguf`.
2. Run the benchmark: `python3 benchmark_bundle/benchmark_results/run_xmind_benchmark.py --model training/gguf/candidate.gguf --dylib ... --out-dir benchmark_bundle/benchmark_results/<candidate-name>/`.
3. If the candidate beats `canonical.gguf` on §5 BPB AND does not regress §3.5 determinism, then:
   - Move the *current* `canonical.gguf` to `archive/<old-name>.gguf` (descriptive lineage name).
   - Move `candidate.gguf` to `archive/<candidate-name>.source.gguf` (preserve raw source).
   - Copy `archive/<candidate-name>.source.gguf` to `canonical.gguf` (new promoted runtime weight).
   - Append a new entry to `PROMOTION_RECORD.md` (this file) with date, SHA-256, BPB, and justification.
   - Update `lineage_manifest.json` and `benchmark_table.json`.
4. Run `validate_apex.py` to confirm canonical still works at runtime. If it fails, ROLL BACK the promotion immediately.

## Runtime resolution

`xmind_federation/client.py` resolves the runtime base as (in order):
1. `XMindClient(model_path=...)` keyword argument.
2. `XMIND_MODEL` environment variable.
3. **Default:** `models v7/training/gguf/canonical.gguf`.

The default is the doctrine's single source of truth at the runtime layer. Anything else is an override and should be justified explicitly.
