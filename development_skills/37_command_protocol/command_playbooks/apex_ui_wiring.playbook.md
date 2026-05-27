# Command Playbook: /apex:ui_wiring

## Purpose
Map and validate UI controls, state, APIs, backend, routes, permissions, and tests.

## Trigger Intent
ui_wiring

## Required Skills
- SKILL_UI_INTERACTION_WIRING_001
- SKILL_FRONTEND_BACKEND_DATAFLOW_001

## Required Inputs
- User request or target path.
- Known constraints, source documents, and validation expectations.

## Required Outputs
- UI wiring map
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
