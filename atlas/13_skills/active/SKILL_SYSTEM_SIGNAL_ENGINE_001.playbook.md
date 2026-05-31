# system signal engine

<!-- Imported from /Users/desmondearly/.agents/skills/system-signal-engine/SKILL.md on 2026-05-27. -->
<!-- Full source directory archived at platform/sdlc/16_knowledge/external_collateral/local_runtime_skills_2026-05-27/agents/system-signal-engine. -->
<!-- Runtime alias: system-signal-engine; canonical id: SKILL_SYSTEM_SIGNAL_ENGINE_001. -->
**Summary.** Bridge to the GEN.OS system-signal-engine custom agent persona. Use when the user explicitly asks to use, adopt, or spawn system-signal-engine, or when the task needs this repo-specific role. Use this agent for real-time telemetry systems, event processing pipelines, signal aggregation, anomaly detection infrastructure, and metrics architecture. Invoke when designing or debugging system observability, alert pipelines, or event-driven architectures. Reads the project-local role file and memory from `.codex/` first, with `.claude/` as fallback.

Relative links from the source skill body were rewritten to the archived source directory when possible.

# System Signal Engine

## Overview

This skill bridges Codex to the GEN.OS custom agent profile `system-signal-engine`.
The canonical role file is `.codex/agents/system-signal-engine.md` with fallback `.claude/agents/system-signal-engine.md`.
The original agent metadata declares `project` memory; prefer `.codex/agent-memory/system-signal-engine/MEMORY.md` when present.

## Workflow

1. Resolve the role definition from `.codex/agents/system-signal-engine.md`. If it does not exist, fall back to `.claude/agents/system-signal-engine.md`.
2. Load `.codex/agent-memory/system-signal-engine/MEMORY.md` first when present. Fall back to `.claude/agent-memory/system-signal-engine/MEMORY.md` only if the `.codex` mirror is absent.
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
- Role summary from source: Use this agent for real-time telemetry systems, event processing pipelines, signal aggregation, anomaly detection infrastructure, and metrics architecture. Invoke when designing or debugging system observability, alert pipelines, or event-driven architectures.
- Treat the role file as authoritative for tone, domain boundaries, and acceptance criteria.
