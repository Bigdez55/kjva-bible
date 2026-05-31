# SKILL_RUNTIME_ORCHESTRATION_001 Playbook

## Purpose

Use this skill to design deployment and orchestration for multi-tenant platforms across local, Docker Compose, GEN.OS sovereign orchestration, optional Kubernetes, public cloud, hybrid cloud, and on-prem environments.

## Core Doctrine

A production platform needs a Kubernetes-class orchestration plane, but it does not need Kubernetes as the canonical dependency. For sovereign ecosystems: - xOrchestra is a future GEN.OS orchestration layer and is not a current Storbits dependency. - Kubernetes is optional compatibility. - Docker Compose is acceptable for local development. - Correctness must never depend on the orchestrator.

## Required Outputs

- Runtime mode matrix
- Orchestrator abstraction
- xOrchestra orchestration design
- Optional Kubernetes adapter design
- Service placement model
- Storage volume model
- Config/secrets model
- Service discovery model
- Health supervision model
- Deployment/rollback model
- Proof gates

## Trigger Phrases

- orchestration
- Kubernetes
- GEN.OS
- sovereign orchestration
- deployment platform
- runtime
- scheduler
- XMesh
- service discovery
- operator
- Docker Compose
- cloud deployment
- on-prem

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/04_runtime_orchestration/SKILL.md`.

## Full Imported Instructions

# Skill: Runtime Orchestration — Standalone / Docker Compose / Optional Kubernetes / Future xOrchestra First

## Purpose

Use this skill to design deployment and orchestration for multi-tenant platforms across local, Docker Compose, GEN.OS sovereign orchestration, optional Kubernetes, public cloud, hybrid cloud, and on-prem environments.

## Trigger Phrases

- orchestration
- Kubernetes
- GEN.OS
- sovereign orchestration
- deployment platform
- runtime
- scheduler
- XMesh
- service discovery
- operator
- Docker Compose
- cloud deployment
- on-prem

## Core Doctrine

A production platform needs a Kubernetes-class orchestration plane, but it does not need Kubernetes as the canonical dependency.

For sovereign ecosystems:

- xOrchestra is a future GEN.OS orchestration layer and is not a current Storbits dependency.
- Kubernetes is optional compatibility.
- Docker Compose is acceptable for local development.
- Correctness must never depend on the orchestrator.

## Required Outputs

1. Runtime mode matrix.
2. Orchestrator abstraction.
3. xOrchestra orchestration design.
4. Optional Kubernetes adapter design.
5. Service placement model.
6. Storage volume model.
7. Config/secrets model.
8. Service discovery model.
9. Health supervision model.
10. Deployment/rollback model.
11. Proof gates.

## Runtime Modes

Support or explicitly exclude:

| Mode | Use |
|---|---|
| Local Process | development, Acer node, laptop |
| Docker Compose | dev/test/lab |
| Standalone / Docker Compose / Optional Kubernetes / Future xOrchestra | canonical sovereign production |
| Kubernetes Adapter | enterprise compatibility |
| Cloud Managed | optional customer deployment |
| On-Prem | regulated/private deployment |
| Edge/NAS | local storage/edge workloads |

## Orchestrator Provider Interface

Define:

```text
OrchestratorProvider
  local
  docker_compose
  genos
  kubernetes_optional
  cloud_optional
```

Required interface capabilities:

```text
schedule_workload()
stop_workload()
restart_workload()
health_check()
register_service()
resolve_service()
mount_volume()
read_config()
read_secret()
emit_event()
collect_metrics()
rollout()
rollback()
scale()
```

## Standalone / Docker Compose / Optional Kubernetes / Future xOrchestra Components

| Component | Responsibility |
|---|---|
| GEN.OS Workload Scheduler | Places services across nodes |
| XMesh Service Registry | Service discovery and routing |
| Forge Deploy Controller | Build, release, rollback, rollout |
| Storbits Volume Manager | Persistent local/NAS/cloud-backed volumes |
| Health Supervisor | Node/process/service health |
| Sealed Config Plane | Config and secrets |
| Tenant Isolation Domains | Runtime boundaries |
| Observability Plane | Metrics/logs/traces/evidence |
| Policy Router | Routes by consistency, region, tenant, latency |

## Kubernetes Compatibility Position

Kubernetes is:

- optional deployment target
- interoperability bridge
- enterprise adoption adapter
- comparison benchmark
- not the canonical control plane

## Required Gates

1. Local mode starts service.
2. Docker Compose starts service.
3. xOrchestra provider contract documented.
4. Optional Kubernetes adapter documented.
5. Service discovery works in chosen MVP mode.
6. Health check detects failed service.
7. Restart recovers service.
8. Config loaded without hardcoded secrets.
9. Rollback path defined.
10. BitCore/database correctness independent from orchestrator.

## Anti-Patterns

Avoid:

- hard dependency on Kubernetes when sovereignty is required
- orchestrator-specific logic inside business services
- storing secrets in env files committed to repo
- assuming restart equals recovery
- using orchestration to hide database correctness gaps



## xOrchestra Future Optional Path

xOrchestra is not done yet. Treat it as a future GEN.OS orchestration path, not a current dependency.

Current Storbits runtime priority:

1. Local process mode.
2. Docker Compose mode.
3. Standalone server deployment mode.
4. Optional Kubernetes adapter later for enterprise compatibility.
5. Future xOrchestra adapter after xOrchestra is built and stable.

Do not require GEN.OS, xOrchestra, or XMesh to build Storbits Local Node, Storbits SaaS, or the standalone omni-database.

## Current Orchestrator Provider Contract

```text
OrchestratorProvider
  provider = "local" | "docker_compose" | "standalone" | "kubernetes_optional" | "xorchestra_future"
```

The `xorchestra_future` provider must remain a roadmap placeholder until xOrchestra exists.

## Current Runtime Gates

1. Local mode works.
2. Docker Compose mode works.
3. Standalone deployment path documented.
4. Kubernetes marked optional.
5. xOrchestra marked future/not complete.
6. No current Storbits gate requires GEN.OS.
7. Database correctness independent from runtime/orchestrator.

## xOrchestra Provider Contract

Create or document an adapter:

```text
OrchestratorProvider
  provider = "local" | "docker_compose" | "xorchestra" | "kubernetes_optional"

  schedule_workload()
  stop_workload()
  restart_workload()
  health_check()
  register_service()
  resolve_service()
  mount_volume()
  read_config()
  read_secret()
  emit_event()
  collect_metrics()
  rollout()
  rollback()
  scale()
  quarantine()
```

## xOrchestra Gates

1. Local mode still works without xOrchestra.
2. Docker Compose dev mode still works.
3. xOrchestra provider contract exists.
4. Kubernetes provider is marked optional.
5. Kubernetes is not required for production sovereignty.
6. Service discovery path through XMesh is defined.
7. Health supervisor restart behavior is defined.
8. Forge deployment/rollback path is defined.
9. Persistent volume contract is defined.
10. Tenant isolation domain model is defined.

