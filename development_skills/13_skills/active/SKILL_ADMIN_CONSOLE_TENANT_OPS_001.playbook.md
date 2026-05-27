# SKILL_ADMIN_CONSOLE_TENANT_OPS_001 Playbook

## Purpose

Use this skill to design the platform operator console and tenant admin console for multi-tenant systems.

## Core Doctrine

A multi-tenant platform needs two admin experiences: platform operators manage the whole system; tenant admins manage their own tenant. These permissions must never blur.

## Required Outputs

- Admin personas
- Console IA/sitemap
- Platform admin features
- Tenant admin features
- Permission model
- Audit model
- Operational workflows
- Support access model
- Dashboard metrics
- Proof gates

## Trigger Phrases

- admin console
- tenant dashboard
- operator console
- tenant ops
- platform admin
- customer admin
- management UI
- settings
- users page
- billing page

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/14_admin_console_tenant_ops/SKILL.md`.

## Full Imported Instructions

# Skill: Admin Console and Tenant Operations

## Purpose

Use this skill to design the platform operator console and tenant admin console for multi-tenant systems.

## Trigger Phrases

- admin console
- tenant dashboard
- operator console
- tenant ops
- platform admin
- customer admin
- management UI
- settings
- users page
- billing page

## Core Doctrine

A multi-tenant platform needs two admin experiences: platform operators manage the whole system; tenant admins manage their own tenant. These permissions must never blur.

## Required Outputs

1. Admin personas.
2. Console IA/sitemap.
3. Platform admin features.
4. Tenant admin features.
5. Permission model.
6. Audit model.
7. Operational workflows.
8. Support access model.
9. Dashboard metrics.
10. Proof gates.

## Personas

| Persona | Scope |
|---|---|
| Platform Owner | full internal governance |
| Platform Admin | system operations |
| Platform Support | limited support actions |
| Tenant Owner | owns customer tenant |
| Tenant Admin | manages tenant users/settings |
| Billing Admin | billing/plan/payment |
| Security Admin | SSO/audit/security |
| Developer Admin | API keys/integrations |
| Viewer | read-only |

## Platform Admin Console

Required areas:

- tenants
- plans
- system health
- usage/metering
- incidents
- audit events
- feature flags
- deployments
- regions/nodes
- backups/restores
- support access
- security alerts

## Tenant Admin Console

Required areas:

- users
- roles
- service accounts
- API keys
- workspaces/projects
- billing/plan
- usage/quotas
- audit logs
- security/SSO
- data export
- integrations
- support

## Required Gates

1. Tenant admin cannot open platform admin page.
2. Tenant admin sees only their tenant.
3. Platform support action audited.
4. Billing admin sees billing but not security secrets.
5. Security admin manages SSO but not billing.
6. API key creation audited.
7. Tenant export requires permission.
8. Suspension state visible.
9. Quota usage displayed.
10. No fake dashboard metrics.

## Anti-Patterns

Avoid:

- one admin role for everything
- platform admin UI accessible by tenant admin
- support impersonation without audit
- fake metrics
- destructive actions without confirmation/audit

