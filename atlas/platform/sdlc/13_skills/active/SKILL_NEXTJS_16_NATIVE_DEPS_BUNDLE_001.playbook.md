# Next.js 16 Native Dependencies + Proxy Filename Convention

> Promoted from ATLAS production audit D-phase 2026-05-29. Two distinct lessons
> packaged together because they share the same surface (next.config.ts +
> proxy/middleware file).

## Lesson 1 — Native Dependencies

### The Problem

Native Node modules (those with `.node` bindings) cannot be bundled by webpack.
Examples:
- `keytar` — OS keychain access via libsecret/Security framework
- `better-sqlite3` — embedded SQLite driver
- `sharp` — libvips image processing
- `node-pty` — terminal emulation

`npm run build` fails with cryptic errors like:
```
Module parse failed: Unexpected character '' (1:0)
You may need an appropriate loader to handle this file type
> node_modules/keytar/build/Release/keytar.node
```

### The Fix

```typescript
// next.config.ts
const nextConfig: NextConfig = {
  // ...
  serverExternalPackages: [
    "keytar",
    "better-sqlite3",
    // Add any other native dep your app uses
  ],
};
```

`serverExternalPackages` tells Next.js: "Do not bundle these — load them at
runtime from node_modules". The packaged app's `node_modules/` must include them.

For Electron + electron-builder, ensure these aren't in `files: '!node_modules/**'`
exclude list. Use extraResources or explicit includes.

## Lesson 2 — Proxy Filename Convention

### The Versions

| Next.js | File | Export |
|---|---|---|
| 13-14 | `src/middleware.ts` | named `middleware` |
| 15 | `src/middleware.ts` | default |
| 16+ | `src/proxy.ts` | default |

Next.js 16 deprecated `middleware.ts` in favor of `proxy.ts`. When you start
a Next 16 app or upgrade from 15, RENAME the file. The build output gives a
hint but it's easy to miss:

```
The 'middleware' file convention is deprecated. Please use 'proxy' instead.
```

### How to Verify Pickup

`npm run build` output MUST include:
```
ƒ Proxy (Middleware)    # Next 16 with src/proxy.ts
```
OR (Next 15):
```
ƒ Middleware            # Next 15 with src/middleware.ts
```

If you see NEITHER, the file was not picked up. Either:
- Wrong filename for your Next version
- Named export instead of default
- File in wrong directory (must be `src/` if your tsconfig sets that as root, else project root)

### Default Export Required

```typescript
// ❌ WRONG — named export silently ignored
import { NextResponse } from "next/server";
export function proxy(req: Request) { /* ... */ }

// ✅ RIGHT — default export
import { NextResponse } from "next/server";
export default function proxy(req: Request) { /* ... */ }
```

## Combined next.config.ts Template (Next 16)

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: ["keytar", "better-sqlite3"],
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "no-referrer" },
        { key: "Content-Security-Policy", value: "default-src 'self'; script-src 'self'; ..." },
      ],
    }];
  },
};

export default nextConfig;
```

## Validation Gates

| Gate | Command | Pass |
|---|---|---|
| Native deps externalized | `grep serverExternalPackages next.config.ts` | shows array including all native deps |
| Build succeeds | `npm run build` | exit 0; output shows `ƒ Proxy (Middleware)` |
| Proxy filename matches version | check next major + filename | match per table above |
| Default export | `grep "export default" src/proxy.ts` | match |
| No webpack native errors | `npm run build 2>&1 \| grep ".node"` | empty |

## Incident Record

| Date | Project | Bug | Commit |
|---|---|---|---|
| 2026-05-29 | ATLAS | Build fails on keytar.node + better-sqlite3.node; Next 16 wants proxy.ts not middleware.ts | efd6b43 |

## Related Skills

- `SKILL_ATLAS_OAUTH_WIRING_001` — proxy.ts is the auth enforcement layer
- `SKILL_DURABLE_STORAGE_MIGRATION_001` — better-sqlite3 is the desktop DB driver
- `SKILL_FULLSTACK_REACT_ELECTRON_THREEJS_001` — Electron + Next.js app pattern
