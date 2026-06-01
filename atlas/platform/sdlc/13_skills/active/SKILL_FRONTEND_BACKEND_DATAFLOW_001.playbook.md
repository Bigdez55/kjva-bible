# Playbook: Frontend Backend Dataflow Connection Map

## Skill ID
SKILL_FRONTEND_BACKEND_DATAFLOW_001

## Purpose
Map how screens connect to APIs, services, databases, external systems, reports, workflows, and audit logs.

## Trigger Conditions
- User asks how data comes in/goes out, how reporting works, or how frontend connects to backend/data.

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
- Produce Dataflow matrix.
- Produce Screen-to-data matrix.
- Produce Missing link list.
- Update ledgers and regression cases if a miss or new failure pattern is discovered.

## Output Format
- Dataflow matrix
- Screen-to-data matrix
- Missing link list

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
- /apex:dataflow_map

## Related Workflows
- 05_workflows/ui_feature_wiring_audit.md
