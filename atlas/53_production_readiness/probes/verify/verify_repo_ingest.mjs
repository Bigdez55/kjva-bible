/**
 * verify_repo_ingest.mjs — proves audit build-item B (the keystone) is WIRED:
 * the live git scan is converted into DURABLE, tenant-scoped repo_connectors rows,
 * the DB-backed read returns them, and the [id] lookup that /api/repos/[id]/{files,commit}
 * use resolves a real twin_root (so those routes stop returning a blanket 403).
 *
 * Checks, on a throwaway temp db (never touches the real ATLAS db):
 *   1. migrate-on-boot creates the schema + seeds the local tenant (item A prereq).
 *   2. ingestRepoConnectors(tenant, {repoPaths:[ATLAS root]}) INSERTs >= 1 connector.
 *   3. The connector id is PATH-UNIQUE (repo:<base>-<hash>) and twin_root === the repo path.
 *   4. scopedSelectWhere by id resolves the row WITH twin_root — the exact lookup the
 *      file/commit write routes perform; previously zero rows => 403.
 *   5. Re-running ingest is IDEMPOTENT (updates, no duplicate insert).
 *
 * Prints VERIFY_OK on success. Run:
 *   node platform/systems/53_production_readiness/probes/verify/verify_repo_ingest.mjs
 */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const REPO_ROOT = process.cwd();
const SHELL = join(REPO_ROOT, "apps", "frontend", "shell");
const tmp = mkdtempSync(join(tmpdir(), "atlas-ingest-verify-"));
const dbPath = join(tmp, "atlas.db");

process.env.ATLAS_RUNTIME = "desktop";
process.env.ATLAS_LOCAL_IDENTITY_ENABLED = "1";
process.env.ATLAS_SQLITE_PATH = dbPath;
process.env.ATLAS_DISCOVER_REPOS = "0"; // scan only the explicit repoPaths below

const imp = (rel) => import(pathToFileURL(join(SHELL, rel)).href);

try {
  // 1. migrate-on-boot (item A prereq)
  const { runMigrations } = await imp("src/lib/db/migrate.ts");
  const { resolveLocalTenantId } = await imp("src/lib/auth/local-identity.ts");
  await runMigrations();
  // Same canonical resolver migrate seeds + the proxy attributes requests to.
  const tenantId = resolveLocalTenantId();

  // 2. ingest the ATLAS repo itself as the known target
  const { ingestRepoConnectors, connectorId } = await imp("src/lib/live/ingestRepos.ts");
  const first = await ingestRepoConnectors(tenantId, { repoPaths: [REPO_ROOT] });
  if (first.runtime !== "desktop") throw new Error(`expected desktop runtime, got ${first.runtime}`);
  if (first.inserted < 1) throw new Error(`expected >=1 connector inserted, got inserted=${first.inserted}`);

  const expectedId = connectorId(tenantId, REPO_ROOT);
  if (!/^repo:[a-z0-9_]+-[0-9a-f]{8}$/.test(expectedId)) {
    throw new Error(`connector id is not path-unique: ${expectedId}`);
  }

  // 3 + 4. the [id] lookup the write routes use must resolve the row WITH twin_root
  const { getDb } = await imp("src/lib/db/client.ts");
  const schema = await imp("src/lib/db/schema.ts");
  const { scopedSelectWhere } = await imp("src/lib/db/tenant-scope.ts");
  const drizzleUrl = pathToFileURL(join(SHELL, "node_modules", "drizzle-orm", "index.js")).href;
  const { eq } = await import(drizzleUrl);
  const db = await getDb();

  const resolved = await scopedSelectWhere(
    db,
    schema.repo_connectors,
    tenantId,
    eq(schema.repo_connectors.id, expectedId),
  ).all();
  if (resolved.length !== 1) throw new Error(`[id] lookup did not resolve exactly one row (got ${resolved.length})`);
  const connector = resolved[0];
  if (!connector.twin_root) throw new Error("resolved connector has no twin_root — file/commit routes would still 403");
  if (connector.twin_root !== REPO_ROOT) throw new Error(`twin_root mismatch: ${connector.twin_root} !== ${REPO_ROOT}`);
  if (connector.tenant_id !== tenantId) throw new Error(`tenant_id mismatch: ${connector.tenant_id} !== ${tenantId}`);

  // the sync_packet snapshot must carry a self-consistent id (list id === detail key === [id])
  const snap = JSON.parse(connector.sync_packet ?? "{}");
  if (snap.summary?.id !== expectedId) {
    throw new Error(`sync_packet summary.id (${snap.summary?.id}) != connector id (${expectedId})`);
  }

  // 5. idempotency — re-ingest updates, does not duplicate
  const second = await ingestRepoConnectors(tenantId, { repoPaths: [REPO_ROOT] });
  if (second.inserted !== 0) throw new Error(`re-ingest should insert 0, inserted=${second.inserted}`);
  const after = await scopedSelectWhere(
    db,
    schema.repo_connectors,
    tenantId,
    eq(schema.repo_connectors.id, expectedId),
  ).all();
  if (after.length !== 1) throw new Error(`idempotency broken: ${after.length} rows for id after re-ingest`);

  // 6. CROSS-TENANT regression — the exact crash the golden-path test caught:
  // a SECOND tenant ingesting the SAME repo path must NOT collide on the global
  // PK (repo_connectors.id). It must self-heal its own tenants row (ensureTenant)
  // and produce a DISTINCT, tenant-namespaced connector id.
  const otherTenant = "local-stub";
  const other = await ingestRepoConnectors(otherTenant, { repoPaths: [REPO_ROOT] });
  if (other.inserted < 1) throw new Error(`cross-tenant ingest inserted ${other.inserted} (expected >=1)`);
  const otherId = connectorId(otherTenant, REPO_ROOT);
  if (otherId === expectedId) throw new Error(`tenant namespacing failed: ${otherId} === ${expectedId}`);
  const otherRows = await scopedSelectWhere(
    db,
    schema.repo_connectors,
    otherTenant,
    eq(schema.repo_connectors.id, otherId),
  ).all();
  if (otherRows.length !== 1) throw new Error(`cross-tenant row not isolated (got ${otherRows.length})`);
  // The first tenant's row must be untouched by the second tenant's ingest.
  const firstStillThere = await scopedSelectWhere(
    db,
    schema.repo_connectors,
    tenantId,
    eq(schema.repo_connectors.id, expectedId),
  ).all();
  if (firstStillThere.length !== 1) throw new Error(`first tenant row clobbered by cross-tenant ingest`);

  console.log(
    `VERIFY_OK repo-ingest: ${first.inserted} connector(s) durable, id ${expectedId}, ` +
      `twin_root resolves for [id] write routes, re-ingest idempotent (updated=${second.updated}), ` +
      `cross-tenant isolated (${otherId} != ${expectedId})`,
  );
} catch (e) {
  console.error("VERIFY_FAIL:", e.message);
  process.exitCode = 1;
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
