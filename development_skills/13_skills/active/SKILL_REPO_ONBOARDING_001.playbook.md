# Playbook: Repo Onboarding

## Skill ID
SKILL_REPO_ONBOARDING_001

## Purpose
Tiered onboarding sequence for any repo adopting Development_Skills. The four tiers run sequentially the first time a repo onboards (T1 → T2 → T3 once per feature → T4 periodically) and individually thereafter.

## Inputs
- `tier` — `1`, `2`, `3`, or `4`. Required.
- `target` — absolute path to the child repo on disk. Required.
- `intent_brief` — string. **Required for Tier 2 only.** A 1–3 sentence statement of what the repo is for and the next outcome it must achieve. Must come from the caller; the skill does not invent it.

## Preconditions
- `target` is a git repository (or local-only with `.git/` initialized) on a clean branch.
- `target/development_skills/` exists and was synced from upstream Development_Skills (run `infrastructure/scripts/sync_scripts/sync_to_child_repo.py --target <target>` first if missing).
- Central Development_Skills working tree is clean and `python3 infrastructure/scripts/registry_sync/sync_registries.py --check` is green.
- After sync, verify `target/.claude/universal/` exists and `target/.claude/commands/` has ≥1 `apex:*.md` file. If either is missing, the sync script has a path bug — do not proceed; fix the script first.
- `target/CLAUDE.md` exists and references `@AGENTS.md`. Create it if missing.
- `target/.claude/settings.json` exists with repo-scoped permissions. Create from template if missing.

## Tiers

### TIER 1 — Capture reality (no human input required)

Goal: produce a faithful, mechanically-derived snapshot of what the repo *is* today. **Never ask the user what the repo does or what is being built. Discover it by looking.**

#### Discovery protocol (run before writing any file)

Execute every step that applies; record findings in memory for use in all subsequent steps:

1. **Git history** — `git log --oneline --all` (first 200 commits), `git branch -a`, `git remote -v`. Derive: primary language/framework guesses from commit messages, branch naming conventions, active authors, project age, current active branch.
2. **Language artifacts** — read whichever exist: `package.json`, `Cargo.toml`, `pyproject.toml`, `requirements.txt`, `go.mod`, `pom.xml`, `build.gradle`, `Gemfile`, `composer.json`. Extract: language, runtime version, declared dependencies, scripts/targets, main entry points.
3. **Directory tree** — `find . -maxdepth 3 -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/__pycache__/*'`. Derive: top-level component topology, test layout, deployment artifacts, documentation.
4. **Existing documentation** — read (if present): `README.md`, `ARCHITECTURE.md`, any `docs/` files, existing `development_skills/04_architecture/adrs/ADR-*.md`, existing `development_skills/19_truth_state/current.truth.yaml`. Extract any stated purpose, tech decisions, or system descriptions. **These are inputs, not substitutes for discovery — verify stated facts against code before accepting them.**
5. **Source structure** — inspect `src/`, `lib/`, `app/`, or equivalent: identify primary modules/services, their imports/exports, database drivers, external HTTP calls, auth patterns, UI framework (if any).
6. **Deployment signals** — read whichever exist: `Dockerfile`, `docker-compose.yml`, `.github/workflows/*.yml`, `vercel.json`, `netlify.toml`, `fly.toml`, `render.yaml`. Derive: target environment, CI steps, preview/production URLs.
7. **Test surface** — count and categorize tests under `test/`, `tests/`, `spec/`, `__tests__/`, or inline. Derive: test framework, coverage breadth, presence of integration/e2e tests.
8. **Cross-repo ecosystem map** — read from central Development_Skills (path via `development_skills/` symlink or known upstream path):
   - `18_registry/repo_ledger.yaml` — all known repos in the ecosystem, their type, and remote URLs.
   - `39_repo_twins/twins/` — for each twin that shares a dependency or technology with this repo, read `architecture.snapshot.yaml` and `dependency.graph.yaml`.
   - `04_architecture/adrs/ADR-*.md` — scan all ADRs for cross-repo references (repo names, shared APIs, shared data contracts, shared auth).
   - Any `development_skills/04_architecture/adrs/` ADRs already in **this** repo — extract cross-repo decisions already documented.
   - Produce a **cross-repo relationship table**: for each other known repo, classify the relationship as one of: `produces_for` (this repo outputs something the other consumes), `consumes_from` (the reverse), `shares_contract` (shared API/schema), `independent` (no known link), or `gap` (ADR or code references the other but no wired dependency exists). **`gap` is the most valuable finding** — these become explicit nodes in the dependency impact diagram labeled `[UNWIRED]`.

After completing all 8 steps, summarize findings into an internal "reality model" before writing any output artifact. The reality model answers: *what does this repo do, what is it made of, how is it deployed, what is working, what is missing, and how does it connect to (or fail to connect to) the broader ecosystem.*

#### Authoring steps

1. Author `development_skills/19_truth_state/current.truth.yaml` using the upstream template but with identity fields (`truth_id`, `repo`, `summary`, `primary_language`, `framework`, `deployment_target`, `component_count`, `test_count`, `last_verified`) derived entirely from the discovery protocol above. Set `last_verified` to today's date. Do not overwrite this file on subsequent re-syncs (the upstream sync script excludes it via `PER_ITEM_EXCLUDES`).
2. Read [04_architecture/diagrams/DIAGRAM_TAXONOMY.md](../../04_architecture/diagrams/DIAGRAM_TAXONOMY.md) and detect the repo type(s) from the discovery protocol (web_app, api_service, operating_system, compiler, database, dashboard, agent_system, etc.). Produce **all mandatory diagrams for the detected type(s)** — not just seven. Place each under `development_skills/04_architecture/diagrams/source/<layer>/`. Mark all optional diagrams `status: missing` in the diagram registry so they are visible and generatable on-demand.

   **Minimum mandatory for every repo (Layer 1 — Architecture):**
   - `architecture/system_context_<name>.mmd` — system boundary, external actors, integrations; **include all ecosystem repos from the cross-repo table (step 8) as external nodes labeled by relationship type; gaps labeled `[UNWIRED]`**
   - `architecture/component_map_<name>.mmd` — top-level modules and dependencies from imports + dir structure
   - `architecture/data_flow_<name>.mmd` — data sources, transforms, sinks; include cross-repo data flows found in step 8
   - `architecture/execution_sequence_<name>.mmd` — primary request/job path start to finish
   - `architecture/dependency_impact_<name>.mmd` — **full dep graph**: internal + external repos + gaps as dashed `[UNWIRED]` edges; primary gap-visibility surface
   - `architecture/test_coverage_<name>.mmd` — components with tests vs. untested (from step 7)
   - `architecture/deployment_impact_<name>.mmd` — CI trigger to production/preview chain including cross-repo infra deps

   **Additional mandatory by detected repo type (from taxonomy):**
   - UI repos (web_app, mobile_app, desktop_app, dashboard): also produce `feature/feature_map_<name>.mmd`, `feature/ui_navigation_<name>.mmd`, `feature/ui_state_<name>.mmd`, `feature/user_journey_<name>.mmd`, `ecosystem/ecosystem_map_<name>.mmd`. For each page/screen: `feature/page_feature_map_<page>.mmd`.
   - Operating system repos: also produce all 11 Layer 8 diagrams (`kernel/kernel_subsystem_<name>.mmd`, `kernel/syscall_map_<name>.mmd`, `kernel/memory_layout_<name>.mmd`, `kernel/process_model_<name>.mmd`, `kernel/ipc_map_<name>.mmd`, `kernel/driver_stack_<name>.mmd`, `kernel/boot_sequence_<name>.mmd`, `kernel/interrupt_map_<name>.mmd`, `kernel/filesystem_layout_<name>.mmd`, `kernel/capability_model_<name>.mmd`, `infrastructure/network_topology_<name>.mmd`).
   - Compiler repos: also produce all 7 Layer 9 diagrams (`compiler/compiler_pipeline_<name>.mmd`, `compiler/ir_graph_<name>.mmd`, `compiler/codegen_targets_<name>.mmd`, `compiler/runtime_model_<name>.mmd`, `compiler/type_system_<name>.mmd`, `compiler/ownership_model_<name>.mmd`, `compiler/stdlib_map_<name>.mmd`).
   - Database repos: also produce all 6 Layer 10 diagrams (`database/storage_model_<name>.mmd`, `database/replication_model_<name>.mmd`, `database/cache_model_<name>.mmd`, `database/query_plan_<name>.mmd`, `database/wal_flow_<name>.mmd`, `api/schema_map_<name>.mmd`).
   - Any repo with auth/network/sensitive data: also produce `security/security_model_<name>.mmd`, `security/threat_model_<name>.mmd`, `security/trust_boundary_<name>.mmd`, `security/auth_flow_<name>.mmd`.
   - Agent system repos: also produce `agent/agent_workflow_<name>.mmd`, `agent/agent_topology_<name>.mmd`, `agent/skill_graph_<name>.mmd`, `agent/knowledge_mesh_<name>.mmd`.
   - All repos (Layer 11 — Ecosystem): also produce `ecosystem/cross_repo_dependency_<name>.mmd` and `ecosystem/ecosystem_map_<name>.mmd`.

   **Stubs are acceptable; blanks are not.** Every mandatory diagram must exist on disk with at minimum a `[DISCOVERY PENDING]` placeholder node. Real content from the discovery protocol must replace placeholders within the same T1 run wherever the data exists.
3. Run `python3 development_skills/25_automation/registry_sync/sync_registries.py --write` inside the target.
4. Run every script under `development_skills/25_automation/drift_checkers/` and write findings into `development_skills/23_evidence/evidence_packets/EP-<date>-onboarding-tier1.yaml`.
5. Populate the repo's twin in central Development_Skills under [39_repo_twins/twins/<NAME>/](../../39_repo_twins/twins/). Replace placeholder `[]` content in `architecture.snapshot.yaml`, `component.graph.yaml`, `dependency.graph.yaml`, and `diagram.registry.yaml` with values derived from the discovery protocol and steps 1–2. Update `last_known_state.md` with a one-paragraph factual summary (no speculation). Flip `sync_status.yaml` from `pending_ingestion` to `synced`. **Do this on a separate branch in central Development_Skills, not on `main`.**
6. Commit and push the target-repo branch (typically `claude/onboarding-tier1`).

Outputs: target's `current.truth.yaml` (derived from code, not from user), 7 diagrams (reflecting discovered architecture), populated registries, drift evidence packet, populated twin in upstream, pushed target branch.

### TIER 2 — Capture intent (requires `intent_brief`)

Goal: turn raw direction into structured artifacts that downstream tiers can execute against.

Steps:
1. Open `development_skills/00_intake/intake_packets/IDEA-NNNN-<name>.yaml`. The placeholder version (auto-generated during the build-out) has a generic `raw_idea` — replace it with content derived from the caller's `intent_brief`. Update `value_statement`, `assumptions`, `open_questions`, and `date`.
2. Run [/apex:intake](../../37_command_protocol/slash_commands/apex_intake.md) to validate and register the intake packet.
3. Run [/apex:starter](../../37_command_protocol/slash_commands/apex_starter.md) to compile a starter packet under `development_skills/30_repo_starter/starter_packets/STARTER-<NAME>.yaml`.
4. Run [/apex:slice](../../37_command_protocol/slash_commands/apex_slice.md) to plan the first vertical slice under `development_skills/22_vertical_slices/SLICE-0001-<topic>.yaml`. **The slice MUST include a preview deployment requirement** (target, build steps, rollback path).
5. Run [/apex:spec](../../37_command_protocol/slash_commands/apex_spec.md) for every spec category required by the slice (typically functional, non-functional, acceptance, security at minimum).
6. Author 1–3 baseline ADRs under `development_skills/04_architecture/adrs/ADR-NNNN-*.md` capturing existing-but-undocumented decisions visible in the code (e.g. language choice, framework, runtime, deployment target). Use [04_architecture/adrs/ADR_TEMPLATE.md](../../04_architecture/adrs/ADR_TEMPLATE.md). Add rows to [18_registry/decision_ledger.yaml](../../18_registry/decision_ledger.yaml).
7. Run `sync_registries.py --write` and capture an evidence packet at `EP-<date>-onboarding-tier2.yaml` linking the slice, specs, ADRs, and starter packet.

Outputs: real intake packet (replacing placeholder), starter packet, SLICE-0001 with preview deploy, baseline specs, 1–3 ADRs, registry updates, Tier-2 evidence packet.

Failure mode: if `intent_brief` was not supplied, halt and surface the requirement to the caller. Do not invent intent.

### TIER 3 — Slice loop (every feature)

Goal: deliver a feature with full proof and traceability. This loop runs *per feature*, not per session.

Steps:
1. [/apex:slice](../../37_command_protocol/slash_commands/apex_slice.md) — plan the slice with proof and deployment requirements.
2. [/apex:diagram](../../37_command_protocol/slash_commands/apex_diagram.md) — update or add the seven mandated maps that the slice touches.
3. Implement the change in the target repo (code + tests).
4. [/apex:verify](../../37_command_protocol/slash_commands/apex_verify.md) — run all gates (registry sync, schema, drift, traceability, tests).
5. [/apex:deploy_preview](../../37_command_protocol/slash_commands/apex_deploy_preview.md) — execute the preview deployment plan from the slice.
6. Author an evidence packet under `23_evidence/evidence_packets/` linking the slice, ADR(s), diagrams, tests, preview URL, and rollback path.
7. [/apex:detect_drift](../../37_command_protocol/slash_commands/apex_detect_drift.md) — run all drift checkers; resolve any findings before merge.
8. [/apex:sync_docs](../../37_command_protocol/slash_commands/apex_sync_docs.md) — regenerate docs from updated truth.
9. If a mistake was made during the slice (failed verify, repeated drift, broken deploy, etc.): [/apex:improve_skill](../../37_command_protocol/slash_commands/apex_improve_skill.md) — file an improvement proposal under `13_skills/skill_refinery/improvement_proposals/`.
10. Append rows to [18_registry/change_ledger.yaml](../../18_registry/change_ledger.yaml) and [18_registry/traceability.yaml](../../18_registry/traceability.yaml).

Outputs: slice yaml, diagrams, verify report, preview URL, evidence packet, drift report, regenerated docs, optional skill improvement proposal, change ledger row, traceability row.

### TIER 4 — Ongoing hygiene (periodic)

Goal: keep the system honest between feature work.

Cadence: at the start of every working session in the repo, plus an explicit weekly pass.

Steps:
1. Run [/apex:detect_drift](../../37_command_protocol/slash_commands/apex_detect_drift.md) before any new work in the session.
2. Capture any mistakes (whether surfaced by drift or by manual review) into `development_skills/13_skills/skill_refinery/mistake_ledgers/<YYYY-MM>.md` with date, context, root cause, and remediation.
3. If a mistake recurs (same root cause appears twice), promote it via [/apex:improve_skill](../../37_command_protocol/slash_commands/apex_improve_skill.md): create or update a skill in [13_skills/active/](../../13_skills/active/), add a validation test in [08_verification/skill_tests/](../../08_verification/skill_tests/), and bump `improvement_history` in the skill yaml.
4. Sync improved skills back to **central Development_Skills** by running the upstream sync script in reverse (or by manually copying the new/changed skill yaml + playbook to `Development_Skills/13_skills/active/`, committing on a branch, and opening a PR upstream).
5. If the repo has changed materially since last twin ingest (architecture, dependencies, deployment target, or component count differ): re-run Tier 1 step 5 to refresh the twin in central Development_Skills.
6. If `current.truth.yaml` `last_verified` is older than 30 days: re-run Tier 1 steps 1, 3, and 4 to refresh the truth snapshot.

Outputs: drift report (per session), mistake ledger entries, promoted skills, refreshed twin (when warranted), refreshed truth state (when warranted).

## Failure modes

| Failure | Detection | Remediation |
|---|---|---|
| Tier 2 invoked without `intent_brief` | input validation | Halt and surface to caller; do not fabricate intent. |
| Target is not a git repo | precondition check at start of any tier | Run `git init` (and remote setup if applicable) before retrying. |
| Working tree on target is dirty | `git status --porcelain` before branch creation | Commit or stash before onboarding to avoid mixing user work with onboarding output. |
| Twin (T1) skipped | `39_repo_twins/twins/<NAME>/sync_status.yaml` still says `pending_ingestion` | Re-run T1 step 5; verify status flipped to `synced`. |
| `current.truth.yaml` overwritten by re-sync | sync should exclude it via `PER_ITEM_EXCLUDES` in [25_automation/sync_scripts/sync_to_child_repo.py](../../25_automation/sync_scripts/sync_to_child_repo.py) | Confirm exclusion; if regression, restore from git history and refresh per ADR-0011. |
| Mistake repeats without skill update (T4) | mistake ledger shows same root cause ≥ 2 times | Promote via `/apex:improve_skill`; add validation test. |

## Validation
See [08_verification/skill_tests/TEST_SKILL_REPO_ONBOARDING_001_001.yaml](../../08_verification/skill_tests/TEST_SKILL_REPO_ONBOARDING_001_001.yaml).

## See also
- [/apex:onboard](../../37_command_protocol/slash_commands/apex_onboard.md) — invokes this playbook.
- [APEX_PROTOCOL.md](../../APEX_PROTOCOL.md) — overall doctrine.
- [21_repo_sync/repo_sync.protocol.md](../../21_repo_sync/repo_sync.protocol.md) — how `development_skills/` reaches the target in the first place.
- [ADR-0011](../../04_architecture/adrs/ADR-0011-repo-sync-delete-and-identity-exclude.md) — identity-file exclusion that protects per-tier `current.truth.yaml`.
