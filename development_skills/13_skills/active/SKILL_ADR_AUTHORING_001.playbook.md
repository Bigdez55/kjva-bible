# Playbook: ADR Authoring

## Skill ID
SKILL_ADR_AUTHORING_001

## Purpose
Author ADRs from doctrinal decisions; update decision_ledger.

## Inputs
- decision context
- options
- tradeoffs

## Steps
1. Load inputs.
2. Validate against [26_schemas/skill/skill.schema.json](../../26_schemas/skill/skill.schema.json).
3. Execute the operation described in `purpose`.
4. Emit outputs.
5. Record `improvement_history` entry on any change.

## Outputs
- ADR-NNNN-*.md
- decision_ledger row

## Failure modes
- decision lacks rollback path
- no options considered

## Validation
See [08_verification/skill_tests/TEST_SKILL_ADR_AUTHORING_001_001.yaml](../../08_verification/skill_tests/TEST_SKILL_ADR_AUTHORING_001_001.yaml).
