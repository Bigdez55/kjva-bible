# GEN.OS WAL Debug — XSTORE Crash Recovery Diagnosis Playbook

## Purpose
Diagnose and recover from XSTORE write-ahead log (WAL) failures in GEN.OS. - `xstore_open()` returns `XSTORE_ERR_CORRUPT` on boot after a crash - B+ tree key lookups return stale or wrong values after recovery

## Imported Source
- Raw source: `16_knowledge/external_collateral/genos_codex_skills_2026-05-17/raw/wal-debug.md`
- Source repo: `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/GENESYS/GENESYS`
- Raw SHA-256: `8733452942f1be8120df2583ad68c5e118552985828921b22fa089ad142dd81d`

## Activation Rule
Use this skill when the request is in the GEN.OS / GENESYS domain and matches `wal-debug`, `wal debug`, or the source skill title.

## Operating Contract
- Read the raw source file above for exact commands, gate definitions, templates, or checklists before executing domain-specific work.
- Preserve GEN.OS constraints around freestanding/system code, validation gates, sprint proof, and repository-specific command paths.
- Do not generalize these patterns into unrelated projects unless the user explicitly asks for cross-project adaptation.

## Required Output Shape
- Objective or gate being addressed.
- Source-backed procedure or checklist.
- Commands/files affected when applicable.
- Validation evidence required for closure.
- Blockers or assumptions.
