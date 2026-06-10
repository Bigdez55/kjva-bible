# KJVA-1 / XMIND-1 — Production Readiness Report

**Date:** 2026-06-09
**Candidate:** KJVA-1 / XMIND-1 (canonical byte-LM + retrieval + constitutional governance)
**Source commit:** 1c35db7 (branch `release/kjva1-xmind1-production-candidate`)
**Prior milestone commit:** d52158a
**Prepared for:** Creator Sovereign promotion decision (replacement of the prior KJVA model/repo)

---

## 1. Executive verdict

**PRODUCTION-CANDIDATE READY — pending Creator approval.**

Every production gate is green. The production stack ships the stable canonical runtime plus
exact scripture retrieval and constitutional governance. No experimental adapter is promoted or
auto-loaded. The candidate is sealed, verifiable, and reversible.

This is a *candidate*, not an applied replacement: per doctrine, **canonical runtime authority is
not changed without explicit Creator authorization.**

## 2. Runtime artifact

```
Runtime authority : models v7/training/gguf/canonical.gguf
Architecture      : byte-level (tokenizer-free), vocab_size=259, n_layers=8, n_heads=6, d_model=384
Tokenizer         : utf8_byte_plus3 (byte b -> token id b+3; ids 0/1/2 = pad/bos/eos)
Single authority  : only canonical.gguf at training/gguf root; adapters opt-in via env var only
```

## 3. SHA verification

```
canonical.gguf SHA-256 : e59c69091a1772a347098efd68d7494419d5e82a75a3e064d95370d1d3f8fb93
Matches PRODUCTION_MANIFEST.json : YES
Unchanged across this sprint     : YES (no training run touched canonical)
```

## 4. CI status

```
Full pytest (models v7/tests)            : 268 passed / 4 skipped / 0 failed
Unified cognitive identity audit         : 12/12 PASS
Production runtime authority audit       : PASS (0 failures)
Byte codec regression (b+3 lock)         : 9/9 PASS
Counter-witness dataset provenance       : 6/6 PASS
```

## 5. Governance status

```
Constitutional governance                : 25/25 (closure sprint complete)
Covenants enforced                       : COV-001..COV-010
Wired governance tests                   : PASS (covenant_wired, governance_block, constitution gate, covenant_contract)
Note                                     : the pattern-enforcer has known phrasing gaps (pre-existing,
                                           tracked separately); the ML safety classifier + covenant gate
                                           are the primary enforcement.
```

## 6. Scripture grounding status

```
Grounding tests (test_scripture_grounding) : 14/14 PASS
Retrieval index                            : 36,822 verses (KJV OT + NT + Apocrypha)
Exact citation                             : /v1/cite returns exact corpus text
Topical / semantic retrieval               : returns relevant references incl. Apocrypha
generation_invoked on exact lookup         : False (retrieval, not LM confabulation)
```

## 7. Retrieval behavior (production contract)

```
Exact reference request  -> retrieve exact corpus text
Invalid reference        -> abstain ("not in KJV+Apocrypha corpus")
Topical request          -> relevant references first, explanation second
Raw generation           -> must NOT invent scripture citations
```

Exact scripture, invalid-reference abstention, and Apocrypha lookup are served by the retrieval
layer and are covered by the grounding gate. **Scripture counter-witness retrieval for
constitutional denials is a v2.1+ runtime enhancement (see §9, not yet wired).**

## 8. Regression gate status

```
Regression gate vs KJVA1_XMIND1_BASELINE_2026-06-08.json : PASS — all checked thresholds met
Baseline                                                  : sealed (DO_NOT_EDIT_BASELINE.md)
```

## 9. Known limitations

```
- Omni-PEFT v2 / v2.1 adapters are NOT promoted; production ships canonical only.
- Raw generation is not exact scripture lookup — exact verses come from retrieval.
- Counter-witness scripture retrieval (deny + cite-from-retrieval + redirect) is NOT yet wired
  at runtime; the v2.1 adapter learned to classify/route but confabulates scripture from weights,
  so content must be supplied by the retriever (verdict: FIX_RUNTIME_RETRIEVAL).
- General reasoning / math / code are not target capability claims (in-domain scribe model).
```

## 10. Rollback path

```
canonical.gguf is unchanged and is the only runtime artifact — rollback is inherent:
  - No promotion has occurred; reverting requires no model swap.
  - If a future adapter/model is promoted, restore by setting runtime authority back to
    canonical.gguf (SHA e59c6909…) and clearing TOKENLESS_ADAPTER/XMIND_ADAPTER env vars.
  - Full procedure: ROLLBACK_PLAN.md (to be finalized in the packaging phase).
```

## 11. Promotion exclusions

```
NOT promoted / NOT runtime-authoritative:
  - alignment_omnipeft_v1            (proof-of-architecture)
  - alignment_omnipeft_scribe_v2     (NO_PROMOTE)
  - alignment_omnipeft_scribe_v21    (NO_PROMOTE -> FIX_RUNTIME_RETRIEVAL)
  - peft_tournament_lora_winner_v1   (reclassified tournament)
  - all training/gguf/archive/* artifacts
Enforced by: scripts/audit_production_runtime_authority.py (PASS) + opt-in-only adapter loading.
```

## 12. Creator approval line

```
Creator Sovereign approval is REQUIRED before replacing the prior KJVA directory with
KJVA-1 / XMIND-1.

Approval authorizes DIRECTORY REPLACEMENT ONLY.
It does NOT authorize promotion of any archived SFT, Omni-PEFT, adapter, or candidate artifact.
canonical.gguf remains the sole runtime authority.

Approved by: ____________________________   Date: __________
```

---

## Outstanding before final packaging (continuation, not blockers)

- `MIGRATION_FROM_KJVA.md` (old→new path map), `ROLLBACK_PLAN.md`, `RELEASE_KJVA1_XMIND1_PRODUCTION_CANDIDATE.md`
- Release package layout under `release/kjva1-xmind1/`
- Parallel improvement track: runtime retrieval wiring (inference protocol + counter-witness
  retriever + retrieval-into-generation + grounded refusal formatter) — this is what would let a
  future v2.1+ adapter become a promotable upgrade. It does NOT block the canonical production candidate.
