# hardware integration engineer

<!-- Imported from /Users/desmondearly/.agents/skills/hardware-integration-engineer/SKILL.md on 2026-05-27. -->
<!-- Full source directory archived at platform/sdlc/16_knowledge/external_collateral/local_runtime_skills_2026-05-27/agents/hardware-integration-engineer. -->
<!-- Runtime alias: hardware-integration-engineer; canonical id: SKILL_HARDWARE_INTEGRATION_ENGINEER_001. -->
**Summary.** Bridge to the GEN.OS hardware-integration-engineer custom agent persona. Use when the user explicitly asks to use, adopt, or spawn hardware-integration-engineer, or when the task needs this repo-specific role. Use this agent for HP EliteBook x360 hardware integration, device driver design, firmware interaction, power management, and hardware-specific kernel configuration. Invoke for hardware-related bugs, driver development, or device capability mapping. Reads the project-local role file and memory from `.codex/` first, with `.claude/` as fallback.

Relative links from the source skill body were rewritten to the archived source directory when possible.

# Hardware Integration Engineer

## Overview

This skill bridges Codex to the GEN.OS custom agent profile `hardware-integration-engineer`.
The canonical role file is `.codex/agents/hardware-integration-engineer.md` with fallback `.claude/agents/hardware-integration-engineer.md`.
The original agent metadata declares `project` memory; prefer `.codex/agent-memory/hardware-integration-engineer/MEMORY.md` when present.

## Workflow

1. Resolve the role definition from `.codex/agents/hardware-integration-engineer.md`. If it does not exist, fall back to `.claude/agents/hardware-integration-engineer.md`.
2. Load `.codex/agent-memory/hardware-integration-engineer/MEMORY.md` first when present. Fall back to `.claude/agent-memory/hardware-integration-engineer/MEMORY.md` only if the `.codex` mirror is absent.
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
- Role summary from source: Use this agent for HP EliteBook x360 hardware integration, device driver design, firmware interaction, power management, and hardware-specific kernel configuration. Invoke for hardware-related bugs, driver development, or device capability mapping.
- Treat the role file as authoritative for tone, domain boundaries, and acceptance criteria.
