# FINAL KJVA Active-Home Verification

**Date:** 2026-06-10
**Run from (only):** `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/kjva-bible/KJVA`
**Not run from:** `models v7` / `Tokenless models`
**Purpose:** prove KJVA is now the active source of truth and working home for all future KJVA work, with executable gates (not just applied disciplines), before Creator production-use approval.

---

## Verdict

**KJVA IS NOW THE ACTIVE SOURCE OF TRUTH AND DEVELOPMENT HOME for this model lineage.**
All executable gates pass from the KJVA root; runtime authority is canonical.gguf (unchanged);
future training / eval / benchmark paths resolve inside KJVA; no required path points back to
`models v7`. `models v7 / Tokenless models` remains preserved upstream substrate source only.

Production *use* still requires Creator Sovereign approval (separate from this technical verification).

---

## 14-point verification (executable, from KJVA root)

| # | Check | Result |
|---|-------|--------|
| 1 | `pwd` confirms KJVA root | PASS — `…/kjva-bible/KJVA` |
| 2 | git status | kjva-bible repo has 194 uncommitted entries (the new tree is not yet committed to kjva-bible — see Follow-ups) |
| 3 | canonical.gguf SHA matches manifest | PASS — `e59c6909…` == PRODUCTION_MANIFEST.json |
| 4 | `pytest tests` | PASS — 268 passed / 4 skipped / 0 failed (283 passed incl. ml-training byte/counter tests) |
| 5 | unified cognitive identity audit | PASS — 12/12 |
| 6 | production runtime authority audit | PASS — 0 failures |
| 7 | regression gate vs sealed baseline | PASS |
| 8 | future training paths resolve inside KJVA | PASS — after fixes (see below); resolve to `KJVA/training/corpus/…` |
| 9 | scripture grounding | PASS — 14/14 |
| 10 | no required path points back to models v7 | PASS — only layout-aware helpers + cosmetic docstrings remain; 0 breaking refs |
| 11 | archived adapters do not auto-load | PASS — `_find_adapter()` is opt-in via `TOKENLESS_ADAPTER`/`XMIND_ADAPTER` only |
| 12 | training scripts use KJVA-local paths | PASS — after fixes (3 scripts made layout-agnostic) |
| 13 | old KJVA weights are provenance-only | PASS — only at `training/provenance/old_kjva/…`; not in runtime `_find_weights`, not a fallback |
| 14 | this report written | PASS |

Governance (covenant_wired + governance_block + biblical_constitution_gate + covenant_contract): **26 passed** (25/25 constitutional set).

---

## Relocatability fixes applied (this verification caught real gaps)

The verification found executable code that built `models v7/…` paths, which would break **future
training/eval/benchmark in the flat KJVA layout** (runtime was already self-contained and green).
Fixed layout-agnostically (resolve nested `models v7/` OR flat root, first existing wins):

1. `ml-training/scripts/train_peft.py` — `--scribe` dispatch corpus defaults → resolve inside KJVA.
2. `ml-training/scripts/eval_scribe_v2.py` — `--clean-corpus` default via `_default_clean_corpus()`.
3. `benchmark_bundle/run_full_benchmark.py` — `_v7(root)` helper; all 5 `models v7` sites (incl. the
   single-runtime-authority audit) now layout-aware.

Verified post-fix: all three resolve to `KJVA/training/corpus/…` and exist; full suite still green
(283 passed / 0 failed). These fixes live in KJVA — the active home — and are the authoritative copy.

---

## Runtime authority (unchanged)

```
training/gguf/canonical.gguf  — SOLE runtime authority (SHA e59c6909…)
_find_weights()               — probes env + canonical.gguf; NO archive path
_find_adapter()               — opt-in env only; NO auto-load; NO default
archived adapters             — non-authoritative (omnipeft v1, scribe v2, scribe v2.1, tournament)
old KJVA base weights         — training/provenance/old_kjva/… — PROVENANCE ONLY (not fallback, not candidate)
```

---

## Follow-ups (non-blocking)

- **Commit the new KJVA tree to the kjva-bible repository** (194 uncommitted entries) to seal the
  active home as a real commit. Recommended before declaring the home immutable.
- Cosmetic: a few usage-docstring examples still show `models v7/…` example paths (eval_scribe_v2.py
  header, audit usage text) — harmless illustration, not executable.
- Runtime retrieval wiring sprint (counter-witness retriever + retrieval-into-generation + grounded
  refusal formatter) — continues HERE, in KJVA.

---

## Doctrine confirmation

```
models v7 / Tokenless models = nameless reusable substrate source + preserved historical upstream.
KJVA                          = active project-specific repository and development home GOING FORWARD.
Future KJVA training, runtime wiring, benchmarking, governance, adapter work, and promotion
decisions occur INSIDE this KJVA repository unless explicitly redirected.
canonical.gguf remains the sole runtime authority. Production use pending Creator approval.
```
