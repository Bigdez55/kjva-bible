# Playbook: Section-by-Section Refactor Execution

## Skill ID
SKILL_SECTION_REFACTOR_EXECUTION_001

## Purpose
Execute refactors one section at a time with baseline capture, dependency mapping, tests, docs, and commits per unit.

## Trigger Conditions
- A large repo must be refactored safely while preserving working features.

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
- Produce Section plan.
- Produce Per-section tests.
- Produce Docs updates.
- Produce Commit strategy.
- Update ledgers and regression cases if a miss or new failure pattern is discovered.

## Output Format
- Section plan
- Per-section tests
- Docs updates
- Commit strategy

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
- /apex:refactor_plan

## Related Workflows
- 05_workflows/section_by_section_refactor_execution.md
