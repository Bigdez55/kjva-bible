# Playbook: Automated Regression Testing

## Skill ID
SKILL_AUTOMATED_REGRESSION_TESTING_001

## Purpose
Run machine-readable regression cases for router, platform build, repo audit, UI wiring, and refactor safety.

## Trigger Conditions
- Regression cases changed or v5/v6/v7 gates need proof.

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
- Produce Regression report.
- Produce Failed cases.
- Produce Evidence.
- Update ledgers and regression cases if a miss or new failure pattern is discovered.

## Output Format
- Regression report
- Failed cases
- Evidence

## Validation Checklist
- Source documents and current repo truth were checked.
- Required output sections are present.
- Router intents and related skills are recorded.
- Tests or manual verification are listed honestly.
- Final report distinguishes proven, partial, and planned claims.

## Source Documents
- handoff_v7_repo_native

## Related Commands
- /apex:runtime_verify

## Related Workflows
- 05_workflows/runtime_test_and_regression_verification.md
