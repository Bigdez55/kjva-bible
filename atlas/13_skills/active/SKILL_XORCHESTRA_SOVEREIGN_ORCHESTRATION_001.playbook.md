# SKILL_XORCHESTRA_SOVEREIGN_ORCHESTRATION_001 Playbook

## Purpose

Use this skill only when planning future GEN.OS integration or when the user explicitly asks to work on xOrchestra.  Do not invoke this skill as a current dependency for Storbits Local Node, Storbits standalone SaaS, or the standalone omni-database build.

## Core Doctrine

Storbits is a standalone omni-database. xOrchestra may eventually become a GEN.OS-native orchestration layer that can run Storbits, but this is future integration work and must not block Storbits development.

## Required Outputs

- Security-aware implementation plan
- Proof gates

## Trigger Phrases

- xOrchestra
- build xOrchestra
- GEN.OS orchestration
- future GEN.OS adapter
- replace Kubernetes later
- sovereign orchestration later
- wire Storbits into GEN.OS later

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/17_xorchestra_sovereign_orchestration/SKILL.md`.

## Full Imported Instructions

# Skill: xOrchestra Future Sovereign Orchestration Adapter

## Purpose

Use this skill only when planning future GEN.OS integration or when the user explicitly asks to work on xOrchestra.

Do not invoke this skill as a current dependency for Storbits Local Node, Storbits standalone SaaS, or the standalone omni-database build.

## Current Status

xOrchestra is not done yet.

Therefore:

- xOrchestra is a future optional orchestration path.
- GEN.OS is not required for Storbits right now.
- Storbits must run standalone first.
- Kubernetes may remain optional compatibility later.
- No Storbits public-release gate may require xOrchestra.

## Trigger Phrases

Invoke only when the user says:

- xOrchestra
- build xOrchestra
- GEN.OS orchestration
- future GEN.OS adapter
- replace Kubernetes later
- sovereign orchestration later
- wire Storbits into GEN.OS later

Do not invoke for ordinary Storbits standalone work.

## Core Doctrine

Storbits is a standalone omni-database.

xOrchestra may eventually become a GEN.OS-native orchestration layer that can run Storbits, but this is future integration work and must not block Storbits development.

## Future Adapter Responsibilities

When xOrchestra is ready, it may provide:

| Capability Class | xOrchestra Future Responsibility |
|---|---|
| workload scheduling | place services, jobs, agents, and stateful nodes |
| service discovery | route through future GEN.OS/XMesh patterns |
| health checks | health supervisor and restart/quarantine policies |
| rolling updates | future Forge deployment controller |
| rollback | future Forge rollback and release evidence |
| stateful workloads | Storbits volume binding and node identity |
| config/secrets | future sealed GEN.OS config plane |
| autoscaling | policy-based scaling by load/tenant/region |
| namespaces | tenant/workspace/isolation domains |
| network policy | policy routes |
| controllers | GEN.OS control agents |
| observability | logs, metrics, traces, health, proof evidence |

## Future OrchestratorProvider Contract

```text
OrchestratorProvider
  name = "xorchestra_future"
  capabilities()
  schedule_workload(spec)
  stop_workload(workload_id)
  restart_workload(workload_id)
  health_check(workload_id)
  register_service(service_spec)
  resolve_service(service_name, tenant_context)
  mount_volume(volume_spec)
  read_config(config_ref)
  read_secret(secret_ref)
  emit_event(event)
  collect_metrics(scope)
  rollout(release_spec)
  rollback(release_id)
  scale(workload_id, policy)
  quarantine(workload_id, reason)
```

## Current Gates

1. Storbits docs clearly state xOrchestra is future optional.
2. Storbits docs do not require GEN.OS right now.
3. Local mode works without xOrchestra.
4. Docker Compose mode works without xOrchestra.
5. Standalone deployment path exists without xOrchestra.
6. Kubernetes is optional, not canonical.
7. xOrchestra integration is placed in the future implementation queue only.

## Claim Hygiene

Allowed now:

- xOrchestra is planned as a future optional GEN.OS orchestration path.
- Storbits can be designed to accept an xOrchestra adapter later.

Forbidden now:

- xOrchestra is complete.
- xOrchestra replaces Kubernetes today.
- Storbits requires xOrchestra.
- Storbits requires GEN.OS.
- public release depends on GEN.OS-native auth.

