# Release: KJVA-1 / XMIND-1 Production Candidate

**Release type:** production candidate (NOT applied; awaits Creator approval for directory replacement)
**Date:** 2026-06-09
**Source branch / commit:** `release/kjva1-xmind1-production-candidate` @ 1c35db7
**Prior milestone:** d52158a

---

## Runtime authority

```
canonical.gguf
SHA-256 : e59c69091a1772a347098efd68d7494419d5e82a75a3e064d95370d1d3f8fb93
vocab=259  n_layers=8  n_heads=6  d_model=384  byte_offset=3 (utf8_byte_plus3)
```

## What ships in production

```
canonical.gguf  +  XMIND runtime  +  exact scripture retrieval
+ invalid-citation abstention  +  constitutional governance (25/25)
+ single-runtime-authority audit  +  sealed regression gate  +  production manifest
```

## What does NOT ship (archived, non-authoritative, never auto-loads)

```
Omni-PEFT v1 / scribe v2 / scribe v2.1 adapters  (NO_PROMOTE)
peft_tournament_lora_winner_v1                    (reclassified)
historical SFT / soup GGUFs                       (archive/)
```

## Verified gates (commit 1c35db7)

| Gate | Result |
|---|---|
| pytest (models v7/tests) | 268 passed / 4 skipped / 0 failed |
| unified cognitive identity audit | 12/12 PASS |
| production runtime authority audit | PASS |
| regression gate vs sealed baseline | PASS |
| scripture grounding | 14/14 |
| constitutional governance | 25/25 |
| byte-codec lock + counter-witness provenance | 9/9 + 6/6 |
| canonical.gguf SHA | e59c6909… unchanged |

## Sprint deltas since prior milestone

- **byte-offset fix** (b+1 → b+3 canonical `byte_codec`) — corrected every flat PEFT/SFT/DPO loader.
- **production runtime authority audit** — enforces single-runtime authority.
- **Omni-PEFT scribe v2 / v2.1** — archived candidates; completion-masking + counter-witness
  data + per-epoch Pareto; verdict FIX_RUNTIME_RETRIEVAL (not promoted).
- production manifest + readiness report + migration + rollback docs.

## Replacement (whole-directory, Creator-authorized)

Procedure: backup → stage → gate-from-staging → swap → gate-from-final → replacement report.
Gated on staging gates passing; reversible via `ROLLBACK_PLAN.md`. The prior KJVA tree
(base weights + provenance) is archived, not destroyed; base weights are carried forward.

## Approval

```
Creator Sovereign approval authorizes DIRECTORY REPLACEMENT ONLY.
It does NOT authorize promotion of any archived adapter/candidate.
canonical.gguf remains the sole runtime authority.

Approved by: ____________________________   Date: __________
```
