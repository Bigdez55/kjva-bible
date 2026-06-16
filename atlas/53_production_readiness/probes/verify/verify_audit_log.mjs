/**
 * Runtime verify probe for CAP_AUDIT_LOG.
 *
 * Proves the immutable audit-log ENGINE is WIRED (appends a hash-chained row), not
 * merely DEFINED. Exercises the REAL appendAuditEvent path against a THROWAWAY temp
 * SQLite DB:
 *   0. mkdtemp + ATLAS_SQLITE_PATH + ATLAS_RUNTIME=desktop; runMigrations() seeds the
 *      genesis anchor row (row_hash=SHA256("GENESIS"), prev_hash=NULL) — the chain
 *      cannot be appended without it.
 *   1. appendAuditEvent(...) (primed against the seeded DB) appends ONE event.
 *   2. assert the newest audit_events row links to the prior row:
 *        newest.prev_hash === previous.row_hash   (hash-chain linkage)
 *      and newest.row_hash is a 64-hex sha256.
 *
 * Prints "VERIFY_OK audit-log: ..." on success. Exits nonzero + VERIFY_FAIL on
 * failure.
 *
 * Run: node platform/systems/53_production_readiness/probes/verify/verify_audit_log.mjs
 */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const SHELL = join(process.cwd(), "apps", "frontend", "shell");
const tmp = mkdtempSync(join(tmpdir(), "atlas-auditlog-verify-"));
const dbPath = join(tmp, "atlas.db");

process.env.ATLAS_RUNTIME = "desktop";
process.env.ATLAS_LOCAL_IDENTITY_ENABLED = "1";
process.env.ATLAS_SQLITE_PATH = dbPath;

const imp = (rel) => import(pathToFileURL(join(SHELL, rel)).href);

const HEX64 = /^[0-9a-f]{64}$/;

try {
  // Seed schema + genesis anchor + local tenant.
  const { runMigrations } = await imp("src/lib/db/migrate.ts");
  const r = await runMigrations();
  if (!r.migrationsApplied) throw new Error("migrationsApplied=false");
  const tenantId =
    (r.tenantsEnsured || []).find((t) => t.startsWith("local-")) || (r.tenantsEnsured || [])[0];
  if (!tenantId) throw new Error("no tenant seeded by runMigrations");

  const { getDb } = await imp("src/lib/db/client.ts");
  const db = await getDb();
  if (db.__runtime !== "desktop") throw new Error(`expected desktop runtime, got ${db.__runtime}`);

  // The genesis anchor must exist before any append (chain needs an anchor).
  const before = db.raw.prepare("SELECT COUNT(*) AS n FROM audit_events").get();
  if (!before || before.n < 1) throw new Error("genesis anchor missing — runMigrations did not seed audit_events");

  // Prime the cached sync DB handle (appendAuditEvent uses getDbSync()), then append.
  const { appendAuditEvent, primeAuditDb } = await imp("src/lib/audit/audit-logger.ts");
  await primeAuditDb();
  const result = appendAuditEvent({
    tenant_id: tenantId,
    actor_id: "verify-actor",
    action: "api.post",
    resource: "route:POST /api/repos/verify/files",
    decision: "success",
    correlation_id: "corr:verify",
  });
  if (!HEX64.test(result.row_hash)) throw new Error(`returned row_hash not 64-hex: ${result.row_hash}`);

  // Read the last TWO rows by insertion order (rowid) and assert chain linkage.
  const lastTwo = db.raw
    .prepare("SELECT id, prev_hash, row_hash FROM audit_events ORDER BY rowid DESC LIMIT 2")
    .all();
  if (lastTwo.length < 2) throw new Error("expected >=2 rows (genesis + appended), got " + lastTwo.length);
  const newest = lastTwo[0];
  const previous = lastTwo[1];

  if (!HEX64.test(newest.row_hash)) throw new Error(`newest.row_hash not 64-hex: ${newest.row_hash}`);
  if (newest.prev_hash !== previous.row_hash) {
    throw new Error(
      `chain broken: newest.prev_hash (${newest.prev_hash}) !== previous.row_hash (${previous.row_hash})`,
    );
  }
  if (newest.row_hash !== result.row_hash) {
    throw new Error(`appended row_hash (${result.row_hash}) is not the newest stored row`);
  }

  console.log(
    `VERIFY_OK audit-log: hash-chained row appended (prev->row linked) ` +
      `[prev=${newest.prev_hash.slice(0, 12)}… row=${newest.row_hash.slice(0, 12)}…]`,
  );
} catch (e) {
  console.error("VERIFY_FAIL:", e && e.message ? e.message : e);
  process.exitCode = 1;
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
