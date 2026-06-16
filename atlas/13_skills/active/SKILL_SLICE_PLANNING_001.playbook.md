# Playbook: SKILL_SLICE_PLANNING_001 — Vertical Slice Planning

## Skill ID
SKILL_SLICE_PLANNING_001

## Version
1.0.0

## Purpose
Author a `SLICE-NNNN` YAML document for a vertical slice of work. A vertical slice is
the smallest unit of shippable functionality that has a proof path, a preview deployment
plan, and traceable links to specs and an intake packet. This is T3 step 1.

---

## Inputs

| Field           | Type     | Required | Description                                                    |
|-----------------|----------|----------|----------------------------------------------------------------|
| `title`         | string   | yes      | Short human-readable name for the slice (max 60 chars)         |
| `spec_ids`      | list     | yes      | List of SPEC-NNNN IDs that define this slice's scope           |
| `intent_brief`  | string   | yes      | 1–3 sentences describing what this slice proves or enables     |

---

## Output Location

```
atlas/22_vertical_slices/<state>/SLICE-NNNN-<slug>.yaml
```

Where `<state>` is `planned` for a newly authored slice.
`<slug>` is the `title` lowercased with spaces replaced by hyphens.

---

## Schema Reference

`atlas/schemas/vertical_slice/vertical_slice.schema.json`

Required fields: `id`, `title`, `status`, `intent_brief`, `spec_ids`, `intake_packet_id`,
`proof_requirements`, `preview_deploy`, `created`, `updated`.

---

## Step-by-Step Execution

### Step 1: Confirm an Intake Packet Exists

Before authoring a slice, verify that an intake packet exists for the broader initiative:
```
READ  atlas/15_intake/
```

If no intake packet covers this work, STOP. Use the intake process to author one first.
The slice must reference a valid `intake_packet_id`.

### Step 2: Derive the Next Slice ID

List existing slice YAML files across all state directories:
```bash
find "atlas/22_vertical_slices/" -name "SLICE-*.yaml" | sort
```

Extract the highest existing NNNN number (zero-padded to 4 digits).
Next ID = highest + 1, formatted as `SLICE-NNNN`.

If no slices exist yet, start at `SLICE-0001`.

**Collision check:** After deriving the ID, confirm no file with that ID already exists
in any sub-directory (planned, active, released, abandoned).

### Step 3: Validate Referenced Spec IDs

For each `spec_id` in the input list:
```bash
find "atlas/03_specs/" -name "<spec_id>*.yaml"
```

If any spec ID does not resolve to an existing file, STOP and report the missing spec.
Do not create a slice referencing non-existent specs.

### Step 4: Derive the Slug

```
slug = title.lower().replace(" ", "-").replace("/", "-")
slug = re.sub(r"[^a-z0-9\-]", "", slug)[:50]
```

### Step 5: Author the Slice YAML

Write to `atlas/22_vertical_slices/planned/SLICE-NNNN-<slug>.yaml`:

```yaml
id: SLICE-NNNN
title: "<title>"
status: planned
intent_brief: >
  <intent_brief — 1-3 sentences>

intake_packet_id: <resolved intake packet id>
spec_ids:
  - SPEC-XXXX
  - SPEC-YYYY

proof_requirements:
  diagrams_must_be_updated:
    - "<name>_component_map.mmd"
    - "<name>_data_flow.mmd"
    # Add any diagram that changes as a result of this slice's implementation
  tests_must_pass:
    - "<test pattern or specific test ID>"
    # e.g. "unit/core.test.ts", "TEST_SKILL_XXX_001"
  adr_must_exist:
    - "<ADR-NNNN if an architectural decision is required>"
    # Leave empty list [] if no ADR is required
  acceptance_criteria_source:
    - <list of SPEC-NNNN IDs whose acceptance_criteria govern this slice>

preview_deploy:
  target: "<vercel | github-pages | local | docker>"
  url_pattern: "<preview URL template, e.g. https://<branch>.myproject.vercel.app>"
  build_steps:
    - step: 1
      command: "<build command>"
      description: "<what this step does>"
    - step: 2
      command: "<deploy command>"
      description: "<what this step does>"
  rollback_path: >
    <Describe how to revert this deploy if it breaks production.
    Must include: how to trigger rollback, expected RTO, who is responsible.>
  health_check: "<URL or command to verify successful deployment>"

traceability:
  intake_packet: <intake_packet_id>
  specs: <spec_ids list>
  adr: []
  diagrams: []

created: <ISO-8601 date>
updated: <ISO-8601 date>
author: <author identifier>
```

### Step 6: Fill in proof_requirements Correctly

**diagrams_must_be_updated:** List every `.mmd` file that will change as a result of
implementing this slice. Minimum: 1 diagram. If the slice adds a new component, at
minimum `component_map` and `data_flow` must be listed.

**tests_must_pass:** List the test IDs or test file patterns that provide evidence this
slice is complete. These become the acceptance gate in CI. Minimum: 1 test.

**adr_must_exist:** If this slice introduces an architectural decision (new library,
new pattern, new service), an ADR is required. Reference it here before the slice can
move from `planned` to `active`. If no architectural decision is needed, use `[]`.

**acceptance_criteria_source:** Reference the spec IDs whose `acceptance_criteria`
sections define the slice's "done" condition. Do not duplicate criteria here —
point to the specs.

### Step 7: Fill in preview_deploy Correctly

**target options:**
- `vercel` — deploy to Vercel preview environment on PR
- `github-pages` — deploy to GitHub Pages branch
- `local` — start a local dev server (for internal tools or libraries)
- `docker` — build and run Docker image locally

**build_steps:** Ordered list of commands needed to go from source to deployed preview.
Steps must be runnable in sequence without manual intervention.

**rollback_path:** MUST describe:
1. The command or action to revert (e.g. `vercel rollback <deployment-id>` or
   `git revert <commit>` + redeploy)
2. Expected time to rollback (RTO)
3. Who is responsible for executing the rollback

If the preview target is not reachable from the current environment, document the
blocked path and set `target: blocked` with a note in rollback_path explaining why.

### Step 8: Link to traceability.yaml

Read `atlas/19_truth_state/traceability.yaml` (or the traceability index
for this project). Add a row:

```yaml
- slice_id: SLICE-NNNN
  title: "<title>"
  intake_packet_id: <id>
  spec_ids: [SPEC-XXXX, SPEC-YYYY]
  status: planned
  created: <ISO date>
```

### Step 9: Run Registry Sync

After writing the slice YAML, run SKILL_REGISTRY_SYNC_001 in `--write` mode to
update `22_vertical_slices/slices.registry.yaml`.

---

## Slice Size Guidelines

A well-scoped vertical slice should:
- Reference no more than 8 specs
- Have no more than 6 build_steps in the preview_deploy
- Be implementable in a single development session (not a multi-week epic)
- Have a clearly testable outcome that a CI job can verify automatically

**Slice too large:** If the spec_ids list exceeds 8 or the scope clearly spans multiple
independent features, split into 2 or more slices. Each sub-slice must independently
satisfy the proof_requirements for its own scope.

---

## Failure Modes and Mitigations

| Failure                              | Mitigation                                                                   |
|--------------------------------------|------------------------------------------------------------------------------|
| No intake packet exists              | STOP. Author an intake packet first. Slices cannot float without intake.     |
| Referenced spec ID does not exist    | STOP. Create the spec first via SKILL_SPEC_AUTHORING_001, then plan slice.  |
| Slice ID collision                   | Re-derive: scan all 4 state sub-dirs, find actual highest ID, increment.     |
| Preview deploy target not reachable  | Set `target: blocked`; document the blocker in `rollback_path` field.        |
| rollback_path field left empty       | Invalid slice. The rollback_path is mandatory. Fail schema validation.       |
| Slice too large (>8 specs)           | Split into multiple slices. Update traceability to link them as a sequence.  |
| No adr_must_exist for new library    | Halt slice planning. Author ADR first, reference it, then proceed.           |

---

## Validation
See `08_verification/skill_tests/TEST_SKILL_SLICE_PLANNING_001_001.yaml`.

The test asserts:
- Output YAML passes `schemas/vertical_slice/vertical_slice.schema.json` validation.
- `id` matches the `SLICE-NNNN` pattern and is unique across all state directories.
- All `spec_ids` resolve to existing files.
- `proof_requirements.tests_must_pass` is non-empty.
- `preview_deploy.rollback_path` is non-empty.
- A traceability row exists for the new slice ID.
- `slices.registry.yaml` contains the new slice after `--write`.
