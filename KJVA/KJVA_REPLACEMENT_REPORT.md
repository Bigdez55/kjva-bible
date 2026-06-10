# KJVA Replacement Report — KJVA-1 / XMIND-1

**Replacement type:** whole-directory migration executed under Creator instruction; production use
pending Creator approval. Backup + staging + gated + reversible.

---

## Source-of-truth doctrine (read first)

`models v7` was the **nameless, reusable substrate source**. After this replacement, **KJVA is now
the active project-specific repository and development home for this model lineage.** All future
KJVA-specific training, runtime wiring, benchmarking, governance changes, adapter work, and
promotion decisions occur **inside the KJVA repository** unless explicitly redirected. The
`Tokenless models / models v7` source remains preserved as the reusable substrate source and
historical upstream — it is not where KJVA work continues. KJVA is not merely a deploy artifact.

---

## 1. Replacement date
2026-06-09 (stamp `20260609_233014`)

## 2. Old path
`/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/kjva-bible/KJVA` (prior tree)

## 3. Backup paths (rollback assets — do not delete until Creator-accepted)
```
KJVA_BACKUP_20260609_233014     # cp/rsync backup of the prior tree (verified: base weights 72M present)
KJVA_REPLACED_20260609_233014   # the prior tree, moved aside at the swap
KJVA_OLD_FILE_INVENTORY_20260609_233014.txt
```

## 4. New production path
`/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/kjva-bible/KJVA`
(now the full models v7 substrate, flat — no nested `models v7/`; the development home going forward)

## 5. Canonical GGUF SHA
```
training/gguf/canonical.gguf
SHA-256: e59c69091a1772a347098efd68d7494419d5e82a75a3e064d95370d1d3f8fb93   (unchanged)
```

## 6. Full test result (from final KJVA path)
`pytest tests/` → **268 passed / 4 skipped / 0 failed**
`ml-training/tests` byte-codec + counter-witness → **15 passed**

## 7. Unified identity audit
`scripts/audit_unified_cognitive_identity.py` → **12 PASS / 0 FAIL**

## 8. Production runtime authority audit
`scripts/audit_production_runtime_authority.py` → **PASS** (single root gguf, no archive in
resolution, adapters opt-in only, SHA matches manifest)

## 9. Regression gate
`benchmark_bundle/baselines/regression_gate.py` vs sealed baseline → **PASS**

## 10. Scripture grounding
`tests/test_scripture_grounding.py` → **14/14 PASS**

## 11. Governance
covenant_wired + governance_block + biblical_constitution_gate + covenant_contract → **26 passed**
(constitutional set 25/25; COV-001..COV-010)

## 12. Archived candidates status
Retained for lineage / benchmark / rollback / future training; NON-authoritative; never auto-load.
```
training/gguf/archive/*                       (historical SFT / soup / aligned candidates)
training/gguf/archive/adapters/*              (omnipeft v1, scribe v2, scribe v2.1, tournament)
ml-training/runs/*                            (training runs carried forward)
training/provenance/old_kjva/*                (prior KJVA base weights + records — provenance only)
```

Old KJVA base weights (`training/provenance/old_kjva/training/weights.safetensors`) are preserved
for **provenance and lineage only**. They are **not** fallback runtime weights, and **not** a
candidate promotion artifact unless separately re-registered through the promotion process.
canonical.gguf is and remains the sole runtime authority.

## 13. Omni-PEFT status
```
v2  (scribe)   : NO_PROMOTE
v2.1 (scribe)  : NO_PROMOTE -> FIX_RUNTIME_RETRIEVAL
Not promoted. Not runtime-authoritative. Opt-in via TOKENLESS_ADAPTER/XMIND_ADAPTER only.
```

## 14. Rollback instructions
See `ROLLBACK_PLAN.md`. In brief:
```bash
ROOT="/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/kjva-bible"; STAMP="20260609_233014"
mv "$ROOT/KJVA" "$ROOT/KJVA_FAILED_REPLACEMENT_$STAMP"
mv "$ROOT/KJVA_REPLACED_$STAMP" "$ROOT/KJVA"
```
There is no active model-weight rollback because canonical.gguf remains unchanged. There is still a
directory-level rollback path (above) to restore the prior KJVA tree.

## 15. Creator approval line
```
The directory replacement is COMPLETE and gate-verified. PRODUCTION USE of the new KJVA tree
requires Creator Sovereign approval.

Approval authorizes production use of KJVA-1 / XMIND-1 (canonical.gguf + retrieval + governance).
It does NOT authorize promotion of any archived SFT / Omni-PEFT / adapter / candidate artifact.
canonical.gguf remains the sole runtime authority.

Creator Sovereign approval recorded before production use:
Approved by: ____________________________   Date: __________
```

---

## Follow-ups (non-blocking; for future work in the new KJVA home)
- Future training base-checkpoint paths that referenced `../kjva-bible/KJVA/training/weights.safetensors`
  now resolve to this same tree; the prior base is preserved at
  `training/provenance/old_kjva/training/weights.safetensors`. Rewire training base paths when the
  next training run is set up.
- Runtime retrieval wiring sprint (parallel track): inference-instruction protocol + counter-witness
  retriever + retrieval-into-generation + grounded refusal formatter (turns the v2.1 adapter's
  learned routing into grounded biblical responses; prerequisite for a future promotable upgrade).
- The `Tokenless models / models v7` source is preserved as the reusable substrate source and
  historical upstream (this work committed on `release/kjva1-xmind1-production-candidate`). It is
  NOT where KJVA work continues. Per the source-of-truth doctrine above, **future KJVA-specific
  development happens inside this KJVA repository** — do not make KJVA changes in `models v7`.
