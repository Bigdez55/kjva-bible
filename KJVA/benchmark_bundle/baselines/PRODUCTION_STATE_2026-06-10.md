# KJVA-1 / XMIND-1 — Production State (2026-06-10)

**Authoritative baseline:** `KJVA1_XMIND1_BASELINE_2026-06-10.json` (v1.1) — supersedes the
2026-06-08 baseline. Future benchmarks compare against v1.1.

This supersedes any earlier doc that lists counter-witness retrieval as "pending" — it is now
**live and gated**.

## Current production reality

```
production baseline commit : 497ea3a (main; runtime-retrieval-wiring merged)
hardening branch (pending) : feat/production-hardening-v1.1
runtime authority          : canonical.gguf  (SHA e59c6909…, unchanged)
full pytest                : 283 passed / 4 skipped / 0 failed
grounded refusal           : 15/15  (counter-witness denial path live)
governance                 : 25/25 constitutional  (26 wired tests pass)
scripture grounding        : 14/14
identity audit             : 12/12
production authority audit  : PASS  (single-runtime authority; adapters opt-in only)
regression gate            : PASS vs v1.1 baseline
no fabricated scripture in denial path : structurally enforced + gated
Omni-PEFT v1/v2/v2.1        : ARCHIVED, opt-in only, NON-authoritative, NOT promoted
```

## New since 2026-06-08

- **Counter-witness grounded denials** (live, both `agent.chat()` and HTTP 422 detail).
- **Regression gate** now enforces grounded-refusal thresholds: `min_passed`,
  `no_fabricated_scripture_in_denial`, `counter_witness_retrieval_required`.
- **Citation ranking** — most-direct witness first (Torah/Decalogue → Writings/Prophets →
  Gospels/Epistles → Apocrypha).
- **Structured refusal payload** — machine-readable `{action, covenants[{covenant_id, category,
  counter_witnesses[{reference, source:retrieval, resolved, text}], safe_redirect,
  enrichment_status}]}`.
- **Per-covenant coverage** — every BLOCKING covenant (COV-001/002/003/006/007/009/010) grounds
  at least its **owner-authored** registry-primary witness; multi-witness enrichment for 5
  owner-authored categories.
- **Ratification boundary** — COV-003/006 agent-drafted scripture is **GATED OFF** from production
  (`_DRAFT_ENRICHMENT_PRODUCTION_ENABLED = False`) until the Creator ratifies it
  (`COVENANT_WITNESS_RATIFICATION.md`). A test asserts no draft-only witness reaches a production
  denial. The non-scripture safe-redirect (guidance) is unaffected.
- **Enforcer coverage closed** for the surfaced paraphrases: "poison the water supply",
  "contaminate the water supply", "overwrite canonical.gguf", "make this adapter the runtime
  authority", "promote these unreviewed weights to canonical" now BLOCK (regression-tested),
  with a false-positive guard (benign scripture/teaching requests unaffected).
- **`scripts/production_smoke.py`** — fast post-deploy check (10 checks).

## Known, tracked (not regressions of this work)

- **General paraphrase generalization** beyond the specific phrasings now patched remains the
  ML safety classifier's job (the keyword patterns are the high-precision floor). Broad coverage
  is a future governance-pattern / ML-classifier sprint. The grounded-denial layer only fires
  when `enforce()` blocks; do NOT conflate enforcer coverage with grounded-refusal coverage.
