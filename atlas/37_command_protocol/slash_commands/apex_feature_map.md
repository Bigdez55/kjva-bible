# /apex:feature_map

## Purpose

Run a full UI feature audit on a target repo. Produces a per-page map of every element, each element's wiring status (WORKS / BROKEN / DEAD / DUPLICATE / UNKNOWN), and flags duplicates and dead connections. Outputs Mermaid diagrams and YAML files suitable for CI staleness checks and T3 slice planning.

This command invokes `SKILL_UI_FEATURE_AUDIT_001`.

---

## Inputs

| Parameter | Required | Default | Description |
|---|---|---|---|
| `target` | Yes | — | Absolute path to the UI repo to audit |
| `pages` | No | all discovered pages | Comma-separated list of page/screen names to audit |
| `output_dir` | No | `04_architecture/diagrams/source/feature/` | Directory where diagrams and YAML files are written |

### Example invocations

Audit an entire repo:
```
/apex:feature_map target=/Users/me/projects/my-app
```

Audit specific pages only:
```
/apex:feature_map target=/Users/me/projects/my-app pages=Home,Settings,Dashboard
```

Write outputs to a custom directory:
```
/apex:feature_map target=/Users/me/projects/my-app output_dir=/tmp/audit-out
```

---

## Preconditions

Before running this command, ensure:

1. `target` is a UI-bearing repo. Supported types: `web_app`, `mobile_app`, `desktop_app`, `dashboard`.
2. T1 onboarding has been run on the target (`current.truth.yaml` exists in the repo or its twin).
3. Source files are readable (not encrypted, not behind a password).
4. The output directory is writable (command will create it with `mkdir -p` if absent).

If preconditions are not met, the command will stop and report what is missing before doing any work.

---

## Step-by-step execution

### Phase 1 — Framework detection

Identify the UI framework:

- Check for `package.json` — look for `next`, `react-router`, `expo`, `react-native`, `electron`, `tauri` in dependencies.
- Check for `angular.json` (Angular), `nuxt.config.*` (Nuxt/Vue), `svelte.config.*` (SvelteKit).
- Check for Python dashboard markers: `app.py` with `dash`, `streamlit` imports.
- Log detected framework to output.

### Phase 2 — Page/screen discovery

Based on detected framework, enumerate all pages/screens:

- **Next.js (pages router)**: walk `pages/` directory, exclude `_app`, `_document`, `api/`.
- **Next.js (app router)**: walk `app/` directory, find all `page.tsx` / `page.jsx` / `page.js` files.
- **React Router / Vite**: read `src/App.tsx` or router config, extract `<Route path=...>` entries.
- **React Native / Expo**: walk `screens/` or `src/screens/`, read navigator files for registered screens.
- **Electron / Tauri**: read window creation calls and navigation state.
- **SvelteKit**: walk `src/routes/`, find `+page.svelte` files.
- **Nuxt**: walk `pages/` directory.
- **Angular**: read `app-routing.module.ts` or standalone route config.

If `pages` parameter was supplied, filter discovered pages to match the provided list.

Log discovered pages. If zero pages found, report the issue and stop.

### Phase 3 — Element extraction per page

For each page in scope:

1. Read all component files that compose that page (follow imports one level deep).
2. Extract every:
   - Interactive element: `<button>`, `<a>`, `<input>`, `<select>`, `<Switch>`, `<Toggle>`, `<Modal>`, `<Dropdown>`, `<Tab>`, `<NavItem>`.
   - Display element: `<Table>`, `<Chart>`, `<Card>`, `<List>`, `<DataGrid>`.
   - Data-bound element: `fetch(`, `axios.`, `useQuery(`, `useMutation(`, `socket.on(`, `EventSource`.
3. For each element record: label/name, type, file path, line number, handler name (onClick, onChange, onSubmit, etc.).

### Phase 4 — Wiring status derivation

For each element:

1. If no handler attached and no data binding: status = **DEAD**.
2. If handler name found — search codebase:
   ```
   grep -rn "function <handlerName>\|const <handlerName>\|<handlerName> ="
   ```
3. If handler found, inspect body for: `TODO`, `FIXME`, `throw new Error`, `console.error`, large commented blocks. If present: status = **BROKEN**. Otherwise: status = **WORKS**.
4. If handler not found after search: status = **BROKEN** (reference without implementation).
5. If static analysis is inconclusive: status = **UNKNOWN**.
6. After processing all elements on a page, scan for elements with identical label + handler appearing two or more times: status = **DUPLICATE** for each instance beyond the first.

### Phase 5 — Cross-page navigation audit

For every `<Link to=`, `navigate(`, `router.push(`, `<a href=` found:

- Extract destination route string.
- Verify it matches a discovered page route.
- If destination not in discovered pages: flag as dead navigation link.

### Phase 6 — Write outputs

For each page, write:

1. `<output_dir>/page_feature_map_<page>.mmd` — Mermaid graph with color-coded elements.
2. `<output_dir>/page_feature_map_<page>.yaml` — YAML validating against `platform/sdlc/14_templates/feature_map.schema.json`.

After all pages, write:

3. `<output_dir>/feature_map_<repo>.mmd` — full system Mermaid diagram (all pages as subgraphs, navigation edges).
4. `<output_dir>/system_map_<repo>.yaml` — YAML validating against `platform/sdlc/14_templates/system_map.schema.json`.

---

## Outputs

| File | Description |
|---|---|
| `page_feature_map_<page>.mmd` | Per-page Mermaid diagram, one per page |
| `page_feature_map_<page>.yaml` | Per-page element YAML, validates against feature_map schema |
| `feature_map_<repo>.mmd` | Full system Mermaid diagram |
| `system_map_<repo>.yaml` | Cross-page summary YAML with health scores |

### Diagram color conventions

| Status | Color | Hex |
|---|---|---|
| WORKS | green | #90EE90 |
| BROKEN | red | #FFB6C1 |
| DEAD | gray | #D3D3D3 |
| DUPLICATE | yellow | #FFD700 |
| UNKNOWN | blue | #ADD8E6 |

---

## Success criteria

The command succeeds when:

- At least one page was discovered and audited.
- All per-page `.mmd` and `.yaml` files are written without error.
- `feature_map_<repo>.mmd` and `system_map_<repo>.yaml` are written.
- Both YAML outputs pass schema validation.
- Output summary is printed to stdout.

---

## Output summary format

```
Feature audit complete for <repo>:
  Pages discovered: N
  Total elements: N
    WORKS: N (N%)
    BROKEN: N (N%)
    DEAD: N (N%)
    DUPLICATE: N (N%)
    UNKNOWN: N (N%)
  Diagrams written: N
  Health score: N%
  Critical findings:
    - <list of BROKEN/DEAD items that are on primary user paths>
```

---

## Failure modes

| Failure | Detection | Remediation |
|---|---|---|
| Target not a UI repo | No pages, routes, or screen dirs found | Report framework mismatch; suggest running `/apex:t1` first |
| Zero pages discovered | Discovery phase returns empty list | Try alternate path patterns; treat root component as single page if SPA |
| Component parse error | Syntax error reading JSX/TSX file | Skip file, log warning, mark page as PARTIAL |
| Output dir not writable | mkdir -p fails | Report permission error; suggest alternate `output_dir` |
| Schema validation failure | YAML fields missing or wrong type | Fix required fields before writing; report specific validation errors |
| Handler grep times out | Large codebase, grep slow | Increase timeout or scope grep to `src/` only |
| All elements UNKNOWN | Cannot parse component statically | Report partial result; recommend manual review of flagged files |

---

## Skill reference

This command is a thin wrapper around:

- **Skill**: `SKILL_UI_FEATURE_AUDIT_001`
- **Playbook**: `13_skills/active/SKILL_UI_FEATURE_AUDIT_001.playbook.md`
- **Test**: `08_verification/skill_tests/TEST_SKILL_UI_FEATURE_AUDIT_001_001.yaml`
- **Schemas**: `platform/sdlc/14_templates/feature_map.schema.json`, `platform/sdlc/14_templates/system_map.schema.json`
