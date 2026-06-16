/**
 * Runtime verify probe for CAP_RATE_LIMIT.
 *
 * Proves the rate-limit ENGINE is WIRED (writes a durable bucket row), not merely
 * DEFINED. Exercises the REAL token-bucket against a THROWAWAY temp SQLite DB:
 *   0. mkdtemp + ATLAS_SQLITE_PATH + ATLAS_RUNTIME=desktop; runMigrations() seeds
 *      the genesis anchor + the local tenant + all tables (incl. rate_limit_buckets).
 *   1. checkRateLimitWith(db, ...) for a tenant/route — assert allowed:true on the
 *      first call (a fresh bucket always allows).
 *   2. assert a row now EXISTS in rate_limit_buckets for that (tenant,user,route) —
 *      durable proof the engine persisted state, not just returned a verdict.
 *
 * Prints "VERIFY_OK rate-limit: ..." on success. Exits nonzero + VERIFY_FAIL on
 * failure. Uses the migrations-seeded tenant id (FK-safe regardless of schema).
 *
 * Run: node platform/systems/53_production_readiness/probes/verify/verify_rate_limit.mjs
 */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const SHELL = join(process.cwd(), "apps", "frontend", "shell");
const tmp = mkdtempSync(join(tmpdir(), "atlas-ratelimit-verify-"));
const dbPath = join(tmp, "atlas.db");

process.env.ATLAS_RUNTIME = "desktop";
process.env.ATLAS_LOCAL_IDENTITY_ENABLED = "1";
process.env.ATLAS_SQLITE_PATH = dbPath;

const imp = (rel) => import(pathToFileURL(join(SHELL, rel)).href);

try {
  // Seed schema + genesis + local tenant.
  const { runMigrations } = await imp("src/lib/db/migrate.ts");
  const r = await runMigrations();
  if (!r.migrationsApplied) throw new Error("migrationsApplied=false");
  const tenantId =
    (r.tenantsEnsured || []).find((t) => t.startsWith("local-")) || (r.tenantsEnsured || [])[0];
  if (!tenantId) throw new Error("no tenant seeded by runMigrations");

  // Resolve the REAL engine + DB handle.
  const { getDb } = await imp("src/lib/db/client.ts");
  const { checkRateLimitWith } = await imp("src/lib/rate-limit/token-bucket.ts");
  const schema = await imp("src/lib/db/schema.ts");
  // Resolve drizzle-orm from the shell package (where it is installed).
  const drizzleUrl = pathToFileURL(join(SHELL, "node_modules", "drizzle-orm", "index.js")).href;
  const { eq, and } = await import(drizzleUrl);

  const db = await getDb();
  if (db.__runtime !== "desktop") throw new Error(`expected desktop runtime, got ${db.__runtime}`);

  // Use a NON-NULL userId so a perUser policy would not throw in bucketUserId; the
  // route below resolves to the perTenant DEFAULT_POLICY anyway (no listed limit).
  const userId = "user-verify";
  const method = "POST";
  const pathname = "/api/repos/verify/files";

  const res = checkRateLimitWith(db, { tenantId, userId, method, pathname });
  if (res.allowed !== true) throw new Error(`first call must be allowed; got allowed=${res.allowed}`);

  // Durable proof: a bucket row now exists for this (tenant, route).
  const rows = db
    .select()
    .from(schema.rate_limit_buckets)
    .where(
      and(
        eq(schema.rate_limit_buckets.tenant_id, tenantId),
        eq(schema.rate_limit_buckets.route, res.routeKey),
      ),
    )
    .all();
  if (rows.length < 1) throw new Error("no rate_limit_buckets row was written (engine did not persist)");
  const bucket = rows[0];
  if (typeof bucket.request_count !== "number" || bucket.request_count < 1) {
    throw new Error(`bucket.request_count must be >=1, got ${bucket.request_count}`);
  }

  // Cross-check via raw SQL too (independent of drizzle mapping).
  const rawCount = db.raw
    .prepare("SELECT COUNT(*) AS n FROM rate_limit_buckets WHERE tenant_id = ?")
    .get(tenantId);
  if (!rawCount || rawCount.n < 1) throw new Error("raw COUNT(rate_limit_buckets) < 1");

  console.log(
    `VERIFY_OK rate-limit: durable bucket row written, allowed=${res.allowed} ` +
      `(route=${res.routeKey}, count=${bucket.request_count}, tenant=${tenantId})`,
  );
} catch (e) {
  console.error("VERIFY_FAIL:", e && e.message ? e.message : e);
  process.exitCode = 1;
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
