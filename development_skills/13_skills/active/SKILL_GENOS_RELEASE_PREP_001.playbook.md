# GEN.OS Release Preparation Protocol Playbook

## Purpose
Run at sprint close after all gates pass. python platform/check_language_policy.py ruff check . make -f Makefile.rfc002 run-tests pytest -q bandit -r platform/ ai/ -ll trivy fs . --severity CRITICAL,HIGH --exit-code 1 \

## Imported Source
- Raw source: `16_knowledge/external_collateral/genos_codex_skills_2026-05-17/raw/release-prep.md`
- Source repo: `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/GENESYS/GENESYS`
- Raw SHA-256: `2bd81d48250c18befcede7227351ea926b627180eb8f5d864adbfcec46d2aabb`

## Activation Rule
Use this skill when the request is in the GEN.OS / GENESYS domain and matches `release-prep`, `release prep`, or the source skill title.

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
