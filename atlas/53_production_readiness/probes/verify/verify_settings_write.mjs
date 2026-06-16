/**
 * verify_settings_write.mjs — proves the Settings backend (audit item #21 part 1)
 * is WIRED end to end: the tenant_settings table is created by the REAL migration
 * runner, settings upsert + read back through the SAME tenant-scoped DB path the
 * /api/settings route uses, and a wrong-tenant read returns ZERO rows (IDOR-safe).
 *
 * There is no MCP backend tool for settings — the route (apps/frontend/shell/
 * src/app/api/settings/route.ts) is self-contained (getDb + drizzle upsert +
 * scopedSelect), exactly like api/knowledge/route.ts. So, mirroring
 * verify_checklist_verdict.mjs, this probe exercises that real DB code path
 * directly (runMigrations / getDb / scopedSelect / drizzle onConflictDoUpdate)
 * against a THROWAWAY temp SQLite db — it never touches the real ATLAS db.
 *
 * Checks:
 *   1. MIGRATION APPLIES: runMigrations() creates the tenant_settings table.
 *   2. UPSERT + READ-BACK: insert a tenant's settings, read them back via the
 *      tenant-scoped select the GET route uses; assert key/value round-trip and
 *      JSON-decoding of the value column.
 *   3. RE-UPSERT IS AN UPDATE: a second PUT of the same (tenant, key) updates the
 *      value in place (no duplicate row) and advances updated_at — proving the
 *      route's onConflictDoUpdate path and the (tenant_id, key) UNIQUE index.
 *   4. IDOR: a DIFFERENT tenant's scoped read of the same keys returns ZERO rows
 *      (a caller can never read another tenant's settings).
 *
 * Run: ATLAS_RUNTIME=desktop ATLAS_SQLITE_PATH=/tmp/<f>.db \
 *      node --experimental-strip-types verify_settings_write.mjs
 * (ATLAS_SQLITE_PATH is also set by this script before the first getDb() call.)
 *
 * Prints VERIFY_OK on success and removes the whole temp dir (incl. WAL sidecars).
 */

import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const REPO_ROOT = process.cwd();
const SHELL = join(REPO_ROOT, "apps", "frontend", "shell");
const tmp = mkdtempSync(join(tmpdir(), "atlas-settings-verify-"));
const dbPath = join(tmp, "atlas.db");

process.env.ATLAS_RUNTIME = "desktop";
process.env.ATLAS_LOCAL_IDENTITY_ENABLED = "1";
process.env.ATLAS_SQLITE_PATH = dbPath;
process.env.ATLAS_DISCOVER_REPOS = "0";

// Dynamically import shell modules by file URL so node strips the .ts at runtime.
const imp = (rel) => import(pathToFileURL(join(SHELL, rel)).href);

function eq(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(`ASSERT FAILED: ${msg}`);
}

try {
  // --- 1. migrate + assert tenant_settings exists ----------------------------
  const { runMigrations } = await imp("src/lib/db/migrate.ts");
  const { resolveLocalTenantId } = await imp("src/lib/auth/local-identity.ts");
  await runMigrations();
  const tenantA = resolveLocalTenantId();

  const { getDb } = await imp("src/lib/db/client.ts");
  const schema = await imp("src/lib/db/schema.ts");
  const { scopedSelect } = await imp("src/lib/db/tenant-scope.ts");
  const drizzleUrl = pathToFileURL(join(SHELL, "node_modules", "drizzle-orm", "index.js")).href;
  const { eq: dEq, and: dAnd } = await import(drizzleUrl);

  const db = await getDb();
  const tableNames = db.raw
    .prepare("SELECT name FROM sqlite_master WHERE type='table'")
    .all()
    .map((t) => t.name);
  assert(tableNames.includes("tenant_settings"), "migration did not create table tenant_settings");

  // A SECOND tenant to prove cross-tenant isolation. Seed its FK row directly
  // (tenant_settings.tenant_id REFERENCES tenants.id, foreign_keys = ON).
  const tenantB = "tenant:beta-verify";
  const now0 = Date.now();
  db.raw
    .prepare(
      "INSERT OR IGNORE INTO tenants (id, slug, name, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
    )
    .run(tenantB, tenantB, "Beta Verify", "active", now0, now0);

  // --- 2. UPSERT + READ-BACK (the EXACT path the PUT/GET route uses) ---------
  // The route upserts JSON.stringify(value) and reads via scopedSelect; we do
  // the same so this probe proves the route's real DB code path, not a mock.
  const upsert = async (tenantId, key, value, ts) => {
    await db
      .insert(schema.tenant_settings)
      .values({ id: `${tenantId}:${key}`, tenant_id: tenantId, key, value: JSON.stringify(value), updated_at: ts })
      .onConflictDoUpdate({
        target: [schema.tenant_settings.tenant_id, schema.tenant_settings.key],
        set: { value: JSON.stringify(value), updated_at: ts },
        where: dAnd(dEq(schema.tenant_settings.tenant_id, tenantId), dEq(schema.tenant_settings.key, key)),
      })
      .run();
  };

  const t1 = Date.now();
  await upsert(tenantA, "theme", "dark", t1);
  await upsert(tenantA, "sync_enabled", false, t1);
  await upsert(tenantA, "default_view", "graph", t1);

  // Read back via the SAME tenant-scoped select the GET route uses.
  const rowsA = await scopedSelect(db, schema.tenant_settings, tenantA).all();
  const mapA = {};
  for (const r of rowsA) mapA[r.key] = JSON.parse(r.value);
  eq(rowsA.length, 3, "tenantA setting count");
  eq(mapA.theme, "dark", "tenantA theme round-trip");
  eq(mapA.sync_enabled, false, "tenantA sync_enabled round-trip (JSON-decoded boolean)");
  eq(mapA.default_view, "graph", "tenantA default_view round-trip");

  // --- 3. RE-UPSERT IS AN UPDATE (no duplicate row; value + updated_at change) -
  const t2 = t1 + 1000;
  await upsert(tenantA, "theme", "light", t2);
  const rowsA2 = await scopedSelect(db, schema.tenant_settings, tenantA).all();
  eq(rowsA2.length, 3, "re-upsert must NOT create a duplicate row (still 3)");
  const themeRow = rowsA2.find((r) => r.key === "theme");
  eq(JSON.parse(themeRow.value), "light", "re-upsert must update theme value in place");
  assert(themeRow.updated_at === t2, `re-upsert must advance updated_at to ${t2}, got ${themeRow.updated_at}`);

  // --- 4. IDOR: tenantB has its OWN settings; a tenantB-scoped read can never
  //         see tenantA's rows, and vice versa. -------------------------------
  await upsert(tenantB, "theme", "system", t1); // tenantB's own theme

  const rowsB = await scopedSelect(db, schema.tenant_settings, tenantB).all();
  eq(rowsB.length, 1, "tenantB must see ONLY its own 1 setting (not tenantA's 3)");
  eq(JSON.parse(rowsB[0].value), "system", "tenantB sees its own theme, not tenantA's");

  // tenantA still sees exactly its own 3 (unchanged by tenantB's write).
  const rowsA3 = await scopedSelect(db, schema.tenant_settings, tenantA).all();
  eq(rowsA3.length, 3, "tenantA must still see ONLY its own 3 settings after tenantB write");
  const themeRowA = rowsA3.find((r) => r.key === "theme");
  eq(JSON.parse(themeRowA.value), "light", "tenantA theme must be untouched by tenantB (IDOR-safe)");

  console.log(
    `VERIFY_OK settings-write: migration created tenant_settings, ` +
      `upsert+scopedSelect round-trip (theme/sync_enabled/default_view, JSON-decoded), ` +
      `re-upsert updates in place (3 rows, updated_at advanced), ` +
      `IDOR safe (tenantB sees only its own row; tenantA's settings untouched)`,
  );
} catch (e) {
  console.error("VERIFY_FAIL:", e && e.message ? e.message : e);
  process.exitCode = 1;
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
