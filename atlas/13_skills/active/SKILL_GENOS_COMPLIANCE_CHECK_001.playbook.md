# GEN.OS Compliance Check — Full Platform Validation Playbook

## Purpose
Run before sprint close and before every PR to `main`. python platform/check_language_policy.py Exit 0 = PASS. Run `/compile-check` skill. Record pass count. Must meet sprint target.

## Imported Source
- Raw source: `16_knowledge/external_collateral/genos_codex_skills_2026-05-17/raw/compliance-check.md`
- Source repo: `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/GENESYS/GENESYS`
- Raw SHA-256: `a4279761801267da0649caecdef14170119570c689eef77fe92572d633b02aa0`

## Activation Rule
Use this skill when the request is in the GEN.OS / GENESYS domain and matches `compliance-check`, `compliance check`, or the source skill title.

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
