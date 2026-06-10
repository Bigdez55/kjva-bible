# KJVA-1 / XMIND-1 — Production State (2026-06-10)

**Authoritative baseline:** `KJVA1_XMIND1_BASELINE_2026-06-10.json` (v1.1) — supersedes the
2026-06-08 baseline. Future benchmarks compare against v1.1.

This supersedes any earlier doc that lists counter-witness retrieval as "pending" — it is now
**live and gated**.

## Current production reality

```
production baseline commit : 497ea3a (main; runtime-retrieval-wiring merged)
runtime authority          : canonical.gguf  (SHA e59c6909…, unchanged)
full pytest                : 280 passed / 4 skipped / 0 failed
grounded refusal           : 12/12  (counter-witness denial path live)
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
  at least its registry-primary witness; multi-witness enrichment for 7 categories. COV-003/006
  enrichment is **agent-drafted, pending Creator ratification** (flagged in payload).
- **`scripts/production_smoke.py`** — fast post-deploy check (10 checks).

## Known, tracked (not regressions of this work)

- **Enforcer paraphrase gaps:** the covenant enforcer's keyword/ML patterns miss some natural
  phrasings (e.g. "overwrite canonical.gguf", "poison the water supply"). The grounded-denial
  layer only fires when `enforce()` blocks, so these phrasings produce no denial. This is a
  pre-existing enforcer-coverage issue, separate from the grounded layer — candidate for a future
  governance-pattern / ML-classifier sprint. Do NOT conflate with grounded-refusal coverage.
