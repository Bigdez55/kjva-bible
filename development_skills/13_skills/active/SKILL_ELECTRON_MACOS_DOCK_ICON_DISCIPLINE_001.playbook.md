# Electron macOS Dock Icon Discipline

> Promoted from ATLAS 2026-05-30 incident — two dock icons appeared per app
> launch, and the brand icon was a hard square instead of the macOS squircle.

## The Three Rules

1. **Squircle, not square.** macOS app icons are rounded squircles (~22.37% corner radius). A hard-edged PNG looks like a broken third-party app, not a native one.
2. **One dock icon per app launch.** If your Electron main spawns a child process via `process.execPath`, macOS treats it as a second app and shows a second dock icon. Use system `node` for child Node processes in dev.
3. **Never silent.** `try { app.dock.setIcon(...) } catch {}` swallows every failure. Always log: missing file, empty nativeImage, missing `app.dock` API, exception.

## Rule 1 — Squircle Icon

### Generator (zero-dep, pure Node)

`scripts/build-mac-icon.mjs` reads `src/app/icon.png` and writes a rounded-corner version to `electron/build/icon-mac.png`. Uses pure Node `zlib` for PNG decode/encode + a CSS-style rounded-rect alpha mask. No `sharp`, no `canvas`, no `imagemagick`.

Key parameters:
- `paddingRatio = 0.0625` (~6.25% padding around the design)
- `radiusRatio = 0.2237` (Apple's continuous-corner ratio, approximated as rounded rect)

### Wire into Electron

```javascript
function iconPath() {
  if (isDev) {
    if (process.platform === 'darwin') {
      const masked = path.resolve(__dirname, 'build', 'icon-mac.png')
      if (existsSync(masked)) return masked
    }
    return path.resolve(__dirname, '..', 'src', 'app', 'icon.png')
  }
  // packaged: bundled brand asset
  const brand = path.join(appRoot(), 'public', 'atlas-ui', 'brand')
  if (process.platform === 'darwin') return path.join(brand, 'ATLAS.icns')
  // ...
}
```

## Rule 2 — Single Dock Entry

### The Bug

```javascript
// WRONG — spawns a second "Electron" dock icon in macOS
serverProcess = spawn(process.execPath, [entry], {
  env: { ...process.env, ELECTRON_RUN_AS_NODE: '1', ... },
})
```

`process.execPath` is the Electron binary. Even with `ELECTRON_RUN_AS_NODE=1`, macOS sees a second Electron.app launch and renders a second dock entry.

### The Fix

```javascript
// dev: use system node; packaged: keep process.execPath (no system node guaranteed)
const nodeBin =
  isDev && existsSync('/opt/homebrew/bin/node')
    ? '/opt/homebrew/bin/node'
    : isDev && existsSync('/usr/local/bin/node')
      ? '/usr/local/bin/node'
      : process.execPath

if (nodeBin !== process.execPath) {
  delete childEnv.ELECTRON_RUN_AS_NODE   // no meaning for node
}

serverProcess = spawn(nodeBin, [entry], { cwd: ..., env: childEnv, stdio: 'ignore' })
```

System `node` does not register a macOS dock entry → single dock icon.

## Rule 3 — Explicit Failure Logging

### The Bug

```javascript
// WRONG — silent. Generic Electron icon shows; no signal why.
if (process.platform === 'darwin' && existsSync(icon)) {
  try { app.dock.setIcon(nativeImage.createFromPath(icon)) } catch {}
}
```

### The Fix

```javascript
if (process.platform === 'darwin') {
  if (!existsSync(icon)) {
    appendLog('warn', 'dock.icon.missing', { path: icon })
  } else {
    try {
      const img = nativeImage.createFromPath(icon)
      if (img.isEmpty()) {
        appendLog('warn', 'dock.icon.empty_native_image', { path: icon })
      } else if (app.dock && typeof app.dock.setIcon === 'function') {
        app.dock.setIcon(img)
        appendLog('info', 'dock.icon.set', { path: icon, size: img.getSize() })
      } else {
        appendLog('warn', 'dock.icon.api_unavailable', { hasDock: !!app.dock })
      }
    } catch (err) {
      appendLog('error', 'dock.icon.set_failed', {
        path: icon,
        message: err?.message ?? String(err),
      })
    }
  }
}
```

Now every failure mode is debuggable from `~/.atlas/logs/electron-main.log`.

## Validation Gates

| Gate | Pass condition |
|---|---|
| Squircle present | `electron/build/icon-mac.png` exists; visual inspection shows rounded corners + transparent border |
| Icon set log | `~/.atlas/logs/electron-main.log` contains `dock.icon.set` with `size: 1024x1024` |
| Single dock entry | `ps aux \| grep electron/dist/Electron.app/Contents/MacOS \| grep -v helper \| wc -l` = 1 per app instance |
| No silent catch | `grep "try.*setIcon.*catch.*{}" electron/main.mjs` returns empty |
| Brand parity | dock icon visually matches `src/app/icon.png` (with squircle masking) |

## Incident Record

| Date | Project | Symptom | Fix |
|---|---|---|---|
| 2026-05-30 | ATLAS | User screenshot showed two macOS dock icons per launch — branded ATLAS + generic "Electron". Brand icon was a hard square. | Switched child server spawn to system node; generated squircle via pure-Node PNG mask script; replaced silent try/catch with explicit log branches. Commit `9f43fae`. |

## Related Skills

- `SKILL_FULLSTACK_REACT_ELECTRON_THREEJS_001` — Electron + Next.js app pattern
- `SKILL_ELECTRON_SINGLE_INSTANCE_DISCIPLINE_001` — prevents multiple windows from double-click
- `SKILL_ELECTRON_VSCODE_ENV_ISOLATION_001` — the sibling spawn issue (ELECTRON_RUN_AS_NODE from VSCode)
- `SKILL_ELECTRON_MACOS_PACKAGE_SIGN_001` — packaged-build icon embedding
- `SKILL_UI_LIVE_VERIFICATION_BEFORE_DONE_001` — visual verification discipline
