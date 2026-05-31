# SKILL_ATLAS_MCP_001 — ATLAS MCP Server

## Purpose

Use this skill when the user needs ATLAS capabilities exposed to Claude Code or
Codex via the Model Context Protocol (stdio transport). The MCP server lives at
`apps/backend/atlas-mcp/` and imports directly from `apps/frontend/atlas/src/lib/` using relative
paths — no Next.js dependency, no ATLAS server required to be running.

## Pre-Gates

1. **Confirm node_modules** — if `apps/backend/atlas-mcp/node_modules/` is missing,
   surface the install command before claiming the server is runnable.
2. **Confirm atlas/src/lib is intact** — the MCP server imports
   `localAtlas.ts`, `atlas-data.ts`, and three graph modules. If these files
   move or are renamed, update the imports in `apps/backend/atlas-mcp/src/index.ts`.
3. **Never run npm install automatically** — present the command to the user.

## Server Start Steps

1. Install deps (user runs once):
   ```bash
   cd apps/atlas-mcp && npm install
   ```
2. Dev mode (tsx, no compile step):
   ```bash
   cd apps/atlas-mcp && npm run dev
   ```
3. Production build + run:
   ```bash
   cd apps/atlas-mcp && npm run build && npm start
   ```

## Tool Reference

| Tool | Required params | What it calls (source: `src/core.ts`) |
|------|-----------------|---------------------------------------|
| `atlas_graph_query` | none (mode defaults to full) | `buildGraph()`, `localGraph()`, `shortestPath()`, `contextPacket()` |
| `atlas_skill_get` | `skill_id` | `findSkillFile()`, `readText()` — reads `13_skills/active/SKILL_*.yaml` + `.playbook.md` |
| `atlas_trigger_route` | `phrase` | `routePhrase()` → `execFileSync("python3", ROUTER_CLI, phrase, "--json")` |
| `atlas_context_compile` | none (scope defaults to full) | `compileContext()` — direct filesystem scan |
| `atlas_knowledge_search` | `query` | `skillFiles()` + `skillRecord()` + `nodeMatches()` |

## Claude Code Config

Add to `.mcp.json` in the repo root (or `~/.claude.json` for global):

```json
{
  "mcpServers": {
    "atlas": {
      "command": "npx",
      "args": ["tsx", "apps/backend/atlas-mcp/src/index.ts"],
      "env": {}
    }
  }
}
```

Or after `npm run build`:

```json
{
  "mcpServers": {
    "atlas": {
      "command": "node",
      "args": ["apps/backend/atlas-mcp/dist/index.js"],
      "env": {}
    }
  }
}
```

## Forbidden Actions

- Do not switch to HTTP/SSE transport without explicit user request.
- Do not use `@/` path aliases from inside `apps/backend/atlas-mcp/` — use relative paths only.
- Do not assert graph or skill state without calling the appropriate tool.
- Do not run `npm install` automatically.

## Required Outputs

1. `apps/backend/atlas-mcp/package.json`
2. `apps/backend/atlas-mcp/tsconfig.json`
3. `apps/backend/atlas-mcp/src/index.ts` — stdio MCP server with 5 tools
4. `SKILL_ATLAS_MCP_001.yaml` + `SKILL_ATLAS_MCP_001.playbook.md`
5. Registry + router wired (skills.registry.yaml total updated, trigger_router.yaml target + intent added)
6. `.mcp.json` config block
7. Install command surfaced for user

## Validation

After wiring registry + router:
```bash
python3 25_automation/validate_skill_router_integration.py
```

Expected: `PASS: skill router integration (180 active skills — all registered and routed)`
