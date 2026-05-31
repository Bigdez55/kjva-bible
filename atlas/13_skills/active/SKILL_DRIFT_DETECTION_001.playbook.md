# Playbook: Drift Detection

## Skill ID
SKILL_DRIFT_DETECTION_001

## Purpose
Detect drift between code, registries, diagrams, ADRs, traceability, and truth state.

## Inputs
- repo state
- source ranking yaml
- last-known hashes

## Steps
1. Load inputs.
2. Validate against [26_schemas/skill/skill.schema.json](../../26_schemas/skill/skill.schema.json).
3. Execute the operation described in `purpose`.
4. Emit outputs.
5. Record `improvement_history` entry on any change.

## Outputs
- drift report
- severity classification

## Failure modes
- mtime confused with content change
- OneDrive sync false positives

## Validation
See [08_verification/skill_tests/TEST_SKILL_DRIFT_DETECTION_001_001.yaml](../../08_verification/skill_tests/TEST_SKILL_DRIFT_DETECTION_001_001.yaml).
