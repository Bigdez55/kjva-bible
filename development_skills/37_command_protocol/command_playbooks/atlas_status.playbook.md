# Command Playbook: /atlas:status

## Purpose
Produce read-only Atlas subsystem status and evidence summary.

## Trigger Intent
atlas_status

## Required Inputs
- None beyond repo-local execution context.

## Required Outputs
- `23_evidence/atlas_platform/status/atlas_status.json`
- `23_evidence/atlas_platform/status/atlas_status.md`

## Validation Gates
- Read-only by policy; no mutation expected unless `--apply` pointer updates are introduced.

## Post-conditions
- Status data is ready for handoff assembly.
