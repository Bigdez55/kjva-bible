# Command Playbook: /apex:runtime_verify

## Purpose
Run or define tests proving features and refactors work at runtime.

## Trigger Intent
runtime_verify

## Required Skills
- SKILL_RUNTIME_REGRESSION_VERIFY_001
- SKILL_AUTOMATED_REGRESSION_TESTING_001

## Required Inputs
- User request or target path.
- Known constraints, source documents, and validation expectations.

## Required Outputs
- runtime verification report
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
