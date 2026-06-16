# Single Front-End Source of Truth (+ Feature Reconciliation)

> Canonical skill playbook. Source of truth: `platform/sdlc/13_skills/active/SKILL_SINGLE_FRONTEND_SOURCE_OF_TRUTH_001.playbook.md`
> Human-authored. Companion to [[wired-not-defined]], [[ui-live-verification-before-done]], [[find-before-create]], [[source-of-truth-reconciliation]].

**Summary.** An app has exactly ONE front-end — one rendered surface the user actually sees — and the
API/data layer is separate from it. Never build (or leave) a second parallel UI for the same product.
Every rendered surface must be backed by live data (no fixtures presented as real). When you discover
two front-ends, you do NOT pick one and delete the other on inference — you **reconcile every feature
first**, then collapse to one with nothing lost and no duplicates.

## When to invoke

Triggers (any of):
- "this is not the app", "the front-end is actually here", "you're pulling from the wrong place",
  "there are two UIs", "why are there two places for the front end", "make it look like X not Y".
- Building/auditing any web app's UI; before adding a new page/screen; before a routing/redirect change.
- A repo contains both a static UI (HTML/JS) AND a framework UI (React/Vue/Next pages) for the same product.
- Fixtures/sample/mock data rendered in a shipped surface; a metric that is actually `Math.random()`/hardcoded.
- The data shown is not the user's real entities (e.g., a repo list that vacuumed the whole disk).

## Core directives

### 1. One render surface, one data layer — and they are NOT the same thing
- There is ONE UI the user sees. The backend (API routes, server) is a **separate layer** that the one
  UI consumes. Next.js / a server framework can be **API-only** while a static UI is the front-end —
  that is one front-end + one backend, not two front-ends.
- A second set of pages that renders the same product is a DUPLICATE front-end — the defect. It causes:
  drift (fixes land in one, not the other), "the wrong one is served", and split features.

### 2. The rendered surface must be data-backed — fixtures are theater
- No hardcoded/sample/mock data shown as if real. No `Math.random()` shown as a metric. No invented
  repo names, star counts, dates, uptimes. If data is absent → honest empty/loading state, never fake.
- A page that "looks done" while reading a fixture is NOT done. The fixture is the most dangerous bug:
  it passes a glance and lies. Grep every shipped surface for fixture literals before calling it done.

### 3. The data set must be the user's REAL entities — not a blind vacuum
- Scope the data to what the user actually owns (e.g., their GitHub repos), sourced from the authoritative
  system (the GitHub API / an explicit registry), NOT a blind filesystem walk that ingests every unrelated
  folder. A wrong/over-broad data set is BOTH wrong data AND a performance sink (scanning everything).

### 4. Never resolve a two-front-end split by deleting one on inference
- Each front-end usually has features the other lacks (this is WHY the split is dangerous). Before
  collapsing: **inventory both** — every surface, feature, interaction, and the API each uses — and find
  what is split / unique to each. THEN decide per surface: keep · merge · drop — questioning each, with
  the user where it is genuinely their call. Deleting login/settings/checklist "to consolidate" amputates
  real capability. Reconcile first; delete last.

### 5. Collapse to one with no duplicates
- One canonical surface per concept (no `/graph` + `/graph-engine` + `Graph.html` triplets). Route every
  legacy alias/deep-link to the single surface (no 404s) and retire the others. Verify zero dead links.

## Procedure

1. **Detect & inventory both.** List every UI surface in each front-end + the API each consumes + which
   are live vs fixture. (Parallelize with read-only agents for breadth.)
2. **Reconcile.** Build a per-surface decision matrix: canonical surface, keep/merge/drop, which features
   migrate, data source. Surface genuine choices to the user; default to no-feature-lost.
3. **Make the data layer real.** Fix the shared data loader to fetch live; delete fixtures; scope the data
   set to the user's real entities; ensure honest empty states.
4. **Build/migrate each surface** into the single front-end's look, data-backed. One agent per disjoint
   surface; adversarially verify each (no fixtures, consistent shell, live-wired, links resolve).
5. **Cut over routing.** Serve the canonical front-end at `/` (rewrite to keep the URL); redirect legacy
   routes/aliases to their one surface; retire the duplicate UI (delete dead pages/components after
   confirming nothing kept imports them).
6. **Rebuild + verify the rendered surface.** Open each surface (or have the user verify if the runtime is
   loopback-bound and unreachable by your tooling — say so honestly); confirm live data, no fixtures, no
   duplicate, no dead link. Build/typecheck/tests green.

## Detection symptoms

- Two directories of UI for one product (e.g., `public/*-ui/*.html` AND `src/app/**/page.tsx`).
- Routing config that calls one of them "the mock" / "the real one" — a tell that a split was rationalized.
- A page renders identically regardless of backend state (it's reading a fixture).
- A "live" number that never changes / is random / is a constant baked in the API payload builder.
- The user repeatedly points at the same UI folder and says "this is the real one."

## Anchor episode

**ATLAS, 2026-06-03.** ATLAS had TWO front-ends: a rich static `public/atlas-ui/*.html` Command Center
(the canonical look) and a parallel React `src/app/**/page.tsx` tree (22 routes). A prior session had
wired `next.config` to serve the React pages at `/` and labeled atlas-ui "mvp-data theater" — so the user
kept being shown the wrong UI. Inventory revealed the split was real and bidirectional: atlas-ui had the
look + UX (command palette, graph constellation, walkthroughs) but was **fixture-backed** (`data.js` shipped
a fake "Canon dataset"); React had **live data + real features** (auth, ingest, settings persistence, the
3,378-item checklist) but a plainer shell. Neither was a superset. Compounding it, the repo list was a blind
OneDrive vacuum (~36 unrelated projects) instead of the user's 30 GitHub repos. Resolution: reconcile every
surface (no deletion on inference), make `data.js` a live `/api/live-atlas` loader (fixtures deleted), scope
repos to the user's real GitHub set, migrate the React-only surfaces into the atlas-ui shell, then cut `/`
over to the single atlas-ui and retire the React UI (Next.js → API-only). One front-end, live, no duplicates.

## Anti-patterns

- Two UIs for one product, "temporarily" — it is never temporary; it drifts immediately.
- Rationalizing the split ("this one's the real/live one, that one's the mock") instead of unifying.
- Shipping a surface that reads a fixture because "the API isn't ready" — return honest empty instead.
- Collapsing by deleting the front-end you didn't author, before inventorying its features.
- A redirect/rewrite that points the homepage at a surface you have NOT verified renders live data.
- **Serving a static page at a DIFFERENT base path via rewrite** (e.g. `/` → `/atlas-ui/index.html`)
  without a `<base href="/atlas-ui/">` — its RELATIVE assets (`shell.js`/`data.js`/css) resolve to
  `/shell.js` etc. against the new base → **404 → blank screen** (page loads, scripts don't). Add
  `<base href>` (or use absolute asset paths). This bit ATLAS: `/` was blank while `/atlas-ui/index.html` worked.
- **Verifying a UI with curl / HTTP-200 instead of a real browser.** 200 ≠ rendered: the HTML returns
  200 while its assets 404 and the page is blank. ALWAYS render the surface in a real browser
  (playwright on the host: assert `window`-state + visible body text + zero pageerrors) before "done".
  curl proves the route exists; only a browser proves it renders.

## Cross-refs

- `wired-not-defined` / `architecture-honesty` — DEFINED vs WIRED vs CALLED; fixtures are "defined, not real".
- `ui-live-verification-before-done` — verify the rendered surface (or have the user verify) before "done".
- `find-before-create` — don't create a second UI; find and extend the one that exists.
- `source-of-truth-reconciliation` — the inventory/decision-matrix method for two competing sources.
- `frontend-backend-dataflow` — map UI→API so the one front-end is fully wired to the one backend.

## Changelog

- **1.0.0** (2026-06-03) — Initial authoring. Anchor: ATLAS two-front-end consolidation (static atlas-ui +
  React page tree → single live atlas-ui; fixtures deleted; repo set scoped to the user's GitHub repos).
  Five directives + reconciliation procedure. Human-authored.
