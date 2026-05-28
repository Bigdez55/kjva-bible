# ATLAS Workspace Shell and Command Palette Playbook

## Purpose
Port and maintain the ATLAS workspace shell as the uniform platform chrome for authenticated pages: destination sidebar, topbar wordmark, centered command palette, left navigation rail, active work surface, right inspector, and bottom activity drawer.

## Trigger Conditions
- The user references the static ATLAS UI prototype or `New updates/new ui`.
- The user asks for shared chrome, workspace shell, command palette, sidebar, topbar, or route uniformity.
- The user asks to make ATLAS pages flow as one system.

## Hard Constraints
- Do not fork the shell page-by-page.
- Do not replace functional Next.js pages with inert static HTML.
- Use ATLAS proprietary names only.
- The command palette is the primary search/action surface.
- Every page must expose a clear purpose, operational question, state, evidence, and agent-relevant output.
- Route aliases are acceptable only when they preserve the same functional surface.

## Workflow

### Observe
- Inspect `New updates/new ui/DESIGN_SYSTEM.md`, `PLATFORM_AUDIT.md`, and the target Next.js route/component tree.
- Identify whether the request is shell styling, route addition, command palette behavior, data contract, or page-specific interaction.

### Orient
- Map static HTML concepts to live platform concepts:
  - `atlas-shell.css/js` -> React shared workbench component.
  - `atlas-data.js` -> typed ATLAS data modules and API routes.
  - `routeOf(id)` -> route alias map or typed routing helper.
  - destination pages -> App Router routes.

### Decide
- Preserve the live data-backed flow where it exists.
- Add missing destinations as route aliases or functional starter pages.
- Add command palette entries for destinations, repos, notes, skills, and actions.
- Keep the shell reusable and route-agnostic.

### Act
- Update `apps/atlas/src/components/atlas-workbench.tsx`.
- Add or update App Router pages for missing destinations.
- Update global ATLAS tokens in `globals.css`.
- Run Next.js validation and route smoke tests.

## Validation Checklist
- `npm run typecheck`
- `npm run lint`
- `npm run test`
- `npm run build`
- Route manifest includes the expected ATLAS destinations.
- `/`, `/graph`, `/trace`, `/repos`, `/skills`, `/canon`, `/proof`, `/settings`, `/profile`, `/help`, `/login`, and `/brand` return HTTP 200 locally.
- Command palette opens with `Cmd/Ctrl+K`.
- Sidebar routes preserve proprietary ATLAS naming.
