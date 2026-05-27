# Command Playbook: /apex:repo_audit

## Purpose
Audit an existing repo before refactor or docs sync.

## Trigger Intent
repo_audit

## Required Skills
- SKILL_EXISTING_REPO_AUDIT_001
- SKILL_SOURCE_TRUTH_RECONCILIATION_001

## Required Inputs
- User request or target path.
- Known constraints, source documents, and validation expectations.

## Required Outputs
- repo audit maps
- Validation evidence.
- Skill-refinement check.

## Hard Constraints
- Preserve existing user work and unrelated dirty files.
- Use repo-native source-of-truth ranking.
- Do not claim runtime success without tests or explicit manual verification.

## Validation Gates
- Required artifacts exist.
- Router intent is correct.
- Relevant tests or manual checks are reported.

## Final Report Requirements
- Commands run.
- Files inspected or changed.
- Gate results.
- Proven, partial, planned, and blocked claims.

## Related Commands
- /apex:route
- /apex:runtime_verify
