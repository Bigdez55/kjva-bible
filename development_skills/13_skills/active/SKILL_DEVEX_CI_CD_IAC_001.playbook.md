# SKILL_DEVEX_CI_CD_IAC_001 Playbook

## Purpose

Use this skill to design developer workflow, environments, CI/CD, IaC, migrations, branch discipline, release gates, and reproducible deployment for multi-tenant platforms.

## Core Doctrine

A multi-tenant platform must be reproducible. Local, staging, and production should not be hand-built differently. Every environment needs clear gates and rollback.

## Required Outputs

- Environment strategy
- Local dev setup
- CI pipeline
- CD/release pipeline
- IaC structure
- Migration strategy
- Secret/config strategy
- Branch/commit discipline
- Rollback strategy
- Proof gates

## Trigger Phrases

- CI/CD
- infrastructure as code
- IaC
- developer experience
- deployment pipeline
- environments
- migrations
- release gates
- Terraform
- Helm
- GitOps
- Forge deploy

## Source Skill

Canonical imported source: `16_knowledge/external_collateral/security_updates_2026-05-20/multi_tenant_platform_skills-2/10_devex_ci_cd_iac/SKILL.md`.

## Full Imported Instructions

# Skill: DevEx, CI/CD, and Infrastructure as Code

## Purpose

Use this skill to design developer workflow, environments, CI/CD, IaC, migrations, branch discipline, release gates, and reproducible deployment for multi-tenant platforms.

## Trigger Phrases

- CI/CD
- infrastructure as code
- IaC
- developer experience
- deployment pipeline
- environments
- migrations
- release gates
- Terraform
- Helm
- GitOps
- Forge deploy

## Core Doctrine

A multi-tenant platform must be reproducible. Local, staging, and production should not be hand-built differently. Every environment needs clear gates and rollback.

## Required Outputs

1. Environment strategy.
2. Local dev setup.
3. CI pipeline.
4. CD/release pipeline.
5. IaC structure.
6. Migration strategy.
7. Secret/config strategy.
8. Branch/commit discipline.
9. Rollback strategy.
10. Proof gates.

## Environment Model

```text
local
dev
test
staging
production
sovereign/private deployment
```

## Pipeline Stages

Required:

1. lint/static checks
2. unit tests
3. integration tests
4. tenancy isolation tests
5. security scans
6. migration dry-run
7. build artifact
8. deploy to test/staging
9. smoke tests
10. release approval where needed
11. production deploy
12. post-deploy verification

## IaC Areas

Define infrastructure for:

- networking
- compute/runtime
- storage
- database
- secrets
- identity
- observability
- backups
- queues/events
- tenant provisioning resources
- optional Kubernetes adapter
- GEN.OS deployment descriptors where applicable

## Required Gates

1. One-command local dev setup.
2. CI fails on tests.
3. CI runs tenant isolation tests.
4. Migration dry-run passes.
5. Secrets not committed.
6. Deployment artifact reproducible.
7. Rollback command documented.
8. Staging smoke test passes.
9. Production checklist exists.
10. Release evidence captured.

## Anti-Patterns

Avoid:

- manual production changes
- snowflake environments
- migrations with no rollback
- untested tenant migrations
- secrets in repo
- deploy without smoke gates

