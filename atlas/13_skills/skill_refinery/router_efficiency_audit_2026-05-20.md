# Router Efficiency Audit - 2026-05-20

## Scope

Checked the trigger router, runtime router, assistant-surface map, ATLAS trigger helper, and active trigger-router skill for the same failure class that caused `invoke all skills` to be treated as too project-specific.

## Findings

| Finding | Risk | Fix |
| --- | --- | --- |
| `all skills` and assistant-surface acquisition were semantically adjacent. | Runtime agents could treat invocation as acquisition and load repo-specific assets. | Added `all_skills` behavioral protocol and separated acquisition phrases from invocation phrases. |
| Generic root verbs included project-specific skill IDs. | `build`, `audit`, `fix`, `analyze`, and similar generic actions could activate Elson, IPOS, GEN.OS, SUPER C, or SC skills without a target. | Added runtime suppression of project-specific skill prefixes unless the selected target/domain binds them. |
| Generic noun branches included project-specific skill IDs. | `platform`, `dashboard`, `api`, `report`, `query`, `analysis`, and `neural` could over-route. | Runtime now reports suppressed project-specific skills and keeps only portable skills unless target-bound. |
| `.claude/universal` and `.codex/universal` names implied assets were portable. | Imported folders contain project-specific agents even when stored under universal paths. | Added universal invocation policy: imported assistant assets are available sources, not universal runtime law. |
| Alias duplication could produce repeated behavioral matches. | Output noise and unstable route reports. | Deduped normalized aliases in `route_intent.py`. |
| External agents treated the runtime Skill tool registry as the full skill library. | Agents reported repository-native `SKILL_*` playbooks as "not invokable" instead of applying them as disciplines. | Added tool-callable versus playbook-applied contract and explicit route output fields. |

## Current Runtime Rules

- `invoke all skills`, `use all skills`, `run all skills`, `activate all skills`, `all skills`, `all skills and agents`, `full skill stack`, and `universal skills` activate portable universal coverage.
- `pull/acquire all skills`, `.claude .codex .gemini`, and `all assistant surfaces` activate assistant-surface acquisition.
- External runtime Skill tools are optional callable helpers; `13_skills/active/SKILL_*.yaml` + `.playbook.md` are repository-native disciplines.
- Project-specific prefixes are suppressed unless bound:
  - `SKILL_ELSON_` requires Elson/trading/finance context.
  - `SKILL_IPOS_` requires IPOS/paratransit/transit/VTA context.
- `SKILL_GENOS_`, `SKILL_SUPER_C_`, and `SKILL_SC_` require GEN.OS/SUPER C/compiler/kernel context.
- Assistant acquisition skills require `.claude`, `.codex`, `.gemini`, or assistant-surface acquisition language.

## Validation

- YAML parse checks passed.
- Duplicate-key checks passed for touched router YAML files.
- Route assertions passed for all-skills invocation, assistant-surface acquisition, generic platform build, Elson platform build, generic dashboard build, IPOS dashboard build, and compiler build.
- ATLAS app `npm run test`, `npm run typecheck`, and `npm run lint` passed after the first all-skills fix.
- `python3 25_automation/validate_trigger_determinism.py` now enforces the all-skills contract, suppression rules, target activation, and security-route cases.

## Remaining Optimization Queue

- Move project-specific skill lists out of generic noun/root catalog entries and into explicit targets during the next catalog normalization pass.
- Classify imported assistant assets with `portable`, `target_bound`, or `raw_only` fields in the normalized registries.
- Move project-specific skill lists out of generic noun/root catalog entries once the runtime suppression gate has protected behavior.
