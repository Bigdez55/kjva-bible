# Immutable Audit Log with SHA-256 Hash Chain

> Promoted from ATLAS Phase C.1.3 2026-05-29 (Gate 5).

## Schema (Drizzle SQLite + Postgres compatible)

```typescript
audit_events {
  event_id       TEXT PRIMARY KEY    // UUID v4
  tenant_id      TEXT NOT NULL
  actor_id       TEXT NOT NULL       // sub from JWT
  session_id     TEXT NOT NULL
  action         TEXT NOT NULL       // "login"|"denied"|"repo_ingest"|...
  resource       TEXT NOT NULL       // route + ID
  decision       TEXT NOT NULL       // "allow"|"deny"
  ip             TEXT
  user_agent     TEXT
  correlation_id TEXT NOT NULL       // x-request-id
  prev_hash      TEXT NOT NULL       // SHA-256 of prior row
  row_hash       TEXT NOT NULL       // SHA-256 of this row (excluding row_hash)
  ts             INTEGER NOT NULL
  exported_at    INTEGER             // NULL until S3 export
}

INDEX audit_events_tenant_ts_idx (tenant_id, ts)
```

## Append Pattern

```typescript
// src/lib/audit/audit-logger.ts
import { sha256 } from "@noble/hashes/sha256";
import { bytesToHex } from "@noble/hashes/utils";

export async function appendAuditEvent(event: AuditEventInput): Promise<void> {
  const db = await getDb();
  const eventId = crypto.randomUUID();
  const ts = new Date();

  // Read last row by insertion order (use rowid for SQLite, serial col for Postgres)
  const [last] = await db.select().from(audit_events).orderBy(desc(audit_events.rowid)).limit(1);
  const prev_hash = last?.row_hash ?? AUDIT_GENESIS_HASH;

  const canonical = canonicalJson({
    event_id: eventId, tenant_id: event.tenant_id, actor_id: event.actor_id,
    session_id: event.session_id, action: event.action, resource: event.resource,
    decision: event.decision, ip: event.ip, user_agent: event.user_agent,
    correlation_id: event.correlation_id, prev_hash, ts: ts.getTime(),
  });
  const row_hash = bytesToHex(sha256(new TextEncoder().encode(canonical)));

  await db.insert(audit_events).values({
    event_id: eventId, ...event, prev_hash, row_hash, ts,
  });
}
```

## Verify Pattern

```typescript
// src/lib/audit/audit-verifier.ts
export async function verifyChain(tenantId?: string): Promise<{ valid: boolean; brokenAt?: string }> {
  const db = await getDb();
  const rows = await (tenantId
    ? db.select().from(audit_events).where(eq(audit_events.tenant_id, tenantId)).orderBy(audit_events.ts)
    : db.select().from(audit_events).orderBy(audit_events.ts));

  let expectedPrev = AUDIT_GENESIS_HASH;
  for (const row of rows) {
    if (row.event_id === AUDIT_GENESIS_EVENT_ID) {
      if (row.row_hash !== AUDIT_GENESIS_HASH) return { valid: false, brokenAt: row.event_id };
      expectedPrev = row.row_hash;
      continue;
    }
    if (row.prev_hash !== expectedPrev) return { valid: false, brokenAt: row.event_id };
    const recomputed = computeRowHash(row);
    if (recomputed !== row.row_hash) return { valid: false, brokenAt: row.event_id };
    expectedPrev = row.row_hash;
  }
  return { valid: true };
}
```

## Middleware Hook

```typescript
// src/lib/middleware/audit-log.ts
export async function auditDenial(req: Request, reason: string, status: number): Promise<void> {
  await appendAuditEvent({
    tenant_id: req.headers.get("x-atlas-tenant-id") ?? "anonymous",
    actor_id: req.headers.get("x-atlas-subject") ?? "anonymous",
    session_id: req.headers.get("x-atlas-session-id") ?? "none",
    action: "denied",
    resource: new URL(req.url).pathname,
    decision: status === 401 ? "deny_unauthorized" : "deny_forbidden",
    ip: req.headers.get("x-forwarded-for") ?? "",
    user_agent: req.headers.get("user-agent") ?? "",
    correlation_id: req.headers.get("x-request-id") ?? crypto.randomUUID(),
  });
}
```

## Nightly NDJSON Export

```python
# infrastructure/scripts/atlas_core/audit_export.py
import json, sqlite3, boto3, os
from datetime import datetime

def export_audit_events():
    bucket = os.environ.get("ATLAS_AUDIT_S3_BUCKET")
    if not bucket:
        print("ATLAS_AUDIT_S3_BUCKET not set; skipping export")
        return
    conn = sqlite3.connect(os.environ.get("ATLAS_SQLITE_PATH"))
    rows = conn.execute("SELECT * FROM audit_events WHERE exported_at IS NULL ORDER BY ts").fetchall()
    if not rows:
        print("no new audit events")
        return
    ndjson = "\n".join(json.dumps(dict(row)) for row in rows)
    key = f"audit/{datetime.utcnow().isoformat()}-{len(rows)}.ndjson"
    boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=ndjson)
    conn.execute("UPDATE audit_events SET exported_at = ? WHERE exported_at IS NULL",
                 (int(datetime.utcnow().timestamp() * 1000),))
    conn.commit()
    print(f"exported {len(rows)} events to s3://{bucket}/{key}")
```

## Retention Policy (docs/audit-retention-policy.md)

| Tier | Storage | Duration |
|---|---|---|
| Hot | DB (SQLite/Postgres) | 90 days |
| Cold | S3 NDJSON | 7 years |
| Tamper evidence | SHA-256 hash chain | Forever |

## Validation Gates

| Gate | Pass |
|---|---|
| Genesis row present | event_id="GENESIS" + row_hash=SHA256("GENESIS") |
| Append computes hash | insert N rows → all row_hash values verifiable |
| Tamper detected | mutate any row_hash → verifyChain returns {valid:false, brokenAt:...} |
| Nightly export idempotent | re-run with no new rows → no-op |
| App user lacks UPDATE/DELETE | Postgres: `REVOKE UPDATE, DELETE ON audit_events FROM app_user` |

## Incident Record

| Date | Project | Bug | Commit |
|---|---|---|---|
| 2026-05-29 | ATLAS | No audit log; Gate 5 blocked | 240121c |
