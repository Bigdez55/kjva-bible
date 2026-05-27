# Universal Skill Surface

## Purpose

This directory is the single universal invocation surface for Development_Skills.
Claude, Codex, Gemini-style agents, and repo-local coding agents must use this
surface instead of treating their own runtime skill list as the full skill system.

## Canonical Rule

The source of truth is:

- `13_skills/skills.registry.yaml`
- `13_skills/active/SKILL_*.yaml`
- `13_skills/active/SKILL_*.playbook.md`
- `13_skills/skill_refinery/trigger_router.yaml`
- `37_command_protocol/trigger_router.yaml`
- `25_automation/route_intent.py`

Assistant-specific folders are projections:

- `.claude/commands/invoke-all-skills.md`
- `.codex/commands/invoke-all-skills.md`
- `.gemini/commands/invoke-all-skills.md`

No assistant-specific projection may redefine the skill system independently.

## Invocation Meaning

`invoke all skills`, `use all skills`, `run all skills`, `activate all skills`,
and `full skill stack` mean:

```text
Route the request through the universal coverage matrix, then apply the selected
repository-native skills and playbooks required by the target, proof state, and
corrective state.
```

They do not mean:

```text
Call only the runtime-registered skills visible to Claude, Codex, or Gemini.
```

They also do not mean:

```text
Load every project-specific skill regardless of target.
```

## Required Runtime Sequence

1. Run `python3 25_automation/route_intent.py "<user request>" --json`.
2. Read this universal surface contract.
3. Use `13_skills/skill_refinery/universal_skill_invocation_policy.md`.
4. Use `13_skills/skill_refinery/cross_runtime_invoke_all_skills_contract.md`.
5. Treat every `13_skills/active/SKILL_*.yaml` plus matching `.playbook.md` as a repository-native discipline.
6. Call only runtime-tool skills that are relevant, available, safe, and non-destructive.
7. Suppress project-specific skills unless the selected target/domain binds them.
8. Report tool-called skills separately from playbook-applied disciplines.

## Required Output Fields

Every all-skills response must include:

- `tool_called_skills`
- `playbook_applied_disciplines`
- `activated_project_specific_skills`
- `suppressed_project_specific_skills`
- `validation_or_proof_gates`
- `misses_logged_or_none`

## Integration Gate

The router integration gate is:

```bash
python3 25_automation/audit_skill_router_integration.py
python3 25_automation/validate_trigger_determinism.py
```

Passing means:

- every active skill is in `13_skills/skills.registry.yaml`;
- every active skill has a matching playbook;
- every active skill is reachable from both trigger-router catalogs;
- no router catalog points at inactive skill IDs.

