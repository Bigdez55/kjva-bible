# Playbook: SKILL_CONTEXT_COMPILATION_002
# Deep Context Compilation with Cross-Repo Mesh

## Skill ID
SKILL_CONTEXT_COMPILATION_002

## Purpose
Upgrade of SKILL_CONTEXT_PACKET_001. Compiles a full agent context packet enriched
with cross-repo dependency edges from repo twins and knowledge mesh nodes from
Bookworm indexes. Applies token budget management when combined context exceeds 50K
tokens. Use this skill when working across multiple repos or when Bookworm knowledge
enrichment is needed.

---

## Inputs

| Parameter        | Type    | Required | Default | Description                                             |
|------------------|---------|----------|---------|---------------------------------------------------------|
| persona          | enum    | yes      | —       | Same persona enum as SKILL_CONTEXT_PACKET_001           |
| target           | path    | yes      | —       | Absolute path to the repo root                          |
| include_twins    | boolean | no       | true    | Whether to include cross-repo twin data                 |
| include_bookworm | boolean | no       | true    | Whether to enrich with Bookworm knowledge mesh data     |

---

## Steps

### Step 1 — Execute all steps from SKILL_CONTEXT_PACKET_001

Run the full base compilation first:

```bash
# Steps 1-7 of SKILL_CONTEXT_PACKET_001 execute here
# Produces: base context_packet.yaml at 42_context_compiler/output/generated/
```

This includes:
- Persona validation
- Schema load
- Truth state verification
- Slice selection and compilation
- Schema validation of base packet

The base packet is held in memory as `base_packet` — not yet written to the final
output path. The enrichment steps below augment it before final write.

### Step 2 — Load repo twins (if include_twins: true)

```bash
TWINS_DIR="<target>/39_repo_twins/twins"

if [ ! -d "$TWINS_DIR" ]; then
  echo "WARNING: No twins directory found at $TWINS_DIR"
  echo "Continuing without cross-repo mesh data."
  include_twins=false
fi
```

For each subdirectory in `39_repo_twins/twins/`:

```python
twin_dirs = [d for d in os.listdir(TWINS_DIR) if os.path.isdir(os.path.join(TWINS_DIR, d))]

for twin_name in twin_dirs:
    sync_status_file = f"{TWINS_DIR}/{twin_name}/sync_status.yaml"
    dependency_graph_file = f"{TWINS_DIR}/{twin_name}/dependency.graph.yaml"
    arch_snapshot_file = f"{TWINS_DIR}/{twin_name}/architecture.snapshot.yaml"
```

Read `sync_status.yaml` for each twin and extract:
- `status` (synced | pending_ingestion | stale)
- `last_synced` (ISO 8601 date)
- `component_count` (integer)
- `repo_url` (string)

### Step 3 — Extract cross-repo dependency edges

For each twin with `status: synced`, read its `dependency.graph.yaml` and extract
edges that reference the target repo:

```yaml
# Example edge structure in dependency.graph.yaml
edges:
  - from: <twin_repo>
    to: <target_repo>
    type: depends_on | imports | extends | deploys_with
    component: <component_name>
    direction: inbound | outbound
```

Build a `cross_repo_mesh` section for the packet:

```yaml
cross_repo_mesh:
  - twin_name: <name>
    repo_url: <url>
    sync_status: synced | pending_ingestion | stale
    last_synced: <date>
    component_count: <int>
    staleness_warning: <true|false>
    dependency_edges:
      - from: <repo>
        to: <repo>
        type: <edge_type>
        component: <component>
```

If a twin has `status: pending_ingestion` or `status: stale`, include it with
`staleness_warning: true`. Do not omit it — the agent must know the relationship
exists even if data is outdated.

### Step 4 — Read Bookworm indexes (if include_bookworm: true)

```bash
BOOKWORM_DIR="<target>/38_bookworm_engine/indexing"

if [ ! -d "$BOOKWORM_DIR" ]; then
  echo "WARNING: Bookworm indexing directory not found."
  echo "Run Bookworm ingestion first to enable knowledge mesh enrichment."
  include_bookworm=false
fi
```

Read the following index files if present:
- `38_bookworm_engine/indexing/file_index.yaml` — list of all indexed files
- `38_bookworm_engine/indexing/component_index.yaml` — component-level knowledge
- `38_bookworm_engine/indexing/knowledge_graph.yaml` — knowledge node graph

Check index freshness:

```python
from datetime import date, datetime

index_meta_file = f"{BOOKWORM_DIR}/index_metadata.yaml"
with open(index_meta_file) as f:
    meta = yaml.safe_load(f)

index_age_days = (date.today() - datetime.fromisoformat(meta["last_indexed"]).date()).days
if index_age_days > 7:
    print(f"WARNING: Bookworm index is {index_age_days} days old. Consider re-running ingestion.")
```

### Step 5 — Select relevant knowledge nodes

From the Bookworm knowledge graph, filter nodes relevant to the current persona and
task. Use the persona's domain to select node categories:

```yaml
# Knowledge node category map per persona
node_categories:
  apex_coding_agent:    [patterns, algorithms, component_implementations, best_practices]
  qa_agent:             [test_patterns, coverage_gaps, known_bugs, verification_approaches]
  deployment_agent:     [deployment_recipes, ci_patterns, rollback_procedures, env_configs]
  architecture_agent:   [architectural_decisions, design_patterns, ecosystem_topology]
  drift_agent:          [drift_indicators, registry_anomalies, staleness_patterns]
```

Limit to top 20 most relevant nodes by relevance score to control token budget.

### Step 6 — Build knowledge_nodes section

```yaml
knowledge_nodes:
  index_age_days: <int>
  stale_warning: <true|false>
  node_count: <int>
  nodes:
    - node_id: <id>
      category: <category>
      title: <title>
      summary: <1-2 sentence summary>
      source_file: <relative path>
      relevance_score: <0.0-1.0>
```

### Step 7 — Apply token budget management

Estimate token count of the combined packet:

```python
import json

packet_text = json.dumps(combined_packet)
estimated_tokens = len(packet_text) // 4  # rough estimate: 4 chars per token

TOKEN_BUDGET = 50_000

if estimated_tokens > TOKEN_BUDGET:
    print(f"WARNING: Combined context is ~{estimated_tokens} tokens, exceeds budget of {TOKEN_BUDGET}.")
    print("Applying priority ranking from 19_truth_state/source_of_truth_ranking.yaml")
```

Load `19_truth_state/source_of_truth_ranking.yaml` and trim lower-priority slices
until estimated token count falls below 50K. Priority order (highest to lowest):
1. truth_state
2. active_slice / open_specs
3. component_map / registries
4. architecture diagrams
5. knowledge_nodes (trim by reducing node_count)
6. cross_repo_mesh (trim to highest-dependency twins only)

Record which slices were trimmed in the packet metadata under `trimmed_slices`.

### Step 8 — Assemble and write enriched packet

Merge base packet with enrichment sections:

```yaml
# Final enriched packet structure
context_packet_id: CP-<persona>-<YYYYMMDD>-enriched
generated_at: <ISO8601>
skill_id: SKILL_CONTEXT_COMPILATION_002
persona: <persona>
target_repo: <target>
include_twins: <bool>
include_bookworm: <bool>
estimated_tokens: <int>
token_budget: 50000
budget_exceeded: <bool>
trimmed_slices: []
slices:
  # ... base slices from SKILL_CONTEXT_PACKET_001
cross_repo_mesh:
  # ... Step 3 output
knowledge_nodes:
  # ... Step 6 output
```

Write to `42_context_compiler/output/generated/context_packet_enriched.yaml`.

### Step 9 — Validate and emit summary

```python
jsonschema.validate(enriched_packet, schema)
print("Schema validation: PASSED")
```

Console summary:

```
Enriched context packet compiled for persona: <persona>
Output: 42_context_compiler/output/generated/context_packet_enriched.yaml
Base slices: <count>
Cross-repo twins included: <count>
Knowledge nodes included: <count>
Estimated tokens: <int>
Token budget applied: <true|false>
Trimmed slices: <list or 'none'>
Schema validation: PASSED
```

---

## Output

- **File**: `42_context_compiler/output/generated/context_packet_enriched.yaml`
- Contains all base slices from SKILL_CONTEXT_PACKET_001 plus `cross_repo_mesh`
  and `knowledge_nodes` sections.

---

## When to Use This vs SKILL_CONTEXT_PACKET_001

| Condition                                       | Skill to Use                    |
|-------------------------------------------------|---------------------------------|
| Single-repo focused task                        | SKILL_CONTEXT_PACKET_001        |
| Task spans multiple repos                       | SKILL_CONTEXT_COMPILATION_002   |
| Bookworm knowledge enrichment needed            | SKILL_CONTEXT_COMPILATION_002   |
| Token budget is very tight                      | SKILL_CONTEXT_PACKET_001        |
| Working with drift_agent across all registries  | SKILL_CONTEXT_COMPILATION_002   |

---

## Failure Modes

| Failure                           | Cause                              | Resolution                                        |
|-----------------------------------|------------------------------------|---------------------------------------------------|
| Bookworm index stale              | Ingestion not run recently         | Run 38_bookworm_engine/ingestion/run_ingestion.py |
| Token budget exceeded after trim  | Too many twins + large knowledge   | Reduce include_twins or include_bookworm to false |
| Twin not synced                   | pending_ingestion status           | Use last known state; staleness_warning is set    |
| Base compilation fails            | See SKILL_CONTEXT_PACKET_001 modes | Resolve base failure first                        |
| Schema validation fails           | Enrichment added invalid structure | Check cross_repo_mesh and knowledge_nodes shapes  |

---

## Related Skills

- `SKILL_CONTEXT_PACKET_001` — base skill; this skill extends it
- `SKILL_REPO_TWIN_INGEST_001` — use to sync twins before this skill
- `SKILL_TRUTH_STATE_CHECK_001` — verify truth before any compilation

---

## Validation

`TEST_SKILL_CONTEXT_COMPILATION_002_001` verifies:
1. Output contains `cross_repo_mesh` section when twins are present
2. Output contains `knowledge_nodes` section when Bookworm index exists
3. Token budget trimming removes lowest-priority slices first
4. Stale twins appear with `staleness_warning: true` rather than being omitted

See [08_verification/skill_tests/TEST_SKILL_CONTEXT_COMPILATION_002_001.yaml](../../08_verification/skill_tests/TEST_SKILL_CONTEXT_COMPILATION_002_001.yaml).
