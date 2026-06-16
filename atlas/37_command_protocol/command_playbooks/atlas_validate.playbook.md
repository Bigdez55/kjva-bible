# Command Playbook: /atlas:validate

## Purpose
Run Atlas-safe gates and provide blocker-aware results.

## Trigger Intent
atlas_validate

## Required Inputs
- `--safe-only` (required operational mode).

## Required Outputs
- `08_verification/gate_results/atlas_platform_core_safe_gates.yaml`
- `08_verification/gate_results/atlas_platform_core_safe_gates.json`
- `23_evidence/platform/gates/atlas_safe_gate_results.md`

## Validation Gates
- Gate execution and returned verdict matrix are evidence for follow-on commands.

## Post-conditions
- `/atlas:flow` can proceed only with approved blocker posture.
