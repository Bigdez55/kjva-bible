/**
 * verify_migrate_on_boot.mjs — proves the durable-persistence prerequisite is WIRED:
 * migrate-on-boot creates the schema + seeds the required tenant rows, and a write
 * persists and reads back on the live desktop runtime (the fix for the audit's
 * "no atlas.db / no such table / FOREIGN KEY constraint failed" finding).
 *
 * Prints VERIFY_OK on success. Run:
 *   node --experimental-strip-types platform/systems/53_production_readiness/probes/verify/verify_migrate_on_boot.mjs
 * Uses a throwaway temp db; never touches the real ATLAS db.
 */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const SHELL = join(process.cwd(), "apps", "frontend", "shell");
const tmp = mkdtempSync(join(tmpdir(), "atlas-migrate-verify-"));
const dbPath = join(tmp, "atlas.db");

process.env.ATLAS_RUNTIME = "desktop";
process.env.ATLAS_LOCAL_IDENTITY_ENABLED = "1";
process.env.ATLAS_SQLITE_PATH = dbPath;

const imp = (rel) => import(pathToFileURL(join(SHELL, rel)).href);

try {
  const { runMigrations } = await imp("src/lib/db/migrate.ts");
  const r = await runMigrations();
  if (!r.migrationsApplied) throw new Error("migrationsApplied=false");
  const localTenant = (r.tenantsEnsured || []).find((t) => t.startsWith("local-")) || (r.tenantsEnsured || [])[0];
  if (!localTenant) throw new Error("no local tenant seeded");

  const { getDb } = await imp("src/lib/db/client.ts");
  const schema = await imp("src/lib/db/schema.ts");
  // Resolve drizzle-orm from the shell package (where it is installed), not repo root.
  const drizzleUrl = pathToFileURL(join(SHELL, "node_modules", "drizzle-orm", "index.js")).href;
  const { eq, and } = await import(drizzleUrl);
  const db = await getDb();

  // schema must have been created
  const tables = db.raw.prepare("SELECT name FROM sqlite_master WHERE type='table'").all().map((t) => t.name);
  for (const need of ["tenants", "knowledge_notes", "repo_connectors"]) {
    if (!tables.includes(need)) throw new Error(`missing table ${need}`);
  }

  // a write must persist + read back under the seeded local tenant (FK satisfied)
  const now = Date.now();
  db.insert(schema.knowledge_notes).values({
    id: "verify-note", tenant_id: localTenant, title: "verify", note_type: "test",
    status: "active", excerpt: "x", body: "y", backlinks: "[]",
    related_graph_nodes: "[]", created_at: now, updated_at: now,
  }).run();
  const rows = db.select().from(schema.knowledge_notes)
    .where(and(eq(schema.knowledge_notes.id, "verify-note"), eq(schema.knowledge_notes.tenant_id, localTenant))).all();
  if (rows.length !== 1) throw new Error("write did not persist");

  console.log(`VERIFY_OK migrate-on-boot: ${tables.length} tables, tenant ${localTenant}, write persisted`);
} catch (e) {
  console.error("VERIFY_FAIL:", e.message);
  process.exitCode = 1;
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
