# SKILL_SECURITY_COMPLIANCE_GOVERNANCE_001 Playbook

## Purpose

Use this skill to design security, governance, compliance posture, audit trails, policy enforcement, secrets, encryption, and risk controls for a multi-tenant platform.

## Core Doctrine

Security must be native to the platform. Multi-tenancy multiplies blast radius, so default-deny, tenant isolation, auditability, and key separation must be designed early.

## Required Outputs

- Security baseline
- Threat model
- Data classification
- Control matrix
- Key/secrets model
- Audit/event model
- Compliance mapping
- Privileged access workflow
- Incident/security response model
- Proof gates

## Trigger Phrases

- security
- compliance
- governance
- audit
- SOC 2
- HIPAA
- PCI
- GDPR
- encryption
- secrets
- zero trust
- policy
- risk

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/07_security_compliance_governance/SKILL.md`.

## Full Imported Instructions

# Skill: Security, Compliance, and Governance

## Purpose

Use this skill to design security, governance, compliance posture, audit trails, policy enforcement, secrets, encryption, and risk controls for a multi-tenant platform.

## Trigger Phrases

- security
- compliance
- governance
- audit
- SOC 2
- HIPAA
- PCI
- GDPR
- encryption
- secrets
- zero trust
- policy
- risk

## Core Doctrine

Security must be native to the platform. Multi-tenancy multiplies blast radius, so default-deny, tenant isolation, auditability, and key separation must be designed early.

## Required Outputs

1. Security baseline.
2. Threat model.
3. Data classification.
4. Control matrix.
5. Key/secrets model.
6. Audit/event model.
7. Compliance mapping.
8. Privileged access workflow.
9. Incident/security response model.
10. Proof gates.

## Security Control Areas

Always address:

| Area | Controls |
|---|---|
| Identity | MFA, SSO, session revocation |
| Authorization | RBAC/ABAC, least privilege |
| Data | encryption, classification, masking |
| Network | segmentation, service identity |
| Secrets | sealed secret storage, rotation |
| Audit | immutable audit events |
| Admin | privileged access, break-glass |
| Tenant Isolation | denial gates, data boundary tests |
| Supply Chain | dependency scanning, signed builds |
| Runtime | health checks, hardening, sandboxing |
| Incident | detection, response, evidence |

## Audit Event Schema

```json
{
  "audit_event_id": "uuid",
  "tenant_id": "uuid optional",
  "actor_id": "uuid",
  "actor_type": "user|service_account|agent|system",
  "action": "string",
  "resource_type": "string",
  "resource_id": "string",
  "decision": "allowed|denied",
  "reason": "string",
  "ip": "string optional",
  "user_agent": "string optional",
  "timestamp": "timestamp",
  "hash_prev": "optional",
  "hash_current": "optional"
}
```

## Required Gates

1. Admin action emits audit event.
2. Denied action emits audit event.
3. Audit event cannot be silently modified.
4. Secret not printed in logs.
5. Tenant key reference exists.
6. Key rotation plan documented.
7. RBAC denial passes.
8. ABAC denial passes.
9. Cross-tenant data access denied.
10. Dependency/security scan documented.

## Compliance Posture

Do not claim compliance without audit evidence and formal controls. Use wording:

- "SOC 2-aligned control design"
- "HIPAA-style safeguard mapping"
- "PCI-style segmentation plan"
- "GDPR/CCPA data rights workflow design"

## Anti-Patterns

Avoid:

- claiming compliant prematurely
- no audit for support access
- plaintext secrets in config
- global admin without break-glass controls
- security only at API edge



## Public Release Audit Logging Gate

Before public release, audit logging must be implemented for security-relevant and tenant-relevant events.

Audit logs must cover:

| Event Area | Required Audit Events |
|---|---|
| Auth | login, logout, failed login, MFA challenge, session revocation |
| Tenant | tenant created, suspended, reactivated, offboarded |
| Users | invite, role change, removal |
| Service Accounts | created, token rotated, revoked |
| API Keys | created, used for sensitive action, rotated, revoked |
| Data | export, delete, restore, retention/legal hold change |
| Billing | plan change, quota change, billing admin action |
| Admin | platform admin/support access, impersonation, break-glass |
| Security | denied access, cross-tenant denial, rate-limit abuse |
| AI | tool call, recommendation, supervised approval, autopilot action |
| Orchestration | deployment, rollback, service restart, quarantine |

Minimum audit requirements:

1. Audit event has tenant_id when tenant-scoped.
2. Audit event has actor_id or system actor.
3. Audit event has action and decision.
4. Audit event has resource type/id when applicable.
5. Audit event has request_id/trace_id when applicable.
6. Audit event is append-only.
7. Audit event cannot be silently modified.
8. Sensitive values are redacted.
9. Audit export is permission-gated.
10. Privileged access is always audited.

## Required Public Release Audit Gates

1. Successful login audited.
2. Failed login audited.
3. Admin role change audited.
4. Tenant creation audited.
5. Tenant suspension audited.
6. Cross-tenant denial audited.
7. Rate-limit abuse audited.
8. Data export audited.
9. Service account token rotation audited.
10. AI tool call audited where applicable.
11. Audit event tamper attempt detected or prevented.
12. Audit logs do not expose secrets.

