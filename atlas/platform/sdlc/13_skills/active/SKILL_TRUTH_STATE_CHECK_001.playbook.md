# Playbook: SKILL_TRUTH_STATE_CHECK_001
# Truth State Drift Check

## Skill ID
SKILL_TRUTH_STATE_CHECK_001

## Purpose
Verify that `19_truth_state/current.truth.yaml` accurately reflects actual repo state.
Detect drift in component count, test count, and verification age. Emit a structured
drift report when thresholds are exceeded.

---

## Inputs

| Parameter    | Type    | Default | Description                                       |
|--------------|---------|---------|---------------------------------------------------|
| target       | path    | `.`     | Absolute path to the repo root being checked      |
| max_age_days | integer | 30      | Maximum allowed age of `last_verified` timestamp  |

---

## Drift Thresholds

| Metric          | Threshold              | Action if exceeded  |
|-----------------|------------------------|---------------------|
| component_count | off by more than 2     | Flag as DRIFTED     |
| test_count      | off by more than 10%   | Flag as DRIFTED     |
| last_verified   | older than max_age_days| Flag as STALE       |

---

## Steps

### Step 1 — Load current.truth.yaml

Verify the file exists before proceeding:

```bash
TRUTH_FILE="<target>/19_truth_state/current.truth.yaml"

if [ ! -f "$TRUTH_FILE" ]; then
  echo "ERROR: current.truth.yaml not found at $TRUTH_FILE"
  echo "Resolution: Run T1 (Truth State initialization) first."
  exit 1
fi
```

Read and extract these fields from the YAML:
- `component_count` (integer)
- `test_count` (integer)
- `last_verified` (ISO 8601 date string)
- `version` (string)
- `repo_root` (path)

If any of these fields are absent, treat the file as malformed and exit with ERROR status.

### Step 2 — Count actual components

```bash
ACTUAL_COMPONENTS=$(find <target> \
  -type f \
  \( -name "*.component.yaml" -o -name "component.yaml" \) \
  | wc -l | tr -d ' ')

echo "Recorded component_count: <truth_component_count>"
echo "Actual component_count:   $ACTUAL_COMPONENTS"
COMPONENT_DELTA=$((ACTUAL_COMPONENTS - truth_component_count))
```

Drift condition: `abs(delta) > 2`

If component directories follow a different naming convention in the target repo,
adjust the `find` pattern to match (e.g., `src/components/*/index.ts`).

### Step 3 — Count actual tests

```bash
ACTUAL_TESTS=$(find <target> \
  -type f \
  \( -name "*_test.*" -o -name "*.test.*" -o -name "*.spec.*" -o -name "test_*.py" \) \
  | wc -l | tr -d ' ')

echo "Recorded test_count: <truth_test_count>"
echo "Actual test_count:   $ACTUAL_TESTS"
```

Drift condition: `abs(actual - recorded) / recorded > 0.10` (10% tolerance).
If `recorded` is 0, flag as DRIFTED if `actual > 0`.

### Step 4 — Check last_verified age

```python
from datetime import date, datetime

last_verified = datetime.fromisoformat("<truth_last_verified>").date()
today = date.today()
age_days = (today - last_verified).days

if age_days > max_age_days:
    print(f"STALE: last_verified is {age_days} days old (threshold: {max_age_days})")
else:
    print(f"OK: last_verified is {age_days} days old")
```

### Step 5 — Run check_truth_drift.py

```bash
python3 <target>/19_truth_state/check_truth_drift.py --check \
  --truth <target>/19_truth_state/current.truth.yaml \
  --target <target>
```

This script performs internal consistency checks:
- Registry entry counts vs. file system
- ADR sequence integrity
- Spec linkage completeness

Exit code semantics: `0` = no drift, `1` = drift detected, `2` = script error.

### Step 6 — Compile drift findings

Aggregate all results into an internal findings object:

```yaml
findings:
  component_count:
    recorded: <int>
    actual: <int>
    delta: <int>
    status: OK | DRIFTED
  test_count:
    recorded: <int>
    actual: <int>
    delta_pct: <float>
    status: OK | DRIFTED
  last_verified:
    recorded: <date>
    age_days: <int>
    status: OK | STALE
  script_exit_code: <0|1|2>
  overall_status: CLEAN | DRIFTED | ERROR
```

Set `overall_status`:
- `CLEAN` if all three metrics are OK and script exit code is 0
- `DRIFTED` if any metric is DRIFTED or script exit code is 1
- `ERROR` if script exit code is 2 or file was malformed

### Step 7 — Write drift report

```bash
REPORT_DATE=$(date +%Y-%m-%d)
REPORT_DIR="<target>/20_drift_detection/drift_reports"
REPORT_FILE="$REPORT_DIR/DRIFT-$REPORT_DATE.yaml"
mkdir -p "$REPORT_DIR"
```

Emit the following YAML structure to `$REPORT_FILE`:

```yaml
drift_report_id: DRIFT-<YYYY-MM-DD>
generated_at: <ISO8601 timestamp>
skill_id: SKILL_TRUTH_STATE_CHECK_001
target_repo: <target>
truth_file: 19_truth_state/current.truth.yaml
findings:
  component_count:
    recorded: <int>
    actual: <int>
    delta: <int>
    threshold: 2
    status: OK | DRIFTED
  test_count:
    recorded: <int>
    actual: <int>
    delta_pct: <float>
    threshold_pct: 0.10
    status: OK | DRIFTED
  last_verified:
    recorded: <date>
    age_days: <int>
    max_age_days: <max_age_days>
    status: OK | STALE
  script_check:
    exit_code: <0|1|2>
    status: OK | DRIFTED | ERROR
overall_status: CLEAN | DRIFTED | ERROR
resolution_required: <true|false>
```

---

## Output

- **Primary**: `20_drift_detection/drift_reports/DRIFT-<YYYY-MM-DD>.yaml`
- **Console**: Summary table showing status for each metric

---

## When to Run This Skill

| Trigger                                     | Rationale                       |
|---------------------------------------------|---------------------------------|
| Every 30 days (scheduled)                   | Routine hygiene                 |
| After any major refactor or folder rename   | Post-change verification        |
| At start of T4 hygiene pass                 | Pre-hygiene baseline            |
| After adding or removing more than 3 comps  | Spot check                      |
| Before releasing a context packet to agent  | Pre-flight check                |

---

## Failure Modes

| Failure                          | Cause                            | Resolution                                    |
|----------------------------------|----------------------------------|-----------------------------------------------|
| current.truth.yaml missing       | T1 never run                     | Run T1 (Truth State init) first               |
| Repo not accessible              | Path wrong or not mounted        | Verify `target`; check OneDrive sync status   |
| check_truth_drift.py not found   | Script missing from 19_truth_state | Re-clone or restore from backup             |
| Drift on component_count         | Components added or removed      | Re-run T1 Step 1 to regenerate truth          |
| Drift on test_count              | Tests added or removed           | Update truth manually or re-run T1            |
| last_verified too old            | Hygiene pass overdue             | Run full T4 hygiene pass                      |

---

## Post-Run Actions

**If `overall_status: CLEAN`:**
- No action required.
- Archive report in `20_drift_detection/drift_reports/`.

**If `overall_status: DRIFTED`:**
1. Review specific drifted fields in the report.
2. Re-run T1 Step 1 to regenerate `current.truth.yaml` from actual state.
3. Re-run this skill to confirm clean state.
4. Record resolution in `19_truth_state/drift_history.yaml`.

**If `overall_status: ERROR`:**
1. Check Python environment and script availability.
2. Verify `target` path is correct and accessible.
3. Escalate to manual review if errors persist.

---

## Related Skills

- `SKILL_DRIFT_DETECTION_001` — broader drift detection across all registries
- `SKILL_CONTEXT_PACKET_001` — uses truth state as input; run this check first
- `SKILL_REGISTRY_SYNC_001` — sync registries after resolving drift

---

## Validation

`TEST_SKILL_TRUTH_STATE_CHECK_001_001` verifies:
1. A known-drifted truth file produces `overall_status: DRIFTED`
2. A fresh truth file with zero delta produces `overall_status: CLEAN`
3. A truth file with `last_verified` 31 days ago at `max_age_days=30` produces STALE

See [08_verification/skill_tests/TEST_SKILL_TRUTH_STATE_CHECK_001_001.yaml](../../08_verification/skill_tests/TEST_SKILL_TRUTH_STATE_CHECK_001_001.yaml).
