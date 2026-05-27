# Slash Command: /apex:package_repo

## Purpose
Package repo evidence, docs, diagrams, and release artifacts.

## Output
`23_evidence/`

## Inputs
- `target` (string, required): the entity being acted on (repo name, slice id, etc.)
- Source-of-truth files: see [19_truth_state/source_of_truth_ranking.yaml](../../development_skills/19_truth_state/source_of_truth_ranking.yaml)
- Relevant schemas: [26_schemas/](../../26_schemas/)

## Preconditions
- Repo structure check passes ([apex_structure_check.yml](../../.github/workflows/apex_structure_check.yml))
- `python3 25_automation/registry_sync/sync_registries.py --check` is green
- Caller has write access to `23_evidence/`

## Step-by-step

### 1. Load context
Compile a context packet via [42_context_compiler/compile_context.py](../../development_skills/42_context_compiler/compile_context.py) for the appropriate persona ([12_agents/personas/](../../development_skills/12_agents/personas/)).

### 2. Validate inputs
- Required input fields present.
- Input matches the relevant schema in [26_schemas/](../../26_schemas/).
- No conflicts with existing artifacts in `23_evidence/`.

### 3. Author artifact
- Use the matching template in [14_templates/](../../14_templates/).
- Reference the active ADRs ([04_architecture/adrs/](../../development_skills/04_architecture/adrs/)) and skills ([13_skills/active/](../../development_skills/13_skills/active/)).
- Write artifact to `23_evidence/` with a deterministic filename.

### 4. Update registries
- Run `python3 25_automation/registry_sync/sync_registries.py --write` to refresh the relevant `*.registry.yaml`.
- Add a row to [18_registry/change_ledger.yaml](../../18_registry/change_ledger.yaml).

### 5. Update traceability
- If artifact is a spec/ADR/diagram/test/evidence/release, add a row to [18_registry/traceability.yaml](../../18_registry/traceability.yaml).

### 6. Validate
- Schema-validate the new artifact.
- Run drift checkers under [25_automation/drift_checkers/](../../25_automation/drift_checkers/).

### 7. Capture evidence
- Append an evidence packet to [23_evidence/evidence_packets/](../../23_evidence/evidence_packets/) referencing the new artifact.

## Outputs
- Artifact in `23_evidence/`
- Updated `*.registry.yaml`
- Change ledger row
- Optional evidence packet
- Optional drift report

## Success criteria
- New artifact exists, validates against schema, is referenced from the appropriate registry, and CI continues to pass.

## Failure modes

| Failure | Detection | Remediation |
|---|---|---|
| Schema mismatch | `schema-validate` CI gate | fix artifact to match schema |
| Registry drift | `registry-sync-check` | `sync_registries.py --write` |
| Missing prerequisite | structure-check fails | seed required directory/file |
| Duplicate artifact id | author-time check | choose next free ID |
| OneDrive sync collision | hash mismatch on rerun | re-run after sync settles |

## Rollback
Revert the commit that introduced the artifact:
```bash
git revert <sha>
python3 25_automation/registry_sync/sync_registries.py --write
```

## Example invocation

```bash
# Pseudocode — actual invocation is via the agent harness
/apex:package_repo target=Development_Skills
```

## See also
- [APEX_PROTOCOL.md](../../APEX_PROTOCOL.md)
- [../../development_skills/37_command_protocol/commands.registry.yaml](../commands.registry.yaml)
- [25_automation/](../../25_automation/)
