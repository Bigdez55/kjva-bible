# Playbook: SKILL_REGISTRY_SYNC_001 — Registry Sync

## Skill ID
SKILL_REGISTRY_SYNC_001

## Version
1.0.0

## Purpose
Keep every `*.registry.yaml` file in the repo derived from disk state via
`sync_registries.py`. Registries are never hand-edited. The registry is the single
source of truth about what files exist on disk; if it drifts, CI breaks and traceability
is lost.

---

## Inputs

| Field    | Type   | Required | Default            | Description                                      |
|----------|--------|----------|--------------------|--------------------------------------------------|
| `mode`   | enum   | yes      | —                  | `check` (read-only diff) or `write` (update disk) |
| `target` | path   | no       | current directory  | Root path to scan; must contain `atlas/` |

---

## What Each Registry Tracks

| Registry File                                        | Derived From                                          |
|------------------------------------------------------|-------------------------------------------------------|
| `13_skills/active/skills.registry.yaml`              | All `*.yaml` files in `13_skills/active/`             |
| `03_specs/<category>/specs.registry.yaml`            | All `*.yaml` files in each spec category directory    |
| `22_vertical_slices/slices.registry.yaml`            | All `SLICE-*.yaml` files in `22_vertical_slices/`     |
| `08_verification/skill_tests/tests.registry.yaml`    | All `TEST_*.yaml` files in `08_verification/skill_tests/` |
| `04_architecture/diagrams/source/architecture/diagram.registry.yaml` | All `*.mmd` files under `source/architecture/` |
| `11_ecosystem/repo_ledger/repos.registry.yaml`       | All `*.yaml` files in `11_ecosystem/repo_ledger/`     |
| `schemas/schemas.registry.yaml`                   | All schema directories under `schemas/`            |
| `23_adr/adr.registry.yaml`                           | All `ADR-*.yaml` files in `23_adr/`                   |

Each registry contains at minimum:
- `generated`: ISO-8601 timestamp
- `count`: integer count of items
- `items`: list of `{id, path, status}` entries

---

## The sync_registries.py Script

**Location:** `atlas/infrastructure/scripts/registry_sync/sync_registries.py`

**Modes:**
- `--check` — Scan disk, compare against current registry files, print a drift report.
  Does NOT modify any file. Exit code 0 = clean; exit code 1 = drift found.
- `--write` — Scan disk and overwrite all registry files with the derived state.
  Produces a summary of what changed.

**Optional flags:**
- `--target <path>` — Override the root path to scan (default: cwd).
- `--registry <name>` — Sync only a specific registry by name.
- `--verbose` — Print every item scanned, not just diffs.

---

## Step-by-Step Execution

### Step 1: Run --check First (always)
```bash
python3 "atlas/infrastructure/scripts/registry_sync/sync_registries.py" --check
```

Read the output carefully. A clean run prints:
```
[OK] All registries up to date. 0 items drifted.
```

A drifted run prints one or more entries like:
```
[DRIFT] skills.registry.yaml
  + SKILL_NEW_THING_001 (on disk, not in registry)
  - SKILL_OLD_001      (in registry, not on disk)
  ~ SKILL_CHANGED_001  (hash mismatch)
```

### Step 2: Interpret Drift Output

| Prefix | Meaning                                          | Typical Cause                          |
|--------|--------------------------------------------------|----------------------------------------|
| `+`    | File exists on disk but is absent from registry  | New skill/spec/slice added without sync |
| `-`    | Registry references a file not found on disk     | File deleted or renamed without sync   |
| `~`    | File exists and is registered but content changed | File was updated; registry is stale    |

### Step 3: Decide Whether to Write

**Safe to --write immediately when:**
- All `+` entries are new files you intentionally created in this session.
- All `-` entries are files you intentionally deleted or renamed in this session.
- No `~` entries point to files that were expected to be stable.

**Investigate before --write when:**
- You see `-` entries for files you did NOT delete.
- You see `~` entries on registry files themselves (indicates hand-edit).
- Drift count is unexpectedly large (>10 items) — could indicate a path misconfiguration.

### Step 4: Run --write (if safe)
```bash
python3 "atlas/infrastructure/scripts/registry_sync/sync_registries.py" --write
```

The script prints a summary:
```
[WRITTEN] skills.registry.yaml         (3 items added, 1 removed)
[WRITTEN] slices.registry.yaml         (1 item added)
[UNCHANGED] tests.registry.yaml
```

### Step 5: Verify
Run `--check` again after `--write`. Expected output:
```
[OK] All registries up to date. 0 items drifted.
```

If drift persists after `--write`, a scan_dir configuration is likely wrong. See
failure modes below.

### Step 6: Commit Registry Files
Stage and commit all modified `*.registry.yaml` files together with the changes that
caused the drift (new skills, specs, slices, etc.):
```bash
git add atlas/**/*.registry.yaml
git commit -m "sync: update registries after <describe change>"
```

---

## When to Use --check vs --write

| Situation                                           | Use         |
|-----------------------------------------------------|-------------|
| CI pipeline validation job                         | `--check`   |
| Before opening a PR                                 | `--check`   |
| After adding a new skill, spec, slice, or ADR       | `--write`   |
| After deleting or renaming a tracked file           | `--write`   |
| Investigating unexpected CI failure                 | `--check`   |
| Onboarding a new repo twin                          | `--write`   |
| Resolving a merge conflict in a registry file       | `--write` after resolving the merge |

Never run `--write` directly in CI. CI always uses `--check`; a non-zero exit fails
the job and the developer must run `--write` locally and push.

---

## CI Integration

The `registry-validate` GitHub Actions job runs:
```yaml
- name: Check registries
  run: python3 "atlas/infrastructure/scripts/registry_sync/sync_registries.py" --check
```

Exit code 1 (drift found) fails the job. The PR cannot merge until drift is resolved.

---

## Failure Modes and Mitigations

| Failure                                  | Symptom                                           | Mitigation                                                       |
|------------------------------------------|---------------------------------------------------|------------------------------------------------------------------|
| Stale registry causes CI failure         | `registry-validate` job exits 1 on PR             | Run `--write` locally, commit registry files, push.              |
| Registry conflict during merge           | Git conflict markers in `*.registry.yaml`          | Accept one side, then run `--write` to re-derive from disk.      |
| Hand-edited registry                     | `~` drift on registry file itself                 | Never hand-edit registries. Run `--write` to restore.            |
| `scan_dir` misconfigured                 | Persistent drift after `--write`                  | Check `sync_registries.py` config block for correct glob rules.  |
| Missing scan_dir (directory not found)   | Script errors with `FileNotFoundError`            | Create the missing directory or fix the path in config.          |
| Path contains spaces (OneDrive)          | Script fails to glob files                        | Ensure all paths in the script are quoted; use `pathlib.Path`.   |
| Registry file is read-only               | `--write` fails with `PermissionError`            | Check file permissions; ensure OneDrive sync is not locking file.|

---

## Important Rules
- NEVER hand-edit a `*.registry.yaml` file. The next `--write` run will overwrite it.
- NEVER add a registry file to `.gitignore`. Registries are committed artifacts.
- ALWAYS run `--check` in CI, `--write` locally.
- If `--check` passes locally but fails in CI, check for uncommitted registry changes.

---

## Validation
See `08_verification/skill_tests/TEST_SKILL_REGISTRY_SYNC_001_001.yaml`.

The test asserts:
- `--check` exits 0 on a clean repo with no pending file changes.
- `--check` exits 1 and prints a drift report after adding a new file without syncing.
- `--write` produces registry files that cause a subsequent `--check` to exit 0.
- Registry files are valid YAML with required fields: `generated`, `count`, `items`.
