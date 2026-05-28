# ATLAS Operational Workspace Shell Playbook

## Skill ID
SKILL_ATLAS_OPERATIONAL_WORKSPACE_001

## Purpose
Convert ATLAS from a presentation/demo UI into an operational workspace with repo navigation, file exploration, editable linked knowledge, graph relationships, commit history, command routing, and ingestion actions.

## Trigger Conditions
- User says the platform is not operational.
- User expects ATLAS to operate like linked notes, graph exploration, VS Code, GitHub, or a repo-native command workspace.
- User asks for live testing/demo readiness beyond static UI/UX.

## Hard Constraints
- Use `ATLAS`, `Atlas Graph Engine`, and `Atlas Knowledge Vault`.
- Do not use external product names as subsystem names.
- A working platform must include actions that change state or return live API evidence.
- Static cards, JSON dumps, and marketing sections are insufficient unless paired with operational controls.
- Browser `localStorage` is acceptable only for demo persistence; production persistence requires a database/storage backlog item.

## Workflow

### Observe
- Inspect the current app routes, API endpoints, state model, repo connector data, graph data, knowledge notes, and ingest contract.
- Identify which expected workspace behavior is missing: navigation, editing, backlinks, graph selection, commit view, command routing, ingestion, or persistence.

### Orient
- Map each workspace surface to a comparable operating behavior:
  - repo/file explorer
  - editor/preview
  - linked note/backlink panel
  - graph canvas
  - commit feed
  - command router
  - repo ingest action
- Decide which data can be demo-backed and which requires production persistence.

### Decide
- Build the smallest complete operational shell that supports a live user walkthrough.
- Add API contracts when the UI needs backend data.
- Add local state/persistence only when it helps live demo testing and is clearly labeled.

### Act
- Implement repo selection and file selection.
- Implement editable note state and save behavior.
- Implement linked-note creation.
- Implement visible graph/backlink relationships.
- Implement commit feed and repo ingest action.
- Keep trigger router and proof APIs accessible from the workspace.
- Run lint, build, route smoke checks, and production URL checks before claiming completion.

## Required Outputs
- Repo explorer
- File explorer
- Editor and preview surface
- Backlinks panel
- Graph relationship panel
- Commit feed
- Command router
- Ingestion action
- Persistence statement
- Validation evidence

## Validation Checklist
- `npm run lint` passes.
- `npm run build` passes.
- `/api/workspace` returns `200`.
- Homepage renders operational shell labels.
- Repo/file selection exists in UI code.
- Save/edit behavior exists in UI code.
- Ingest action calls `/api/ingest/repo-event`.
- Command action calls `/api/trigger-route`.
- Final report distinguishes demo persistence from production persistence.
