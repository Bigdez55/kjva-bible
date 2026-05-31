# Drizzle Dual-Driver Storage (Desktop SQLite + Hosted Postgres)

> Promoted from ATLAS Phase C.0 2026-05-29.

## Purpose

Ship a JavaScript app as both an Electron desktop binary (SQLite) and a hosted
web service (Postgres) from a single schema source.

## The Pattern

### 1. Driver selection by env

```typescript
// src/lib/db/client.ts
import type { BetterSQLite3Database } from "drizzle-orm/better-sqlite3";
import type { NeonHttpDatabase } from "drizzle-orm/neon-http";

export type Db = BetterSQLite3Database<typeof schema> | NeonHttpDatabase<typeof schema>;

let cached: Db | null = null;

export async function getDb(): Promise<Db> {
  if (cached) return cached;
  const runtime = process.env.ATLAS_RUNTIME ?? "desktop";
  if (runtime === "desktop") {
    const { default: Database } = await import("better-sqlite3");
    const { drizzle } = await import("drizzle-orm/better-sqlite3");
    const dbPath = process.env.ATLAS_SQLITE_PATH ?? defaultDesktopPath();
    const conn = new Database(dbPath);
    conn.pragma("journal_mode=WAL");
    conn.pragma("foreign_keys=ON");
    conn.pragma("synchronous=NORMAL");
    cached = drizzle(conn, { schema });
  } else if (runtime === "hosted") {
    const { neon } = await import("@neondatabase/serverless");
    const { drizzle } = await import("drizzle-orm/neon-http");
    const url = process.env.ATLAS_DB_URL;
    if (!url) throw new Error("ATLAS_DB_URL required when ATLAS_RUNTIME=hosted");
    cached = drizzle(neon(url), { schema });
  } else {
    throw new Error(`Unknown ATLAS_RUNTIME: ${runtime}`);
  }
  return cached;
}

export function resetDbCache(): void { cached = null; }
```

### 2. Single schema, both dialects

```typescript
// src/lib/db/schema.ts
import { sqliteTable, text, integer, real, index, uniqueIndex } from "drizzle-orm/sqlite-core";

export const tenants = sqliteTable("tenants", {
  id: text("id").primaryKey(),
  slug: text("slug").notNull().unique(),
  display_name: text("display_name").notNull(),
  plan: text("plan").notNull().default("free"),
  region: text("region"),
  status: text("status").notNull().default("active"),
  created_at: integer("created_at", { mode: "timestamp_ms" }).notNull(),
  updated_at: integer("updated_at", { mode: "timestamp_ms" }).notNull(),
});

export const knowledge_notes = sqliteTable("knowledge_notes", {
  id: text("id").primaryKey(),
  tenant_id: text("tenant_id").notNull().references(() => tenants.id),
  title: text("title").notNull(),
  content: text("content").notNull(),
  source_rank: integer("source_rank").notNull(),
  backlinks: text("backlinks", { mode: "json" }),
  created_at: integer("created_at", { mode: "timestamp_ms" }).notNull(),
  updated_at: integer("updated_at", { mode: "timestamp_ms" }).notNull(),
}, (t) => [
  index("knowledge_notes_tenant_idx").on(t.tenant_id),
]);

// audit_events with hash chain
export const audit_events = sqliteTable("audit_events", {
  event_id: text("event_id").primaryKey(),
  tenant_id: text("tenant_id").notNull(),
  actor_id: text("actor_id").notNull(),
  session_id: text("session_id").notNull(),
  action: text("action").notNull(),
  resource: text("resource").notNull(),
  decision: text("decision").notNull(),
  ip: text("ip"),
  user_agent: text("user_agent"),
  correlation_id: text("correlation_id").notNull(),
  prev_hash: text("prev_hash").notNull(),
  row_hash: text("row_hash").notNull(),
  ts: integer("ts", { mode: "timestamp_ms" }).notNull(),
  exported_at: integer("exported_at", { mode: "timestamp_ms" }),
}, (t) => [
  index("audit_events_tenant_ts_idx").on(t.tenant_id, t.ts),
]);

export const rate_limit_buckets = sqliteTable("rate_limit_buckets", {
  id: text("id").primaryKey(),
  tenant_id: text("tenant_id").notNull(),
  user_id: text("user_id").notNull(),
  route: text("route").notNull(),
  tokens: real("tokens").notNull(),
  last_refill: integer("last_refill", { mode: "timestamp_ms" }).notNull(),
  window_ms: integer("window_ms").notNull(),
}, (t) => [
  uniqueIndex("rate_limit_bucket_unique").on(t.tenant_id, t.user_id, t.route),
]);

// ... (remaining 6 tables: tenant_memberships, repo_connectors, graph_edges, proof_claims, ingest_runs, agent_handoffs)
```

### 3. Idempotent migration runner with genesis seed

```typescript
// src/lib/db/migrate.ts
import { migrate as sqliteMigrate } from "drizzle-orm/better-sqlite3/migrator";
import { sha256 } from "@noble/hashes/sha256";
import { bytesToHex } from "@noble/hashes/utils";

export const AUDIT_GENESIS_EVENT_ID = "GENESIS";
export const AUDIT_GENESIS_HASH = bytesToHex(sha256(new TextEncoder().encode("GENESIS")));

export async function runMigrations(): Promise<{ migrated: boolean; genesis: boolean }> {
  const db = await getDb();
  if (db.__runtime === "desktop") {
    await sqliteMigrate(db, { migrationsFolder: "drizzle/migrations" });
  } else {
    // hosted — neon migrator
  }
  // Genesis row — idempotent
  const existing = await db.select().from(audit_events)
    .where(eq(audit_events.event_id, AUDIT_GENESIS_EVENT_ID));
  if (existing.length === 0) {
    await db.insert(audit_events).values({
      event_id: AUDIT_GENESIS_EVENT_ID,
      tenant_id: "system",
      actor_id: "system",
      session_id: "GENESIS",
      action: "init",
      resource: "audit_events",
      decision: "allow",
      correlation_id: "GENESIS",
      prev_hash: "0".repeat(64),
      row_hash: AUDIT_GENESIS_HASH,
      ts: new Date(),
    });
    return { migrated: true, genesis: true };
  }
  return { migrated: true, genesis: false };
}
```

### 4. Native deps externalization (Next.js)

```typescript
// next.config.ts — REQUIRED for webpack
serverExternalPackages: ["keytar", "better-sqlite3"],
```

Without this, webpack fails to bundle native `.node` bindings.

## Validation Gates

| Gate | Command | Pass |
|---|---|---|
| Schema drift | `npx drizzle-kit check` | exit 0 |
| Migration creates all 10 tables | runMigrations() on fresh DB | tables count = 10 |
| Genesis row present | SELECT * FROM audit_events WHERE event_id="GENESIS" | 1 row |
| WAL mode enabled | `sqlite3 atlas.db "PRAGMA journal_mode"` | `wal` |
| Tenant scoping works | scopedSelect tests | 2 distinct tenants → disjoint result sets |
| Build externalizes natives | `npm run build` | succeeds without keytar/better-sqlite3 bundle errors |

## Incident Record

| Date | Project | Bug | Commit |
|---|---|---|---|
| 2026-05-29 | ATLAS | All tenant data lived in JSON/static files, no DB — production blocked | a5cce23 (types), 6d6e539 (impl), efd6b43 (native deps externalized) |
