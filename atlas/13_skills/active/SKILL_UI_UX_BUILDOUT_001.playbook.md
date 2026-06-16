# ATLAS Multi-Tenant UI/UX Buildout Infrastructure Playbook

## Skill ID
SKILL_ATLAS_UI_UX_BUILDOUT_001

## Purpose
Turn ATLAS UI/UX work into a repeatable multi-tenant platform buildout process that connects tenant workspaces, repo connectors, skills, trigger routing, graph intelligence, knowledge vaulting, proof gates, and Vercel deployment.

## Trigger Conditions
- User asks to build out ATLAS UI/UX.
- User defines ATLAS as a multi-tenant platform.
- User asks to wire ATLAS to all repos for POC and use cases.
- User asks for backend connections so coding agents can tap skills/resources or submit repo commit/change events.
- User asks to normalize buildouts, optimize the process, or create infrastructure around skills.

## Hard Constraints
- Use `ATLAS` as the user-facing product name.
- Use `Atlas Graph Engine` and `Atlas Knowledge Vault`; do not reintroduce external subsystem names.
- Treat ATLAS as a tenant-scoped platform, not a local-only docs shell.
- Start the POC by wiring the user's repo estate as the first tenant corpus.
- Route repo commits, diffs, validation results, sync events, and agent reports through a tenant-scoped ingestion contract.
- Do not claim deploy readiness without `npm run lint`, `npm run build`, and a documented Vercel preview path.

## Workflow

### Observe
- Inspect the current ATLAS app, route tree, package scripts, Vercel config, repo sync packets, and repo twins.
- Identify the exact requested surface: tenant dashboard, repo connector map, graph explorer, knowledge vault, proof console, skill refinery, agent console, or deployment view.
- Check existing skills/templates before adding new artifacts.

### Orient
- Map each UI surface to tenant scope, backing repo connector, skill family, router intent, data source, and proof gate.
- Decide whether the work is product UI, operational workflow, router/skill infrastructure, tenant plumbing, or deployment plumbing.
- Identify naming drift, disconnected mockups, missing interactions, missing tenant isolation, or validation gaps.

### Decide
- Produce the minimum complete buildout package: product surface map, tenant/workspace model, repo connector POC map, route/component inventory, interaction contracts, skill bindings, proof bindings, and preview deployment plan.
- Define backend route contracts for tenant state, skills/resources, agent context, and repo event ingestion.
- Select validation gates before implementation.
- Add or update regression cases when a request exposes a repeated routing/buildout miss.

### Act
- Implement or update the Vercel app shell.
- Generate or refresh the tenant repo connector manifest.
- Add or update API route handlers for coding-agent access and repo-event ingestion when the UI surface needs backend access.
- Fill the reusable buildout templates for the target surface.
- Wire router/skill references when the UI introduces a durable workflow.
- Run validation and record results honestly.

## Required Outputs
- Product surface map
- Multi-tenant workspace model
- Repo connector POC map
- Agent backend API contracts
- Repo commit/change ingestion contract
- UI route and component inventory
- Interaction contracts
- Skill/router binding map
- Data and proof binding map
- Vercel preview plan
- Validation gates
- Buildout optimization backlog

## Validation Checklist
- `apps/frontend/shell` builds locally.
- `python3 infrastructure/scripts/core/atlas.py tenants --check` routes tenant repo wiring.
- `python3 infrastructure/scripts/core/atlas.py repo-event --repo ATLAS --event-type commit --check` validates repo event ingestion.
- ATLAS naming is used consistently.
- Proprietary graph/vault names are preserved.
- Each UI route has an owner skill and output contract.
- Each interactive control has a defined state, action, failure mode, and validation method.
- Coding agents have a documented context endpoint and repo-event ingestion endpoint.
- Repo commit/change events are tenant-scoped before graph/vault/proof propagation.
- Tenant boundaries and repo connector states are visible before external users are added.
- Vercel project root, install, build, and dev commands are documented.
