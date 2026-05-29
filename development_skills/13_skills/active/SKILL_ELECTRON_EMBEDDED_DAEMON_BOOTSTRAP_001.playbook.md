# Electron Embedded Daemon Bootstrap

> Promoted from Storbits incident 2026-05-29. Canonical skill. Edit this file,
> not the runtime shim.

## Purpose

Establish the correct startup ordering, path resolution, and runtime injection
pattern for Electron apps that manage an embedded backend daemon (Python,
Node.js, or any other process). Ensures the renderer always starts in the
correct mode with a valid auth token, and that the daemon is cleaned up on quit.

---

## The Required Startup Order

```
app.whenReady()
  │
  ├─ configStore = new ConfigStore(...)     ← read persisted mode/config
  ├─ daemon = new DaemonManager(...)        ← init with correct paths
  ├─ registerIpc()                          ← wire IPC before any window
  ├─ await bootstrapRuntime()               ← start daemon, set runtime.*
  └─ await createWindow()                   ← load HTML; did-finish-load injects runtime
```

**Critical constraint:** `bootstrapRuntime()` must complete before
`createWindow()`. The `did-finish-load` handler calls `applyRuntimeToConsole()`,
which reads from `runtime.*`. If the daemon hasn't started yet, the token and
baseUrl are empty and the renderer starts in DEMO_ENGINE.

---

## Path Resolution: Dev vs Packaged

```javascript
// In app.whenReady():

const repoRoot = app.isPackaged
  ? process.resourcesPath                           // Contents/Resources/
  : path.resolve(__dirname, '../..');               // repo root (2 levels up from electron/)

const bundledPythonDir = app.isPackaged
  ? path.join(process.resourcesPath, 'assets', 'python')
  : path.resolve(__dirname, '../assets/python');

daemon = new DaemonManager({ appDataDir: app.getPath('userData'), repoRoot, bundledPythonDir });
```

In the packaged app, `process.resourcesPath` points to `Contents/Resources/`.
All `extraResources` (storbits package, console HTML, bundled Python) land there.

In dev mode, `__dirname` is `desktop/electron/` — navigate up to the repo root.

---

## bootstrapRuntime() — Mode Selection Logic

```javascript
async function bootstrapRuntime() {
  const config = configStore.read();

  // Restore DEMO_ENGINE — no daemon needed
  if (config.lastMode === 'DEMO_ENGINE') {
    runtime = { mode: 'DEMO_ENGINE', baseUrl: '', token: '', ... };
    return;
  }

  // Restore CLOUD_TENANT — no daemon, just load saved URL + token
  if (config.lastMode === 'CLOUD_TENANT' && config.cloudBackendUrl) {
    runtime = { mode: 'CLOUD_TENANT', baseUrl: config.cloudBackendUrl,
                token: configStore.getToken(), ... };
    return;
  }

  // Default: try to start LOCAL_NODE daemon
  try {
    const state = await daemon.start({ root: config.localRoot, timeoutMs: 30000 });
    runtime = { mode: 'LOCAL_NODE', baseUrl: state.baseUrl, token: state.token, ... };
    configStore.write({ lastMode: 'LOCAL_NODE', localRoot: state.root });
  } catch (err) {
    // Daemon failed to start — fall back to DEMO_ENGINE, never block
    runtime = { mode: 'DEMO_ENGINE', ..., lastError: err.message };
  }
}
```

---

## applyRuntimeToConsole() — Runtime Injection

```javascript
async function applyRuntimeToConsole() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const script = `
    localStorage.setItem('sb_mode', ${JSON.stringify(runtime.mode)});
    if (${JSON.stringify(Boolean(runtime.baseUrl))})
      localStorage.setItem('sb_backend', ${JSON.stringify(runtime.baseUrl)});
    if (${JSON.stringify(Boolean(runtime.token))})
      localStorage.setItem('sb_token', ${JSON.stringify(runtime.token)});
    window.STORBITS_DESKTOP_RUNTIME = ${JSON.stringify({ ...runtime, token: runtime.token ? '<set>' : '' })};
    window.dispatchEvent(new CustomEvent('storbits-runtime-updated',
      { detail: window.STORBITS_DESKTOP_RUNTIME }));
    if (typeof setMode === 'function') setMode(${JSON.stringify(runtime.mode)});
  `;
  await mainWindow.webContents.executeJavaScript(script, true);
}

// Wire to window load:
mainWindow.webContents.on('did-finish-load', () => {
  applyRuntimeToConsole().catch((err) => { runtime.lastError = err.message; });
});
```

**Key points:**
- `localStorage.setItem('sb_mode', ...)` persists across renderer reloads.
- `if (typeof setMode === 'function') setMode(...)` is safe even if the
  console page doesn't define `setMode` — no error thrown.
- `window.dispatchEvent(new CustomEvent('storbits-runtime-updated', ...))` lets
  the page subscribe to runtime changes without polling localStorage.
- Token is injected only if truthy — never writes an empty string that would
  overwrite a valid token from a previous session.

---

## Console Page — setMode Pattern

The console HTML must define `setMode` at module scope (not inside a callback):

```javascript
let ENGINE_MODE = 'DEMO_ENGINE';

// Initial definition — updates badge and re-renders current page
function setMode(m) {
  ENGINE_MODE = m;
  const b = document.getElementById('hdr-badge');
  if (b) b.textContent = m;
  if (typeof currentPage !== 'undefined' && PAGES[currentPage]) PAGES[currentPage]();
}

// Phase L upgrade — also persists to localStorage and updates mode selector
setMode = function(m) {
  ENGINE_MODE = m;
  localStorage.setItem('sb_mode', m);
  const b = document.getElementById('hdr-badge');
  if (b) b.textContent = m;
  const s = document.getElementById('mode-sel');
  if (s) s.value = m;
  if (typeof currentPage !== 'undefined' && PAGES[currentPage]) PAGES[currentPage]();
};

// Restore from localStorage on page load (handles reload without IPC re-inject)
(function() {
  const m = localStorage.getItem('sb_mode');
  if (m && m !== 'DEMO_ENGINE') setMode(m);
})();
```

The init IIFE at the bottom handles page refreshes — localStorage survives
renderer reloads even if `applyRuntimeToConsole()` doesn't re-run.

---

## Daemon Token Hygiene

```javascript
// In DaemonManager.start():
const token = config.token || randomToken();  // fresh random token every start

// Pass via env var — NOT command-line args (ps shows args to all users)
env: {
  ...process.env,
  STORBITS_ADMIN_TOKEN: token,
  STORBITS_KMS_MASTER_KEY: masterKey,
  PYTHONPATH: repoRoot,
}

// State file: store placeholder, not the real token
fs.writeFileSync(statePath, JSON.stringify({ ...this.state, token: '<ephemeral>' }));

// Return real token to main.js
return { baseUrl, token, root, port, pid };
```

The real token lives only in memory (`runtime.token` in main.js, localStorage
`sb_token` in renderer). It is never written to disk.

---

## waitForReady() — Health Polling

```javascript
async function waitForReady({ port, token, timeoutMs = 30000 }) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await requestJson({ port, token, pathName: '/readyz' });
      if (res.body?.ok) return res.body;
    } catch (_) {}
    await new Promise(r => setTimeout(r, 250));
  }
  throw new Error(`daemon did not become ready within ${timeoutMs}ms`);
}
```

The 30-second default is appropriate for cold Python startup including module
import time. Reduce only if the daemon is pre-warmed.

---

## Bundled Python Detection

```javascript
function findBundledPython(dir) {
  const bin = path.join(dir, 'bin', 'python3');
  try {
    fs.accessSync(bin, fs.constants.X_OK);
    return bin;
  } catch (_) {
    return null;
  }
}

// In DaemonManager: fall back to system python3 if bundled not found
const pythonPath = findBundledPython(bundledPythonDir) || 'python3';
```

Download bundled Python via a setup script:
```bash
npm run setup   # downloads python-build-standalone to desktop/assets/python/
```

In electron-builder `extraResources`:
```json
{
  "from": "../assets",
  "to": "assets"
}
```

---

## Clean Shutdown — Before-Quit Handler

```javascript
app.on('before-quit', async (event) => {
  if (daemon && runtime.mode === 'LOCAL_NODE' && daemon.child) {
    event.preventDefault();     // hold quit until daemon stops
    await daemon.stop();        // sends SIGTERM, waits for exit
    app.exit(0);               // then quit cleanly
  }
});
```

Without this, the daemon process becomes an orphan. Verify after testing:
```bash
pgrep -f "storbits.cli.main"   # must return empty after app quits
```

---

## Validation Gates

| Gate | Command / Check | Pass |
|------|----------------|------|
| Config persisted | `cat ~/Library/Application Support/<App>/config.json` | `lastMode: LOCAL_NODE` |
| Daemon running | `curl http://localhost:<port>/readyz` | `{"ok":true}` |
| Auth enforced | `curl http://localhost:<port>/v1/tables` | `401 unauthorized` |
| Token in renderer | DevTools: `localStorage.getItem('sb_token')` | Non-empty string |
| Mode badge | Visual check | Shows `LOCAL_NODE` not `DEMO_ENGINE` |
| Daemon path correct | Check daemon log | Path is NOT under AppTranslocation |
| Clean quit | Quit app; `pgrep -f storbits.cli` | No output (no orphan) |

---

## Incident Record

| Date | Project | Bug | Root Cause | Fix |
|------|---------|-----|-----------|-----|
| 2026-05-29 | Storbits | UI showed DEMO_ENGINE; user could not use personal data | `setMode()` not called from `applyRuntimeToConsole()`; mode badge not updating despite LOCAL_NODE in config | Added `if (typeof setMode === 'function') setMode(...)` to injected script |

## Related Skills

- `SKILL_ELECTRON_MACOS_PACKAGE_SIGN_001` — packaging, fuses, signing
- `SKILL_ELECTRON_VSCODE_ENV_ISOLATION_001` — RunAsNode env isolation
- `SKILL_ELECTRON_SINGLE_INSTANCE_DISCIPLINE_001` — single-instance lock
