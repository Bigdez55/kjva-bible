# SKILL_MULTI_REGION_CONSENSUS_REPLICATION_001 Playbook

## Purpose

Use this skill to design distributed consensus, replication, geo-distribution, failover, consistency modes, and correctness gates.

## Core Doctrine

Distributed correctness is one of the hardest parts of platform engineering. Do not fake it. Use explicit policy modes and proof gates.

## Required Outputs

- Node identity model
- Cluster membership model
- Replication log design
- Leader/quorum model
- Consistency policy modes
- Region placement strategy
- Failover strategy
- Conflict handling
- Jepsen-style test plan
- Proof gates

## Trigger Phrases

- consensus
- replication
- multi-region
- quorum
- leader election
- failover
- strict consistency
- eventual consistency
- distributed database
- split brain
- region outage

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/12_multi_region_consensus_replication/SKILL.md`.

## Full Imported Instructions

# Skill: Multi-Region Consensus and Replication

## Purpose

Use this skill to design distributed consensus, replication, geo-distribution, failover, consistency modes, and correctness gates.

## Trigger Phrases

- consensus
- replication
- multi-region
- quorum
- leader election
- failover
- strict consistency
- eventual consistency
- distributed database
- split brain
- region outage

## Core Doctrine

Distributed correctness is one of the hardest parts of platform engineering. Do not fake it. Use explicit policy modes and proof gates.

## Required Outputs

1. Node identity model.
2. Cluster membership model.
3. Replication log design.
4. Leader/quorum model.
5. Consistency policy modes.
6. Region placement strategy.
7. Failover strategy.
8. Conflict handling.
9. Jepsen-style test plan.
10. Proof gates.

## Policy Modes

Define behavior for:

```text
StrictSerializable
SnapshotSerializable
CausalSession
BoundedStaleness
EventualFast
CRDTLocalFirst
AnalyticSnapshot
StreamingExactlyOnce
```

## Consensus Requirements

Future distributed platform must define:

- node ID
- cluster ID
- region ID
- membership changes
- leader election
- quorum write
- quorum read where required
- log replication
- snapshotting
- replica promotion
- split-brain prevention
- committed write durability

## Replication Modes

| Mode | Use |
|---|---|
| sync quorum | money/billing/critical writes |
| async replica | analytics/read replicas |
| active-standby | DR |
| active-active | global availability |
| bounded staleness | dashboards/feeds |
| CRDT | local-first/edge conflict handling |

## Required Gates

1. Leader kill.
2. Follower kill.
3. Network partition.
4. Clock skew.
5. Delayed message.
6. Duplicate message.
7. Quorum loss.
8. Replica promotion.
9. Split-brain prevention.
10. No acknowledged committed write loss.
11. Region outage simulation.
12. RTO/RPO measurement.

## Anti-Patterns

Avoid:

- claiming distributed correctness without fault tests
- hiding consistency tradeoffs
- active-active without conflict policy
- no split-brain test
- no quorum loss behavior
- no recovery proof

