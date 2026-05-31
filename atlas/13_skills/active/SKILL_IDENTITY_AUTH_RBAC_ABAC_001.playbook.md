# SKILL_IDENTITY_AUTH_RBAC_ABAC_001 Playbook

## Purpose

Use this skill to design enterprise-grade identity and access control for a multi-tenant platform.

## Core Doctrine

Authentication proves who the actor is. Authorization proves what the actor can do in a specific tenant, workspace, resource, and context. Never rely on frontend-only authorization.

## Required Outputs

- Actor model
- Authentication model
- Tenant membership model
- Role model
- Permission model
- ABAC policy model
- Service account model
- API token model
- Session model
- Audit model
- Enforcement points
- Proof gates

## Trigger Phrases

- authentication
- authorization
- login
- SSO
- SAML
- OIDC
- RBAC
- ABAC
- service accounts
- API keys
- tenant roles
- permissions
- policy engine

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/02_identity_auth_rbac_abac/SKILL.md`.

## Full Imported Instructions

# Skill: Identity, Authentication, RBAC, and ABAC

## Purpose

Use this skill to design enterprise-grade identity and access control for a multi-tenant platform.

## Trigger Phrases

- authentication
- authorization
- login
- SSO
- SAML
- OIDC
- RBAC
- ABAC
- service accounts
- API keys
- tenant roles
- permissions
- policy engine

## Core Doctrine

Authentication proves who the actor is. Authorization proves what the actor can do in a specific tenant, workspace, resource, and context.

Never rely on frontend-only authorization.

## Required Outputs

1. Actor model.
2. Authentication model.
3. Tenant membership model.
4. Role model.
5. Permission model.
6. ABAC policy model.
7. Service account model.
8. API token model.
9. Session model.
10. Audit model.
11. Enforcement points.
12. Proof gates.

## Actor Types

Support or explicitly exclude:

| Actor | Description |
|---|---|
| Human User | Person using the platform |
| Tenant Admin | Customer-side administrator |
| Platform Admin | Internal operator |
| Service Account | Non-human integration identity |
| AI Agent | Automated actor with scoped permissions |
| Support Impersonation Actor | Highly audited support workflow |
| Break-Glass Actor | Emergency access with strict audit |

## Authentication Requirements

Choose based on platform maturity:

| Capability | MVP | Enterprise |
|---|---|---|
| Email/password | optional | optional |
| Magic link | optional | optional |
| MFA | recommended | required |
| OIDC | recommended | required |
| SAML | later | required for enterprise |
| SCIM | later | required for enterprise provisioning |
| Session revocation | required | required |
| Device/session tracking | recommended | required |

## RBAC Model

Minimum roles:

```text
PlatformOwner
PlatformAdmin
PlatformSupport
TenantOwner
TenantAdmin
TenantDeveloper
TenantAnalyst
TenantBillingAdmin
TenantViewer
ServiceAccount
AIWorker
```

## Permission Format

Use explicit permissions:

```text
resource.action.scope
```

Examples:

```text
tenant.read.own
tenant.update.own
users.invite.tenant
records.read.tenant
records.write.tenant
billing.read.tenant
audit.read.tenant
admin.read.platform
admin.write.platform
```

## ABAC Context

Policies must evaluate:

```json
{
  "actor_id": "uuid",
  "actor_type": "user|service_account|agent",
  "tenant_id": "uuid",
  "workspace_id": "uuid",
  "resource_type": "record",
  "resource_id": "uuid",
  "action": "read",
  "resource_labels": ["confidential"],
  "actor_attributes": {
    "role": "TenantAdmin",
    "department": "finance"
  },
  "environment": {
    "ip": "string",
    "region": "string",
    "mfa": true,
    "risk_score": 0
  }
}
```

## Enforcement Points

Enforce authorization at:

1. API gateway.
2. Service method.
3. Database query layer.
4. Object/blob layer.
5. Search/vector/graph query layer.
6. Admin console action layer.
7. Background job layer.
8. AI agent/tool invocation layer.

## Required Gates

1. Unauthenticated request denied.
2. Authenticated wrong-tenant request denied.
3. Tenant viewer cannot write.
4. Tenant admin cannot access platform admin actions.
5. Platform support access is audited.
6. Service account limited to assigned scopes.
7. API key rotation works.
8. Session revocation works.
9. MFA required for admin actions where configured.
10. Cross-tenant token replay denied.

## Anti-Patterns

Avoid:

- global admin role used for normal operations
- tenant role not tied to tenant_id
- service accounts with human-equivalent powers
- unscoped API keys
- authorization only at route level
- missing audit for privileged actions



## Production Auth Provider Gate

Before public release, the platform must choose a production auth strategy.

Evaluate these provider paths:

| Provider Path | Best Use | Sovereignty Tradeoff | Notes |
|---|---|---|---|
| Clerk | fast SaaS auth, org-aware app UX | external dependency | good speed-to-value candidate |
| Auth.js | framework-native/customizable auth | more self-owned responsibility | good when app owns session logic |
| Auth0 | enterprise identity/SSO maturity | external dependency and cost | strong enterprise adoption path |
| Descope | auth flows, passwordless, B2B/B2C options | external dependency | evaluate for workflow speed |
| Custom/Self-Hosted Auth | maximum control | higher build burden | future option after provider decision |
| Hybrid | provider now, portable auth adapter later | medium | practical migration path without GEN.OS dependency |

The decision log must include:

- selected provider
- rejected providers
- reason
- lock-in risk
- SSO/SAML/OIDC support path
- tenant/org model support path
- session claims strategy
- migration/exit strategy
- public release risks

## Auth Provider Adapter Contract

Do not let app code depend directly on one provider everywhere. Create an abstraction:

```text
AuthProviderAdapter
  verify_request()
  get_actor()
  get_session()
  get_tenant_memberships()
  get_roles()
  get_permissions()
  require_mfa()
  create_service_account_token()
  revoke_session()
  rotate_api_key()
```

Provider-specific implementation can be Clerk/Auth.js/Auth0/Descope/GEN.OS-native, but tenant-aware services should consume the adapter contract.

## Tenant and Session Claims

Every protected request must resolve server-side claims.

Minimum session/JWT/server-session claims:

```json
{
  "sub": "actor_id",
  "actor_type": "user|service_account|agent",
  "session_id": "uuid",
  "tenant_id": "uuid",
  "tenant_slug": "string",
  "tenant_memberships": ["tenant_id"],
  "workspace_id": "uuid optional",
  "roles": ["TenantAdmin"],
  "permissions": ["records.read.tenant"],
  "plan_id": "business",
  "mfa": true,
  "auth_provider": "clerk|authjs|auth0|descope|custom",
  "issued_at": "timestamp",
  "expires_at": "timestamp"
}
```

Rules:

1. Never trust tenant_id from client body alone.
2. Tenant claim must be validated against membership.
3. Server must reject a tenant claim the actor does not belong to.
4. Session must include actor type.
5. Service accounts and AI agents must not inherit human privileges by default.
6. Admin actions may require MFA claim.
7. Public release requires session revocation to work.
8. Public release requires expired session denial to be tested.

## Public Release Auth Gates

Required before launch:

1. Unauthenticated protected request denied.
2. Invalid session denied.
3. Expired session denied.
4. Revoked session denied.
5. Wrong-tenant claim denied.
6. Missing tenant claim denied on tenant-scoped route.
7. User without tenant membership denied.
8. Tenant viewer write denied.
9. Tenant admin platform-admin denied.
10. Service account scope denial passes.
11. MFA-required admin action denies non-MFA session.
12. Provider outage behavior documented.
13. Provider migration/exit path documented.



## Storbits Current Auth Doctrine

For Storbits right now:

1. Do not require GEN.OS-native auth.
2. Do not require a GEN.OS identity bridge.
3. Do not block public release planning on xOrchestra or GEN.OS.
4. Use a production-ready auth provider or a clearly justified custom/self-hosted auth layer.
5. Preserve sovereignty through an `AuthProviderAdapter` so providers can be swapped later.

Current provider candidates:

- Clerk
- Auth.js
- Auth0
- Descope
- Custom/self-hosted auth

Future-only candidates:

- GEN.OS identity bridge
- xOrchestra-aware identity/session propagation

Future-only candidates must not appear as current release blockers for Storbits.

