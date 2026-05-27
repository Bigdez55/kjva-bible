# Playbook: UI Interaction and Feature Wiring

## Skill ID
SKILL_UI_INTERACTION_WIRING_001

## Purpose
Map and repair UI controls so rendered buttons, toggles, forms, settings, routes, and modals actually perform intended behavior.

## Trigger Conditions
- Buttons, toggles, switches, profile/account settings, forms, menus, or UI features do not work or kick users out.

## Required Inputs
- User request or command text.
- Target repo, artifact, feature, or workflow when applicable.
- Current source-of-truth files and validation gates when available.

## Canonical Rules
- Preserve source-of-truth ranking.
- Do not claim completion without validation evidence.
- Record misses in the skill refinery ledger when discovered.

## Workflow

### Observe
- Identify the user goal, repo/project state, relevant sources, and required artifacts.
- Inspect code, docs, schemas, ledgers, or router config before making claims.

### Orient
- Map the request to router intents, related skills, source-of-truth rank, and validation gates.
- Identify missing backbone components, stale docs, untested behavior, or recurrence risk.

### Decide
- Choose the smallest complete artifact set that satisfies the intent.
- Define outputs, tests, evidence, and stop rules before execution.

### Act
- Produce UI control behavior matrix.
- Produce Broken control list.
- Produce Root cause candidates.
- Produce Regression tests.
- Update ledgers and regression cases if a miss or new failure pattern is discovered.

## Output Format
- UI control behavior matrix
- Broken control list
- Root cause candidates
- Regression tests

## Validation Checklist
- Source documents and current repo truth were checked.
- Required output sections are present.
- Router intents and related skills are recorded.
- Tests or manual verification are listed honestly.
- Final report distinguishes proven, partial, and planned claims.

## Source Documents
- handoff_v7_repo_native
- handoff_v6_repo_refactor

## Related Commands
- /apex:ui_wiring

## Related Workflows
- 05_workflows/ui_feature_wiring_audit.md
