# Deterministic Trigger Operating Contract

## Purpose

This contract makes trigger routing foolproof enough for cross-agent use. It defines how natural trigger words, repository-native skills, external runtime skills, project-specific assets, and validation gates must interact.

## Non-Negotiable Rules

1. One trigger surface: all natural language, `/atlas:*` aliases, Claude commands, Codex usage, and Gemini usage must route through the canonical trigger router.
2. Verb-first routing controls intent; noun branches specialize; modifiers tune; targets bind project scope; proof validates; correctives repair.
3. `invoke all skills` means universal coverage matrix, not exhaustive tool calls.
4. External runtime `Skill(...)` registries are incomplete relative to ATLAS.
5. Repository-native `13_skills/active/SKILL_*.yaml` entries are applied by reading YAML/playbooks as disciplines.
6. Project-specific skills are suppressed until an explicit target/domain binds them.
7. Acquisition and invocation are separate:
   - Acquisition: pull/acquire/scan `.claude`, `.codex`, `.gemini`.
   - Invocation: invoke/use/run/apply all skills.
8. No destructive, setup, recurring, config-writing, or background tool runs unless explicitly requested.
9. Every route must be explainable by selected root, noun, target, modifiers, matched intents, active skills, suppressed skills, and proof requirements.
10. Any miss updates the skill refinery with a rule, test, or regression case.

## Runtime Output Contract

Every router response should support:

- `selected_root`
- `selected_noun`
- `selected_target`
- `active_modifiers`
- `active_output_contract`
- `proof_requirements`
- `corrective_override`
- `matched_intents`
- `skills`
- `suppressed_skills`
- `allowed_project_families`
- `tool_called_skills`
- `playbook_applied_disciplines`
- `required_outputs`

## Universal Invocation Contract

For `invoke all skills`, the required result is:

- `matched_intents` includes `all_skills`.
- Acquisition intents are absent unless acquisition language is present.
- Tool-called skills may be empty.
- Playbook-applied disciplines must include the selected repository-native skills.
- Project-specific skills remain suppressed unless target-bound.
- Required outputs include selected portable skills and suppressed project-specific skills.

## Generic Route Suppression Contract

Generic requests such as `build a platform`, `build dashboard`, `audit security`, or `fix API` must not activate:

- `SKILL_ELSON_*` unless Elson/trading/finance context is present.
- `SKILL_IPOS_*` unless IPOS/paratransit/transit/VTA context is present.
- `SKILL_GENOS_*`, `SKILL_SUPER_C_*`, or `SKILL_SC_*` unless GEN.OS/SUPER C/compiler/kernel context is present.
- Assistant acquisition skills unless `.claude`, `.codex`, `.gemini`, or assistant-surface acquisition language is present.

## Validation Gate

The contract is enforced by:

```bash
python3 25_automation/validate_trigger_determinism.py
python3 25_automation/validate_skills_stack.py
python3 25_automation/registry_sync/sync_registries.py --check
```

No agent should claim the trigger system is stable if those gates fail.
