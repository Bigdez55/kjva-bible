# SKILL_BILLING_METERING_QUOTAS_001 Playbook

## Purpose

Use this skill to design tenant plans, subscriptions, usage events, metering, billing, quotas, entitlements, and enforcement.

## Core Doctrine

A multi-tenant platform without metering and quota enforcement is operationally blind. Billing can come later, but usage events must start early.

## Required Outputs

- Plan model
- Entitlement model
- Usage event taxonomy
- Metering pipeline
- Quota enforcement model
- Billing account model
- Invoice integration path
- Over-limit behavior
- Admin/reporting needs
- Proof gates

## Trigger Phrases

- billing
- metering
- usage
- quotas
- plans
- subscriptions
- entitlements
- invoices
- limits
- usage-based pricing
- SaaS pricing

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/06_billing_metering_and_quotas/SKILL.md`.

## Full Imported Instructions

# Skill: Billing, Metering, and Quotas

## Purpose

Use this skill to design tenant plans, subscriptions, usage events, metering, billing, quotas, entitlements, and enforcement.

## Trigger Phrases

- billing
- metering
- usage
- quotas
- plans
- subscriptions
- entitlements
- invoices
- limits
- usage-based pricing
- SaaS pricing

## Core Doctrine

A multi-tenant platform without metering and quota enforcement is operationally blind. Billing can come later, but usage events must start early.

## Required Outputs

1. Plan model.
2. Entitlement model.
3. Usage event taxonomy.
4. Metering pipeline.
5. Quota enforcement model.
6. Billing account model.
7. Invoice integration path.
8. Over-limit behavior.
9. Admin/reporting needs.
10. Proof gates.

## Plan Model

Minimum:

```json
{
  "plan_id": "business",
  "name": "Business",
  "limits": {
    "users": 50,
    "storage_gb": 500,
    "api_requests_per_month": 1000000,
    "projects": 25,
    "ai_actions_per_month": 10000
  },
  "features": {
    "sso": true,
    "audit_export": true,
    "priority_support": false
  }
}
```

## Usage Event Schema

Every usage event must include:

```json
{
  "event_id": "uuid",
  "tenant_id": "uuid",
  "actor_id": "uuid optional",
  "event_type": "api_request|storage_write|ai_action|export|compute",
  "quantity": 1,
  "unit": "request|byte|token|job|minute",
  "timestamp": "timestamp",
  "source_service": "service-name",
  "idempotency_key": "string"
}
```

## Quota Types

Evaluate:

| Quota | Examples |
|---|---|
| User seats | users per tenant |
| Storage | GB/TB per tenant |
| API requests | requests per minute/month |
| Compute | job minutes, CPU/GPU seconds |
| AI usage | actions, embeddings, generated outputs |
| Projects/workspaces | count limits |
| Retention | log/data retention days |
| Exports | monthly export count/size |

## Required Gates

1. Usage event emitted.
2. Duplicate usage event deduped by idempotency key.
3. Quota increment works.
4. Over-quota request denied or degraded correctly.
5. Plan upgrade changes entitlements.
6. Plan downgrade handles over-limit state.
7. Tenant usage report generated.
8. Billing admin permission required.
9. Cross-tenant billing access denied.
10. Usage event audit trail retained.

## Anti-Patterns

Avoid:

- adding billing after platform has no usage data
- no idempotency on usage events
- hardcoded plan limits in code
- quota checks only in UI
- billing admin same as tenant owner without explicit permission

