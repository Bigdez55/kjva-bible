# GEN.OS Security Audit Checklist Playbook

## Purpose
Run with `guardian-sentinel` + `reliability-security-sentinel` agents. Classify findings: P0 (critical/blocking), P1 (fix before release), P2 (fix this sprint), P3 (backlog). grep -r "Capabilities" init/gensd/services/*.gsd 2>/dev/null

## Imported Source
- Raw source: `16_knowledge/external_collateral/genos_codex_skills_2026-05-17/raw/security-audit.md`
- Source repo: `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/GENESYS/GENESYS`
- Raw SHA-256: `9b57b883a25d70567aa98e9a66615e062af4258ccebf37296334c883e84ddc3a`

## Activation Rule
Use this skill when the request is in the GEN.OS / GENESYS domain and matches `security-audit`, `security audit`, or the source skill title.

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
