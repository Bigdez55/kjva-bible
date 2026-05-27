# SKILL_DATA_ISOLATION_STORAGE_001 Playbook

## Purpose

Use this skill to design tenant-aware storage, database isolation, backup, restore, retention, encryption, and data lifecycle.

## Core Doctrine

Data isolation is the heart of multi-tenancy. Every storage system must know tenant boundaries: relational tables, documents, blobs, search indexes, vector indexes, graph edges, logs, backups, and caches.

## Required Outputs

- Data isolation strategy
- Storage topology
- Tenant key hierarchy
- Data residency model
- Backup/restore model
- Export/offboarding model
- Retention/legal hold model
- Cache isolation model
- Search/vector/graph isolation model
- Proof gates

## Trigger Phrases

- tenant data isolation
- data model
- database per tenant
- schema per tenant
- row-level security
- tenant_id
- encryption keys
- backup restore
- data export
- offboarding
- data residency

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/03_data_isolation_and_storage/SKILL.md`.

## Full Imported Instructions

# Skill: Data Isolation and Storage

## Purpose

Use this skill to design tenant-aware storage, database isolation, backup, restore, retention, encryption, and data lifecycle.

## Trigger Phrases

- tenant data isolation
- data model
- database per tenant
- schema per tenant
- row-level security
- tenant_id
- encryption keys
- backup restore
- data export
- offboarding
- data residency

## Core Doctrine

Data isolation is the heart of multi-tenancy. Every storage system must know tenant boundaries: relational tables, documents, blobs, search indexes, vector indexes, graph edges, logs, backups, and caches.

## Required Outputs

1. Data isolation strategy.
2. Storage topology.
3. Tenant key hierarchy.
4. Data residency model.
5. Backup/restore model.
6. Export/offboarding model.
7. Retention/legal hold model.
8. Cache isolation model.
9. Search/vector/graph isolation model.
10. Proof gates.

## Isolation Models

Evaluate:

| Model | Pros | Cons | Best For |
|---|---|---|---|
| Shared DB + tenant_id | cheap, fast | highest leakage risk if poorly enforced | MVP/SMB |
| Shared DB + RLS | stronger DB enforcement | DB-specific complexity | SaaS with strong SQL backing |
| Schema per tenant | better separation | migration complexity | mid-market |
| DB per tenant | strong isolation | operational overhead | enterprise |
| Cluster per tenant | strongest SaaS isolation | expensive | regulated/sovereign |
| Hybrid | flexible | policy complexity | broad SaaS platform |

## Recommended Default

Use a hybrid model:

```text
MVP:
  pooled tenant_id + strict query enforcement + tests

Enterprise:
  tenant tier determines isolation:
    free/smb -> pooled
    business -> pooled with stronger controls
    enterprise -> schema/db isolation
    sovereign -> dedicated cluster/deployment
```

## Required Tenant Fields on Data

Every tenant-owned record must include:

```text
tenant_id
workspace_id when applicable
created_by
created_at
updated_at
classification
retention_policy_id
data_region
```

## Storage Plan Must Cover

| Storage Layer | Tenant Isolation Requirement |
|---|---|
| Relational data | tenant-aware queries/RLS/schema/db |
| Document data | tenant_id in document metadata |
| Blob/files | tenant-scoped metadata and ACL |
| Search index | tenant filter mandatory |
| Vector index | tenant filter mandatory |
| Graph edges | tenant boundary validation |
| Cache | tenant-prefixed keys |
| Queue/events | tenant_id in every event |
| Logs | tenant_id where safe and relevant |
| Backups | tenant-aware restore path |
| Analytics | tenant-safe aggregation |

## Encryption/KMS Model

Minimum hierarchy:

```text
Platform Root Key
  Environment Key
    Tenant Key
      Data Class Key
        Object/Record Key optional
```

Required:

1. Tenant-scoped key references.
2. Key rotation plan.
3. Key revocation strategy.
4. Backup key handling.
5. Secret isolation.
6. No plaintext secrets in logs.

## Backup/Restore

Must support:

1. Platform backup.
2. Tenant-scoped backup.
3. Tenant-scoped restore.
4. Point-in-time restore later.
5. Export package.
6. Offboarding archive.
7. Legal hold retention.

## Required Gates

1. Tenant A cannot read Tenant B SQL rows.
2. Tenant A cannot read Tenant B documents.
3. Tenant A cannot read Tenant B blobs.
4. Tenant A cannot search Tenant B data.
5. Tenant A cannot retrieve Tenant B vectors.
6. Tenant A cannot traverse Tenant B graph edges unless explicitly shared.
7. Tenant backup contains only Tenant A data.
8. Tenant restore restores only Tenant A data.
9. Tenant deletion honors retention/legal hold.
10. Cache keys cannot collide across tenants.

## Anti-Patterns

Avoid:

- shared cache keys without tenant prefix
- background jobs without tenant context
- global search index without tenant filter
- vector similarity search without tenant filter
- graph traversal crossing tenant boundary by default
- backups that cannot restore one tenant

