# Playbook: SKILL_REPO_TWIN_INGEST_001
# Repo Twin Ingest — Bookworm Ingestion Pipeline

## Skill ID
SKILL_REPO_TWIN_INGEST_001

## Purpose
Ingest a child repo into its ATLAS twin by running the Bookworm
ingestion pipeline. Populates architecture snapshot, component graph, and dependency
graph from actual file system state. Writes a factual last-known-state summary.
Updates repo ledger. Skips ingestion if twin is already synced and fresh (< 30 days),
unless `--force` is passed.

---

## Inputs

| Parameter   | Type    | Required | Description                                                       |
|-------------|---------|----------|-------------------------------------------------------------------|
| twin_name   | string  | yes      | Name of the twin directory under `39_repo_twins/twins/`           |
| target_path | path    | no       | Absolute path to child repo on disk. Skip ingestion if not given. |

---

## Steps

### Step 1 — Verify twin directory exists

```bash
TWIN_DIR="<repo_root>/39_repo_twins/twins/<twin_name>"

if [ ! -d "$TWIN_DIR" ]; then
  echo "ERROR: Twin directory not found at $TWIN_DIR"
  echo "Resolution: Run create_repo_twin.py first to scaffold the twin structure."
  exit 1
fi
```

Expected files inside a properly scaffolded twin:
- `sync_status.yaml`
- `architecture.snapshot.yaml`
- `component.graph.yaml`
- `dependency.graph.yaml`
- `last_known_state.md`

### Step 2 — Check sync_status.yaml — skip if fresh

```bash
SYNC_STATUS_FILE="$TWIN_DIR/sync_status.yaml"

if [ ! -f "$SYNC_STATUS_FILE" ]; then
  echo "WARNING: sync_status.yaml missing. Proceeding with full ingestion."
else
  # Read status and last_synced
  STATUS=$(python3 -c "import yaml; d=yaml.safe_load(open('$SYNC_STATUS_FILE')); print(d.get('status',''))")
  LAST_SYNCED=$(python3 -c "import yaml; d=yaml.safe_load(open('$SYNC_STATUS_FILE')); print(d.get('last_synced',''))")
fi
```

Compute age in days:

```python
from datetime import date, datetime

last_synced = datetime.fromisoformat(LAST_SYNCED).date()
age_days = (date.today() - last_synced).days

if STATUS == "synced" and age_days < 30 and not FORCE:
    print(f"Twin '{twin_name}' is already synced ({age_days} days ago). Skipping.")
    print("Use --force to re-ingest anyway.")
    exit(0)
```

If `status: synced` and `last_synced` is less than 30 days ago: skip and exit 0,
unless `--force` was passed.

### Step 3 — Check target_path reachability

```bash
if [ -z "$TARGET_PATH" ]; then
  echo "WARNING: No target_path provided. Marking twin as pending_ingestion."
  # Skip to Step 7b (mark as pending)
  REACHABLE=false
elif [ ! -d "$TARGET_PATH" ]; then
  echo "WARNING: target_path '$TARGET_PATH' does not exist on disk."
  echo "Check repo_ledger.yaml for the repo URL if you need to clone it."
  REACHABLE=false
else
  REACHABLE=true
fi
```

If not reachable: jump to Step 7b (mark pending, do not ingest). Never fabricate
content for a repo that is not accessible.

### Step 4 — Run Bookworm ingestion

```bash
python3 <repo_root>/38_bookworm_engine/ingestion/run_ingestion.py \
  --target "$TARGET_PATH" \
  --output-dir "<repo_root>/38_bookworm_engine/indexing/"
```

This script requires `pyyaml`. If it fails with `ModuleNotFoundError`:

```bash
pip install pyyaml
# Then retry the ingestion command
```

Expected output files in `38_bookworm_engine/indexing/`:
- `file_index.yaml` — all files indexed with path, size, type
- `component_index.yaml` — detected components with names, types, file locations
- `dependency.graph.yaml` — dependency edges between components and external packages
- `index_metadata.yaml` — timestamp, file count, component count

If the script errors for any other reason, check its log output. Common issues:
- Unsupported file type (add to ingestion config's ignore list)
- Permission denied on a subdirectory
- Corrupt file encoding (add to ignore list)

### Step 5 — Populate architecture.snapshot.yaml

Read `38_bookworm_engine/indexing/component_index.yaml` and
`38_bookworm_engine/indexing/file_index.yaml`, then write:

```yaml
# 39_repo_twins/twins/<twin_name>/architecture.snapshot.yaml
snapshot_id: SNAP-<twin_name>-<YYYYMMDD>
twin_name: <twin_name>
target_path: <target_path>
ingested_at: <ISO8601>
file_count: <int from file_index>
component_count: <int from component_index>
top_level_dirs: [<list of root dirs>]
primary_language: <detected from component_index>
framework: <detected or null>
components:
  - name: <component_name>
    type: <module|class|service|function|package>
    file: <relative path within target_path>
    exports: []
```

### Step 6 — Populate dependency.graph.yaml

Read `38_bookworm_engine/indexing/dependency.graph.yaml` and copy it into the twin:

```yaml
# 39_repo_twins/twins/<twin_name>/dependency.graph.yaml
dependency_graph_id: DEP-<twin_name>-<YYYYMMDD>
twin_name: <twin_name>
ingested_at: <ISO8601>
external_dependencies:
  - name: <package_name>
    version: <version or null>
    type: runtime | dev | peer
internal_edges:
  - from: <component_a>
    to: <component_b>
    type: imports | calls | extends | implements
```

### Step 7 — Populate component.graph.yaml

```yaml
# 39_repo_twins/twins/<twin_name>/component.graph.yaml
component_graph_id: CG-<twin_name>-<YYYYMMDD>
twin_name: <twin_name>
ingested_at: <ISO8601>
component_count: <int>
nodes:
  - id: <component_id>
    name: <component_name>
    type: <type>
    file: <relative_path>
edges:
  - from: <component_id>
    to: <component_id>
    relationship: depends_on | calls | extends
```

### Step 7a — Write last_known_state.md (facts only)

Write a one-paragraph factual summary derived entirely from the indexes.
Do not speculate about purpose, quality, or anything not directly in the index data.

```markdown
# Last Known State — <twin_name>

**Ingested:** <ISO8601 date>
**Target path:** <target_path>
**File count:** <int>
**Component count:** <int>
**Primary language:** <detected>
**External dependencies:** <count> packages (<list top 5 by name>)
**Top-level directories:** <list>

This summary was generated by SKILL_REPO_TWIN_INGEST_001 from Bookworm indexes.
It reflects the state of the repository as of the ingestion date above.
```

No editorial judgment, no speculation about code quality or architecture intent.

### Step 7b — If target_path not reachable: mark pending

Write to `sync_status.yaml`:

```yaml
status: pending_ingestion
last_synced: null
note: target not reachable on disk
checked_at: <ISO8601 today>
twin_name: <twin_name>
```

Write to `last_known_state.md`:

```markdown
# Last Known State — <twin_name>

**Status:** Pending ingestion — target not reachable on disk.
**Checked:** <ISO8601 date>

No ingestion has been performed. Run SKILL_REPO_TWIN_INGEST_001 with a valid
target_path to populate this twin.
```

Then exit. Do not write placeholder data to any other twin files.

### Step 8 — Flip sync_status.yaml to synced

```yaml
status: synced
last_synced: <ISO8601 today>
ingested_by: SKILL_REPO_TWIN_INGEST_001
component_count: <int>
file_count: <int>
target_path: <target_path>
twin_name: <twin_name>
```

### Step 9 — Update repo_ledger.yaml

Read `18_registry/repo_ledger.yaml` and find the entry for this repo.
Update its fields:

```yaml
# In 18_registry/repo_ledger.yaml
- repo_id: <existing id>
  twin_name: <twin_name>
  last_ingested: <ISO8601 today>
  component_count: <int from component_index>
  sync_status: synced
```

If no entry exists for this twin, append a new one. Do not delete or reorder
existing entries.

---

## Output Summary

| Artifact                                                     | Action      |
|--------------------------------------------------------------|-------------|
| `39_repo_twins/twins/<twin_name>/architecture.snapshot.yaml` | Written     |
| `39_repo_twins/twins/<twin_name>/component.graph.yaml`       | Written     |
| `39_repo_twins/twins/<twin_name>/dependency.graph.yaml`      | Written     |
| `39_repo_twins/twins/<twin_name>/last_known_state.md`        | Written     |
| `39_repo_twins/twins/<twin_name>/sync_status.yaml`           | Updated     |
| `18_registry/repo_ledger.yaml`                               | Updated     |

---

## Failure Modes

| Failure                          | Cause                              | Resolution                                             |
|----------------------------------|------------------------------------|--------------------------------------------------------|
| Twin directory missing           | Twin never scaffolded              | Run create_repo_twin.py first                          |
| target_path doesn't exist        | Repo not cloned locally            | Check repo_ledger.yaml for url; offer to clone         |
| run_ingestion.py fails: pyyaml   | Missing Python dependency          | `pip install pyyaml` then retry                        |
| run_ingestion.py not found       | Bookworm not in repo               | Restore 38_bookworm_engine/ingestion/ from git         |
| component_index.yaml empty       | Repo has no recognized components  | Review ingestion config; may need language-specific parser |
| repo_ledger.yaml not found       | Registry missing                   | Create it or run SKILL_REGISTRY_SYNC_001               |

---

## What NOT To Do

- Do NOT fabricate `last_known_state.md` content when target is unreachable
- Do NOT populate component or dependency graphs with placeholder data
- Do NOT mark `status: synced` unless ingestion completed successfully
- Do NOT remove existing entries from `repo_ledger.yaml`

---

## Related Skills

- `SKILL_CONTEXT_COMPILATION_002` — uses twin data for cross-repo mesh
- `SKILL_REGISTRY_SYNC_001` — sync registries after ingest
- `SKILL_TRUTH_STATE_CHECK_001` — update truth state after major ingest

---

## Validation

`TEST_SKILL_REPO_TWIN_INGEST_001_001` verifies:
1. Unreachable target_path results in `pending_ingestion` status, not an error crash
2. Successful ingestion writes all 4 twin files with non-empty content
3. A twin already synced < 30 days ago is skipped without `--force`
4. `repo_ledger.yaml` entry is updated with correct component_count after ingest

See [08_verification/skill_tests/TEST_SKILL_REPO_TWIN_INGEST_001_001.yaml](../../08_verification/skill_tests/TEST_SKILL_REPO_TWIN_INGEST_001_001.yaml).
