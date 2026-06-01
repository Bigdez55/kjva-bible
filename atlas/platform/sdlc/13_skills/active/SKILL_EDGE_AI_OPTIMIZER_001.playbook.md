# edge ai optimizer

<!-- Imported from /Users/desmondearly/.agents/skills/edge-ai-optimizer/SKILL.md on 2026-05-27. -->
<!-- Full source directory archived at platform/sdlc/16_knowledge/external_collateral/local_runtime_skills_2026-05-27/agents/edge-ai-optimizer. -->
<!-- Runtime alias: edge-ai-optimizer; canonical id: SKILL_EDGE_AI_OPTIMIZER_001. -->
**Summary.** Bridge to the GEN.OS edge-ai-optimizer custom agent persona. Use when the user explicitly asks to use, adopt, or spawn edge-ai-optimizer, or when the task needs this repo-specific role. Use this agent for on-device AI optimization, Ollama/Llama model quantization, inference latency reduction, memory-constrained model deployment, and edge ML pipeline design. Invoke when GENESYS AI inference is too slow, uses too much memory, or needs hardware-specific tuning. Reads the project-local role file and memory from `.codex/` first, with `.claude/` as fallback.

Relative links from the source skill body were rewritten to the archived source directory when possible.

# Edge Ai Optimizer

## Overview

This skill bridges Codex to the GEN.OS custom agent profile `edge-ai-optimizer`.
The canonical role file is `.codex/agents/edge-ai-optimizer.md` with fallback `.claude/agents/edge-ai-optimizer.md`.
The original agent metadata declares `project` memory; prefer `.codex/agent-memory/edge-ai-optimizer/MEMORY.md` when present.

## Workflow

1. Resolve the role definition from `.codex/agents/edge-ai-optimizer.md`. If it does not exist, fall back to `.claude/agents/edge-ai-optimizer.md`.
2. Load `.codex/agent-memory/edge-ai-optimizer/MEMORY.md` first when present. Fall back to `.claude/agent-memory/edge-ai-optimizer/MEMORY.md` only if the `.codex` mirror is absent.
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
- Role summary from source: Use this agent for on-device AI optimization, Ollama/Llama model quantization, inference latency reduction, memory-constrained model deployment, and edge ML pipeline design. Invoke when GENESYS AI inference is too slow, uses too much memory, or needs hardware-specific tuning.
- Treat the role file as authoritative for tone, domain boundaries, and acceptance criteria.
