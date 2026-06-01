# GEN.OS ISO Build Pipeline Playbook

## Purpose
Build phases 0-9. Run on Ubuntu build host (Linux required for debootstrap). Reference: `GENOS_BUILD_EXECUTION_PLAN.md`, `build/` directory. sudo apt-get install \ debootstrap docker.io qemu-utils squashfs-tools \

## Imported Source
- Raw source: `16_knowledge/external_collateral/genos_codex_skills_2026-05-17/raw/iso-build.md`
- Source repo: `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/GENESYS/GENESYS`
- Raw SHA-256: `82fad311b4ae9276c87a4eac42984b7c8c7a053375e8e8da2e08fb0a74fb6fb9`

## Activation Rule
Use this skill when the request is in the GEN.OS / GENESYS domain and matches `iso-build`, `iso build`, or the source skill title.

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
