# SKILL_TESTING_GATES_RED_TEAM_001 Playbook

## Purpose

Use this skill to design the proof system for multi-tenant platforms: tests, gates, fixtures, red-team checks, claim hygiene, and acceptance criteria.

## Core Doctrine

No proof, no claim. Multi-tenant platforms must be tested against the exact failures that would destroy trust.

## Required Outputs

- Test strategy
- Unit/integration/e2e test plan
- Tenant isolation test plan
- Security test plan
- Resilience test plan
- Performance/load test plan
- Red team checklist
- Gate scripts
- Evidence paths
- Claim hygiene result

## Trigger Phrases

- test gates
- proof gates
- red team
- validation
- acceptance criteria
- claim hygiene
- tenant isolation tests
- security tests
- release gates

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/13_testing_gates_red_team/SKILL.md`.

## Full Imported Instructions

# Skill: Testing, Proof Gates, and Red Team Review

## Purpose

Use this skill to design the proof system for multi-tenant platforms: tests, gates, fixtures, red-team checks, claim hygiene, and acceptance criteria.

## Trigger Phrases

- test gates
- proof gates
- red team
- validation
- acceptance criteria
- claim hygiene
- tenant isolation tests
- security tests
- release gates

## Core Doctrine

No proof, no claim. Multi-tenant platforms must be tested against the exact failures that would destroy trust.

## Required Outputs

1. Test strategy.
2. Unit/integration/e2e test plan.
3. Tenant isolation test plan.
4. Security test plan.
5. Resilience test plan.
6. Performance/load test plan.
7. Red team checklist.
8. Gate scripts.
9. Evidence paths.
10. Claim hygiene result.

## Test Categories

| Category | Examples |
|---|---|
| Unit | policy functions, tenant resolvers |
| Integration | API + DB + auth |
| E2E | tenant admin workflow |
| Security | cross-tenant access denial |
| Resilience | crash, restore, failover |
| Performance | load, quotas, noisy neighbor |
| Compliance | audit events, export/delete |
| Regression | previous bugs never return |

## Mandatory Multi-Tenant Gates

1. Tenant A cannot read Tenant B records.
2. Tenant A cannot update Tenant B records.
3. Tenant A cannot list Tenant B users.
4. Tenant A cannot access Tenant B files.
5. Tenant A cannot search Tenant B content.
6. Tenant A cannot retrieve Tenant B vectors.
7. Tenant A cannot traverse Tenant B graph.
8. Tenant A cannot read Tenant B audit logs.
9. Tenant A cannot access Tenant B billing.
10. Platform admin access is audited.

## Required Gate Script Pattern

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "[MULTITENANT-GATE] start"

# static checks
# unit tests
# integration tests
# tenant isolation tests
# auth denial tests
# quota tests
# audit tests
# backup/restore tests
# claim hygiene checks

echo "[MULTITENANT-GATE] PASS"
```

## Red Team Checklist

Attempt to break:

- tenant_id injection
- missing tenant filter
- IDOR/BOLA access
- service account over-scope
- API key reuse
- search leakage
- vector leakage
- graph traversal leakage
- cache key collision
- admin impersonation misuse
- quota bypass
- audit deletion/tamper
- backup restore cross-contamination

## Claim Hygiene

Every final report must include:

```text
Allowed Claims
Forbidden Claims
Evidence
Known Limitations
Active Blockers with Closure Path
```

## Anti-Patterns

Avoid:

- tests that only check happy path
- no fixtures for Tenant A/Tenant B
- no negative authorization tests
- no red-team review
- no saved evidence
- claiming compliance without evidence

