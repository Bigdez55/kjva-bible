# Command Playbook: /atlas:ingest

## Purpose
Collect Atlas source-of-truth state and produce a deterministic ingest snapshot for downstream steps.

## Trigger Intent
atlas_ingest

## Required Inputs
- Runtime command context (repo path).
- Optional `--apply` when pointer stability is required.

## Required Outputs
- `23_evidence/platform/ingest/atlas_ingest_<run_id>.yaml`
- `23_evidence/platform/ingest/atlas_ingest_<run_id>.json`
- `23_evidence/platform/ingest/atlas_ingest_<run_id>.md`

## Validation Gates
- `/atlas:ingest --check` remains read-only.
- `/atlas:status --format json` can verify generated status wiring.

## Post-conditions
- `23_evidence/platform/ingest/atlas_ingest_latest.yaml` is updated when `--apply` is used.
