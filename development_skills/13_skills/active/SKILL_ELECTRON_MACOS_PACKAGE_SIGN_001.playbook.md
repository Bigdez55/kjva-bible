# Electron macOS Packaging and Ad-Hoc Signing

> Promoted from Storbits incident 2026-05-29. Canonical skill. Edit this file,
> not the runtime shim.

## Purpose

Ensure every macOS Electron build is correctly signed (ad-hoc or Developer ID),
immune to `ELECTRON_RUN_AS_NODE` inheritance, and free from App Translocation.
A single `npm run pack` must produce a launchable `.app` with no manual steps.

---

## The Two Required Fixes

### Fix 1 — electronFuses in package.json

Always set these two fuses in the `build.electronFuses` block:

```json
{
  "build": {
    "electronFuses": {
      "runAsNode": false,
      "enableEmbeddedAsarIntegrityValidation": false
    }
  }
}
```

| Fuse | Why |
|------|-----|
| `runAsNode: false` | Ignores `ELECTRON_RUN_AS_NODE=1` inherited from VS Code, Claude Code, and any other Electron-based parent process. Without this, the packaged app runs as plain Node.js and exits immediately. |
| `enableEmbeddedAsarIntegrityValidation: false` | Disables ASAR hash verification at launch. Required for ad-hoc signed builds that are not notarized — otherwise macOS rejects the app on open. |

Verify fuses after build:
```bash
npx @electron/fuses read --app dist/mac-arm64/YourApp.app
# Must show: RunAsNode is Disabled
```

---

### Fix 2 — Inside-Out Ad-Hoc Signing in the Build Script

electron-builder leaves the binary "linker-signed" — `Identifier=Electron`, no
Info.plist binding, rejected by Gatekeeper. You must re-sign after build.

Add this block to your `scripts/package-dev.js`:

```javascript
if (process.platform === 'darwin') {
  const appDir = path.join(root, 'dist', 'mac-arm64');
  const apps = fs.existsSync(appDir)
    ? fs.readdirSync(appDir).filter((f) => f.endsWith('.app'))
    : [];
  if (apps.length === 0) {
    console.warn('[pack] No .app found to sign in', appDir);
    process.exit(0);
  }
  const appPath = path.join(appDir, apps[0]);
  console.log('[pack] Ad-hoc signing', appPath);

  // Sign inner bundles FIRST — codesign requires inside-out order
  const frameworks = path.join(appPath, 'Contents', 'Frameworks');
  if (fs.existsSync(frameworks)) {
    for (const entry of fs.readdirSync(frameworks)) {
      const entryPath = path.join(frameworks, entry);
      if (fs.statSync(entryPath).isDirectory()) {
        spawnSync('codesign', ['--force', '--sign', '-', entryPath], { stdio: 'pipe' });
      }
    }
  }

  // Then sign the outer bundle
  const signResult = spawnSync(
    'codesign', ['--force', '--sign', '-', appPath],
    { stdio: 'inherit' }
  );
  if (signResult.status !== 0) {
    console.error('[pack] codesign failed');
    process.exit(signResult.status === null ? 1 : signResult.status);
  }
  console.log('[pack] Done —', appPath);
}
```

Verify signature after build:
```bash
codesign -dvv dist/mac-arm64/YourApp.app 2>&1
```

Expected output (pass):
```
Identifier=com.yourdomain.yourapp
Format=app bundle with Mach-O thin (arm64)
Signature=adhoc
flags=0x2(adhoc)
Sealed Resources version=2 rules=13 files=<N>
```

Failure signature (linker-signed stub — must re-sign):
```
Identifier=Electron
Signature=adhoc
flags=0x20002(adhoc,linker-signed)
Info.plist=not bound
Sealed Resources=none
```

---

## App Translocation Prevention

macOS quarantines apps opened from `~/Desktop`, `~/Downloads`, or any
non-`/Applications` path if they carry the `com.apple.quarantine` xattr. The OS
then runs the app from a random temp path:
```
/private/var/folders/.../AppTranslocation/.../YourApp.app/
```

This changes `process.resourcesPath` on every launch, breaking relative paths
to bundled resources.

**After copying the app to Desktop or any non-standard location:**
```bash
xattr -r -d com.apple.quarantine ~/Desktop/YourApp.app
```

**To permanently prevent translocation:** install to `/Applications/`:
```bash
cp -R dist/mac-arm64/YourApp.app /Applications/
```

Apps in `/Applications/` are never translocated.

---

## Complete package.json Build Config Reference

```json
{
  "name": "@yourorg/desktop",
  "main": "main.js",
  "scripts": {
    "start": "env -u ELECTRON_RUN_AS_NODE electron .",
    "pack": "node scripts/package-dev.js",
    "dist": "node scripts/package-release.js"
  },
  "build": {
    "appId": "com.yourdomain.yourapp",
    "productName": "YourApp",
    "asar": true,
    "electronFuses": {
      "runAsNode": false,
      "enableEmbeddedAsarIntegrityValidation": false
    },
    "mac": {
      "category": "public.app-category.developer-tools",
      "target": ["dmg", "zip"],
      "hardenedRuntime": true,
      "gatekeeperAssess": false
    }
  }
}
```

Note: `"start": "env -u ELECTRON_RUN_AS_NODE electron ."` is the **dev mode**
companion fix — strips the env var for development runs. See
`SKILL_ELECTRON_VSCODE_ENV_ISOLATION_001` for full dev-mode diagnosis.

---

## Validation Gates

| Gate | Command | Pass |
|------|---------|------|
| Fuse: RunAsNode disabled | `npx @electron/fuses read --app dist/mac-arm64/<App>.app` | `RunAsNode is Disabled` |
| Signature: correct identifier | `codesign -dvv dist/mac-arm64/<App>.app 2>&1 \| grep Identifier` | `Identifier=com.yourappid` |
| Signature: sealed resources | `codesign -dvv dist/mac-arm64/<App>.app 2>&1 \| grep Sealed` | `Sealed Resources version=2` |
| Signature: not linker-signed | `codesign -dvv dist/mac-arm64/<App>.app 2>&1 \| grep flags` | `flags=0x2(adhoc)` NOT `0x20002` |
| No quarantine | `xattr -l ~/Desktop/<App>.app \| grep quarantine` | No output |
| App launches | `open dist/mac-arm64/<App>.app` | Window opens, no silent exit |
| No translocation | Check `process.resourcesPath` in main.js startup log | Path is NOT under `/private/var/folders/...` |

---

## Incident Record

| Date | Project | Bug | Root Cause | Fix |
|------|---------|-----|-----------|-----|
| 2026-05-29 | Storbits | Packaged app silently exited code 0 before main.js loaded | `ELECTRON_RUN_AS_NODE=1` inherited from Claude Code (VS Code Electron shell); linker-signed stub | `runAsNode:false` fuse + inside-out ad-hoc signing in package-dev.js |

## Related Skills

- `SKILL_ELECTRON_VSCODE_ENV_ISOLATION_001` — dev-mode diagnosis for `ELECTRON_RUN_AS_NODE`
- `SKILL_ELECTRON_SINGLE_INSTANCE_DISCIPLINE_001` — single-instance lock pattern
- `SKILL_ELECTRON_EMBEDDED_DAEMON_BOOTSTRAP_001` — bundled daemon startup and mode injection
