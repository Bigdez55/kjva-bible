# Command Playbook: /atlas:graph

## Purpose
Build or refresh Atlas Graph Engine artifacts from a resolved ingest snapshot.

## Trigger Intent
atlas_graph_engine

## Required Inputs
- Optional `--from-ingest` pointing to an ingest snapshot.
- `--apply` only when stable artifact pointers are required.

## Required Outputs
- `23_evidence/platform/graph/atlas_graph_<run_id>.json`
- `43_graph_engine/exports/atlas_graph_<run_id>.json`
- `43_graph_engine/reports/atlas_graph_report_<run_id>.md`

## Validation Gates
- Guarded by governance checks when `--require-gates` is enabled.
- `/atlas:validate --safe-only` is expected before merge paths.

## Post-conditions
- `43_graph_engine/atlas_graph_engine.manifest.yaml` is updated when `--apply` is used.
