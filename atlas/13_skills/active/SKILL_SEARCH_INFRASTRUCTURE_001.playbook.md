# Search Infrastructure — Production Readiness Playbook

**Skill:** `SKILL_SEARCH_INFRASTRUCTURE_001`
**Corpus category owned:** `Search Infrastructure` (53_production_readiness)
**Layer:** data

---

## When to use

Use this playbook whenever search is on the critical path to production:

- You are introducing or scaling Elasticsearch, OpenSearch, Algolia, Typesense,
  Meilisearch, `pgvector`, or a dedicated vector database.
- You are defining or changing **index mappings, analyzers, tokenizers, synonyms,
  or stopwords**.
- You are planning a **reindex, schema migration, or alias cutover**.
- You need to **tune, measure, or regression-test relevance / ranking / vector
  similarity**.
- **Query latency, throughput, or cluster health** is degrading or needs an SLO.
- Search must become **multi-tenant and access-controlled**.
- A production-readiness audit reaches the **Search Infrastructure** category.

If search is being added as an afterthought to a feature, stop and run this
checklist first — search outages and relevance regressions are silent and
expensive.

---

## Key practices (organized by corpus section)

### 1. Index schema and mappings

- **Pin the schema.** Every production index has an explicit, version-controlled
  mapping. **Disable dynamic mapping** (`dynamic: strict` or `dynamic: false`)
  so an unexpected field shape cannot explode the mapping or cause a type
  conflict that rejects all writes.
- **Right-type fields.** Distinguish `text` (analyzed, for matching) from
  `keyword` (exact, for filters/aggregations/sorts). Use multi-fields when you
  need both.
- **Treat mapping changes as migrations**, not edits. Most mapping changes are
  not reversible in place — they require a new index + reindex.

### 2. Analyzers, tokenizers, synonyms, stopwords

- Declare analyzers, tokenizers, char filters, synonyms, and stopwords **as code**
  and keep them **byte-identical across every environment**.
- An analyzer change changes tokenization. You **must reindex** — never mutate an
  analyzer in place, or old and new documents will be tokenized differently and
  relevance silently splits into two regimes.
- Prefer synonym **graph** filters at query time when you need to change synonyms
  without a full reindex, but know the trade-offs and document the decision.

### 3. Indexing pipeline and freshness

- **Decouple indexing from the request path.** Writes flow through a durable
  queue/stream (Kafka, SQS, outbox + worker). The user request must not block on
  the search cluster.
- Make ingest **idempotent** (deterministic document IDs) so retries and replays
  do not duplicate documents.
- Failures **retry with backoff** and land in a **dead-letter** path — never
  silently drop a document.
- Define and monitor **freshness SLO** (system-of-record-to-searchable lag).

### 4. Reindex and zero-downtime cutover

- **Always read/write through an alias**, never a raw index name. Reindexing then
  becomes: build `index_v2` → backfill → verify → atomically repoint the alias →
  keep `index_v1` for instant rollback.
- The backfill must be **reproducible from the system of record**, **resumable**,
  and **idempotent**. Rehearse it in staging, including a mid-run kill + resume.
- **Verify before cutover:** document counts match the source, and a sample of
  golden queries returns expected results against the new index.

### 5. Relevance and ranking

- Maintain a **golden query / judgment set** (queries + graded relevant docs).
- Run a **relevance regression suite in CI** computing nDCG / MRR / recall.
  Ranking, boosting, and analyzer changes must show **measured deltas** before
  merge. No blind boosting by eyeballing a handful of queries.
- For vector/hybrid search, pin the embedding model + version, and regression-test
  recall@k and latency together (ANN parameters trade recall for speed).

### 6. Query performance and SLOs

- Set explicit **p95 and p99 latency ceilings** and alert on them.
- Enable **slow-query logging** and review it; index the fields you filter/sort on.
- Avoid deep pagination (`from`/`size` over large offsets) — use `search_after`
  / cursors. Cap expensive aggregations and wildcard/leading-wildcard queries.
- **Rate-limit and circuit-break** both bulk ingest and query traffic so a
  runaway reindex or query storm cannot take down the cluster.

### 7. Cluster health and capacity

- Size shards intentionally: target **~10-50 GB per shard**, avoid the
  "too many tiny shards" and "one giant shard" anti-patterns.
- Run **replicas >= 1** in production. No single-node, zero-replica production
  cluster.
- Monitor and alert on: **unassigned shards / cluster status (green/yellow/red)**,
  **JVM heap pressure & GC pauses**, and **disk watermarks** (low / high /
  flood-stage). Flood-stage flips indices to **read-only** and silently fails
  writes — alert *before* you reach it.

### 8. Security, multi-tenancy, and data governance

- **Authenticate** the cluster; store credentials/API keys in a **secret manager**
  — never in source, committed env files, or client bundles.
- **Enforce tenant scoping server-side** (per-tenant filter, filtered alias, or
  document-level security). Client-side filtering is a data-leak waiting to
  happen.
- **Classify PII** in indexed documents; provide field-level redaction/encryption
  and a **retention / deletion (right-to-be-forgotten)** path.

### 9. Backup and recovery

- Schedule **snapshots** of indices to durable storage and **test restore** into
  a clean cluster. Even if index data is rebuildable from the source, rehearse
  recovery so you know the RTO.

---

## Concrete checklist / workflow

```
[ ] Every prod index has an explicit, version-controlled mapping; dynamic mapping disabled.
[ ] All app reads/writes go through an alias — no raw/dated index names in code.
[ ] Analyzers/synonyms/stopwords are code, identical across envs; changes => reindex.
[ ] Indexing decoupled via durable queue; idempotent IDs; retries + dead-letter.
[ ] Reindex/backfill is reproducible, resumable, idempotent; rehearsed in staging (kill+resume).
[ ] Pre-cutover verification: doc counts match SoR + golden queries pass on new index.
[ ] Golden judgment set + relevance regression (nDCG/MRR/recall) gating CI.
[ ] Query latency p95/p99 SLO with dashboards + alerts; slow-query log on.
[ ] Shards sized ~10-50GB; replicas >= 1; no single-node prod cluster.
[ ] Cluster health alerts: unassigned shards, heap/GC, disk watermarks (pre flood-stage).
[ ] Bulk + query traffic rate-limited and circuit-broken.
[ ] Tenant scoping enforced server-side; cross-tenant read proven impossible by test.
[ ] Secrets in secret manager; nothing in source/client bundle.
[ ] PII classified; redaction/encryption + retention/deletion path exist.
[ ] Snapshots scheduled to durable storage; restore tested.
```

---

## Anti-patterns

| Anti-pattern | Why it bites | Do instead |
| --- | --- | --- |
| Dynamic mapping on in production | Field explosion / type conflict rejects all writes | `dynamic: strict`, version the mapping |
| Reindex in place against the live index name | Hard outage, no rollback | Alias + build new index + atomic cutover |
| Analyzer/synonym edit without reindex | Old docs keep old tokenization; relevance splits | Treat analyzer change as a reindex migration |
| Tuning ranking by eyeballing a few queries | Aggregate relevance regresses silently | Golden judgment set + nDCG/MRR in CI |
| Single-node, zero-replica prod cluster | One node loss = red cluster, data loss | Replicas >= 1, intentional shard sizing |
| Ignoring disk watermarks | Flood-stage flips indices read-only, writes fail silently | Alert before high/flood-stage |
| Client-side / missing tenant filter | Cross-tenant data leak | Server-side filter or document-level security |
| Indexing on the synchronous request path | Ingest/cluster slowdown cascades to user timeouts | Durable queue + worker, with backpressure |
| Credentials in source / client bundle | Credential leak, full-cluster compromise | Secret manager, server-side only |
| Deep `from`/`size` pagination | O(n) cost, heap pressure, slow queries | `search_after` / cursor pagination |

---

## Related

- `SKILL_PRODUCTION_READINESS_AUDIT_001` — parent audit; this skill owns the
  "Search Infrastructure" corpus category it audits against.
- `SKILL_DRIFT_DETECTION_001` — detect mapping/analyzer/config drift across
  environments.
- `SKILL_CONTINUOUS_INTEGRATION_PIPELINE_001` — gate relevance and reindex
  rehearsals in CI.
- `SKILL_AUTOMATED_REGRESSION_TESTING_001` — frame the golden-query relevance
  suite as a regression gate.
