# SKILL_MERGEABLE_CONTEXT_ENGINE_001 Playbook

## Purpose

Use this skill when context from multiple systems (Bookworm, Atlas, skill graphs, repo state) must be merged into a single prioritized payload for an agent or retrieval operation. The engine ranks sources, resolves conflicts, and produces a unified output with a full conflict log.

## The One Rule

**Never merge context without source ranking applied first.** A merge that does not know the tier of each source is a guess, not a decision.

## Source Hierarchy

```
PRIMARY   (weight 1.0) — canonical files, git-tracked, live ingestion outputs
SECONDARY (weight 0.6) — derived artifacts, synthesis outputs, atlas exports
TERTIARY  (weight 0.2) — cached summaries, stale exports, session memory
```

Higher tier always wins on the same key. No exceptions. Staleness does not change tier.

## Pre-Gates

1. **Source inventory** — enumerate every context source with its tier and `last_updated` date.
2. **Staleness check** — flag any source where `today - last_updated > 7 days`. Stale sources enter the merge at their tier but are flagged in output.
3. **Structural key check** — verify `id`, `version`, and `schema` are identical across all sources before proceeding. Mismatch on structural keys = block merge.

## Merge Steps

1. Rank all sources using `46_mergeable_context_engine/source_ranking/source_ranking_rules.yaml`.
2. For each key in the merged payload, select the value from the highest-ranked source.
3. Log every conflict using the schema in `46_mergeable_context_engine/conflict_resolution/conflict_resolution.schema.yaml`.
4. For `list_union` keys (`related_skills`, `domains`, `trigger_conditions`): take the union of all source values, deduplicated.
5. Emit the merged payload and the conflict log together.

## Context Packet Format

Use `46_mergeable_context_engine/bookworm_context_packets/context_packet.template.yaml` for any Bookworm-sourced packet entering the merge. Fill `source_ids`, `tier`, `generated_at`, and `is_stale` before merging.

## Graph Types

| Graph type | Schema | When to use |
|---|---|---|
| Model context graph | `model_context_graphs/model_context_graph.schema.yaml` | Model lineage, capability provenance |
| Repo context graph | `repository_context_graphs/repo_context_graph.schema.yaml` | Repo structure, skill coverage state |
| Skill context graph | `skill_context_graphs/skill_context_graph.schema.yaml` | Active skill set, coverage gaps, relationships |

## Forbidden Actions

- Do not merge without ranking sources first.
- Do not silently discard a conflicted value — log it.
- Do not let a tertiary source override a primary source on any key.
- Do not emit a merged payload without an accompanying conflict log (even if the log is empty).
- Do not trust a stale source as if it were fresh — flag it.

## Required Outputs

1. **Ranked source list** — tier, weight, is_stale for each input source.
2. **Merged context payload** — key/value map with highest-ranked values.
3. **Conflict log** — one record per conflict using `conflict_resolution.schema.yaml`.
4. **Source provenance chain** — which source contributed each key in the final payload.
5. **Staleness flags** — list of source_ids that exceeded the stale threshold.

## Validation

```bash
python3 infrastructure/scripts/validate_skill_router_integration.py
```

Must pass 179/179/179 (or current total) after this skill is registered and routed.

## Related Skills

- `SKILL_CONTEXT_PACKET_001` — produces the individual packets this engine merges
- `SKILL_TRUTH_STATE_CHECK_001` — provides truth-state input before merge
- `SKILL_SOURCE_TRUTH_RECONCILIATION_001` — post-merge reconciliation
- `SKILL_ATLAS_REPO_INGESTION_LOOP_001` — upstream ingestion feeding primary-tier sources
