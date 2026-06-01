# GEN.OS CI Pre-flight — Pre-Push Validation Checklist Playbook

## Purpose
Run this before every `git push`. Mirrors CI exactly. No surprises. cd /Users/desmondearly/Library/CloudStorage/OneDrive-Personal/GENESYS/GENESYS python platform/check_language_policy.py || { echo "BLOCKED: Language policy"; exit 1; }

## Imported Source
- Raw source: `16_knowledge/external_collateral/genos_codex_skills_2026-05-17/raw/ci-preflight.md`
- Source repo: `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/GENESYS/GENESYS`
- Raw SHA-256: `04a226381c8c3eb3b8bdf7422994063d2f4df11233d5dc8eeafb4cff43ae4d18`

## Activation Rule
Use this skill when the request is in the GEN.OS / GENESYS domain and matches `ci-preflight`, `ci preflight`, or the source skill title.

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
