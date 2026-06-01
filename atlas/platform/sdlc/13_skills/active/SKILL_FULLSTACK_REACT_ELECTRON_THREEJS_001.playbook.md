# Playbook: Full-Stack React Electron Three.js

## Skill ID
SKILL_FULLSTACK_REACT_ELECTRON_THREEJS_001

## Purpose
Guide full-stack React, Electron, and Three.js application architecture, state/data flow, build, testing, packaging, and performance.

## Trigger Conditions
- React, Electron, Three.js, desktop app, 3D UI, or full-stack frontend implementation is requested.

## Required Inputs
- User request or command text.
- Target repo, artifact, feature, or workflow when applicable.
- Current source-of-truth files and validation gates when available.

## Canonical Rules
- Preserve source-of-truth ranking.
- Do not claim completion without validation evidence.
- Record misses in the skill refinery ledger when discovered.

## Mandatory Electron Lifecycle Gates (P1 — never skip)

### 1. Single-instance lock — REQUIRED at module scope

Every Electron `main.mjs` MUST begin with the single-instance guard before
any `app.whenReady()` call. Missing this causes a new process and a duplicate
embedded server every time the app is double-clicked or the Dock icon is clicked.

```js
// CORRECT — guard before whenReady
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
      mainWindow.focus()
    }
  })
  app.whenReady().then(() => { /* start server + create window */ })
}
```

```js
// WRONG — new process + duplicate server on every launch
app.whenReady().then(async () => {
  await startServer()
  createWindow()
})
```

### 2. Dock / activate handler (macOS) — show existing, not create new

```js
// CORRECT
app.on('activate', () => {
  if (mainWindow) { mainWindow.show(); mainWindow.focus() }
  else createWindow()
})
```

### 3. Server lifecycle — start once, kill on before-quit

- Spawn the embedded server only inside the `gotLock` branch of `whenReady()`.
- Kill it in `app.on('before-quit')`, not `window-all-closed` — on macOS the
  process lives on after all windows close.

## Anti-Patterns (correction ledger 2026-05-29)

| Anti-pattern | Consequence | Fix |
|---|---|---|
| No `requestSingleInstanceLock()` | New process + duplicate server every launch | Add lock before `whenReady()` |
| `activate` always calls `createWindow()` | Second window spawns on Dock click | Check for existing window first |
| Kill server in `window-all-closed` | Server dies when user closes window on macOS | Move kill to `before-quit` |
| Calling system `open(url)` instead of `BrowserWindow.loadURL()` | App opens in Chrome/Safari, not native window | Load URL in `BrowserWindow` only |

## Workflow

### Observe
- Identify the user goal, repo/project state, relevant sources, and required artifacts.
- Inspect code, docs, schemas, ledgers, or router config before making claims.

### Orient
- Map the request to router intents, related skills, source-of-truth rank, and validation gates.
- Identify missing backbone components, stale docs, untested behavior, or recurrence risk.

### Decide
- Choose the smallest complete artifact set that satisfies the intent.
- Define outputs, tests, evidence, and stop rules before execution.

### Act
- Produce Component standard.
- Produce State/data flow.
- Produce Build/test standard.
- Produce Performance gate.
- Update ledgers and regression cases if a miss or new failure pattern is discovered.

## Output Format
- Component standard
- State/data flow
- Build/test standard
- Performance gate

## Validation Checklist
- Source documents and current repo truth were checked.
- Required output sections are present.
- Router intents and related skills are recorded.
- Tests or manual verification are listed honestly.
- Final report distinguishes proven, partial, and planned claims.

## Source Documents
- handoff_v7_repo_native

## Related Commands
- /apex:platform_build

## Related Workflows
- 05_workflows/platform_build_auto_invocation.md
