# SKILL_ATLAS_GRAPH_ENGINE_001 Playbook

## Purpose

Use this skill when building or reviewing the Atlas Graph Engine as a graph intelligence workbench. The output must be queryable, deterministic, provenance-backed, proof-aware, drift-aware, Ideation-aware, and capable of exporting coding-agent context.

## Required Pre-Gates

1. Data pipeline first: name static sources, semantic rules, mutable overlays, computed properties, and provenance pointers.
2. Provenance required: every node and edge must expose source path or URI, derivation, assertion, evidence, and confidence.
3. Determinism check: layout must use seed, stable node coordinates, saved layout metadata, and non-reshuffling placement.
4. Cache invalidation: centrality, proof rollup, freshness, and cluster membership must name invalidation events.
5. Component pressure: start with minimal production components and split only under pressure.

## Functional Requirements

- Global Constellation view.
- Local Context Lens.
- Layered Dependency view.
- Proof and Drift Heatmap.
- Agent Context Builder.
- Search and filters.
- Shortest path.
- Local graph extraction.
- Saved queries.
- Agent context export as JSON and markdown.

## Forbidden Actions

- Do not ship a basic unlabeled dot graph.
- Do not treat visual polish as the primary deliverable.
- Do not create graph nodes without provenance.
- Do not use external product names as internal subsystem names.
- Do not claim production graph completion before live ingestion, durable query persistence, and permission scoping exist.

## Validation

- `npm run typecheck`
- `npm run test`
- `npm run lint`
- `npm run build`
- Regression case `REG-034` routes graph intelligence language to this skill.
