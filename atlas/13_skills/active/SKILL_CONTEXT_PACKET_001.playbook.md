# Playbook: SKILL_CONTEXT_PACKET_001
# Coding Agent Context Packet Generation

## Skill ID
SKILL_CONTEXT_PACKET_001

## Purpose
Compile a targeted context packet for an agent persona. Each persona requires a
specific set of repo state slices. The compiled packet is saved as a
`context_packet.yaml` under `42_context_compiler/output/generated/` and fed to
the agent before it begins work.

---

## Inputs

| Parameter   | Type   | Required | Description                                              |
|-------------|--------|----------|----------------------------------------------------------|
| persona     | enum   | yes      | One of: apex_coding_agent, qa_agent, deployment_agent, architecture_agent, drift_agent |
| target      | path   | yes      | Absolute path to the repo root                           |
| output_path | path   | no       | Override output directory (default: 42_context_compiler/output/generated/) |

---

## Persona Context Slice Map

| Persona              | Required Slices                                                    |
|----------------------|--------------------------------------------------------------------|
| apex_coding_agent    | truth_state, component_map, active_slice, open_specs, ADRs        |
| qa_agent             | test_coverage, verification_ledger, open_drift_reports, evidence_packets |
| deployment_agent     | deployment_impact, ci_pipeline, release_ledger, preview_plans     |
| architecture_agent   | all 7 architecture diagrams, decision_ledger, ecosystem_map       |
| drift_agent          | drift_state, all registries, traceability rows, last truth_state  |

---

## Steps

### Step 1 — Validate persona input

```python
VALID_PERSONAS = [
    "apex_coding_agent",
    "qa_agent",
    "deployment_agent",
    "architecture_agent",
    "drift_agent",
]

if persona not in VALID_PERSONAS:
    raise ValueError(
        f"Unrecognized persona '{persona}'. "
        f"Valid options: {', '.join(VALID_PERSONAS)}"
    )
```

If persona is not recognized, halt immediately. Do not attempt to guess or
default to another persona — context mismatches cause agent errors.

### Step 2 — Read context_packet.schema.yaml

```bash
SCHEMA_FILE="<target>/42_context_compiler/context_packet.schema.yaml"

if [ ! -f "$SCHEMA_FILE" ]; then
  echo "ERROR: schema file not found at $SCHEMA_FILE"
  exit 1
fi
```

The schema defines required fields, field types, and which slices are valid.
Load it before building the packet to validate output at Step 5.

### Step 3 — Verify truth state exists

Before compiling any packet, confirm `current.truth.yaml` is present and not stale:

```bash
TRUTH_FILE="<target>/19_truth_state/current.truth.yaml"

if [ ! -f "$TRUTH_FILE" ]; then
  echo "ERROR: current.truth.yaml missing. Run SKILL_TRUTH_STATE_CHECK_001 first."
  exit 1
fi
```

Optionally run `SKILL_TRUTH_STATE_CHECK_001` at this point to confirm truth is clean.

### Step 4 — Determine context slices for persona

Based on the persona, select the required slices from this lookup:

```yaml
slice_map:
  apex_coding_agent:
    - truth_state          # 19_truth_state/current.truth.yaml
    - component_map        # 18_registry/component_registry.yaml
    - active_slice         # 14_slices/active/current_slice.yaml
    - open_specs           # 03_specs/ — specs with status: open
    - ADRs                 # 04_architecture/decisions/
  qa_agent:
    - test_coverage        # 08_verification/coverage_report.yaml
    - verification_ledger  # 08_verification/verification_ledger.yaml
    - open_drift_reports   # 20_drift_detection/drift_reports/ (open only)
    - evidence_packets     # 08_verification/evidence/
  deployment_agent:
    - deployment_impact    # 23_deployment/impact_assessment.yaml
    - ci_pipeline          # .github/workflows/ or ci_pipeline.yaml
    - release_ledger       # 23_deployment/release_ledger.yaml
    - preview_plans        # 23_deployment/preview_plans/
  architecture_agent:
    - diagram_system_context     # 04_architecture/diagrams/
    - diagram_container          # 04_architecture/diagrams/
    - diagram_component          # 04_architecture/diagrams/
    - diagram_sequence           # 04_architecture/diagrams/
    - diagram_data_flow          # 04_architecture/diagrams/
    - diagram_deployment         # 04_architecture/diagrams/
    - diagram_ecosystem          # 04_architecture/diagrams/
    - decision_ledger            # 04_architecture/decisions/ledger.yaml
    - ecosystem_map              # 04_architecture/ecosystem_map.yaml
  drift_agent:
    - drift_state          # 20_drift_detection/current_drift_state.yaml
    - component_registry   # 18_registry/component_registry.yaml
    - spec_registry        # 18_registry/spec_registry.yaml
    - adr_registry         # 18_registry/adr_registry.yaml
    - traceability_rows    # 21_traceability/rows/
    - last_truth_state     # 19_truth_state/current.truth.yaml
```

### Step 5 — Run compile_context.py

```bash
python3 <target>/42_context_compiler/compile_context.py \
  --persona <persona> \
  --target <target> \
  --output <output_path>
```

The compiler will:
1. Read each slice file listed for the persona
2. Flatten nested YAML into the packet structure
3. Add metadata (generated_at, skill_id, persona, target)
4. Write `context_packet.yaml` to the output directory

### Step 6 — Validate output against schema

```python
import yaml
import jsonschema

with open("<output_path>/context_packet.yaml") as f:
    packet = yaml.safe_load(f)

with open("<target>/42_context_compiler/context_packet.schema.yaml") as f:
    schema = yaml.safe_load(f)

jsonschema.validate(packet, schema)
print("Schema validation: PASSED")
```

If validation fails, print the specific field that failed and halt.
Do not deliver an invalid packet to an agent.

### Step 7 — Emit summary to console

After successful compilation, print:

```
Context packet compiled for persona: <persona>
Output: <output_path>/context_packet.yaml
Slices included: <count>
Schema validation: PASSED
Generated at: <ISO8601 timestamp>
```

---

## Output

- **File**: `42_context_compiler/output/generated/context_packet.yaml`
- **Structure**:

```yaml
context_packet_id: CP-<persona>-<YYYYMMDD>
generated_at: <ISO8601>
skill_id: SKILL_CONTEXT_PACKET_001
persona: <persona>
target_repo: <target>
slices:
  truth_state: { ... }
  component_map: { ... }
  # ... additional slices per persona
```

---

## Failure Modes

| Failure                        | Cause                              | Resolution                                   |
|--------------------------------|------------------------------------|----------------------------------------------|
| Persona not recognized         | Typo or unsupported persona        | Check valid persona list in Step 1           |
| current.truth.yaml missing     | T1 never run                       | Run SKILL_TRUTH_STATE_CHECK_001 first        |
| Slice file not found           | Repo incomplete                    | Check that target repo has expected structure|
| Schema validation fails        | Compiler emitted invalid structure | Review compile_context.py output, check schema version |
| compile_context.py not found   | Script missing                     | Restore from 42_context_compiler/            |

---

## Related Skills

- `SKILL_TRUTH_STATE_CHECK_001` — verify truth is clean before compiling
- `SKILL_CONTEXT_COMPILATION_002` — upgrade: adds cross-repo mesh and Bookworm data
- `SKILL_DRIFT_DETECTION_001` — run first if drift_agent persona is requested

---

## When to Use vs SKILL_CONTEXT_COMPILATION_002

Use **SKILL_CONTEXT_PACKET_001** (this skill) when:
- Working within a single repo
- Token budget is tight
- Cross-repo context is not relevant to the current task

Use **SKILL_CONTEXT_COMPILATION_002** when:
- Working across multiple repos
- Bookworm knowledge mesh enrichment is needed
- Ecosystem-level context is required

---

## Validation

`TEST_SKILL_CONTEXT_PACKET_001_001` verifies:
1. Each persona produces a packet containing exactly the expected slices
2. Missing truth file triggers correct error message
3. Invalid persona triggers halt with correct error

See [08_verification/skill_tests/TEST_SKILL_CONTEXT_PACKET_001_001.yaml](../../08_verification/skill_tests/TEST_SKILL_CONTEXT_PACKET_001_001.yaml).
