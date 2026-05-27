# Playbook: SKILL_INTENT_COMPILATION_001
# Intent Compilation — Intake to Specs + Architecture Seed

## Skill ID
SKILL_INTENT_COMPILATION_001

## Purpose
Convert a raw intake packet (IDEA-NNNN-*) into structured spec YAMLs and an
architecture seed. The compiler detects repo type, language, framework, and
deployment target from the intake, then emits draft specs and a list of required
architecture artifacts with full traceability links.

---

## Inputs

| Parameter  | Type   | Required | Default       | Description                                      |
|------------|--------|----------|---------------|--------------------------------------------------|
| intake_id  | string | yes      | —             | Intake packet ID in format IDEA-NNNN-<slug>      |
| output_dir | path   | no       | `03_specs/`   | Directory to write draft spec YAMLs              |

---

## Steps

### Step 1 — Locate and read intake packet

```bash
INTAKE_FILE="<repo_root>/00_intake/intake_packets/<intake_id>.yaml"

if [ ! -f "$INTAKE_FILE" ]; then
  echo "ERROR: Intake packet not found at $INTAKE_FILE"
  echo "Resolution: Create the intake packet first using /apex:intake"
  exit 1
fi
```

Read and validate key intake fields:
- `raw_idea` (string, minLength 10 — if shorter, compiler will reject)
- `intake_id` (must match filename)
- `submitted_at` (ISO 8601 date)
- `repo_type` (optional at intake time; compiler will attempt detection)
- `primary_language` (optional)
- `framework` (optional)
- `deployment_target` (optional)

If `raw_idea` is fewer than 10 characters, halt with:
`ERROR: raw_idea too vague. Minimum 10 characters required. Please provide more detail.`

### Step 2 — Run compile_intent.py

```bash
python3 <repo_root>/29_intent_compiler/compile_intent.py \
  --intake "$INTAKE_FILE" \
  --output-dir "<output_dir>"
```

The compiler performs these sub-tasks automatically:

**2a. Detect repo_type**
Inspects intake text and any attached manifests to classify as one of:
- `web_app`, `api_service`, `cli_tool`, `mobile_app`, `library`, `data_pipeline`, `ml_project`

If detection is ambiguous, compiler exits with:
`AMBIGUOUS: Cannot determine repo_type. Please add repo_type field to intake packet.`
Prompt the user to add the field to the intake YAML and re-run.

**2b. Detect primary_language**
Derived from intake text or `primary_language` field if present.
Candidates: Python, TypeScript, JavaScript, Go, Rust, Swift, Kotlin, Java.

**2c. Detect framework**
If `repo_type` is `web_app`: look for React, Vue, Angular, Svelte, Next.js, Nuxt.
If `repo_type` is `api_service`: look for FastAPI, Express, Django, Rails, Gin.

**2d. Detect deployment_target**
Options: `cloud_function`, `container`, `static_site`, `mobile_store`, `npm_package`,
`pypi_package`, `edge_worker`, `on_premise`.

### Step 3 — Determine spec categories needed

Based on detected `repo_type`, the compiler selects which spec categories to populate:

| repo_type      | Spec Categories Required                                          |
|----------------|-------------------------------------------------------------------|
| web_app        | functional, ui_ux, api_contract, data_model, auth, deployment    |
| api_service    | functional, api_contract, data_model, auth, deployment, performance |
| cli_tool       | functional, cli_interface, data_model, deployment                |
| mobile_app     | functional, ui_ux, api_contract, data_model, auth, deployment    |
| library        | functional, api_contract, versioning                             |
| data_pipeline  | functional, data_model, pipeline_stages, deployment              |
| ml_project     | functional, data_model, model_interface, training, deployment    |

### Step 4 — Emit draft spec YAMLs

For each spec category identified in Step 3, the compiler writes one draft spec:

```bash
# Example output paths:
03_specs/functional/SPEC-0001-core-features.yaml
03_specs/api_contract/SPEC-0002-api-contract.yaml
03_specs/data_model/SPEC-0003-data-model.yaml
03_specs/auth/SPEC-0004-authentication.yaml
03_specs/deployment/SPEC-0005-deployment-config.yaml
```

Each draft spec YAML has this structure:

```yaml
spec_id: SPEC-NNNN-<topic>
title: <derived from intake>
category: <spec_category>
status: draft
intake_id: <intake_id>
repo_type: <detected>
primary_language: <detected>
framework: <detected>
deployment_target: <detected>
created_at: <ISO8601>
requirements: []      # to be filled by architect/developer
acceptance_criteria: []
linked_adrs: []
linked_diagrams: []
traceability:
  intake: <intake_id>
  specs: []
  tests: []
```

### Step 5 — Emit architecture seed

The compiler writes an architecture seed file:

```bash
29_intent_compiler/seeds/<intake_id>.architecture_seed.yaml
```

Structure:

```yaml
architecture_seed_id: SEED-<intake_id>
intake_id: <intake_id>
repo_type: <detected>
mandatory_diagrams:
  - system_context    # always required
  - container         # required for web_app, api_service, mobile_app
  - component         # required for all except library
  - sequence          # required for api_service, web_app
  - deployment        # required for cloud deployments
  # data_flow and ecosystem added when data_pipeline or ml_project
candidate_adrs:
  - topic: language_choice
    prompt: "Why <primary_language> over alternatives?"
  - topic: framework_selection
    prompt: "Why <framework>?"
  - topic: deployment_target
    prompt: "Why <deployment_target>?"
  - topic: auth_approach
    prompt: "Authentication strategy choice"
spec_categories_to_populate: [<list from Step 3>]
```

The diagram list is driven by `repo_type`:

| repo_type      | Mandatory Diagrams                                              |
|----------------|-----------------------------------------------------------------|
| web_app        | system_context, container, component, sequence, deployment      |
| api_service    | system_context, container, component, sequence, data_flow, deployment |
| cli_tool       | system_context, component                                       |
| mobile_app     | system_context, container, component, sequence, deployment      |
| library        | system_context, component                                       |
| data_pipeline  | system_context, container, data_flow, deployment               |
| ml_project     | system_context, container, data_flow, component, deployment    |

### Step 6 — Register in intents registry

Append an entry to `29_intent_compiler/intents.registry.yaml`:

```yaml
- intake_id: <intake_id>
  compiled_at: <ISO8601>
  repo_type: <detected>
  primary_language: <detected>
  framework: <detected>
  deployment_target: <detected>
  specs_emitted: <count>
  architecture_seed: 29_intent_compiler/seeds/<intake_id>.architecture_seed.yaml
  status: compiled
```

### Step 7 — Write traceability rows

For each spec emitted, write a traceability row in `21_traceability/rows/`:

```yaml
# 21_traceability/rows/TRACE-<intake_id>-<spec_id>.yaml
trace_id: TRACE-<intake_id>-<spec_id>
intake_id: <intake_id>
spec_id: <spec_id>
created_at: <ISO8601>
links:
  - from: <intake_id>
    to: <spec_id>
    relationship: derived_from
```

---

## Output Summary

| Artifact                                              | Location                                     |
|-------------------------------------------------------|----------------------------------------------|
| Draft spec YAMLs (one per category)                   | `03_specs/<category>/SPEC-NNNN-<topic>.yaml` |
| Architecture seed                                     | `29_intent_compiler/seeds/<intake_id>.architecture_seed.yaml` |
| Intents registry entry                                | `29_intent_compiler/intents.registry.yaml`   |
| Traceability rows                                     | `21_traceability/rows/TRACE-*.yaml`          |

---

## Failure Modes

| Failure                       | Cause                              | Resolution                                          |
|-------------------------------|------------------------------------|-----------------------------------------------------|
| Intake packet not found       | File does not exist                | Create intake via /apex:intake first                |
| raw_idea too vague            | Text shorter than 10 chars         | Add more detail to the intake packet                |
| repo_type detection fails     | Intake text insufficient           | Add `repo_type` field explicitly to intake YAML     |
| Output directory not writable | Permissions or path issue          | Verify `output_dir` exists and is writable          |
| intents.registry.yaml missing | First run                          | Compiler creates it on first run                    |

---

## Related Skills

- `SKILL_SPEC_AUTHORING_001` — fill in requirements for each draft spec
- `SKILL_ADR_AUTHORING_001` — author ADRs for the candidate topics in the seed
- `SKILL_ARCHITECTURE_ATLAS_001` — render the mandatory diagrams from the seed
- `SKILL_CONTEXT_PACKET_001` — compile context before agent begins authoring specs

---

## Validation

`TEST_SKILL_INTENT_COMPILATION_001_001` verifies:
1. A valid intake packet with all required fields produces correct spec count
2. A vague `raw_idea` (< 10 chars) triggers the correct error
3. Each detected `repo_type` maps to the correct set of mandatory diagrams
4. All emitted specs contain valid traceability back to the intake_id

See [08_verification/skill_tests/TEST_SKILL_INTENT_COMPILATION_001_001.yaml](../../08_verification/skill_tests/TEST_SKILL_INTENT_COMPILATION_001_001.yaml).
