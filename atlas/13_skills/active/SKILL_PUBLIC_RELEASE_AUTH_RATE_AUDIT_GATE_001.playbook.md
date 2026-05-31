# SKILL_PUBLIC_RELEASE_AUTH_RATE_AUDIT_GATE_001 Playbook

## Purpose

Use this skill before any multi-tenant platform is exposed publicly. This is a launch-blocker skill.  It verifies that production authentication, tenant/session claims, rate limits, audit logging, public endpoint inventory, and cross-tenant denial gates exist before public release.

## Core Doctrine

No multi-tenant platform should go public without production-grade identity, tenant-aware authorization, server-side rate limits, and immutable audit logging. Public release is blocked until these gates pass.

## Required Outputs

- Auth provider decision matrix
- Auth provider adapter contract
- Tenant/session claims schema
- Protected route inventory
- Public route inventory
- Rate limit policy
- Audit event taxonomy
- Cross-tenant denial test plan
- Launch blocker checklist
- Final PASS/FAIL release recommendation

## Trigger Phrases

- before public release
- production auth provider
- Clerk
- Auth.js
- Auth0
- Descope
- tenant claims
- session claims
- JWT claims
- rate limits
- audit logging
- launch gate
- public release checklist
- production readiness auth

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/16_public_release_auth_rate_audit_gate/SKILL.md`.

## Full Imported Instructions

# Skill: Public Release Auth, Tenant Claims, Rate Limits, and Audit Gate

## Purpose

Use this skill before any multi-tenant platform is exposed publicly. This is a launch-blocker skill.

It verifies that production authentication, tenant/session claims, rate limits, audit logging, public endpoint inventory, and cross-tenant denial gates exist before public release.

## Trigger Phrases

- before public release
- production auth provider
- Clerk
- Auth.js
- Auth0
- Descope
- tenant claims
- session claims
- JWT claims
- rate limits
- audit logging
- launch gate
- public release checklist
- production readiness auth

## Core Doctrine

No multi-tenant platform should go public without production-grade identity, tenant-aware authorization, server-side rate limits, and immutable audit logging.

Public release is blocked until these gates pass.

## Required Outputs

1. Auth provider decision matrix.
2. Auth provider adapter contract.
3. Tenant/session claims schema.
4. Protected route inventory.
5. Public route inventory.
6. Rate limit policy.
7. Audit event taxonomy.
8. Cross-tenant denial test plan.
9. Launch blocker checklist.
10. Final PASS/FAIL release recommendation.

## Auth Provider Decision Matrix

Evaluate:

| Provider | Speed | Sovereignty | Enterprise SSO | Tenant/Org Fit | Lock-In | Recommendation |
|---|---:|---:|---:|---:|---:|---|
| Clerk | TBD | TBD | TBD | TBD | TBD | TBD |
| Auth.js | TBD | TBD | TBD | TBD | TBD | TBD |
| Auth0 | TBD | TBD | TBD | TBD | TBD | TBD |
| Descope | TBD | TBD | TBD | TBD | TBD | TBD |
| Custom/Self-Hosted Auth | TBD | TBD | TBD | TBD | TBD | TBD |
| Hybrid Provider + Portable Auth Adapter | TBD | TBD | TBD | TBD | TBD | TBD |

## Required Auth Provider Adapter

```text
AuthProviderAdapter
  verify_request()
  get_actor()
  get_session()
  resolve_tenant()
  get_tenant_memberships()
  get_roles()
  get_permissions()
  require_mfa()
  create_service_account_token()
  revoke_session()
  rotate_api_key()
```

## Required Tenant and Session Claims

Minimum claims:

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

Validation rules:

1. Tenant claim must be server-verified.
2. Tenant claim must match actor membership.
3. Missing tenant claim fails tenant-scoped route.
4. Client-provided tenant_id cannot override server session.
5. Session revocation must be enforced.
6. Expired session must be denied.
7. MFA claim required for high-risk admin actions.

## Required Rate Limit Policy

Rate limits must be enforced by:

- IP
- actor/user
- tenant
- service account
- API token
- endpoint
- plan
- expensive operation
- AI action
- export/import job

Minimum gate:

```text
RATE_LIMIT_EXCEEDED returns 429 with retry_after_seconds
```

## Required Audit Logging

Audit these before launch:

- login
- failed login
- logout/session revoked
- tenant created
- tenant suspended/reactivated
- role change
- API key created/rotated/revoked
- service account created/rotated/revoked
- data export/delete/restore
- billing/plan change
- admin/support access
- cross-tenant denial
- rate-limit abuse
- AI tool call/action
- deployment/rollback if platform-managed

## Protected Route Inventory

Every route must be classified:

| Route | Public? | Auth Required? | Tenant Required? | Rate Limited? | Audit Required? |
|---|---|---|---|---|---|
| /health | yes | no | no | yes | no |
| /api/* | no by default | yes | yes where tenant scoped | yes | depends |

Default rule:

```text
All /api/* routes are protected unless explicitly listed as public.
```

## Launch Blocker Checklist

Public release is blocked if any answer is no:

1. Production auth provider selected or justified.
2. Auth provider adapter exists.
3. Tenant/session claims schema exists.
4. Tenant membership verification works.
5. Session revocation works.
6. Expired session denial works.
7. Protected route inventory exists.
8. Public route inventory exists.
9. Cross-tenant denial tests pass.
10. Rate limits exist server-side.
11. Rate limit events logged.
12. Audit logging exists.
13. Privileged actions audited.
14. Audit logs redact secrets.
15. Admin/support access audited.
16. Service account scopes enforced.
17. API key rotation/revocation works.
18. AI/agent tool calls are scoped and audited.
19. Tenant export/delete/restore audited.
20. Final claim hygiene review completed.

## Required Gates

1. unauthenticated denial
2. invalid session denial
3. expired session denial
4. revoked session denial
5. wrong tenant claim denial
6. missing tenant claim denial
7. role denial
8. service account scope denial
9. IP rate limit
10. tenant rate limit
11. endpoint rate limit
12. audit event emitted
13. audit tamper resistance
14. secret redaction
15. route inventory check

## Final Output

```text
PUBLIC_RELEASE_AUTH_RATE_AUDIT_GATE: PASS|FAIL

Blocking Issues:
- ...

Evidence:
- ...

Allowed Claims:
- ...

Forbidden Claims:
- ...
```



## Storbits Standalone Public Release Correction

For Storbits, public release auth planning must not depend on GEN.OS or xOrchestra.

Current acceptable auth paths:

1. Clerk.
2. Auth.js.
3. Auth0.
4. Descope.
5. Custom/self-hosted auth.
6. Hybrid provider plus portable adapter.

Future-only, not current blockers:

1. GEN.OS identity bridge.
2. xOrchestra-aware session propagation.
3. GEN.OS-native auth plane.

Do not mark Storbits public release incomplete because GEN.OS-native auth is not available.

