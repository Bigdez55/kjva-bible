# Slash Command: /apex:onboard

## Purpose
Run the tiered repo onboarding playbook. Captures current truth (T1), sets direction (T2), runs the slice loop (T3), and maintains hygiene (T4) for any repo adopting ATLAS.

## Output
Per tier; see [SKILL_REPO_ONBOARDING_001.playbook.md](../../13_skills/active/SKILL_REPO_ONBOARDING_001.playbook.md).

- T1 → target's `current.truth.yaml`, 7 mandated diagrams, registry sync, drift evidence packet, populated twin in upstream ATLAS, pushed target branch.
- T2 → real intake packet, starter packet, SLICE-0001 with preview deploy, baseline specs, 1–3 baseline ADRs, registry updates, evidence packet.
- T3 → slice + diagrams + verify + preview + evidence + drift report + doc sync + optional skill improvement, change ledger and traceability rows.
- T4 → drift report (per session), mistake ledger entries, promoted skill improvements, refreshed twin and truth state when warranted.

## Inputs
- `tier` (required): a single tier (`1`, `2`, `3`, or `4`) **or** a range (`1-4`, `1-2`, `2-4`, etc.) to run multiple tiers in sequence.
- `target` (string, required): absolute path to the child repo on disk.
- `intent_brief` (string, **required when Tier 2 is included**): 1–3 sentence statement of what the repo is for and the next outcome it must achieve. Must come from the caller; the command does not fabricate it.

## Preconditions
- Repo structure check passes ([apex_structure_check.yml](../../.github/workflows/apex_structure_check.yml))
- `python3 25_automation/registry_sync/sync_registries.py --check` is green
- `target` is a git repository on a clean branch
- `target/atlas/` exists (sync via [25_automation/sync_scripts/sync_to_child_repo.py](../../25_automation/sync_scripts/sync_to_child_repo.py) first if missing)

## Fast Validation Runner

Run this portable validator from any repo to audit tier completion:

```bash
python3 atlas/25_automation/onboarding_validate_tiers.py --target /absolute/path/to/repo --tiers 1-4
```

For JSON output:

```bash
python3 atlas/25_automation/onboarding_validate_tiers.py --target /absolute/path/to/repo --tiers 1-4 --json
```

## Step-by-step

### 1. Validate inputs
- Parse `tier`: accept a single integer (`1`–`4`) or a dash-range (`1-4`, `2-3`, etc.). Expand to an ordered list of tiers to run, e.g. `1-4` → `[1, 2, 3, 4]`.
- `target` is an absolute path that exists and is a git repository.
- If the list includes Tier 2 and `intent_brief` is empty, halt immediately before running any tier and surface the requirement to the caller.

### 2. Load context
Compile a context packet via [42_context_compiler/compile_context.py](../../42_context_compiler/compile_context.py) for the appropriate persona ([12_agents/personas/](../../12_agents/personas/)) — typically `apex_coding_agent` for T1/T2/T3 and `drift_agent` for T4.

### 3. Execute each tier in sequence
For each tier in the expanded list, follow its body literally as written in [SKILL_REPO_ONBOARDING_001.playbook.md](../../13_skills/active/SKILL_REPO_ONBOARDING_001.playbook.md). Complete every step of a tier and confirm its outputs exist before starting the next tier. Do not skip steps.

**Tier 1 note:** T1 begins with a mandatory discovery protocol — read git history, language artifacts, source structure, deployment signals, and any existing docs *before* writing any output file. Do not prompt the user for context about what the repo does; derive it mechanically. The reality model built during discovery is the sole input to all T1 artifacts.

### 4. Update registries
- Inside the target: `python3 atlas/25_automation/registry_sync/sync_registries.py --write`.
- For T1 step 5 (twin population): run `python3 25_automation/registry_sync/sync_registries.py --write` in the upstream ATLAS checkout on the dedicated onboarding branch.

### 5. Update traceability
- T2 baseline ADRs and the SLICE-0001 spec links → rows in [18_registry/traceability.yaml](../../18_registry/traceability.yaml).
- T3 every slice → rows in `traceability.yaml` and [18_registry/change_ledger.yaml](../../18_registry/change_ledger.yaml).

### 6. Validate
- Schema-validate every new artifact against [26_schemas/](../../26_schemas/).
- Run all drift checkers under [25_automation/drift_checkers/](../../25_automation/drift_checkers/).

### 7. Capture evidence
- T1 → `EP-<date>-onboarding-tier1.yaml`
- T2 → `EP-<date>-onboarding-tier2.yaml`
- T3 → `EP-<date>-<slice-id>.yaml`
- T4 → mistake ledger entries; only generates an evidence packet when a skill is promoted.

## Outputs
See "Output" section above. All outputs land in canonical locations inside the target's `atlas/` (T1, T2, T3) and in upstream ATLAS for the twin (T1) and any promoted skills (T4).

## Success criteria
- Required artifacts for the requested tier exist on disk and validate against schema.
- Registry sync exits 0.
- Drift checkers exit 0 (or surface only known acceptable findings).
- For T1: target's `current.truth.yaml` is present; twin's `sync_status.yaml` reads `synced`.
- For T2: SLICE-0001 exists, contains a preview deploy plan, and ≥1 baseline ADR is recorded in the decision ledger.
- For T3: evidence packet links a passing verify report and a preview URL or rollback record.
- For T4: a drift report exists for this session; any repeated mistake has a corresponding skill improvement proposal.

## Failure modes

| Failure | Detection | Remediation |
|---|---|---|
| `tier == 2` and `intent_brief` missing | input validation | Halt; ask caller for `intent_brief`. |
| Target not a git repo | `[ -d target/.git ]` check | Run `git init` (+ remote if applicable) on target, then retry. |
| Target working tree dirty | `git status --porcelain` non-empty | Stash or commit user work first; do not mix with onboarding output. |
| Tier 1 twin step skipped | upstream `39_repo_twins/twins/<NAME>/sync_status.yaml` still `pending_ingestion` | Re-run tier 1 step 5 in upstream ATLAS. |
| `current.truth.yaml` clobbered on re-sync | exclude rule in `sync_to_child_repo.py` should prevent this (ADR-0011) | Confirm `PER_ITEM_EXCLUDES`; restore from git history if regressed. |
| Repeated mistake never promoted to skill | mistake ledger root-cause appears ≥ 2 times | Run `/apex:improve_skill`; add validation test. |

## Rollback
- T1: revert the onboarding branch on the target repo; revert the twin-population branch in upstream ATLAS.
- T2: revert the upstream commit that introduced the intake/starter/slice/specs/ADRs.
- T3: revert the slice's commit; preview deploy must be torn down per its rollback plan.
- T4: mistake ledger entries are append-only; skill improvements are revertible by version bump.

## Example invocation

```text
# Run all four tiers end-to-end (T2 requires intent_brief)
/apex:onboard tier=1-4 target=/absolute/path/to/LMOS intent_brief="LMOS is a legal matter operations system; next outcome is a pilot intake → matter-creation flow with audit-trail evidence."

# Run only T1 (discovery — no intent_brief needed)
/apex:onboard tier=1 target=/absolute/path/to/LMOS

# Run T1 then T2 together
/apex:onboard tier=1-2 target=/absolute/path/to/LMOS intent_brief="LMOS is a legal matter operations system; next outcome is a pilot intake → matter-creation flow with audit-trail evidence."

# Run a single subsequent tier
/apex:onboard tier=3 target=/absolute/path/to/LMOS
/apex:onboard tier=4 target=/absolute/path/to/LMOS
```

## See also
- Skill: [SKILL_REPO_ONBOARDING_001](../../13_skills/active/SKILL_REPO_ONBOARDING_001.yaml)
- Playbook: [SKILL_REPO_ONBOARDING_001.playbook.md](../../13_skills/active/SKILL_REPO_ONBOARDING_001.playbook.md)
- Sync mechanics: [21_repo_sync/repo_sync.protocol.md](../../21_repo_sync/repo_sync.protocol.md)
- Identity preservation: [ADR-0011](../../04_architecture/adrs/ADR-0011-repo-sync-delete-and-identity-exclude.md)
- [APEX_PROTOCOL.md](../../APEX_PROTOCOL.md)
- [37_command_protocol/commands.registry.yaml](../commands.registry.yaml)
