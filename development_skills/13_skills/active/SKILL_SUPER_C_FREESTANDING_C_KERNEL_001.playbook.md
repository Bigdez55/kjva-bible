# Freestanding C Kernel Development — 57 Core Skills Playbook

## Purpose
Build a bare-metal x86-64 kernel with zero libc dependency. Every kernel .c file begins with `#ifndef PAL_FREESTANDING` / `#define PAL_FREESTANDING` / `#endif`. Prevents libc headers from leaking through PAL. - **File:** Every kernel source file, enforced by CI banned-include scan

## Imported Source
- Raw source: `16_knowledge/external_collateral/desmond_super_c_skills_2026-05-17/raw/claude_skills/freestanding-c-kernel/SKILL.md`
- Source repo: `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/desmond-super-c`
- Raw SHA-256: `141f79b339c7da675a423fcb7361a089ba3aa6ba5b2fe898e45399bbc0acc21d`

## Activation Rule
Use this skill when the request is in the SUPER C / desmond-super-c domain and matches `freestanding-c-kernel`, `freestanding c kernel`, or the source skill title.

## Operating Contract
- Read the raw source before issuing implementation, gate, compiler, kernel, tutorial, governance, security, XISC, or toolchain guidance.
- Preserve the source skill's explicit scope boundaries and validation discipline.
- Do not convert source-specific claims into completion claims without evidence from the target repo.

## Required Output Shape
- Objective and active SUPER C context.
- Applicable source rules or skill patterns.
- Implementation or review sequence.
- Validation gates and proof artifacts.
- Blockers, risk class, or claim boundary.
