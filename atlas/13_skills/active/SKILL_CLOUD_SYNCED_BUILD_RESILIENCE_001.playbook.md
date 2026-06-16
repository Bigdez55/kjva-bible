# Cloud-Synced Build Resilience (Next.js / bundlers over OneDrive/iCloud)

> Canonical skill playbook. Source of truth: `platform/sdlc/13_skills/active/SKILL_CLOUD_SYNCED_BUILD_RESILIENCE_001.playbook.md`
> Human-authored. Companion to [[always-on-service-resource-discipline]], [[verify-validate]], [[onedrive-git-hazard]].

**Summary.** Building a JS/TS app whose repo lives on a **cloud-synced filesystem** (OneDrive
CloudStorage, iCloud Drive, Dropbox) has failure modes a normal build doesn't. This skill captures
them and the working recipe, distilled from a multi-hour ATLAS build saga where `next build --webpack`
hung silently and repeatedly while `turbopack` built clean in ~2 minutes.

## When to invoke

Triggers (any of):
- A build (`next build`, webpack, vite, tsc) **hangs at 0% CPU** with a frozen log and no output.
- "the build is stuck / stalled / taking forever / never finishes".
- The repo is under `CloudStorage/`, `OneDrive`, `iCloud`, `Dropbox`, or any sync-on-access FS.
- A build was killed and now the app won't start (missing `.next/standalone`, `dist/`, etc.).
- Choosing/normalizing a build pipeline for a cloud-synced or always-on-service project.

## Core findings + directives

### 1. Prefer turbopack (or esbuild/vite) over webpack on cloud-synced repos
- **`next build --webpack` hung at "Creating an optimized production build…", 0% CPU, no output, for
  15+ min, reproducibly** — on both node 25 and node 22 LTS, with a clean `.next`, node_modules
  hydrated (reads fast), and SWC present. **`next build --turbopack` built the same app clean in ~2 min.**
- Directive: on cloud-synced repos, **default the build to turbopack** (`next build --turbopack`); keep
  a `build:webpack` fallback. Webpack's many-small-file I/O pattern interacts badly with sync-on-access FS.

### 2. A killed/interrupted `next build` WIPES the prior output — never kill it carelessly
- `next build` clears `.next` (or its output subtrees) at the START, then regenerates. If killed
  mid-run, you're left with **no `.next/standalone/server.js`** → an always-on service that runs from
  it **breaks on its next restart**. Before killing or re-running a build, know that the OLD build is
  already gone. Disable/stop the dependent service first so a crash-respawn doesn't fail-loop.

### 3. Monitor builds by OUTPUT/file-growth, not CPU alone
- Bundlers do work in **worker processes/threads** separate from the `next build` parent. A watcher
  that sums CPU of only the `next build` process sees ~0% and **false-positives "STALLED"**, killing a
  build that was actually progressing. Detect stall by a **frozen `.next` file count + frozen log** over
  several minutes — not by CPU. (This skill's author killed two progressing builds this way.)

### 4. Pin an LTS node for builds; bleeding-edge node breaks bundlers
- The build ran under **node v25.6.1** (bleeding edge). Next 16 / its toolchain is tested against LTS.
  Use an LTS node (e.g. `node@22`) for builds: `export PATH="/opt/homebrew/opt/node@22/bin:$PATH"`.
  (Runtime can stay on the system node; this is a build-time pin.)

### 5. Give the build heap; remove contention
- `NODE_OPTIONS=--max-old-space-size=4096` for the build. Stop the running dev service first (frees
  `.next` handles + RAM + reduces the cloud-sync write-churn the build itself generates).

### 6. Distinguish "slow" from "stalled" empirically before reacting
- 0% CPU can be **I/O-wait** (progressing slowly) OR a true hang. Test the FS directly: `rm -rf .next`
  finishing in ~1s proves the FS isn't globally hung; `time cat` of sample `node_modules` files proves
  reads aren't dehydrated/slow. Rule causes out (OOM? RAM free → no. dehydration? reads fast → no.
  node version? try LTS. cache corruption? `rm -rf .next`. bundler? try turbopack) before a workaround.

## Recipe — reliable build on a cloud-synced repo

```bash
# 1. Stop the dependent service (frees handles + RAM + reduces sync churn)
atlas-service.sh disable web        # or: stop the dev server

# 2. Clean slate (cheap FS test: this should finish in ~1s)
rm -rf .next

# 3. Build with turbopack, LTS node, heap — backgrounded
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
NODE_OPTIONS=--max-old-space-size=4096 next build --turbopack

# 4. Verify OUTPUT exists (not just exit code): .next/standalone/server.js + .next/BUILD_ID
# 5. Re-enable the service from the fresh build
atlas-service.sh enable web
```

## Detection symptoms

- Build log frozen at the first "building…" line; `.next` has no growing output; build PID at 0% CPU.
- App fails to start with "Missing .next/standalone/server.js" after an interrupted build.
- Build "completes exit 0" but produced no output (the wrapper was killed, not the build).

## Anchor episode

**ATLAS, 2026-06-03/04.** Rebuilding the Next 16 standalone to ship the front-end consolidation:
`npm run build` (`next build --webpack`) hung at "Creating an optimized production build…" at 0% CPU,
log frozen, for 15+ min — twice — wiping `.next` each time and leaving the always-on web service with
no standalone to restart from. Ruled out: OOM (40% RAM free), corrupt cache (clean `.next` still hung),
node 25 (node 22 LTS hung too), dehydration (node_modules reads 0.02s), missing SWC (121MB binary
present), FS hang (`rm -rf .next` finished in 1s). Fix: **`next build --turbopack` on node@22 built
clean in ~2 min** with all routes compiled (incl. the previously-404 `/api/settings` + `/api/auth/session`).
Also discovered the CPU-only build watcher was false-flagging progressing builds as STALLED. Permanent
changes: `package.json` `build` → turbopack (kept `build:webpack` fallback).

## Anti-patterns

- Defaulting to `next build --webpack` on a cloud-synced repo "because that's what was there."
- Killing a hanging build without realizing it already wiped the prior output (breaks the service).
- A CPU-only stall detector (misses worker-process progress → kills good builds).
- Building on bleeding-edge node and blaming the app when the toolchain hangs.
- Treating 0% CPU as definitely-stalled without the FS/read/heap/bundler differential.

## Cross-refs

- `always-on-service-resource-discipline` — the service that depends on the build output (don't leave it broken).
- `onedrive-git-hazard` — the same cloud-synced FS class, for git rather than builds.
- `verify-validate` — verify the build produced real OUTPUT (server.js + BUILD_ID), not just exit 0.

## Changelog

- **1.0.0** (2026-06-04) — Initial authoring. Anchor: ATLAS Next-16 webpack-over-OneDrive hang →
  turbopack fix; killed-build `.next` wipe; CPU-only-watcher false stall; LTS-node build pin. Human-authored.
