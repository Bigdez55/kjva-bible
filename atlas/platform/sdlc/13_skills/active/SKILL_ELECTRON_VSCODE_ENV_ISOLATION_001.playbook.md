# Electron VS Code Environment Isolation

> Promoted from Storbits incident 2026-05-29. Canonical skill. Edit this file,
> not the runtime shim.

## Purpose

Prevent `ELECTRON_RUN_AS_NODE=1` — set by VS Code, Claude Code, and any other
Electron-based developer tool — from silently breaking Electron apps launched
from the same terminal session.

---

## The Problem

VS Code (and Claude Code, which runs inside VS Code's Electron shell) sets
`ELECTRON_RUN_AS_NODE=1` in the environment of **all child processes**.

When an Electron binary inherits this variable:

1. It runs as plain Node.js, not as an Electron browser process.
2. `process.type` is `undefined` (should be `"browser"`).
3. `require('electron')` resolves to `node_modules/electron/index.js`, which
   exports the **path to the Electron binary** as a plain string — not the API.
4. Destructuring `const { app, BrowserWindow } = require('electron')` gives
   `undefined` for all keys.
5. With no explicit script path, the process exits immediately with code 0 —
   silently, no error.

```
# This is what you get from require('electron') in RunAsNode mode:
"/Users/you/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
# ↑ 148-character string — not an object. {app} = "string"[0] = undefined.
```

### How to confirm

```bash
env | grep ELECTRON
# ELECTRON_RUN_AS_NODE=1  ← confirmed: this is the problem
```

```javascript
// Add to top of main.js temporarily:
console.log('process.type:', process.type);  // undefined = RunAsNode mode
console.log('electron:', typeof require('electron'));  // "string" = path, not API
```

---

## Fix 1 — Dev Mode: Strip the Variable in the `start` Script

```json
{
  "scripts": {
    "start": "env -u ELECTRON_RUN_AS_NODE electron ."
  }
}
```

`env -u VAR` unsets the variable for the subprocess only. No other environment
variables are affected. This is the minimal, safe fix for development launches.

**After this fix:** `npm start` from a VS Code terminal works correctly.

---

## Fix 2 — Packaged Builds: Disable the `runAsNode` Fuse

The env-strip only helps in development. For packaged `.app` builds, the fuse
is the only reliable fix — the user might launch the app from any context.

```json
{
  "build": {
    "electronFuses": {
      "runAsNode": false
    }
  }
}
```

With `runAsNode: false`, the Electron binary ignores `ELECTRON_RUN_AS_NODE`
entirely, regardless of how it was launched.

Verify:
```bash
npx @electron/fuses read --app dist/mac-arm64/YourApp.app
# RunAsNode is Disabled  ← correct
```

> Note: Setting any `electronFuses` config triggers `@electron/fuses` to patch
> the binary, which invalidates the original linker signature. Always re-sign
> after packaging. See `SKILL_ELECTRON_MACOS_PACKAGE_SIGN_001`.

---

## Diagnosis Checklist

When an Electron app silently exits or APIs are undefined:

```
1. env | grep ELECTRON
   → ELECTRON_RUN_AS_NODE=1? → Apply Fix 1 (dev) + Fix 2 (packaged)

2. Is this a packaged build?
   → npx @electron/fuses read --app <App>.app | grep RunAsNode
   → "Enabled"? → rebuild with runAsNode:false

3. Does the app work when launched from a non-VS-Code terminal?
   → Yes? → Confirms ELECTRON_RUN_AS_NODE inheritance

4. process.type check:
   → undefined? → RunAsNode mode confirmed

5. typeof require('electron') === 'string'?
   → Yes? → RunAsNode mode confirmed; APIs are unavailable
```

---

## Why This Affects Claude Code Users

Claude Code is an Electron desktop app (VS Code-based). When you run `npm start`
from the Claude Code terminal, the Electron environment variable is already
set in that terminal session's environment. Any Electron binary you launch
inherits it.

This means **any Electron project developed with Claude Code as the IDE is
susceptible** to this failure without these two fixes.

---

## Full Validated Configuration

```json
{
  "name": "@yourorg/desktop",
  "scripts": {
    "start": "env -u ELECTRON_RUN_AS_NODE electron .",
    "pack": "node scripts/package-dev.js"
  },
  "build": {
    "electronFuses": {
      "runAsNode": false,
      "enableEmbeddedAsarIntegrityValidation": false
    }
  }
}
```

---

## Validation Gates

| Gate | Command | Pass |
|------|---------|------|
| Dev mode fix applied | `grep "ELECTRON_RUN_AS_NODE" package.json` | `env -u ELECTRON_RUN_AS_NODE` in start script |
| Fuse disabled | `npx @electron/fuses read --app dist/mac-arm64/<App>.app` | `RunAsNode is Disabled` |
| App launches from VS Code terminal | `npm start` from VS Code integrated terminal | Window opens |
| process.type correct | Add `console.log(process.type)` to main.js | Prints `browser` |
| Electron API is object | Add `console.log(typeof require('electron'))` | Prints `object` not `string` |

---

## Incident Record

| Date | Project | Symptom | Root Cause | Fix |
|------|---------|---------|-----------|-----|
| 2026-05-29 | Storbits | App silent exit code 0 from Claude Code terminal; `app` undefined | `ELECTRON_RUN_AS_NODE=1` inherited from Claude Code Electron shell | `env -u` in start script + `runAsNode:false` fuse |

## Related Skills

- `SKILL_ELECTRON_MACOS_PACKAGE_SIGN_001` — packaging, signing, and fuse configuration
- `SKILL_ELECTRON_SINGLE_INSTANCE_DISCIPLINE_001` — single-instance lock pattern
- `SKILL_ELECTRON_EMBEDDED_DAEMON_BOOTSTRAP_001` — bundled daemon startup and mode injection
