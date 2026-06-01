# SKILL_TENANT_MODEL_BOUNDARY_DESIGN_001 Playbook

## Purpose

Use this skill to define what a tenant is, how tenants are structured, how boundaries are enforced, and how tenant lifecycle works.

## Core Doctrine

A tenant is a security, billing, data, operational, and governance boundary. It is not merely a label.

## Required Outputs

- Tenant definition
- Tenant hierarchy
- Tenant lifecycle states
- Tenant boundary matrix
- Tenant metadata model
- Tenant isolation requirements
- Tenant domain/event model
- Tenant provisioning contract
- Tenant offboarding contract
- Tenant edge cases and proof gates

## Trigger Phrases

- tenant model
- tenant boundary
- workspace model
- organization model
- account hierarchy
- multi-tenant structure
- tenant lifecycle
- tenant isolation domain
- org/team/user hierarchy

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/01_tenant_model_and_boundary_design/SKILL.md`.

## Full Imported Instructions

# Skill: Tenant Model and Boundary Design

## Purpose

Use this skill to define what a tenant is, how tenants are structured, how boundaries are enforced, and how tenant lifecycle works.

## Trigger Phrases

- tenant model
- tenant boundary
- workspace model
- organization model
- account hierarchy
- multi-tenant structure
- tenant lifecycle
- tenant isolation domain
- org/team/user hierarchy

## Core Doctrine

A tenant is a security, billing, data, operational, and governance boundary. It is not merely a label.

## Required Outputs

1. Tenant definition.
2. Tenant hierarchy.
3. Tenant lifecycle states.
4. Tenant boundary matrix.
5. Tenant metadata model.
6. Tenant isolation requirements.
7. Tenant domain/event model.
8. Tenant provisioning contract.
9. Tenant offboarding contract.
10. Tenant edge cases and proof gates.

## Tenant Hierarchy Template

```text
Platform
  Tenant
    Organization
      Workspace / Project / Environment
        Team
          User
          Service Account
          Agent
```

Adapt this to the project. Do not force all levels if unnecessary.

## Tenant Types

Evaluate:

| Tenant Type | Meaning |
|---|---|
| Customer Tenant | Paying customer/account |
| Internal Tenant | Internal business unit/team |
| Workspace Tenant | Project or workspace boundary |
| Sovereign Tenant | Dedicated isolated deployment |
| Region Tenant | Geography/regulatory boundary |
| Partner Tenant | External partner with scoped access |
| Agent Tenant | AI/automation actor boundary |

## Lifecycle States

Define allowed states:

```text
requested
provisioning
active
trial
suspended
limited
deleting
export_pending
offboarded
retained
legal_hold
```

## Required Tenant Record

Minimum fields:

```json
{
  "tenant_id": "uuid",
  "tenant_slug": "acme",
  "display_name": "Acme Inc.",
  "status": "active",
  "plan_id": "enterprise",
  "region": "us-west",
  "data_residency": "us",
  "isolation_mode": "pooled|schema|database|cluster|sovereign",
  "created_at": "timestamp",
  "updated_at": "timestamp",
  "owner_user_id": "uuid",
  "kms_key_ref": "tenant-key-ref",
  "quota_profile_id": "quota-enterprise",
  "billing_account_id": "billing-id",
  "retention_policy_id": "retention-id"
}
```

## Boundary Matrix

Always produce:

| Boundary | Tenant-Scoped? | Enforcement Layer | Proof Gate |
|---|---|---|---|
| Users | yes/no | identity | cross-tenant login denial |
| Roles | yes/no | policy | RBAC denial |
| Data | yes/no | database/storage | tenant data leak test |
| Files | yes/no | blob storage | blob tenant ACL test |
| Search Index | yes/no | query/search layer | cross-tenant search denial |
| Vector Index | yes/no | vector layer | cross-tenant vector denial |
| Graph Edges | yes/no | graph layer | cross-tenant traversal denial |
| Billing | yes/no | billing/metering | tenant usage event check |
| Logs | yes/no | observability | log tenant_id check |
| Backups | yes/no | backup system | tenant restore test |
| API Tokens | yes/no | auth | token scope test |

## Required Gates

1. Create tenant.
2. Activate tenant.
3. Suspend tenant.
4. Prevent suspended tenant writes.
5. Export tenant data.
6. Offboard tenant.
7. Preserve legal hold if required.
8. Verify no cross-tenant data access.
9. Verify all events include tenant_id.
10. Verify all logs include tenant_id where appropriate.

## Anti-Patterns

Avoid:

- tenant_id only in UI
- tenant_id optional in backend
- global admin access without audit
- search/vector/graph indexes without tenant filtering
- shared backups with no tenant restore path
- hard deletion without retention/legal-hold logic

