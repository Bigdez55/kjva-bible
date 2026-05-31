# platform integrity auditor

<!-- Imported from /Users/desmondearly/.agents/skills/platform-integrity-auditor/SKILL.md on 2026-05-27. -->
<!-- Full source directory archived at platform/sdlc/16_knowledge/external_collateral/local_runtime_skills_2026-05-27/agents/platform-integrity-auditor. -->
<!-- Runtime alias: platform-integrity-auditor; canonical id: SKILL_PLATFORM_INTEGRITY_AUDITOR_001. -->
**Summary.** Bridge to the GEN.OS platform-integrity-auditor custom agent persona. Use when the user explicitly asks to use, adopt, or spawn platform-integrity-auditor, or when the task needs this repo-specific role. Use this agent for code quality audits, static analysis, dead code detection, dependency hygiene reviews, and platform-wide conformance checks. Invoke after major refactors, before sprint merges, or when code quality metrics are unknown. Reads the project-local role file and memory from `.codex/` first, with `.claude/` as fallback.

Relative links from the source skill body were rewritten to the archived source directory when possible.

# Platform Integrity Auditor

## Overview

This skill bridges Codex to the GEN.OS custom agent profile `platform-integrity-auditor`.
The canonical role file is `.codex/agents/platform-integrity-auditor.md` with fallback `.claude/agents/platform-integrity-auditor.md`.

## Workflow

1. Resolve the role definition from `.codex/agents/platform-integrity-auditor.md`. If it does not exist, fall back to `.claude/agents/platform-integrity-auditor.md`.
2. Load `.codex/agent-memory/platform-integrity-auditor/MEMORY.md` first when present. Fall back to `.claude/agent-memory/platform-integrity-auditor/MEMORY.md` only if the `.codex` mirror is absent.
3. Load additional files from the matching agent-memory directory only when they are directly relevant to the task.
4. If the user explicitly asks for delegation, spawn a subagent and instruct it to adopt the resolved role file before doing work.
5. If the user did not explicitly ask for delegation, apply the role locally instead of spawning by default.
6. When multiple GEN.OS roles are involved, read `.codex/skills/agent-dispatch.md` or use the `genos-agent-dispatch` skill for sequencing.

## Delegation Guidance

- Use `agent_type="explorer"` for repo scans, audits, and bounded read-only analysis.
- Use `agent_type="worker"` for bounded implementation with clear file ownership.
- Use `agent_type="default"` when the role itself matters more than the execution mode.
- Mention the source role file path explicitly in the spawned prompt so the subagent adopts the correct persona.

## Notes

- Original model hint in the source file: `inherit`.
- Role summary from source: Use this agent for code quality audits, static analysis, dead code detection, dependency hygiene reviews, and platform-wide conformance checks. Invoke after major refactors, before sprint merges, or when code quality metrics are unknown.
- Treat the role file as authoritative for tone, domain boundaries, and acceptance criteria.
