# Playbook: Platform Build Starter Pack

## Skill ID
SKILL_PLATFORM_BUILD_001

## Purpose
Expand platform ideas into full frontend, backend, data, API, workflow, security, deployment, and test blueprints.

## Trigger Conditions
- User wants to build a platform, SaaS, app, dashboard, website, repo-backed product, or UI shell that needs backbone.

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
- Produce Platform backbone.
- Produce Artifact manifest.
- Produce Coding-agent execution order.
- Update ledgers and regression cases if a miss or new failure pattern is discovered.

## Output Format
- Platform backbone
- Artifact manifest
- Coding-agent execution order

## Validation Checklist
- Source documents and current repo truth were checked.
- Required output sections are present.
- Router intents and related skills are recorded.
- Tests or manual verification are listed honestly.
- Final report distinguishes proven, partial, and planned claims.

## Source Documents
- handoff_v7_repo_native
- handoff_v5_trigger_router

## Related Commands
- /apex:platform_build

## Related Workflows
- 05_workflows/platform_build_auto_invocation.md
