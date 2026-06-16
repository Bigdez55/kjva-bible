# GitHub OAuth Wiring for the ATLAS Web Service (Next.js)

> Promoted from ATLAS production readiness audit 2026-05-29. Reframed 2026-06-03
> for the always-on web service. Canonical skill.

## Purpose

Wire real OAuth authentication into the **ATLAS web service** (Next.js, served at
`http://127.0.0.1:4317`) using the 127.0.0.1 loopback callback pattern (RFC 8252),
jose-signed JWT sessions, and OS keychain for refresh token storage. Replaces the
broken bearer-token model. The same flow is reused by the **LEGACY** packaged
desktop shell — the loopback callback was chosen so both can share one codebase —
but the canonical target is the resident web service, not Electron.

## The Pattern

### 1. Filename convention by Next.js version

| Next.js version | File | Export |
|---|---|---|
| ≤ 14 | `src/middleware.ts` | named `middleware` |
| 15 | `src/middleware.ts` | default |
| 16+ | `src/proxy.ts` | default |

**Both Next 15 and Next 16 require DEFAULT export.** Named exports are silently ignored.

Verify pickup by running `npm run build` — output must show `ƒ Proxy (Middleware)` or `ƒ Middleware`.

### 2. Loopback OAuth callback (web-service canonical; desktop-compatible)

GitHub OAuth app configuration (the always-on ATLAS web service):
- Homepage URL: `http://127.0.0.1:4317`
- Authorization callback URL: `http://127.0.0.1:4317/api/auth/callback/github`

RFC 8252 permits `127.0.0.1` (and `localhost`) for loopback OAuth flows. Using the
loopback host for the web service means the SAME callback works unchanged for the
LEGACY packaged desktop shell — no per-runtime OAuth app. Custom URL schemes
(`atlas://`) require OS-level registration and add no value.

### 3. Session JWT with jose

```typescript
// src/lib/auth/session.ts
import { SignJWT, jwtVerify } from "jose";

const SESSION_TTL_SECONDS = 24 * 60 * 60;
const ALGORITHM = "HS256";

function getSecret(): Uint8Array {
  const secret = process.env.ATLAS_SESSION_SECRET;
  if (!secret || secret.length < 32) {
    if (process.env.ATLAS_AUTH_ENABLED === "1") {
      throw new Error("ATLAS_SESSION_SECRET must be set (≥32 chars) when auth enabled");
    }
    return new TextEncoder().encode("dev-only-stub-secret-not-for-production-use");
  }
  return new TextEncoder().encode(secret);
}

export async function mintSession(claims: AtlasSessionClaims): Promise<string> {
  return new SignJWT(claims as Record<string, unknown>)
    .setProtectedHeader({ alg: ALGORITHM })
    .setIssuedAt()
    .setExpirationTime(`${SESSION_TTL_SECONDS}s`)
    .sign(getSecret());
}

export async function verifySession(token: string): Promise<AtlasSessionClaims | null> {
  try {
    const { payload } = await jwtVerify(token, getSecret(), { algorithms: [ALGORITHM] });
    return isAtlasSessionClaims(payload) ? payload : null;
  } catch {
    return null;
  }
}
```

### 4. Required session claims (verbatim contract)

```typescript
export interface AtlasSessionClaims {
  sub: string;            // OAuth provider user ID
  tenant_id: string;      // Multi-tenant scope
  session_id: string;     // UUID per login
  roles: string[];        // ["admin"] | ["member"] | ["viewer"]
  permissions: string[];  // ["graph:read","proof:write",...]
  repo_scopes: string[];  // OAuth repo scope grants
  issued_at: number;      // Unix epoch seconds
  expires_at: number;     // issued_at + 86400
}
```

### 5. Edge proxy / middleware

```typescript
// src/proxy.ts (Next 16) OR src/middleware.ts (Next 15)
import { NextResponse, type NextRequest } from "next/server";
import { ATLAS_SESSION_COOKIE, ATLAS_HEADER_TENANT_ID } from "./lib/auth/types.ts";
import { verifySession } from "./lib/auth/session.ts";

const PUBLIC_API_PREFIXES = ["/api/auth/"] as const;
const PUBLIC_API_EXACT = new Set(["/api/health", "/api/ready", "/api/production-readiness"]);

function isPublicApiRoute(pathname: string): boolean {
  if (PUBLIC_API_EXACT.has(pathname)) return true;
  return PUBLIC_API_PREFIXES.some((p) => pathname.startsWith(p));
}

export default async function proxy(request: NextRequest): Promise<NextResponse> {
  const { pathname } = request.nextUrl;

  if (!pathname.startsWith("/api/")) return NextResponse.next();
  if (isPublicApiRoute(pathname)) return NextResponse.next();

  if (process.env.ATLAS_AUTH_ENABLED !== "1") {
    // Stub claims for smoke tests
    const headers = new Headers(request.headers);
    headers.set(ATLAS_HEADER_TENANT_ID, "local-stub");
    return NextResponse.next({ request: { headers } });
  }

  const cookie = request.cookies.get(ATLAS_SESSION_COOKIE);
  if (!cookie?.value) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const claims = await verifySession(cookie.value);
  if (!claims) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const headers = new Headers(request.headers);
  headers.set(ATLAS_HEADER_TENANT_ID, claims.tenant_id);
  return NextResponse.next({ request: { headers } });
}
```

### 6. Refresh token storage via keytar

```typescript
// src/lib/auth/keychain.ts
import keytar from "keytar";

const SERVICE = "atlas-oauth";

export async function storeRefreshToken(userId: string, token: string): Promise<void> {
  try {
    await keytar.setPassword(SERVICE, userId, token);
  } catch (err) {
    // Linux without libsecret falls through; OAuth re-auth on next refresh
    console.warn("Keychain unavailable, refresh token not persisted:", err);
  }
}

export async function getRefreshToken(userId: string): Promise<string | null> {
  try {
    return await keytar.getPassword(SERVICE, userId);
  } catch {
    return null;
  }
}
```

### 7. CSP hardening

In `next.config.ts`:
```typescript
"script-src 'self'"  // NO 'unsafe-inline' — use per-request nonce in proxy
"form-action 'self' https://github.com"
"connect-src 'self' https://api.github.com https://github.com"
"img-src 'self' data: blob: https://avatars.githubusercontent.com"
```

### 8. Local-identity fallback

When OAuth credentials are absent (developer environment without registered OAuth app):

```typescript
// src/app/api/auth/local-identity/route.ts
export async function POST(req: Request) {
  if (process.env.ATLAS_LOCAL_IDENTITY_ENABLED !== "1") {
    return NextResponse.json({ error: "Local identity disabled" }, { status: 403 });
  }
  const userInfo = os.userInfo();
  const claims: AtlasSessionClaims = {
    sub: `local-${userInfo.username}`,
    tenant_id: `local-${userInfo.username}`,
    session_id: crypto.randomUUID(),
    roles: ["admin"],
    permissions: ["*"],
    repo_scopes: [],
    issued_at: Math.floor(Date.now() / 1000),
    expires_at: Math.floor(Date.now() / 1000) + 86400,
  };
  const jwt = await mintSession(claims);
  // ... set cookie + redirect
}
```

## Anti-Patterns

### Misnamed proxy file

```typescript
// WRONG — Next 16 looks for src/proxy.ts, finds nothing → all API routes unguarded
src/middleware.ts  // Next 15 convention
```

### Named export instead of default

```typescript
// WRONG — Next.js silently ignores named exports
export function proxy(req) { /* ... */ }

// RIGHT
export default function proxy(req) { /* ... */ }
```

### Bearer token with === comparison

```typescript
// WRONG — timing attack
if (request.headers.get("authorization") === `Bearer ${SECRET}`) { /* ... */ }

// RIGHT — constant-time
import { timingSafeEqual } from "node:crypto";
const expected = Buffer.from(`Bearer ${SECRET}`);
const actual = Buffer.from(request.headers.get("authorization") ?? "");
if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) {
  return new Response("Unauthorized", { status: 401 });
}
```

### Accepting tenantId from request body without cross-check

```typescript
// WRONG — IDOR
const { tenantId } = await req.json();
return db.select().from(repos).where(eq(repos.tenant_id, tenantId));

// RIGHT — derive from verified session
const sessionTenant = req.headers.get("x-atlas-tenant-id");
const { tenantId: bodyTenantId } = await req.json();
if (bodyTenantId && bodyTenantId !== sessionTenant) {
  return new Response('{"error":"forbidden"}', { status: 403 });
}
return db.select().from(repos).where(eq(repos.tenant_id, sessionTenant));
```

## Validation Gates

| Gate | Command | Pass condition |
|---|---|---|
| Proxy filename matches Next version | Check Next major version + filename | Next 16: `src/proxy.ts`; Next 15: `src/middleware.ts` |
| Default export present | `grep "export default" src/proxy.ts` | match found |
| Build picks up proxy | `npm run build` | output shows `ƒ Proxy (Middleware)` or `ƒ Middleware` |
| Session secret enforced | env without ATLAS_SESSION_SECRET + ATLAS_AUTH_ENABLED=1 | throws on startup |
| 401 on missing cookie | curl -X GET /api/tenant (no cookie) | status 401 |
| 401 on invalid JWT | curl with bogus cookie | status 401 |
| Stub claims when disabled | ATLAS_AUTH_ENABLED=0 + smoke test | passes through |
| Local-identity fallback | ATLAS_LOCAL_IDENTITY_ENABLED=1 + POST /api/auth/local-identity | creates session cookie |
| CSP no unsafe-inline in script-src | `grep "'unsafe-inline'" next.config.ts` | only in style-src (Tailwind) |

## Incident Record

| Date | Project | Bug | Commit |
|---|---|---|---|
| 2026-05-29 | ATLAS | `src/proxy.ts` misnamed + misexported → 13 API routes unauthenticated | 0917a6e (rename) + efd6b43 (Next 16 proxy.ts convention restore) |

## Related Skills

- `SKILL_MULTI_TENANT_ISOLATION_001` — tenant claim enforcement at API routes
- `SKILL_FULLSTACK_REACT_ELECTRON_THREEJS_001` — Electron app overall
- `SKILL_ELECTRON_VSCODE_ENV_ISOLATION_001` — ELECTRON_RUN_AS_NODE prevention
- `SKILL_NEXTJS_16_NATIVE_DEPS_BUNDLE_001` — serverExternalPackages for keytar
