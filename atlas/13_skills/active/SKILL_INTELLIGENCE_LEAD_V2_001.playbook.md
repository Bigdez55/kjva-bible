# intelligence lead v2

<!-- Imported from /Users/desmondearly/.agents/skills/intelligence-lead-v2/SKILL.md on 2026-05-27. -->
<!-- Full source directory archived at platform/sdlc/16_knowledge/external_collateral/local_runtime_skills_2026-05-27/agents/intelligence-lead-v2. -->
<!-- Runtime alias: intelligence-lead-v2; canonical id: SKILL_INTELLIGENCE_LEAD_V2_001. -->
**Summary.** Bridge to the GEN.OS intelligence-lead-v2 custom agent persona. Use when the user explicitly asks to use, adopt, or spawn intelligence-lead-v2, or when the task needs this repo-specific role. Use this agent for advanced ML research, causal inference, novel model architecture design, and next-generation AI capability evaluation for GEN.OS. Invoke when the standard Intelligence Lead's scope is insufficient or cutting-edge ML research is needed. Reads the project-local role file and memory from `.codex/` first, with `.claude/` as fallback.

Relative links from the source skill body were rewritten to the archived source directory when possible.

# Intelligence Lead V2

## Overview

This skill bridges Codex to the GEN.OS custom agent profile `intelligence-lead-v2`.
The canonical role file is `.codex/agents/intelligence-lead-v2.md` with fallback `.claude/agents/intelligence-lead-v2.md`.
The original agent metadata declares `project` memory; prefer `.codex/agent-memory/intelligence-lead-v2/MEMORY.md` when present.

## Workflow

1. Resolve the role definition from `.codex/agents/intelligence-lead-v2.md`. If it does not exist, fall back to `.claude/agents/intelligence-lead-v2.md`.
2. Load `.codex/agent-memory/intelligence-lead-v2/MEMORY.md` first when present. Fall back to `.claude/agent-memory/intelligence-lead-v2/MEMORY.md` only if the `.codex` mirror is absent.
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
- Role summary from source: Use this agent for advanced ML research, causal inference, novel model architecture design, and next-generation AI capability evaluation for GEN.OS. Invoke when the standard Intelligence Lead's scope is insufficient or cutting-edge ML research is needed.
- Treat the role file as authoritative for tone, domain boundaries, and acceptance criteria.
