# Slash Command: /apex:check_path

## Purpose
Mandatory pre-write check. Before any agent creates a file or folder, this command runs the FIND-before-CREATE search and returns one of `OK_TO_CREATE | REUSE_CANDIDATE | REDIRECT_REQUIRED | HALT`. Hard enforcement per [SKILL_FIND_BEFORE_CREATE_001](../../13_skills/active/SKILL_FIND_BEFORE_CREATE_001.yaml).

## Output
A decision record stored alongside the artifact (or in [18_registry/change_ledger.yaml](../../18_registry/change_ledger.yaml) when the artifact format cannot carry metadata).

## Inputs
- `target_path` (string, required): absolute or repo-relative path the agent intends to create.
- `artifact_kind` (string, optional): one of `file | directory | registry_entry | skill | adr | spec | diagram | template | schema | slice | evidence | runbook | policy | intake_packet | starter_packet | repo_twin`.
- `repo_root` (string, optional): defaults to nearest git root of `target_path`.

## Preconditions
- Repo structure check passes ([apex_structure_check.yml](../../.github/workflows/apex_structure_check.yml)).
- `python3 25_automation/registry_sync/sync_registries.py --check` is green.
- Caller has read access to `repo_root`.

## Step-by-step

### 1. Validate inputs
- `target_path` is supplied and resolvable.
- If `artifact_kind` is supplied, it is one of the allowed values.

### 2. Run the six searches
Execute searches 1–6 from [SKILL_FIND_BEFORE_CREATE_001.playbook.md](../../13_skills/active/SKILL_FIND_BEFORE_CREATE_001.playbook.md):

1. Exact path exists?
2. Case/separator variant exists? (collapsed-token comparison)
3. Content fingerprint match? (sha256 over planned bytes vs. tracked files)
4. Artifact-kind canonical home contains an overlapping artifact?
5. Frontmatter/ID already in use within the same kind?
6. OneDrive ghost present in target's parent directory?

### 3. Decide
Apply the decision rules from the skill playbook step 3.

### 4. Enforce
- `OK_TO_CREATE` — proceed; capture `creation_rationale` in the new artifact per skill step 5.
- `REUSE_CANDIDATE` — do not create. Read the candidate and edit in place.
- `REDIRECT_REQUIRED` — write a `MOVED.md` redirect stub at the old canonical path before creating the new one. Update every reference. Use the template in the skill playbook step 6.
- `HALT` — surface the blocker (typically a OneDrive ghost) to the caller; do not proceed until resolved.

### 5. Update registries
- If a `MOVED.md` is written: add a row to [18_registry/change_ledger.yaml](../../18_registry/change_ledger.yaml).
- If a duplicate ID was avoided: no registry change needed; the existing artifact stays canonical.

### 6. Validate
- After any creation, run [25_automation/drift_checkers/check_registry_drift.py](../../25_automation/drift_checkers/check_registry_drift.py) — the new artifact must not introduce drift in the matching registry.

### 7. Capture evidence (when `REDIRECT_REQUIRED` was applied)
- Append a row to [23_evidence/evidence_packets/](../../23_evidence/evidence_packets/) referencing both the old and new paths and the change ledger row.

## Outputs
Same as the skill: `decision`, `candidates`, `rationale` (when `OK_TO_CREATE`), `redirect_record` (when `REDIRECT_REQUIRED`).

## Success criteria
- The decision was made before the file was created (not after).
- If a candidate was found, either it was reused or a `MOVED.md` was authored at the old location.
- No duplicate-by-name or duplicate-by-content artifact exists in the repo.
- `creation_rationale` is recorded for any new artifact created when the search returned candidates.

## Failure modes

| Failure | Detection | Remediation |
|---|---|---|
| Command run after the file was created | timestamp of artifact precedes timestamp of decision record | Treat as a violation; record in mistake ledger. Re-evaluate retroactively and apply `REUSE_CANDIDATE`/`REDIRECT_REQUIRED` if applicable. |
| Decision recorded but not enforced (artifact created anyway when decision was `REUSE_CANDIDATE`) | drift report finds duplicate paths despite a check record | Two-strike rule: file an improvement proposal; tighten downstream enforcement. |
| OneDrive ghost not materialized before search | search 6 false negative | Open parent dir in Finder; mark "Always keep on this device"; re-run command. |

## Rollback
- If a `MOVED.md` was created in error: `git revert` the redirect commit and restore the old canonical path.
- If `OK_TO_CREATE` was applied incorrectly: `git mv` the new artifact onto the canonical candidate; write `MOVED.md` at the new path; update references.

## Example invocation

```text
/apex:check_path target_path=/abs/path/to/repo/13_skills/active/SKILL_FOO_001.yaml artifact_kind=skill
/apex:check_path target_path=04_architecture/adrs/ADR-0042-bar.md artifact_kind=adr
/apex:check_path target_path=39_repo_twins/twins/super_c_academy artifact_kind=repo_twin
```

## See also
- Skill: [SKILL_FIND_BEFORE_CREATE_001](../../13_skills/active/SKILL_FIND_BEFORE_CREATE_001.yaml)
- Playbook: [SKILL_FIND_BEFORE_CREATE_001.playbook.md](../../13_skills/active/SKILL_FIND_BEFORE_CREATE_001.playbook.md)
- Companion: [SKILL_REPO_ONBOARDING_001](../../13_skills/active/SKILL_REPO_ONBOARDING_001.yaml) Tier 4 promotes repeat violations into skill updates.
- Global predecessor (narrower scope): `~/.claude/skills/apex-directory-discipline/`.
- [APEX_PROTOCOL.md](../../APEX_PROTOCOL.md)
- [37_command_protocol/commands.registry.yaml](../commands.registry.yaml)
