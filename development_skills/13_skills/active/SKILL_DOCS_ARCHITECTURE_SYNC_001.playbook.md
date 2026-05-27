# Playbook: Docs Architecture Diagram Sync

## Skill ID
SKILL_DOCS_ARCHITECTURE_SYNC_001

## Purpose
Update documentation, maps, ADRs, diagrams, route maps, feature maps, API maps, and dataflow maps to match code/runtime truth.

## Trigger Conditions
- Docs, diagrams, ADRs, README, or route/API/dataflow maps are missing or stale.

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
- Produce Updated docs/diagram plan.
- Produce Required Mermaid maps.
- Produce Drift notes.
- Update ledgers and regression cases if a miss or new failure pattern is discovered.

## Output Format
- Updated docs/diagram plan
- Required Mermaid maps
- Drift notes

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
- /apex:route

## Related Workflows
- 05_workflows/source_of_truth_reconciliation.md
