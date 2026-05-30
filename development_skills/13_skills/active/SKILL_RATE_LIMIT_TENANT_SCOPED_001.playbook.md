# Per-Tenant Per-User Per-Route Rate Limiting (Token Bucket in DB)

> Promoted from ATLAS Phase C.1.3 2026-05-29 (Gate 4).

## Why DB-Backed (not Redis)

Apps that ship as desktop + hosted from one codebase need rate limiting without
adding Redis as a desktop runtime dependency. The DB (SQLite or Postgres) is
already present and supports the necessary primitives:
- SQLite: WAL mode enables concurrent writers.
- Postgres: `SELECT ... FOR UPDATE SKIP LOCKED` prevents thundering herd.

## Pattern

### Schema

```typescript
rate_limit_buckets {
  id           TEXT PRIMARY KEY
  tenant_id    TEXT NOT NULL
  user_id      TEXT NOT NULL
  route        TEXT NOT NULL
  tokens       REAL NOT NULL              // current count
  last_refill  INTEGER NOT NULL           // unix ms
  window_ms    INTEGER NOT NULL
}
UNIQUE (tenant_id, user_id, route)
```

### Limits Config

```typescript
// src/lib/rate-limit/limits-config.ts
export const ROUTE_LIMITS = {
  "POST /api/ingest/repo-event":   { limit: 20,  perWindow: 60_000, scope: "tenant" },
  "POST /api/proof":               { limit: 30,  perWindow: 60_000, scope: "user" },
  "GET  /api/agent-context":       { limit: 60,  perWindow: 60_000, scope: "tenant" },
  "POST /api/knowledge":           { limit: 50,  perWindow: 60_000, scope: "user" },
  DEFAULT:                         { limit: 200, perWindow: 60_000, scope: "tenant" },
} as const;
```

### Check Function

```typescript
// src/lib/rate-limit/token-bucket.ts
export async function checkRateLimit(
  tenantId: string,
  userId: string,
  route: string,
): Promise<{ allowed: boolean; retryAfterMs: number }> {
  const cfg = ROUTE_LIMITS[route] ?? ROUTE_LIMITS.DEFAULT;
  const keyUserId = cfg.scope === "tenant" ? "__tenant__" : userId;
  const db = await getDb();

  return db.transaction(async (tx) => {
    const [row] = await tx.select().from(rate_limit_buckets)
      .where(and(
        eq(rate_limit_buckets.tenant_id, tenantId),
        eq(rate_limit_buckets.user_id, keyUserId),
        eq(rate_limit_buckets.route, route),
      ));

    const now = Date.now();
    let tokens: number;
    if (!row) {
      tokens = cfg.limit - 1;
      await tx.insert(rate_limit_buckets).values({
        id: crypto.randomUUID(),
        tenant_id: tenantId,
        user_id: keyUserId,
        route,
        tokens,
        last_refill: now,
        window_ms: cfg.perWindow,
      });
      return { allowed: true, retryAfterMs: 0 };
    }

    // Refill proportional to elapsed time
    const elapsed = now - row.last_refill;
    const refill = (elapsed / cfg.perWindow) * cfg.limit;
    tokens = Math.min(cfg.limit, row.tokens + refill);

    if (tokens < 1) {
      const retryMs = Math.ceil((1 - tokens) / cfg.limit * cfg.perWindow);
      return { allowed: false, retryAfterMs: retryMs };
    }

    tokens -= 1;
    await tx.update(rate_limit_buckets)
      .set({ tokens, last_refill: now })
      .where(eq(rate_limit_buckets.id, row.id));

    return { allowed: true, retryAfterMs: 0 };
  });
}
```

### Middleware Hook

```typescript
// src/lib/middleware/rate-limit.ts
export async function rateLimitMiddleware(req: NextRequest): Promise<NextResponse | null> {
  const tenantId = req.headers.get("x-atlas-tenant-id");
  const userId = req.headers.get("x-atlas-subject");
  if (!tenantId || !userId) return null;  // public route or auth-disabled

  const route = `${req.method} ${req.nextUrl.pathname}`;
  const result = await checkRateLimit(tenantId, userId, route);
  if (!result.allowed) {
    await appendAuditEvent({
      tenant_id: tenantId, actor_id: userId, /* ... */
      action: "rate_limited", decision: "deny_rate_limit",
    });
    return new NextResponse(JSON.stringify({ error: "rate_limited" }), {
      status: 429,
      headers: { "Retry-After": String(Math.ceil(result.retryAfterMs / 1000)) },
    });
  }
  return null;  // continue
}
```

## Validation Gates

| Gate | Pass |
|---|---|
| Burst rejection | 21 ops in 1s with limit 20 → 21st = 429 |
| Sustained refill | 25 ops over 70s with limit 20/60s → all 200 |
| Cross-tenant independence | tenant A bursts, tenant B unaffected |
| Retry-After header | always present on 429 |
| 429 audited | appendAuditEvent called with decision=deny_rate_limit |

## Incident Record

| Date | Project | Bug | Commit |
|---|---|---|---|
| 2026-05-29 | ATLAS | No rate limits; Gate 4 blocked | 240121c |
