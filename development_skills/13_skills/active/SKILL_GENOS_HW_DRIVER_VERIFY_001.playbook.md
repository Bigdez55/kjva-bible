# GEN.OS HW Driver Verify — HP EliteBook x360 Driver Verification Playbook

## Purpose
Verify hardware driver correctness for the HP EliteBook x360 target (Sprint 7-9 drivers). /* Config Mechanism #1 — verify address construction */ /* addr = (1<<31) | (bus<<16) | (dev<<11) | (fn<<8) | (reg & 0xFC) */

## Imported Source
- Raw source: `16_knowledge/external_collateral/genos_codex_skills_2026-05-17/raw/hw-driver-verify.md`
- Source repo: `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/GENESYS/GENESYS`
- Raw SHA-256: `51ef7fe3802232e99e2c19c6f7a0d2af082aae82b937c09826729f591cc70c46`

## Activation Rule
Use this skill when the request is in the GEN.OS / GENESYS domain and matches `hw-driver-verify`, `hw driver verify`, or the source skill title.

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
