# Parallel Multi-Agent Execution via Git Worktree Isolation

> Promoted from ATLAS production audit 2026-05-29.

## Purpose

Run 4-8 specialized agents in parallel on the same repo without file lock conflicts
or merge corruption. Each agent works in its own git worktree on its own branch.

## The Pattern

### 1. Pre-create branches (single message)

```bash
cd /path/to/repo
for branch in storage auth tenant-iso audit-ratelimit ci-gate ux design resilience staging; do
  git branch "prod-ready/$branch" main
done
```

### 2. Phase order

```
C.0 (sequential, 1 agent): storage schema lands first
       └─ publishes db/types.ts (BETA UNBLOCK CONTRACT)
            ↓
C.1 (parallel, 6 agents): each in its own worktree
       ├─ auth         → publishes auth/types.ts (BETA UNBLOCK CONTRACT)
       ├─ tenant-iso   → consumes auth/types
       ├─ audit-ratelimit → consumes db/types + auth/types
       ├─ ux           → consumes auth/types
       ├─ design       → standalone (only design tokens + a11y)
       └─ resilience   → standalone (only error boundaries + circuit breaker)
            ↓
C.2 (sequential, 1 agent): CI workflow + release-gate-assertion
```

### 3. Create worktrees just before launching agents

```bash
for branch in auth tenant-iso audit-ratelimit ux design resilience; do
  git worktree add "/tmp/atlas-worktrees/$branch" "prod-ready/$branch"
done
```

### 4. Path-ownership map (fix-assignments.yaml)

```yaml
agents:
  apex-systems-architect:
    branch: prod-ready/auth
    paths:
      - apps/frontend/shell/src/lib/auth/types.ts        # BETA UNBLOCK
      - apps/frontend/shell/src/lib/auth/session.ts
      - apps/frontend/shell/src/proxy.ts                  # or middleware.ts
      - apps/frontend/shell/src/app/api/auth/**
      - apps/frontend/shell/next.config.ts
      - apps/frontend/shell/electron/main.mjs
  reliability-security-sentinel:
    branch: prod-ready/tenant-iso
    paths:
      - apps/frontend/shell/src/lib/auth/require-session.ts
      - apps/frontend/shell/src/lib/auth/require-tenant.ts
      - apps/frontend/shell/src/app/api/**/route.ts       # NOT auth/*
      - apps/frontend/shell/tests/cross-tenant-isolation.test.ts
  # ... etc

shared_files:
  apps/frontend/shell/package.json:
    chain: [storage, audit-ratelimit, ci-gate]  # in this order
  apps/frontend/shell/electron/main.mjs:
    chain: [auth]  # single owner — others propose as PR to auth's branch
```

### 5. Launch agents in single message (parallel block)

```
Send ONE message with 6 Agent tool calls.
Each Agent prompt includes:
  - worktree path: /tmp/atlas-worktrees/<branch>
  - branch name: prod-ready/<branch>
  - exhaustive path-ownership list
  - "DO NOT TOUCH" exclusion list
  - read files first (audit findings, fix assignments, contract types)
  - commit + push command at end
```

### 6. Merge into staging (sequential, by coordinator)

```bash
git worktree add /tmp/atlas-worktrees/staging prod-ready/staging
cd /tmp/atlas-worktrees/staging
git reset --hard origin/prod-ready/storage  # base
for branch in auth tenant-iso audit-ratelimit ux design resilience; do
  git merge --no-ff -m "merge: prod-ready/$branch into staging" "origin/prod-ready/$branch"
done
# Expect at most 1-2 documented conflicts (package.json test script union, etc.)
```

### 7. Resolve merge conflicts manually

The shared-file chain (e.g., package.json test script) gets a manual union by the
coordinator. Document in the merge commit.

### 8. Push staging + final verification

```bash
git push origin prod-ready/staging
# Then run full test suite + build before any gate flip
```

## Anti-Patterns

### All agents share the same working directory

```bash
# WRONG — agents step on each other's files
cd /repo
# 6 agents in parallel editing /repo
```

### No path-ownership map

```yaml
# WRONG — two agents both edit src/middleware.ts
agent1: [src/middleware.ts]
agent2: [src/middleware.ts]
```

### 8+ coupled agents in parallel (fix phase)

Per SKILL_PARALLEL_DEPLOY_001: read-only audits scale to 8; fix phases should
stay ≤ 6 with worktree isolation. Beyond 6, coordination overhead dominates.

### Coordinator touches code

Coordinator should ONLY:
- Pre-create branches + worktrees
- Merge branches into staging
- Resolve documented merge conflicts in shared-file chain
- Flip canonical truth file (e.g., production-readiness.ts) AFTER all evidence

Coordinator should NEVER write feature code (that's specialist agents' job).

## Validation Gates

| Gate | Pass |
|---|---|
| Branches pre-created | `git branch -l prod-ready/*` shows N+1 entries (N agents + staging) |
| Worktrees launched | `git worktree list` shows N+1 entries |
| Each agent commits on its own branch | `git log prod-ready/<branch> --oneline` shows >=1 commit |
| Staging merge conflicts ≤ shared-chain | only files in `shared_files:` chain have conflicts |
| Final test suite passes on staging | full `npm test && npm run build` exit 0 |

## Incident Record

| Date | Project | Pattern | Result |
|---|---|---|---|
| 2026-05-29 | ATLAS | 8 worktrees, 6 parallel C.1 agents | 0 unplanned merge conflicts; 4-hour parallel completion vs estimated 12-hour serial |
