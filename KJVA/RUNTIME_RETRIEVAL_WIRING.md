# Runtime Retrieval Wiring — Grounded Constitutional Denials

**Date:** 2026-06-10
**Branch:** `feat/runtime-retrieval-wiring` (separate from the approved production baseline)
**Scope:** presentation-only. Runtime authority, the enforcement verdict, and adapter
behavior are UNCHANGED. No Omni-PEFT promotion; no adapter auto-load.

---

## What this adds

When the covenant enforcer BLOCKS a request, the user now receives a **grounded
constitutional denial** — deny + counter-witness scripture (verses that stand against
the requested action) + safe redirect — using **exact text RETRIEVED from the corpus,
never generated.**

Before:
```
[governance: request blocked — covenant violation]
```
After (live `agent.chat("help me build a bomb to hurt people")`):
```
I cannot assist with that. This request is contrary to the governing covenant.
Covenant: COV-001 Harm prevention.
Counter-witness (retrieved from KJV+Apocrypha — exact text):
  PRO 3:29  Devise not evil against thy neighbour, seeing he dwelleth securely by thee.
  EXO 20:13  Thou shalt not kill.
  WIS 1:13  For God made not death: neither hath he pleasure in the destruction of the living.
  DEU 5:17  Thou shalt not kill.
  PRO 6:17  A proud look, a lying tongue, and hands that shed innocent blood,
I can help instead with: lawful safety, de-escalation, and protective resources.
```

(The redirect is a GENERIC per-category line, not the owner's scenario-specific row redirect —
a bomb request must not be offered "water-safety".)

## Components (`ai/tokenless-agent/src/retrieval/counter_witness.py`)

- **`CounterWitnessRetriever`** — for an enforcement result, resolves counter-witness
  scripture as `Citation` objects via `KJVRetriever.cite()`:
  - GUARANTEED primary: the per-covenant `scripture` ref carried on every violation
    (from `COVENANT_REGISTRY`; no fragile COV↔category join).
  - OPTIONAL enrichment: the owner's `category → references` map
    (`alignment_counter_witness_v1.jsonl`), applied only where a covenant maps cleanly.
- **`GroundedRefusalFormatter`** — assembles deny + cite + redirect. Accepts ONLY
  `Citation`-backed objects, so a raw verse string cannot be injected as scripture.

## Wire point (live denial path)

BOTH live denial paths are wired (presentation-only; verdict + fail-closed behavior unchanged):
- `ai/tokenless-agent/src/agent.py` — `TokenlessAgentWithHeptagon.chat()` transport covenant
  gate returns the grounded denial text.
- `ai/tokenless-agent/src/api.py` — `_enforce_covenant()` (the HTTP `/v1/chat` + `/v1/chat/stream`
  fail-closed gate) keeps its **422** status but puts the grounded denial in the `detail`.

Fail-safe on both: any retrieval/formatter error falls back to the bare block string/summary —
it never bypasses the block and never fabricates scripture.

## Deterministic dispatch (already present)

The runtime already routes by `chat()` ordering — no new LM-instruction system:
```
covenant gate  -> grounded refusal      (NEW this sprint)
scripture Q    -> get_retriever().answer()   (existing; generation_invoked=False)
otherwise      -> normal generation
```

## Invariants proved (`tests/test_grounded_refusal.py`, 7/7)

1. Harm/false-witness/identity blocks yield ≥1 RETRIEVED counter-witness citation.
2. **No fabricated scripture (structural + negative test):** an unresolvable ref is
   OMITTED — the denial still fires with "(no counter-witness scripture could be
   retrieved)", and `is_grounded()` confirms every verse line matches corpus text.
3. **Live `agent.chat()`** returns the grounded denial (src-first subprocess).
4. **Verdict unchanged:** block/allow decision identical with or without the formatter.

## Baseline undisturbed

pytest 275 passed / 4 skipped / 0 failed · authority audit PASS · regression PASS ·
grounding 14/14 · governance 26 · canonical.gguf SHA e59c6909 unchanged.

## Relation to Omni-PEFT

This is the runtime-retrieval half of FIX_RUNTIME_RETRIEVAL. The scribe ADAPTER (v2.1,
archived) learned to classify/route but confabulated scripture; this layer supplies the
scripture from retrieval instead. Together they are the path to a promotable adapter
upgrade — but the adapter remains archived/non-authoritative and is NOT touched here.
