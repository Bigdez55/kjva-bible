# Command Playbook: /apex:platform_build

## Purpose
Generate a full platform backbone and coding-agent handoff.

## Trigger Intent
platform_build

## Required Skills
- SKILL_PLATFORM_BUILD_001
- SKILL_FRONTEND_BACKEND_DATAFLOW_001

## Required Inputs
- User request or target path.
- Known constraints, source documents, and validation expectations.

## Required Outputs
- platform build artifacts
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
