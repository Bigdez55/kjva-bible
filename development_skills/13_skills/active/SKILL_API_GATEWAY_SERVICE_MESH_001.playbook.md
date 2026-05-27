# SKILL_API_GATEWAY_SERVICE_MESH_001 Playbook

## Purpose

Use this skill to design tenant-aware API routing, rate limiting, service discovery, internal routing, gateway policy, and service-to-service communication.

## Core Doctrine

The gateway is the front door. The mesh is the internal nervous system. Both must carry tenant context safely and consistently.

## Required Outputs

- API boundary map
- Public/private endpoint inventory
- Tenant context propagation model
- Auth enforcement plan
- Rate limit/quotas plan
- Service discovery model
- Internal service identity model
- Request tracing model
- API versioning strategy
- Proof gates

## Trigger Phrases

- API gateway
- service mesh
- XMesh
- routes
- rate limits
- internal services
- microservices
- service discovery
- tenant-aware routing
- API keys

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/05_api_gateway_and_service_mesh/SKILL.md`.

## Full Imported Instructions

# Skill: API Gateway and Service Mesh

## Purpose

Use this skill to design tenant-aware API routing, rate limiting, service discovery, internal routing, gateway policy, and service-to-service communication.

## Trigger Phrases

- API gateway
- service mesh
- XMesh
- routes
- rate limits
- internal services
- microservices
- service discovery
- tenant-aware routing
- API keys

## Core Doctrine

The gateway is the front door. The mesh is the internal nervous system. Both must carry tenant context safely and consistently.

## Required Outputs

1. API boundary map.
2. Public/private endpoint inventory.
3. Tenant context propagation model.
4. Auth enforcement plan.
5. Rate limit/quotas plan.
6. Service discovery model.
7. Internal service identity model.
8. Request tracing model.
9. API versioning strategy.
10. Proof gates.

## Required Tenant Context

Every request must establish:

```json
{
  "request_id": "uuid",
  "tenant_id": "uuid",
  "workspace_id": "uuid optional",
  "actor_id": "uuid",
  "actor_type": "user|service_account|agent",
  "auth_context": {},
  "policy_context": {},
  "trace_id": "uuid"
}
```

## Gateway Responsibilities

1. TLS termination or pass-through.
2. Request ID creation.
3. Authentication.
4. Tenant resolution.
5. Rate limiting.
6. Quota checks.
7. Request validation.
8. Routing.
9. Response shaping.
10. Audit event emission for sensitive actions.

## Service Mesh/XMesh Responsibilities

1. Service discovery.
2. Internal identity.
3. Mutual authentication where applicable.
4. Tenant context propagation.
5. Retry policy.
6. Circuit breaking.
7. Latency monitoring.
8. Backpressure.
9. Policy routing.
10. Failure isolation.

## Required Gates

1. Missing auth denied.
2. Invalid tenant denied.
3. Cross-tenant route denied.
4. Rate limit enforced.
5. Quota exceeded response correct.
6. Trace ID propagated.
7. Request ID in logs.
8. Internal service rejects missing service identity.
9. Deprecated API version warning works.
10. Sensitive route emits audit event.

## Anti-Patterns

Avoid:

- tenant_id only in request body
- trusting client-provided tenant_id without membership check
- internal services bypassing auth/policy
- no API versioning
- missing request tracing



## Public Release Rate Limit Gate

Before public release, rate limiting must exist server-side. UI-only limits do not count.

Rate limits must be evaluated across these dimensions:

| Limit Dimension | Example |
|---|---|
| IP | unauthenticated and abuse protection |
| Actor/User | authenticated user fairness |
| Tenant | noisy-neighbor containment |
| API token | integration control |
| Service account | machine workload control |
| Endpoint | expensive route protection |
| Plan | business/enterprise entitlements |
| Region/runtime node | overload protection |
| AI action | automation cost control |
| Export/import jobs | bulk operation protection |

Minimum rate limit policy schema:

```json
{
  "policy_id": "api-standard",
  "scope": "tenant|actor|token|ip|endpoint|plan",
  "window": "60s",
  "limit": 1000,
  "burst": 100,
  "over_limit_action": "deny|degrade|queue",
  "audit": true
}
```

Required response:

```json
{
  "ok": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded.",
    "retry_after_seconds": 60
  }
}
```

## Required Public Release Rate Limit Gates

1. Anonymous IP rate limit enforced.
2. Authenticated actor rate limit enforced.
3. Tenant-level rate limit enforced.
4. API-token rate limit enforced.
5. Endpoint-specific expensive-route limit enforced.
6. Over-limit response includes retry guidance.
7. Rate-limit event logged.
8. Repeated abuse emits audit/security event.
9. Rate limit cannot be bypassed by changing tenant_id in body.
10. Quota and rate limit behavior are distinct and documented.

