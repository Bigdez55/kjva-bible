# ATLAS Repo Ingestion Loop Playbook

## Skill ID
SKILL_ATLAS_REPO_INGESTION_LOOP_001

## Purpose
Normalize how repo commits, diffs, validation results, sync packets, and coding-agent reports enter ATLAS and update the Atlas Graph Engine, Atlas Knowledge Vault, and Proof Matrix.

## Trigger Conditions
- User says repo commits/changes must be ingested.
- User asks for ATLAS to stay current with GitHub repositories.
- User asks for coding agents to submit events, reports, or proof.

## Hard Constraints
- Every event must include tenant, repo, and event type.
- Event results must identify graph, knowledge, and proof consequences.
- Demo mode may return calculated mutations without durable persistence.
- Production mode requires durable storage and GitHub webhook/OAuth/App setup.

## Workflow

### Observe
- Inspect current repo connector list, event API, agent context endpoint, and proof gates.
- Determine whether the request concerns demo ingestion, production webhooks, coding-agent reports, or GitHub commit sync.

### Orient
- Map event type to required downstream mutations:
  - commit/diff -> graph repo/file edges
  - validation -> proof evidence
  - agent_report -> knowledge note and context packet
  - sync -> repo twin update

### Decide
- Define the event schema.
- Define accepted/rejected validation behavior.
- Define storage target and downstream update behavior.
- Label demo behavior vs production behavior.

### Act
- Implement or update `/api/ingest/repo-event`.
- Update agent context endpoint if coding agents need the contract.
- Add UI action if live demo testing requires manual ingestion.
- Validate via POST smoke test.

## Required Outputs
- Tenant-scoped event contract
- Repo event schema
- Graph mutation output
- Knowledge mutation output
- Proof mutation output
- Demo vs production persistence statement
- Validation evidence

## Validation Checklist
- Missing tenant/repo/eventType is rejected.
- Valid event returns `status: accepted`.
- Response includes graph mutation output.
- Response includes knowledge mutation output.
- Response includes proof mutation output.
- UI ingest action calls the endpoint when applicable.
