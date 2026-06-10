# Migration: prior KJVA → KJVA-1 / XMIND-1

**Date:** 2026-06-09
**Source commit:** 1c35db7 (`release/kjva1-xmind1-production-candidate`)
**Replacement target:** `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/kjva-bible/KJVA`
**Mode:** whole-directory replacement (Creator-authorized), backup + staging + gates + reversible.

> **Recon correction (load-bearing).** The prior `kjva-bible/KJVA` is **not** an obsolete
> simpler model. It is (a) the **canonical base-weights home** — `training/weights.safetensors`
> (75.9 MB) is the exact base `canonical.gguf` was built from — and (b) the **same Tokenless
> substrate** (heptagon / governance / soul_manager / ai/xmind / constitution), at an **earlier**
> revision than models v7. KJVA-1 / XMIND-1 is the **upgrade** of that substrate plus the
> sealed canonical runtime. This migration therefore preserves the base weights and provenance
> by archiving the entire prior directory (nothing is destroyed; the backup is authoritative for
> rollback), and carries `training/weights.safetensors` forward into the new tree so the base
> remains live, not only in backup.

---

## 1. What is being replaced

The full prior `KJVA/` directory tree (substrate at an earlier revision + base weights +
legacy provenance records) is archived and replaced by the KJVA-1 / XMIND-1 production stack.

## 2. What remains compatible

- **Base weights** `training/weights.safetensors` (carried forward; SHA preserved).
- **Byte tokenizer contract**: byte b → token id `b + 3` (vocab 259). Unchanged — now enforced
  by the canonical `byte_codec` (the prior `b+1` loader bug is fixed).
- **Substrate contracts**: Heptagon (7-layer), XMIND inference, Covenant/governance,
  SoulManager — same contract shapes, upgraded implementations.
- **Retrieval index**: 36,822-verse KJV+Apocrypha corpus + index.

## 3. What is intentionally different

- **Runtime authority** is now a single sealed artifact: `training/gguf/canonical.gguf`
  (SHA e59c6909…). The prior tree had no promoted `.gguf` runtime.
- **Governance** is the closed constitutional set (COV-001..COV-010, 25/25) incl. the new
  `constitutional_gate.py`, `creator_sovereign.py`, `deployment_owner.py`.
- **Production authority enforcement**: `scripts/audit_production_runtime_authority.py`.
- **Sealed regression baseline** + gate.

## 4. Runtime path changes

| Old (prior KJVA) | New (KJVA-1 / XMIND-1) |
|---|---|
| base weights only (`training/weights.safetensors`) | `training/gguf/canonical.gguf` is runtime authority (base weights retained for provenance) |
| tokenizer: byte (b+3), but consumers risked b+1 loaders | canonical `byte_codec` (b = vocab−256) everywhere |
| scripture lookup ad hoc | retrieval layer (exact + topical + invalid-abstention) |
| governance partial | constitutional governance 25/25 |

## 5. Model artifact changes

- Runtime: **canonical.gguf** (vocab 259, n_layers 8, d_model 384, byte_offset 3).
- Base: `weights.safetensors` retained (provenance / re-export).
- Archived candidates (NON-authoritative, never auto-load): Omni-PEFT v1/v2/v2.1 adapters,
  tournament LoRA, historical SFT/soup.

## 6. Retrieval behavior

```
exact reference  -> retrieve exact corpus text (generation_invoked=False)
invalid reference -> abstain ("not in KJV+Apocrypha corpus")
topical request  -> references first, explanation second
raw generation   -> must NOT invent scripture citations
```

## 7. Governance behavior

COV-001..COV-010 enforced; 25/25. Scripture **counter-witness** retrieval for denials
(deny + cite-from-retrieval + redirect) is a v2.1+ runtime enhancement — **pending wiring**
(the adapter classifies/routes; scripture content must come from retrieval).

## 8. Testing requirements (must pass before and after replacement)

```
pytest tests                                    : 268 passed / 4 skipped / 0 failed (or better)
scripts/audit_unified_cognitive_identity.py     : 12/12 PASS
scripts/audit_production_runtime_authority.py   : PASS
benchmark_bundle/baselines/regression_gate.py   : PASS
tests/test_scripture_grounding.py               : 14/14 PASS
governance                                      : 25/25 PASS
canonical.gguf SHA                              : e59c6909…
```

## 9. Rollback instructions

See `ROLLBACK_PLAN.md`. In brief: the prior tree is preserved at `KJVA_REPLACED_<stamp>` (and
`KJVA_BACKUP_<stamp>`); restoring is a directory move back. canonical.gguf is unchanged, so no
model rollback is involved.
