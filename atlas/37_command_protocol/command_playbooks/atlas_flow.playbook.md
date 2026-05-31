# Command Playbook: /atlas:flow

## Purpose
Run deterministic Atlas convergence sequence in one command.

## Trigger Intent
atlas_flow

## Required Inputs
- Optional `--steps` for explicit subset execution.
- Optional `--require-gates` to enforce blocker checks.

## Required Outputs
- `23_evidence/atlas_platform/flows/atlas_flow_<run_id>.json`

## Validation Gates
- Flow should emit blockers for every failed step and status `pass/fail`.
- `/atlas:validate --safe-only` is recommended before merge.

## Post-conditions
- Single-command handoff trace is available for context refresh.
