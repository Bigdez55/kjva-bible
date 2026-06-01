# SKILL_OBSERVABILITY_SRE_INCIDENT_RESPONSE_001 Playbook

## Purpose

Use this skill to design logs, metrics, traces, SLOs, alerts, dashboards, incident response, runbooks, and reliability practices for multi-tenant platforms.

## Core Doctrine

You cannot operate what you cannot see. Multi-tenant systems require observability by tenant, service, region, workload, and cost profile.

## Required Outputs

- Observability architecture
- Logging schema
- Metrics inventory
- Trace propagation model
- SLO/SLI model
- Alert rules
- Dashboard requirements
- Incident response runbooks
- Postmortem template
- Proof gates

## Trigger Phrases

- observability
- monitoring
- logs
- metrics
- traces
- SLO
- SLI
- incident response
- alerting
- runbooks
- reliability
- SRE

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/08_observability_sre_incident_response/SKILL.md`.

## Full Imported Instructions

# Skill: Observability, SRE, and Incident Response

## Purpose

Use this skill to design logs, metrics, traces, SLOs, alerts, dashboards, incident response, runbooks, and reliability practices for multi-tenant platforms.

## Trigger Phrases

- observability
- monitoring
- logs
- metrics
- traces
- SLO
- SLI
- incident response
- alerting
- runbooks
- reliability
- SRE

## Core Doctrine

You cannot operate what you cannot see. Multi-tenant systems require observability by tenant, service, region, workload, and cost profile.

## Required Outputs

1. Observability architecture.
2. Logging schema.
3. Metrics inventory.
4. Trace propagation model.
5. SLO/SLI model.
6. Alert rules.
7. Dashboard requirements.
8. Incident response runbooks.
9. Postmortem template.
10. Proof gates.

## Required Log Fields

```json
{
  "timestamp": "timestamp",
  "level": "info|warn|error",
  "service": "service-name",
  "environment": "dev|staging|prod",
  "tenant_id": "uuid optional",
  "actor_id": "uuid optional",
  "request_id": "uuid",
  "trace_id": "uuid",
  "event": "string",
  "message": "string",
  "error_code": "string optional"
}
```

## Required Metrics

At minimum:

```text
requests_total
request_latency_ms
errors_total
auth_denials_total
tenant_quota_denials_total
tenant_storage_bytes
tenant_api_requests_total
tenant_active_users
database_write_latency_ms
database_read_latency_ms
job_queue_depth
audit_events_total
billing_usage_events_total
backup_success_total
restore_success_total
```

## SLO Examples

| Area | Example SLO |
|---|---|
| API availability | 99.9% monthly |
| API latency | p95 below target |
| Tenant isolation | 100% denial gate pass |
| Backups | 100% scheduled backup success |
| Restore | tested per release |
| Audit | 100% privileged actions audited |

## Required Gates

1. Request logs include request_id.
2. Tenant actions include tenant_id where safe.
3. Trace ID propagates across service boundary.
4. Metrics endpoint returns core metrics.
5. Alert fires for high error rate.
6. Alert fires for auth denial spike.
7. Backup failure alert exists.
8. Tenant usage dashboard exists or is specified.
9. Incident runbook exists.
10. Postmortem template exists.

## Anti-Patterns

Avoid:

- logs with secrets
- logs without tenant context
- no tenant-level dashboards
- alerting only on infrastructure, not business events
- no restore testing
- no postmortem process

