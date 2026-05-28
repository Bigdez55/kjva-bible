# Skill Corpus Taxonomy — Controlled Vocabulary

**Version:** 1.0.0
**Status:** active
**Authority:** This document is the controlled vocabulary for skill metadata. `validate_taxonomy.py` enforces it.

---

## Purpose

The skill corpus had 197 unique values in `domains:` across 180 skills — fragmentation that prevented discovery and grouping. This document defines the canonical values for the four metadata fields where free-form strings cause drift:

- `domains:` (skill category, multiple allowed)
- `layer:` (architectural plane, single value)
- `tier:` (maturity level, single value)
- `status:` (lifecycle state, single value)
- `source:` (provenance, single value, new in v1.0.0)

Any value not in this document fails `validate_taxonomy.py` in strict mode. New values are added by editing this file and bumping its version.

---

## Domains (controlled — 36 canonical values)

A skill may list 1–6 domains. The first domain is its **primary**; the rest are secondary qualifiers. Order matters for discovery (the primary determines default categorization in `MASTER_INDEX.md`).

### Product domains

Which named product the skill applies to.

| Domain | Description |
|---|---|
| `atlas` | The Atlas knowledge graph and MCP platform (this repository) |
| `apex` | The Apex Protocol SDLC governance (process discipline, not a product) |
| `ipos` | IPOS paratransit operations dashboard (Transdev / VTA) |
| `genos` | GENESYS kernel + OS subsystem |
| `super_c` | SUPER C compiler / language / toolchain |
| `elson` | Elson trading bot platform |
| `trading_bot` | Generic trading / market / portfolio domain (broader than elson) |
| `kjva_bible` | KJVA Bible application |

### Capability domains

What kind of engineering work the skill performs.

| Domain | Description |
|---|---|
| `frontend` | Browser-side UI engineering (React, Vue, Svelte, Angular, vanilla JS) |
| `backend` | Server-side engineering (Node, Python, FastAPI, etc.) |
| `data_pipeline` | ETL, data ingestion, transformation, schema, medallion architecture |
| `dashboard` | Dashboard composition, KPI cards, status indicators, layout |
| `visualization` | Charts, graphs, geographic maps, data viz beyond stock chart libraries |
| `kpi_reporting` | Contract-bound KPI calculation, MTD aggregation, penalty/incentive |
| `ai` | LLM integration, Claude API, embeddings, NLQ, prompt engineering |
| `ai_insights` | AI-powered analytics, anomaly detection, health scoring, forecasting |
| `ml_ops` | ML model training, distillation, fine-tuning, inference pipelines |
| `security` | Auth, encryption, secrets, threat models, vuln assessment |
| `auth` | Authentication and authorization (subset of security; OAuth/SAML/JWT/RBAC) |
| `accessibility` | WCAG, ARIA, screen readers, keyboard nav, contrast |
| `performance` | Profiling, optimization, Core Web Vitals, bundle size, latency |
| `observability` | Telemetry, logging, tracing, metrics, alerts, SLOs |
| `testing` | Unit, integration, E2E, visual regression, contract, chaos |
| `validation` | Gates, schema validation, invariant checks, audit assertions |
| `ci_cd` | Build automation, GitHub Actions, deployment pipelines, releases |
| `documentation` | Docs authoring, ADR, README, technical writing, knowledge capture |
| `agent_orchestration` | Multi-agent coordination, dispatch, context packets, handoff |
| `governance` | Policy, decisions, ledgers, audit trails, rules of engagement |
| `compiler` | Compiler internals (parsing, lowering, codegen, optimization) |
| `kernel` | OS kernel, drivers, boot, low-level systems |
| `graph_engine` | Knowledge graph, ingestion, queries, relationships |
| `skills` | Meta-skills — skills that operate on the skill corpus itself |

### Architectural/cross-cutting domains

| Domain | Description |
|---|---|
| `multi_tenant_platform` | Multi-tenant architecture concerns |
| `saas` | SaaS-specific patterns (subscription, billing, isolation) |
| `microsoft_365` | M365/SharePoint/SPFx specific patterns |
| `cloud_ops` | Cloud infrastructure operations (AWS/Azure/GCP/Vercel/Netlify) |
| `storage` | Persistence, databases, files, object stores |
| `architecture` | System design, architectural decisions, API contracts |
| `release` | Versioning, release notes, rollback, deployment cadence |

### Provenance domains (auto-applied)

These are added automatically by the migration/promotion scripts. Skills should not be authored with these by hand.

| Domain | Description |
|---|---|
| `imported` | Skill was promoted from an external `.claude/.codex/.gemini` surface |
| `migrated_user` | Skill was migrated from `~/.claude/skills/` to canonical |

---

## Layers (controlled — 8 canonical values)

A skill has exactly one `layer:` value. Layer describes the architectural plane the skill operates on, distinct from its domain.

| Layer | Description |
|---|---|
| `core` | Foundational primitives (data models, base types, shared utilities) |
| `application` | Application-level features (user-facing functionality) |
| `integration` | Cross-system integration (APIs, MCP, external services) |
| `governance` | Process/policy enforcement (validators, gates, audit) |
| `verification` | Testing, validation, proof artifacts |
| `documentation` | Docs, specs, ADRs, knowledge capture |
| `meta` | Skills that operate on the skill corpus itself |
| `active` | (Legacy; transitional) — present in many existing skills; deprecated, do not use in new skills |

**Migration note:** the existing 133 skills with `layer: active` are using `active` as a status-like marker. These will be remapped to one of the seven proper layer values during Phase 2 (in-corpus drift fix). After Phase 2, `layer: active` is forbidden.

---

## Tiers (controlled — 6 canonical values)

A skill has exactly one `tier:` value. Tier describes maturity and is the primary input to the auto-promotion engine (Phase 8). Higher tier = more battle-tested.

| Tier | Description |
|---|---|
| `experimental` | Just created, unproven, expect frequent changes |
| `starter` | Initial production-eligible, ≤30% correction rate, low invocation count |
| `active` | Proven in production, ≤10% correction rate, ≥50 invocations |
| `refining` | Transitional state during a major content rewrite |
| `hardened` | Mature, ≤2% correction rate, ≥200 invocations, validation_tests + improvement_history present |
| `apex` | Near-perfection, ≤0.1% correction rate, ≥1000 invocations, full ledger + regression_cases, cross-runtime usage proven |
| `one-shot-apex` | Special: skills whose correctness is provable in a single invocation (e.g., compiler bootstrap-critical encoders) |

See [LIFECYCLE.md](LIFECYCLE.md) for the auto-promotion criteria and `auto_promote_tier.py` implementation.

---

## Statuses (controlled — 4 canonical values)

A skill has exactly one `status:` value. Status describes lifecycle state and determines which directory the skill lives in.

| Status | Directory | Description |
|---|---|---|
| `experimental` | `experimental/` | In active development, may be unstable |
| `active` | `active/` | Production-ready, invokable, tracked |
| `deprecated` | `deprecated/` | Retired; preserved for audit only; not invoked |
| `superseded` | `superseded/` | Replaced by a newer skill; preserved with pointer to successor |

A skill in `candidate/` has `status: experimental` and `tier: experimental`.
A skill being held in `skill_refinery/` is not yet a real skill — it has no `status` because it has no canonical file yet.

---

## Source (controlled — 3 canonical values, new in v1.0.0)

A skill has exactly one `source:` value. Source describes provenance for traceability. Auto-populated by migration/promotion scripts.

| Source | skill_number range | Description |
|---|---|---|
| `native` | 1–499 | Born in this corpus, authored directly as canonical |
| `migrated_user` | 500–999 | Migrated from `~/.claude/skills/<kebab>/SKILL.md` to canonical (Phase 3) |
| `promoted_external` | 1000–1999 | Promoted from a `.claude/.codex/.gemini` surface of another repo via the import pipeline (Phase 4) |

`skill_number: 2000+` is reserved for future expansion.

---

## Runtime Projection Targets (controlled — 3 canonical values)

A skill's `runtime_projection_targets:` field is an array of zero-or-more values. Default = all three. Empty array OR `runtime_projection: false` means no shims are generated.

| Target | Generated artifact |
|---|---|
| `claude` | `~/.claude/skills/<kebab>/SKILL.md` |
| `codex` | `~/.codex/skills/<kebab>/SKILL.md` + `~/.codex/commands/<kebab>.md` |
| `gemini` | `~/.gemini/commands/<kebab>.md` |

---

## Adding a new value

1. Edit this file, add the value with a description in the appropriate table
2. Bump the `Version:` header (semver: major if any value is removed/renamed; minor if values are added; patch for clarifications)
3. Run `python3 infrastructure/scripts/skill_validators/validate_taxonomy.py --check-self` to confirm the new vocab still parses
4. Commit with message format: `feat(taxonomy): add domain <value> — <reason>`
5. Update `skills.registry.yaml` header `taxonomy_version:` to match

---

## Validator behavior

`validate_taxonomy.py` checks every active SKILL_*.yaml file:

- Every `domains:` value MUST be in the Domains tables above
- `layer:` MUST be in the Layers table
- `tier:` (if present) MUST be in the Tiers table
- `status:` MUST be in the Statuses table
- `source:` (if present) MUST be in the Source table
- `runtime_projection_targets:` (if present) each value MUST be in the Runtime Projection Targets table
- First-day mode: warnings only — strict mode enabled after Phase 2 completes drift fixes

---

## Change Log

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-05-26 | Initial controlled vocabulary established from 197-value scan |
