# Command Playbook: /atlas:report

## Purpose
Generate consolidated Atlas intelligence output for review and handoff.

## Trigger Intent
atlas_report

## Required Inputs
- Gate outcomes (or explicit `--require-gates` block handling).

## Required Outputs
- `09_release/release_evidence/2026-05-17_super_c_atlas_intelligence_core_v0_2_report.md`

## Validation Gates
- `/atlas:validate --safe-only` should be attached when not already run in flow.

## Post-conditions
- Report includes verdict, evidence list, and next implementation unit.
