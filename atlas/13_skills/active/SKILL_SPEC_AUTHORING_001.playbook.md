# Playbook: SKILL_SPEC_AUTHORING_001 — Spec Authoring

## Skill ID
SKILL_SPEC_AUTHORING_001

## Version
1.0.0

## Purpose
Author structured specification documents across all 12 spec categories. Each spec has
a traceable ID, mandatory acceptance criteria, and a link to a vertical slice or intake
packet. Specs are the evidence layer between intent (intake/vision) and proof
(tests/diagrams).

---

## Inputs

| Field             | Type   | Required | Description                                              |
|-------------------|--------|----------|----------------------------------------------------------|
| `category`        | enum   | yes      | One of the 12 spec category codes (see table below)      |
| `title`           | string | yes      | Short description of what this spec defines (max 80 chars)|
| `linked_slice_id` | string | no       | `SLICE-NNNN` to link this spec to a vertical slice        |

---

## Output Location

```
atlas/03_specs/<category>/SPEC-NNNN-<slug>.yaml
```

Where `<slug>` is the `title` lowercased with spaces and special characters replaced
by hyphens.

---

## Schema Reference

`atlas/schemas/spec/spec.schema.json`

Required fields: `id`, `category`, `title`, `description`, `acceptance_criteria`,
`status`, `created`, `updated`.

---

## The 12 Spec Categories

| Category Code           | Directory                              | What It Contains                                                    |
|-------------------------|----------------------------------------|---------------------------------------------------------------------|
| `functional`            | `03_specs/functional_requirements/`   | Behavioral requirements: what the system does. User stories, feature descriptions, state machines. |
| `non_functional`        | `03_specs/non_functional_requirements/` | Quality attributes: performance, scalability, reliability, availability, SLAs. |
| `acceptance`            | `03_specs/acceptance_criteria/`       | Explicit done-conditions that map to automated test cases. Usually derived from functional specs. |
| `agent`                 | `03_specs/agent_requirements/`        | Requirements for AI agent behavior: persona constraints, tool access, output format, escalation rules. |
| `api`                   | `03_specs/api_requirements/`          | API contracts: endpoints, request/response schemas, authentication, versioning, rate limits. |
| `constraints`           | `03_specs/constraints/`               | Hard limits and non-negotiable boundaries: budget, legal, compliance, platform restrictions. |
| `data`                  | `03_specs/data_requirements/`         | Data models, schemas, retention policies, migration requirements, privacy classifications. |
| `integration`           | `03_specs/integration_requirements/`  | Third-party and cross-repo integration requirements: protocols, auth, error handling, SLA. |
| `product`               | `03_specs/product_requirements/`      | Product-level requirements: market positioning, feature flags, rollout strategy, pricing constraints. |
| `security`              | `03_specs/security_requirements/`     | Security controls: authentication, authorization, encryption, audit logging, threat model. |
| `ui`                    | N/A (use `functional` + `acceptance`) | UI/UX requirements: component behavior, accessibility (WCAG level), responsive breakpoints, interaction patterns. Note: no dedicated directory; file under `functional_requirements/` with category tag `ui`. |
| `adr`                   | `03_specs/adr/`                       | Architectural Decision Records: decision context, options considered, decision made, consequences. |

> Note: The `ui` category does not have a dedicated directory. File UI specs in
> `functional_requirements/` and set `category: ui` in the YAML. The `adr` category
> is a spec sub-type; use SKILL_ADR_AUTHORING_001 for full ADR authoring.

---

## Step-by-Step Execution

### Step 1: Validate Category

Confirm the provided `category` value is one of the 12 codes in the table above.
If not, STOP and report: `Unrecognized spec category: <value>. Use one of: functional,
non_functional, acceptance, agent, api, constraints, data, integration, product,
security, ui, adr`.

### Step 2: Resolve the Target Directory

```python
CATEGORY_DIRS = {
    "functional":     "03_specs/functional_requirements/",
    "non_functional": "03_specs/non_functional_requirements/",
    "acceptance":     "03_specs/acceptance_criteria/",
    "agent":          "03_specs/agent_requirements/",
    "api":            "03_specs/api_requirements/",
    "constraints":    "03_specs/constraints/",
    "data":           "03_specs/data_requirements/",
    "integration":    "03_specs/integration_requirements/",
    "product":        "03_specs/product_requirements/",
    "security":       "03_specs/security_requirements/",
    "ui":             "03_specs/functional_requirements/",   # special case
    "adr":            "03_specs/adr/",
}
target_dir = CATEGORY_DIRS[category]
```

### Step 3: Derive the Next Spec ID

List existing spec files in the target directory:
```bash
find "atlas/03_specs/" -name "SPEC-*.yaml" | sort
```

Extract all existing NNNN numbers from filenames across ALL category directories
(IDs are unique globally, not per-category). Next ID = highest + 1, zero-padded to 4.

If no specs exist yet, start at `SPEC-0001`.

**Collision check:** Confirm `SPEC-NNNN` does not appear in any category directory.

### Step 4: Derive the Slug

```
slug = title.lower().replace(" ", "-")
slug = re.sub(r"[^a-z0-9\-]", "", slug)[:50]
```

### Step 5: Author the Spec YAML

Write to `atlas/03_specs/<category_dir>/SPEC-NNNN-<slug>.yaml`:

```yaml
id: SPEC-NNNN
category: <category>
title: "<title>"
status: draft
description: >
  <Full description of what this spec defines. 2-5 sentences.
  Explain the requirement, not the implementation.>

acceptance_criteria:
  - id: AC-001
    statement: >
      <A single testable statement. Must be falsifiable.
      Format: "Given <context>, when <action>, then <outcome>.">
    verification_method: <automated_test | manual_review | diagram_check | ci_check>
  - id: AC-002
    statement: >
      <Second criterion if needed.>
    verification_method: automated_test

linked_slice: <SLICE-NNNN or null>
linked_intake: <intake-packet-id or null>
linked_adr: <ADR-NNNN or null>

constraints:
  # Any hard constraints that bound how this spec can be satisfied
  # e.g. "Must not require a paid API key", "Must support Node 18+"
  - <constraint text>

out_of_scope:
  # Explicit list of things this spec does NOT cover
  - <out-of-scope item>

created: <ISO-8601 date>
updated: <ISO-8601 date>
author: <author identifier>
```

### Step 6: Set the Correct Status

| Status       | When to Use                                                        |
|--------------|--------------------------------------------------------------------|
| `draft`      | Spec is newly authored; not yet reviewed or linked to a slice      |
| `active`     | Spec is reviewed, linked to an active slice, and governs live work |
| `complete`   | All acceptance_criteria have been verified and evidence is in proof matrix |
| `deprecated` | Spec is no longer applicable; superseded by a newer spec           |

New specs are always authored with `status: draft`. Promotion to `active` requires a
linked slice and at least one acceptance criterion with a defined verification_method.

### Step 7: Write Acceptance Criteria Correctly

Each acceptance criterion must:
1. Use the Given/When/Then format OR a direct measurable statement.
2. Be verifiable by one of: automated test, manual review, diagram check, or CI check.
3. Not contain implementation details (describe the outcome, not the mechanism).

**Bad:** "The code should call the API correctly."
**Good:** "Given a valid user session, when the user requests data export, then a CSV
file is downloaded within 3 seconds."

Minimum: 1 acceptance criterion per spec.
Recommended: 2–5 criteria. More than 8 criteria usually means the spec should be split.

### Step 8: Link to Traceability

If `linked_slice_id` was provided, add a traceability row to
`atlas/19_truth_state/traceability.yaml`:

```yaml
- spec_id: SPEC-NNNN
  title: "<title>"
  category: <category>
  slice_id: <SLICE-NNNN or null>
  status: draft
  created: <ISO date>
```

### Step 9: Run Registry Sync

After writing the spec YAML, run SKILL_REGISTRY_SYNC_001 in `--write` mode to
update the relevant `specs.registry.yaml` file.

---

## Category-Specific Guidance

### functional specs
Focus on observable behavior. One spec per user story or feature behavior.
Use state machine notation in `description` if the feature has multiple states.

### non_functional specs
Include numeric targets. "Fast" is not a spec. "P95 response time < 200ms under 1000
concurrent users" is a spec.

### acceptance specs
Usually derived from functional specs. One acceptance spec can cover the test
acceptance gate for an entire slice. Link to the functional spec in `description`.

### agent specs
Document: which tools the agent can call, what it cannot do (safety constraints),
what persona it adopts, and how it escalates when uncertain.

### api specs
Include: HTTP method, path, request schema (JSON), response schema (JSON), error codes,
authentication mechanism, and rate limit. Reference an OpenAPI file if one exists.

### security specs
Must include a threat identifier (e.g. OWASP category) and the control that mitigates it.
Link to ADR if the security control involves an architectural decision.

### data specs
Include: field names, types, nullable status, retention period, and PII classification
(`public | internal | pii | sensitive`).

---

## Failure Modes and Mitigations

| Failure                              | Mitigation                                                                   |
|--------------------------------------|------------------------------------------------------------------------------|
| Duplicate spec ID                    | Re-derive: scan ALL category directories, find actual highest ID, increment. |
| Spec category not recognized         | STOP. Report valid categories. Do not create a file in an unknown directory. |
| No acceptance criteria               | Spec is invalid. Author at least one AC before writing the file.             |
| linked_slice_id does not exist       | Warn but do not block. Set `linked_slice: null` and log the broken reference.|
| Description is empty                 | Spec is invalid. The `description` field must contain at least 2 sentences.  |
| Acceptance criteria lacks verification_method | Set to `manual_review` as fallback; flag for review.              |
| Title exceeds 80 characters          | Truncate and move excess context to `description`.                           |

---

## Validation
See `08_verification/skill_tests/TEST_SKILL_SPEC_AUTHORING_001_001.yaml`.

The test asserts:
- Output YAML passes `schemas/spec/spec.schema.json` validation.
- `id` matches `SPEC-NNNN` pattern and is unique across all category directories.
- `acceptance_criteria` list is non-empty.
- Every acceptance criterion has a `verification_method` field set.
- `status` is one of: `draft`, `active`, `complete`, `deprecated`.
- File is written to the correct category directory.
- A traceability row exists for the spec when `linked_slice_id` is provided.
