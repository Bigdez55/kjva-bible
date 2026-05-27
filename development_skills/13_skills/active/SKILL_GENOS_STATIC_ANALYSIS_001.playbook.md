# GEN.OS Static Analysis — All 4 Tools Playbook

## Purpose
Run before every PR. Zero tolerance: 0 warnings, 0 violations, 0 CVEs. cppcheck --enable=warning,performance,portability \ --error-exitcode=1 \ --suppress=missingInclude \ --suppress=missingIncludeSystem \

## Imported Source
- Raw source: `16_knowledge/external_collateral/genos_codex_skills_2026-05-17/raw/static-analysis.md`
- Source repo: `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/GENESYS/GENESYS`
- Raw SHA-256: `892a0453e0c750425d73f09968e1bc53c200dd02752120a8872f35fd6fe9f689`

## Activation Rule
Use this skill when the request is in the GEN.OS / GENESYS domain and matches `static-analysis`, `static analysis`, or the source skill title.

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
