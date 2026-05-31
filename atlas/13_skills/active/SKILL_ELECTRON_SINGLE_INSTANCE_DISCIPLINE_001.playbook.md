# Electron Single-Instance Discipline

> Promoted from ATLAS P1 incident 2026-05-29. Canonical skill. Edit this file,
> not the runtime shim.

## Purpose

Ensure every Electron main process prevents duplicate instances, duplicate
embedded servers, and duplicate windows. Enforced before any Electron main
is shipped or reviewed.

## The Pattern — Always Use This

```js
// electron/main.mjs — REQUIRED structure

const gotLock = app.requestSingleInstanceLock()

if (!gotLock) {
  // A second instance was launched — quit immediately, no other work
  app.quit()
} else {
  // Focus the existing window when the user tries to open a second instance
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
      mainWindow.focus()
    }
  })

  app.whenReady().then(async () => {
    await startServer()   // runs exactly once
    createWindow()

    // macOS Dock icon clicked — show existing window, don't create a new one
    app.on('activate', () => {
      if (mainWindow) {
        mainWindow.show()
        mainWindow.focus()
      } else {
        createWindow()  // only if window was actually destroyed
      }
    })
  })

  // Kill embedded server when the app truly quits (not just window close)
  app.on('before-quit', () => {
    serverProcess?.kill('SIGTERM')
  })

  // macOS: keep process alive after last window closes (standard behavior)
  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit()
  })
}
```

## Validation Gates

Run these checks before shipping any Electron main process:

| Gate | Command / Action | Pass condition |
|---|---|---|
| Single-instance guard present | `grep -n "requestSingleInstanceLock" electron/main.mjs` | Line present before `whenReady` |
| Second-instance handler present | `grep -n "second-instance" electron/main.mjs` | Handler restores + focuses window |
| Activate does not unconditionally create | `grep -A5 "'activate'" electron/main.mjs` | Checks `mainWindow` before `createWindow()` |
| Server killed on before-quit | `grep -n "before-quit" electron/main.mjs` | `serverProcess.kill()` inside handler |
| No system `open()` for app URL | `grep -n "open(" electron/main.mjs` | No `open(BASE_URL)` calls |
| Double-launch smoke test | Launch app twice | Second launch quits silently |
| Dock-click test (macOS) | Click Dock icon with window open | Window focuses, no second window |
| Orphan check | Quit app, run `pgrep -f server.js` | No orphan process |

## Anti-Patterns

### Missing single-instance lock

```js
// WRONG — spawns new process + new server on every launch
app.whenReady().then(async () => {
  await startServer()
  createWindow()
})
```

**Consequence:** User double-clicks → second Electron process starts → second
`startServer()` runs → port conflict or two servers on different ports → two
windows. Every Dock click repeats this.

**Fix:** Wrap all `app.whenReady()` logic inside the `gotLock` branch.

---

### activate handler that unconditionally calls createWindow()

```js
// WRONG
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
  // ↑ BrowserWindow.getAllWindows() returns [] when the window is hidden,
  //   not destroyed — this creates a second window on Dock click
})
```

**Fix:** Check `mainWindow` reference directly, not the windows array count.

---

### Server killed in window-all-closed

```js
// WRONG on macOS — server dies when user closes the window
app.on('window-all-closed', () => {
  serverProcess?.kill()   // kills server even though app is still in Dock
  app.quit()
})
```

**Fix:** Kill the server in `before-quit` only. Let `window-all-closed` only
call `app.quit()` on non-macOS.

---

### Opening BASE_URL with system open() instead of BrowserWindow

```js
// WRONG — app renders in Chrome/Safari, not a native window
import { exec } from 'node:child_process'
exec(`open http://127.0.0.1:3100`)

// RIGHT
mainWindow.loadURL('http://127.0.0.1:3100')
```

## Incident Record

| Date | Project | Bug | Commit |
|---|---|---|---|
| 2026-05-29 | ATLAS desktop app | Missing `requestSingleInstanceLock()` — new process + duplicate Next.js server spawned on every double-click | `58b50b4` |

## Related Skills

- `SKILL_FULLSTACK_REACT_ELECTRON_THREEJS_001` — full Electron app playbook;
  this skill's gates are now embedded there as hard constraints.
