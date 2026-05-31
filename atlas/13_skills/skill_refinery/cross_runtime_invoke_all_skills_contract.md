# Cross-Runtime Invoke-All-Skills Contract

## Purpose

This contract prevents Claude Code, Codex, or any other coding-agent runtime from misinterpreting `invoke all skills` as only the small set of externally tool-callable skills.

`invoke all skills` means:

```text
Apply the ATLAS universal skill coverage matrix and selected repository-native playbooks.
```

It does not mean:

```text
Call every runtime-registered Skill tool.
```

## Applies To

- Claude Code
- Codex
- Gemini-style repo agents
- Any imported assistant surface under `.claude`, `.codex`, or `.gemini`

## Required Runtime Behavior

When the user says `invoke all skills`, `use all skills`, `all skills now`, `activate all skills`, or `all skills and agents`, the agent must:

1. Run or follow `infrastructure/scripts/route_intent.py` for the phrase.
2. Use `platform/sdlc/13_skills/skill_refinery/universal_skill_invocation_policy.md` as the governing policy.
3. Treat `platform/sdlc/13_skills/active/SKILL_*.yaml` and matching `.playbook.md` files as repository-native disciplines, even if the runtime cannot call them through a Skill tool.
4. Report `tool_called_skills` separately from `playbook_applied_disciplines`.
5. Suppress project-specific skills unless the request contains a binding target such as `IPOS`, `Elson`, `Bookworm`, `ATLAS`, `compiler`, or another explicit domain.
6. Do not run destructive, setup, background, or config-writing tools unless the user explicitly requested that specific tool action.

## Required Response Fields

Every cross-runtime all-skills response must include:

- `tool_called_skills`
- `playbook_applied_disciplines`
- `activated_project_specific_skills`
- `suppressed_project_specific_skills`
- `validation_or_proof_gates`
- `misses_logged_or_none`

## Forbidden Response Pattern

The agent must not answer:

```text
Only the registered Skill tool list counts.
```

The registered runtime Skill tool list is only one execution surface. It is not the full ATLAS skill library.

## Canonical Files

- `.claude/commands/invoke-all-skills.md`
- `.codex/commands/invoke-all-skills.md`
- `AGENTS.md`
- `CLAUDE.md`
- `platform/sdlc/13_skills/skill_refinery/universal_skill_invocation_policy.md`
- `platform/sdlc/13_skills/skill_refinery/deterministic_trigger_operating_contract.md`
- `infrastructure/scripts/validate_trigger_determinism.py`
