# Playbook: SKILL_ARCHITECTURE_ATLAS_001 — Architecture Atlas Generation

## Skill ID
SKILL_ARCHITECTURE_ATLAS_001

## Version
1.0.0

## Purpose
Produce the 7 mandatory Layer 1 architecture diagrams for a target repository. This is
T1 Authoring step 2. The diagrams are written as Mermaid `.mmd` files under
`atlas/04_architecture/diagrams/source/architecture/<name>/` and must be
rendered via SKILL_DIAGRAM_RENDER_001 before the repo can advance past T1.

---

## Inputs

| Field       | Type   | Required | Description                                                       |
|-------------|--------|----------|-------------------------------------------------------------------|
| `target`    | path   | yes      | Absolute path to the repo being documented                        |
| `name`      | string | yes      | Short repo identifier used in file naming (e.g. `genesys`)        |
| `repo_type` | string | yes      | Detected type: `app` / `library` / `tool` / `compiler`            |

---

## Output Location

All 7 files are written to:
```
atlas/04_architecture/diagrams/source/architecture/<name>/
```

Each file is named `<name>_<diagram_type>.mmd`.

Every file must begin with this comment header:
```
%% diagram_type: <type>
%% repo: <name>
%% generated: <ISO-8601 date>
%% skill: SKILL_ARCHITECTURE_ATLAS_001 v1.0.0
```

---

## The 7 Mandatory Diagram Types

### 1. system_context
**Purpose:** Show the repo as a single node inside its broader ecosystem; reveal every
external actor, peer repo, and service it touches.

**Data to extract:**
- Repo list from `11_ecosystem/repo_ledger/` or `twin_registry.yaml`
- Entries in `11_ecosystem/cross_repo_relationship_table.yaml` where this repo appears
- External services referenced in env files, integration specs, or CLAUDE.md

**Mermaid type:** `graph LR`

**Minimum nodes:** 1 target + 2 external actors or peer repos

**Construction rules:**
- Every peer repo in the cross-repo relationship table that lists this repo as a
  participant MUST appear as an external node.
- Shape convention: `([Actor])` for humans/external services; `[Repo]` for repos;
  `[(DB)]` for databases.
- Edge label = relationship type (calls, imports, deploys-to, reads-from).

**Failure mode — no ecosystem ledger:**
Produce diagram with only the target node plus a placeholder `External([External Systems])`.
Add comment: `%% WARNING: no ecosystem ledger found — external nodes are placeholders`.

---

### 2. component_map
**Purpose:** Show the internal modules, packages, and layers of the repo with their
ownership boundaries and cross-module dependencies.

**Data to extract:**
- Top-level directory listing of `target/`
- Any `components:` section in `CLAUDE.md` or equivalent manifest
- Contract files in `schemas/contract/` referencing this repo

**Mermaid type:** `graph TD`

**Minimum nodes:** 3 internal component nodes

**Construction rules:**
- Group related components in `subgraph` blocks when count exceeds 6.
- Include a `tests/` node with edges to every component it exercises.
- Direction is top-down (TD) to reflect layer hierarchy.

---

### 3. data_flow
**Purpose:** Show how data moves through the system from its entry point through
transformation stages to its final output or storage.

**Data to extract:**
- Data specs under `03_specs/data_requirements/`
- Integration specs under `03_specs/integration_requirements/`
- API specs under `03_specs/api_requirements/`
- Pipeline or ETL references in CLAUDE.md

**Mermaid type:** `flowchart LR`

**Minimum nodes:** 3 stages (input → transform → output)

**Construction rules:**
- Label every edge with the data format or transport protocol when known
  (e.g. `JSON`, `CSV`, `gRPC`, `HTTP`).
- Shape convention: `([Source])` for external inputs; `[Process]` for transforms;
  `[(Store)]` for databases; `{Gate}` for validation decision points.

---

### 4. execution_sequence
**Purpose:** Show the runtime call sequence for the primary use-case of the repo so
reviewers can reason about ordering, async boundaries, and error paths.

**Data to extract:**
- Functional specs under `03_specs/functional_requirements/`
- ADRs that describe invocation patterns or architectural decisions
- README.md "Quick Start" or "Usage" sections in the target repo

**Mermaid type:** `sequenceDiagram`

**Minimum nodes:** 3 participants, 4 messages

**Construction rules:**
- Use `-->>` for return/response arrows; `->>` for calls.
- Annotate async steps with `Note over Actor: async`.
- Show at least one error path using `alt`/`else` if error handling exists.

---

### 5. dependency_impact
**Purpose:** Show all internal and cross-repo dependencies with impact direction.
Flag unwired (planned but not yet implemented) cross-repo edges with dashed lines.

**Data to extract:**
- Lock/manifest files: `package.json`, `Cargo.toml`, `requirements.txt`, `go.mod`
- `11_ecosystem/cross_repo_relationship_table.yaml`
- Entries with `status: planned` or `status: unwired` in that table

**Mermaid type:** `graph LR`

**Minimum nodes:** 4 (target + at least 3 deps)

**[UNWIRED] dashed-edge convention:**
Any cross-repo relationship with `status: planned` or `status: unwired` in the
relationship table is rendered as a dashed edge with the label `[UNWIRED]`:
```
RepoA -.->|[UNWIRED]| RepoB
```
Solid edges (`-->`) represent live, implemented dependencies only.

**Construction rules:**
- Annotate edges with the resolved version from the lock file where available.
- Use `subgraph Internal` / `subgraph External` to separate monorepo packages
  from third-party dependencies.

**Failure mode — no relationship table:**
Omit cross-repo edges entirely. Add comment:
`%% WARNING: no cross_repo_relationship_table found — [UNWIRED] edges omitted`.

---

### 6. test_coverage
**Purpose:** Map test files to the components they cover; expose uncovered components
as a visual gap in the proof matrix.

**Data to extract:**
- All `*.test.*`, `*_test.*`, `*_spec.*` files found recursively under `target/`
- Any coverage report files in `08_verification/` for this repo
- Component list derived from the component_map diagram (diagram 2 above)

**Mermaid type:** `graph TD`

**Minimum nodes:** 2 test nodes + 2 component nodes

**Construction rules:**
- Edge label: `covers`.
- Apply `:::uncovered` classDef (styled `fill:#fdd,stroke:#f00`) to every component
  node that has no incoming `covers` edge.

**Failure mode — no tests found:**
Do NOT skip this diagram. Produce the full component graph with every component node
marked `:::uncovered`. Add comment at top:
`%% WARNING: zero test files found — all components are uncovered`.

---

### 7. deployment_impact
**Purpose:** Show where the repo is deployed and which environments or downstream
services are affected when it changes.

**Data to extract:**
- CI/CD files: `.github/workflows/`, `Makefile` deploy targets, `vercel.json`,
  `netlify.toml`, `Dockerfile`, `docker-compose.yml`
- Preview plan referenced in `22_vertical_slices/` if it exists
- Env passport in `schemas/env_passport/` for this repo

**Mermaid type:** `graph TD`

**Minimum nodes:** 2 (repo + at least 1 deployment target)

**Construction rules:**
- Show each distinct deployment environment (preview, staging, production) as a
  separate node.
- Label edges with the trigger condition (e.g. `on PR`, `on merge to main`, `manual`).

**Failure mode — no CI pipeline detected:**
Still produce the diagram with a single edge:
`Repo -->|manual deploy| Unknown[???]`
Add comment: `%% WARNING: no CI pipeline detected — deployment target is unknown`.

---

## Step-by-Step Execution

### Step 1: Resolve Inputs
Confirm `target` path exists and is readable. If not, STOP and report the path.
Confirm `name` is a valid identifier (alphanumeric + hyphens, no spaces).

### Step 2: Gather Source Data
```
READ  <target>/                                            # directory listing
READ  atlas/11_ecosystem/repo_ledger/        # ecosystem repos
READ  atlas/11_ecosystem/cross_repo_relationship_table.yaml
READ  atlas/03_specs/data_requirements/
READ  atlas/03_specs/functional_requirements/
READ  atlas/03_specs/api_requirements/
READ  <target>/package.json  OR  Cargo.toml  OR  requirements.txt  OR  go.mod
READ  <target>/.github/workflows/
GLOB  <target>/**/*.test.*   <target>/**/*_test.*   <target>/**/*_spec.*
```

### Step 3: Build Node + Edge Lists
For each of the 7 diagram types:
1. Enumerate nodes from gathered data.
2. Verify minimum node count. If unmet, add placeholder nodes named `[Unknown-N]`
   and annotate with `%% PLACEHOLDER`.
3. Enumerate edges with labels.
4. Apply failure-mode fallbacks for any missing data source.

### Step 4: Write .mmd Files
Create output directory if it does not exist:
```
atlas/04_architecture/diagrams/source/architecture/<name>/
```

Write each file in order: system_context → component_map → data_flow →
execution_sequence → dependency_impact → test_coverage → deployment_impact.

### Step 5: Validate Syntax
For each `.mmd` file immediately after writing, invoke SKILL_DIAGRAM_RENDER_001
in `--check` mode. If syntax validation fails, fix the file before proceeding
to the next diagram.

### Step 6: Update diagram.registry.yaml
Add or update an entry for each `.mmd` file in:
```
atlas/04_architecture/diagrams/source/architecture/diagram.registry.yaml
```
Required fields per entry: `id`, `diagram_type`, `repo`, `path`, `status`, `generated`.

### Step 7: Log improvement_history
Append to `SKILL_ARCHITECTURE_ATLAS_001.yaml`:
```yaml
improvement_history:
  - version: 1.0.0
    date: <ISO date>
    reason: "Generated <name> atlas — 7 diagrams written."
```

---

## Failure Modes Summary

| Failure                          | Action                                                                       |
|----------------------------------|------------------------------------------------------------------------------|
| Source repo path unreadable      | STOP immediately. Report path. Do not produce a partial atlas.               |
| No tests found                   | Produce test_coverage with all nodes `:::uncovered`; add WARNING comment.    |
| No CI pipeline found             | Produce deployment_impact with `Unknown[???]`; add WARNING comment.          |
| No ecosystem ledger              | Produce system_context with placeholder External node; add WARNING comment.  |
| cross_repo table missing         | Omit [UNWIRED] edges; add WARNING comment in dependency_impact.              |
| Minimum node count not met       | Add `[Unknown-N]` placeholder nodes; annotate with `%% PLACEHOLDER`.         |
| mermaid-cli syntax validation fails | Fix syntax; do not commit broken .mmd files.                              |

---

## Validation
See `08_verification/skill_tests/TEST_SKILL_ARCHITECTURE_ATLAS_001_001.yaml`.

The test asserts:
- All 7 `.mmd` files exist under the correct output path for the given `<name>`.
- Each file contains the required 4-line header comment block.
- Each file passes `npx @mermaid-js/mermaid-cli` syntax check without error.
- `dependency_impact` contains at least one dashed edge if the relationship table
  has any `status: planned` entries for this repo.
- `test_coverage` marks at least one node `:::uncovered` when no test files exist.
