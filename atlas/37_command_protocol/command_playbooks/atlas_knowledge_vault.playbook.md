# Command Playbook: /atlas:knowledge_vault

## Purpose
Command entry that exports Atlas Knowledge Vault notes for navigation, links, and operating context through the canonical router.

## Trigger Intent
atlas_knowledge_vault

## Required Inputs
- Graph artifact or latest Atlas Graph Engine manifest.
- Current status snapshot when available.

## Required Outputs
- `44_atlas_knowledge_vault/reports/atlas_knowledge_vault_<run_id>.md`
- `44_atlas_knowledge_vault/notes/<run_id>/*.md`
- `44_atlas_knowledge_vault/knowledge_vault.manifest.yaml`

## Validation Gates
- Prefer `--require-gates --apply` for merge-safe exports.

## Post-conditions
- Note payload is deterministic for the chosen run id.
