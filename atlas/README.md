# ATLAS

ATLAS is the operational workbench and living development intelligence layer: reusable software development protocols, agent skills, architecture models, repo twins, Bookworm indexing, truth state management, diagram atlases, evidence ledgers, command routing, and one-shot repo starter workflows.

This repository is the central master source for reusable skills, templates, schemas, agents, prompts, and governance rules. It can be copied into every project repository as a local `atlas/` folder.

## Core identity

ATLAS is not just documentation. It is the operating layer for building software from ideation through deployment.

It provides:

1. Intent compilation from raw idea to specs
2. Repo starter packets for new projects
3. Architecture digital twins for living software models
4. Visual architecture atlases for diagrams and maps
5. Skill refinery loops for continuous improvement
6. Bookworm as the knowledge indexing engine (Bookworm controls ATLAS per Layer 1 lock)
7. Repo twins as living copies of project state
8. Context compiler packets for coding agents
9. Proof matrix evidence for requirements, tests, docs, and deployment
10. Preview deployment factory for Vercel, GitHub Pages, local preview, Docker, and other targets

ATLAS is the central nervous system of the SUPER C biome. It is controlled by Bookworm (Citadel Chief Archivist) per the canonical office layer in GEN.OS/Citadel. ATLAS does not own, define, or rank above Bookworm.

## Most important rule

Generated documentation is not the highest source of truth.

Agents must rank sources in this order:

1. Current code and repo tree
2. Truth state files
3. Architecture digital twin
4. Architecture models and component graphs
5. Component contracts and API contracts
6. Traceability and proof matrix
7. Diagram registry and architecture atlas
8. Change ledger and decision ledger
9. ADRs
10. Verification results
11. Generated documentation
12. README files

## Quick install into a local repository

From the parent folder that contains your local repo:

```bash
tar -xzf ATLAS_Apex_v2_1.tar.gz
cd atlas
git init
git add .
git commit -m "Initialize ATLAS v2.1"
```

To copy this into another project repo:

```bash
rsync -a atlas/ /path/to/project/atlas/
```

## Running ATLAS (always-on service)

ATLAS runs as a persistent **local service**, not an Electron desktop app. Two launchd
LaunchAgents keep it alive: `com.atlas.web` (Next.js standalone, port **4317**) and
`com.atlas.mcp` (MCP server, port **4318**). Both auto-start at login and auto-restart
on crash. Electron is deprecated — use the service runner instead.

**Prerequisites:** a production build must exist first.

```bash
cd apps/frontend/shell
npm run build          # creates .next/standalone/server.js
```

**Install + manage via `infrastructure/service/atlas-service.sh`:**

```bash
cd infrastructure/service

./atlas-service.sh install     # one-time: write launchd plists, load + start both agents
./atlas-service.sh status      # launchd state + HTTP health codes for web:4317 and mcp:4318
./atlas-service.sh logs web    # tail logs (web|mcp)
./atlas-service.sh restart     # after a rebuild
./atlas-service.sh stop        # stop both agents
./atlas-service.sh start       # start both agents (after a prior install)
./atlas-service.sh uninstall   # stop, unload, and remove plists
```

The web service binds to `http://127.0.0.1:4317` (PORT is injected by the launchd
plist — running `npm run start` directly without a PORT env var defaults to 3000).
The MCP service binds to `http://127.0.0.1:4318` (PORT injected similarly; code
default is 3001).

Logs are written to `~/.atlas/logs/{web,mcp}.{out,err}.log`.

For remote access (Tailscale private mesh or Cloudflare Tunnel), see
[`infrastructure/service/REMOTE_ACCESS.md`](infrastructure/service/REMOTE_ACCESS.md).

**Status:** the local always-on service is live and working. Public release is gated
(`BLOCK_PUBLIC_RELEASE` — auth-disabled local-identity posture; Cloudflare Access or
`ATLAS_AUTH_ENABLED=1` required before any public exposure).

## One shot command pattern

The agent command protocol (Apex Protocol — ATLAS's SDLC) supports:

```text
/apex:route
/apex:starter
/apex:intake
/apex:spec
/apex:diagram
/apex:scaffold
/apex:slice
/apex:verify
/apex:deploy_preview
/apex:sync_docs
/apex:detect_drift
/apex:improve_skill
/apex:package_repo
/apex:platform_build
/apex:repo_audit
/apex:ui_wiring
/apex:dataflow_map
/apex:refactor_plan
/apex:runtime_verify
```

## Bookworm role

Bookworm is the living repository intelligence engine that ATLAS serves. It ingests files, diagrams, ADRs, commits, skills, mistakes, truth state files, and documentation so that agents can retrieve the real current state of every project. ATLAS is the workbench/interface surface that receives Bookworm-governed knowledge and execution context; ATLAS may visualize, route, and package Bookworm outputs but does not control Bookworm.
