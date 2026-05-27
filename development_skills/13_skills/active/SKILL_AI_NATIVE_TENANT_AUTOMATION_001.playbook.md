# SKILL_AI_NATIVE_TENANT_AUTOMATION_001 Playbook

## Purpose

Use this skill to design AI assistants, agent workflows, tenant-aware automation, policy-safe AI operations, and optimization systems for multi-tenant platforms.

## Core Doctrine

AI in a multi-tenant platform must be tenant-aware, policy-bound, auditable, explainable, and prevented from crossing tenant boundaries.

## Required Outputs

- AI actor model
- Tenant context model
- Tool permission model
- Memory/data isolation model
- Audit model
- Human approval model
- Autonomy maturity ladder
- Safety/rollback plan
- Observability model
- Proof gates

## Trigger Phrases

- AI automation
- AI assistant
- agent
- AIOptimizer
- tenant automation
- support bot
- autonomous operations
- AI admin
- copilots
- workflow automation

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/15_ai_native_tenant_automation/SKILL.md`.

## Full Imported Instructions

# Skill: AI-Native Tenant Automation

## Purpose

Use this skill to design AI assistants, agent workflows, tenant-aware automation, policy-safe AI operations, and optimization systems for multi-tenant platforms.

## Trigger Phrases

- AI automation
- AI assistant
- agent
- AIOptimizer
- tenant automation
- support bot
- autonomous operations
- AI admin
- copilots
- workflow automation

## Core Doctrine

AI in a multi-tenant platform must be tenant-aware, policy-bound, auditable, explainable, and prevented from crossing tenant boundaries.

## Required Outputs

1. AI actor model.
2. Tenant context model.
3. Tool permission model.
4. Memory/data isolation model.
5. Audit model.
6. Human approval model.
7. Autonomy maturity ladder.
8. Safety/rollback plan.
9. Observability model.
10. Proof gates.

## AI Actor Types

| Actor | Role |
|---|---|
| Tenant Assistant | helps tenant users |
| Admin Assistant | helps tenant admins |
| Support Assistant | helps platform support |
| Ops Agent | monitors platform operations |
| AIOptimizer | recommends/executes optimization |
| Data Agent | indexes, labels, transforms data |
| Security Agent | detects anomalies |

## Autonomy Ladder

| Level | Mode | Meaning |
|---|---|---|
| L0 | Observe | read-only monitoring |
| L1 | Advisory | recommends actions |
| L2 | Supervised Apply | human approves |
| L3 | Guarded Autopilot | low-risk auto actions |
| L4 | Full Autopilot | policy-bounded automation |

## Required AI Context

Every AI action must include:

```json
{
  "tenant_id": "uuid",
  "actor_id": "uuid",
  "ai_agent_id": "uuid",
  "tool_name": "string",
  "permission_scope": "string",
  "input_refs": [],
  "output_refs": [],
  "policy_decision": "allowed|denied",
  "human_approval_id": "optional"
}
```

## Required Gates

1. AI cannot access wrong tenant data.
2. AI tool call requires permission.
3. AI action emits audit event.
4. High-risk action requires approval.
5. AI recommendation includes evidence.
6. AI memory is tenant-scoped.
7. AI cannot bypass RBAC/ABAC.
8. AI output does not leak another tenant.
9. Rollback path exists for automated change.
10. Autopilot blocked until gates pass.

## Anti-Patterns

Avoid:

- shared AI memory across tenants
- AI with platform admin privileges by default
- unlogged tool calls
- auto-executing destructive actions
- recommendations without evidence
- AI bypassing policy engine

