# ATLAS UI/UX Buildout Instructions

Use this prompt when turning ATLAS UI/UX work into an implementation-ready multi-tenant platform buildout.

```text
Build the ATLAS UI/UX as a Vercel-ready multi-tenant operational platform.

Rules:
- Use ATLAS as the user-facing product name.
- Use proprietary subsystem names only: Atlas Graph Engine and Atlas Knowledge Vault.
- Treat the user's repo estate as the first POC tenant corpus.
- Provide backend route contracts so coding agents can access tenant state, skills/resources, context packets, and repo-event ingestion.
- Repo commits and changes must enter ATLAS through a tenant-scoped ingestion contract before updating graph, vault, proof, or agent context.
- Do not create disconnected mockups. Every screen must map to tenant scope, repo connectors, skills, router intents, data/proof sources, interactions, and validation gates.
- Produce a product surface map, tenant workspace model, repo connector POC map, route/component inventory, interaction contracts, Vercel preview plan, and validation checklist.
- Validate with npm run lint and npm run build from apps/frontend/shell.
- Validate tenant wiring with python3 infrastructure/scripts/core/atlas.py tenants --check.

Required sections:
1. Surface objective
2. Tenant/workspace model
3. Repo connector map
4. Route map
5. Component inventory
6. Interaction contracts
7. Agent backend API contracts
8. Repo commit/change ingestion contract
9. Skill/router bindings
10. Data/proof bindings
11. Vercel deployment path
12. Validation gates
13. Optimization backlog
```
