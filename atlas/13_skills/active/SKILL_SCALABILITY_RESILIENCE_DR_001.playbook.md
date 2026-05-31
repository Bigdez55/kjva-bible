# SKILL_SCALABILITY_RESILIENCE_DR_001 Playbook

## Purpose

Use this skill to design scaling, resilience, redundancy, backups, restore, disaster recovery, degraded modes, and chaos testing for multi-tenant platforms.

## Core Doctrine

Do not claim high availability or no single point of failure until failure tests prove it. Resilience is not an aspiration; it is a set of tested behaviors.

## Required Outputs

- Scalability model
- Bottleneck analysis
- Resilience architecture
- Backup/restore plan
- DR plan
- Failover model
- Degraded mode behavior
- Capacity plan
- Chaos test plan
- Proof gates

## Trigger Phrases

- scalability
- resilience
- disaster recovery
- failover
- backup
- restore
- redundancy
- high availability
- chaos testing
- no single point of failure

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/11_scalability_resilience_dr/SKILL.md`.

## Full Imported Instructions

# Skill: Scalability, Resilience, and Disaster Recovery

## Purpose

Use this skill to design scaling, resilience, redundancy, backups, restore, disaster recovery, degraded modes, and chaos testing for multi-tenant platforms.

## Trigger Phrases

- scalability
- resilience
- disaster recovery
- failover
- backup
- restore
- redundancy
- high availability
- chaos testing
- no single point of failure

## Core Doctrine

Do not claim high availability or no single point of failure until failure tests prove it. Resilience is not an aspiration; it is a set of tested behaviors.

## Required Outputs

1. Scalability model.
2. Bottleneck analysis.
3. Resilience architecture.
4. Backup/restore plan.
5. DR plan.
6. Failover model.
7. Degraded mode behavior.
8. Capacity plan.
9. Chaos test plan.
10. Proof gates.

## Failure Classes

Address:

| Failure | Required Response |
|---|---|
| process crash | restart and recover |
| node failure | move workload or promote replica |
| disk corruption | detect and restore |
| database failure | failover/restore |
| region outage | regional failover later |
| queue backlog | backpressure and scaling |
| hot tenant | isolate and throttle |
| noisy neighbor | quota/rate limit |
| bad deploy | rollback |
| operator error | PITR/backups |
| secret leak | rotate and audit |
| tenant abuse | suspend/throttle |

## Backup Types

Define:

- full backup
- incremental backup
- tenant-scoped backup
- snapshot
- point-in-time restore later
- offsite backup
- immutable backup
- export package

## Required Gates

1. Backup created.
2. Restore tested.
3. Tenant-scoped restore tested.
4. Process crash recovery tested.
5. Bad deploy rollback tested.
6. Quota limits noisy tenant.
7. Queue backlog alert exists.
8. Corruption detection tested.
9. DR runbook exists.
10. RTO/RPO documented.

## Anti-Patterns

Avoid:

- backup without restore test
- HA claim with single database
- no tenant throttling
- no noisy neighbor plan
- no degraded mode
- no incident runbook

