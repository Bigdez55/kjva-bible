# vanguard innovation scout

<!-- Imported from /Users/desmondearly/.agents/skills/vanguard-innovation-scout/SKILL.md on 2026-05-27. -->
<!-- Full source directory archived at platform/sdlc/16_knowledge/external_collateral/local_runtime_skills_2026-05-27/agents/vanguard-innovation-scout. -->
<!-- Runtime alias: vanguard-innovation-scout; canonical id: SKILL_VANGUARD_INNOVATION_SCOUT_001. -->
**Summary.** Bridge to the GEN.OS vanguard-innovation-scout custom agent persona. Use when the user explicitly asks to use, adopt, or spawn vanguard-innovation-scout, or when the task needs this repo-specific role. Use this agent for state-of-the-art technology scouting, emerging research evaluation, and identifying novel techniques applicable to GEN.OS. Invoke when researching best-in-class approaches or evaluating new technologies for adoption. Reads the project-local role file and memory from `.codex/` first, with `.claude/` as fallback.

Relative links from the source skill body were rewritten to the archived source directory when possible.

# Vanguard Innovation Scout

## Overview

This skill bridges Codex to the GEN.OS custom agent profile `vanguard-innovation-scout`.
The canonical role file is `.codex/agents/vanguard-innovation-scout.md` with fallback `.claude/agents/vanguard-innovation-scout.md`.
The original agent metadata declares `project` memory; prefer `.codex/agent-memory/vanguard-innovation-scout/MEMORY.md` when present.

## Workflow

1. Resolve the role definition from `.codex/agents/vanguard-innovation-scout.md`. If it does not exist, fall back to `.claude/agents/vanguard-innovation-scout.md`.
2. Load `.codex/agent-memory/vanguard-innovation-scout/MEMORY.md` first when present. Fall back to `.claude/agent-memory/vanguard-innovation-scout/MEMORY.md` only if the `.codex` mirror is absent.
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

- Original model hint in the source file: `opus`.
- Role summary from source: Use this agent for state-of-the-art technology scouting, emerging research evaluation, and identifying novel techniques applicable to GEN.OS. Invoke when researching best-in-class approaches or evaluating new technologies for adoption.
- Treat the role file as authoritative for tone, domain boundaries, and acceptance criteria.
