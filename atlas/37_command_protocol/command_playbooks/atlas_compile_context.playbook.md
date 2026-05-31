# Command Playbook: /atlas:compile_context

## Purpose
Compile context packet used for handoff, routing recommendations, and route memory.

## Trigger Intent
atlas_compile_context

## Required Inputs
- Optional `--from-ingest` and `--from-graph` for deterministic provenance.

## Required Outputs
- `42_context_compiler/output/generated/CP-super-c-atlas-intelligence-core.yaml`

## Validation Gates
- Safe-gate history should be present or explicitly blocked when required.

## Post-conditions
- Packet is stable for `/atlas:report` and `/atlas:route` evidence.
