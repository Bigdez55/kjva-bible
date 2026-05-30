# Multi-Tenant Isolation via Scoped Query + Existence-Leak Prevention

> Promoted from ATLAS production audit 2026-05-29. Canonical skill for all multi-tenant apps.

## The Required Pattern

Every protected API route follows the same guard chain:

```typescript
// src/app/api/<route>/route.ts
import { requireSession } from "@/lib/auth/require-session";
import { requireTenant } from "@/lib/auth/require-tenant";
import { scopedSelect } from "@/lib/db/tenant-scope";
import { knowledge_notes } from "@/lib/db/schema";

export async function GET(req: Request) {
  const claims = requireSession(req);           // 1. Verify JWT
  const tenantId = requireTenant(req);          // 2. Extract + validate tenant_id

  const db = await getDb();
  const rows = await scopedSelect(db, knowledge_notes, tenantId);  // 3. Auto-inject tenant filter
  return Response.json({ notes: rows, tenantId });
}
```

## The Three Layers

### Layer 1: Session verification (`requireSession`)

```typescript
// src/lib/auth/require-session.ts
import { UnauthorizedError } from "./errors";
import type { AtlasSessionClaims } from "./types";

export function requireSession(req: Request): AtlasSessionClaims {
  const tenantId = req.headers.get("x-atlas-tenant-id");
  const sessionId = req.headers.get("x-atlas-session-id");
  const sub = req.headers.get("x-atlas-subject");
  const roles = req.headers.get("x-atlas-roles");
  if (!tenantId || !sessionId || !sub) {
    throw new UnauthorizedError("missing_session_headers");
  }
  return {
    sub, tenant_id: tenantId, session_id: sessionId,
    roles: roles?.split(",") ?? [],
    permissions: [], repo_scopes: [],
    issued_at: 0, expires_at: 0,
  };
}
```

### Layer 2: Tenant assertion (`requireTenant`)

```typescript
// src/lib/auth/require-tenant.ts
import { ForbiddenError } from "./errors";

export function requireTenant(req: Request): string {
  const tenantId = req.headers.get("x-atlas-tenant-id");
  if (!tenantId) throw new ForbiddenError("missing_tenant_id");
  return tenantId;
}

export async function requireBodyTenantMatch(req: Request, sessionTenantId: string): Promise<void> {
  const body = await req.clone().json();
  if (body.tenantId && body.tenantId !== sessionTenantId) {
    throw new ForbiddenError("tenant_mismatch");
  }
}
```

### Layer 3: Scoped query wrappers

```typescript
// src/lib/db/tenant-scope.ts
import { eq } from "drizzle-orm";

export async function scopedSelect<T>(db: Db, table: Table, tenantId: string): Promise<T[]> {
  return db.select().from(table).where(eq(table.tenant_id, tenantId));
}

export async function scopedSelectWhere<T>(db: Db, table: Table, tenantId: string, extra: SQL): Promise<T[]> {
  return db.select().from(table).where(and(eq(table.tenant_id, tenantId), extra));
}

export async function scopedInsert<T>(db: Db, table: Table, tenantId: string, data: object): Promise<T> {
  if ("tenant_id" in data && data.tenant_id !== tenantId) {
    throw new ForbiddenError("tenant_mismatch");
  }
  return db.insert(table).values({ ...data, tenant_id: tenantId }).returning();
}

// Audit-grep hatch — use ONLY for cross-tenant admin queries with explicit approval
export function unscoped() { /* returns un-scoped db handle */ }
```

## Existence-Leakage Prevention

**Rule:** A request to read tenant B's object using session A MUST return the same 403 body as a request for a non-existent object. Different responses leak the existence of B's data.

```typescript
// src/lib/auth/errors.ts
const FORBIDDEN_BODY = JSON.stringify({ error: "forbidden" });

export class ForbiddenError extends Error {
  static toResponse(): Response {
    return new Response(FORBIDDEN_BODY, {
      status: 403,
      headers: { "Content-Type": "application/json" },
    });
  }
}

export class UnauthorizedError extends Error {
  static toResponse(): Response {
    return new Response(JSON.stringify({ error: "unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }
}
```

Identical body across:
- Object exists but wrong tenant
- Object does not exist
- Tenant ID forged in body
- Tenant ID forged in header

## Cross-Tenant Isolation Test Suite

Minimum 8 attempt vectors (see ATLAS `tests/cross-tenant-isolation.test.ts` for canonical example with 22 vectors):

| # | Attack vector | Expected response |
|---|---|---|
| 1 | Session A → GET tenant A data | 200 with A data only |
| 2 | Session A → GET non-existent object | 403 body B1 |
| 3 | Session A → GET tenant B object by direct ID | 403 body B1 (byte-identical to #2) |
| 4 | Session A + forged x-atlas-tenant-id=B | 403 body B1 (proxy should reject) |
| 5 | Session A + body tenantId=B (POST) | 403 body B1 |
| 6 | Session A + body tenantId=null | 403 body B1 (or use session tenant — but consistent) |
| 7 | No session → any protected route | 401 body B2 (distinct from 403) |
| 8 | Session A → /api/knowledge returns only A's note set; disjoint from B's |

## Anti-Patterns

### Auth at entry but no scope at data

```typescript
// WRONG — session B caller gets tenant A's data
export async function GET(req: Request) {
  requireSession(req);
  return Response.json(await buildLocalAtlasPayload());  // returns ALL tenants' data
}
```

### Different 403 messages

```typescript
// WRONG — enumerates valid IDs
if (!row) return new Response(JSON.stringify({ error: "not found" }), { status: 404 });
if (row.tenant_id !== sessionTenant) return new Response(JSON.stringify({ error: "wrong tenant" }), { status: 403 });

// RIGHT — same response
if (!row || row.tenant_id !== sessionTenant) return ForbiddenError.toResponse();
```

## Validation Gates

| Gate | Pass condition |
|---|---|
| All API routes call requireSession + requireTenant | `grep -L "requireSession" src/app/api/**/route.ts` is empty (except auth routes) |
| All data queries use scoped wrappers | grep for raw `db.select()` calls outside `lib/db/` |
| Cross-tenant test suite exists | tests/cross-tenant-isolation.test.ts has ≥ 8 vectors |
| 403 body byte-identical | test asserts strict equality |
| 401 distinct from 403 | unauthenticated returns 401, not 403 |

## Incident Record

| Date | Project | Bug | Commit |
|---|---|---|---|
| 2026-05-29 | ATLAS | Auth at entry but `buildLocalAtlasPayload()` returned all-tenant data; advisor caught the gap | b4e6a14 |

## Related Skills

- `SKILL_ATLAS_OAUTH_WIRING_001` — provides the session claims this skill enforces
- `SKILL_DURABLE_STORAGE_MIGRATION_001` — schema has tenant_id on every multi-tenant table
- `SKILL_AUDIT_LOG_IMMUTABLE_001` — logs denials including the 403 reason
