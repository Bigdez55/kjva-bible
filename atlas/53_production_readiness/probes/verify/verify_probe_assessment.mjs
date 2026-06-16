/**
 * verify_probe_assessment.mjs — proves build-item D (probe tie-in) is WIRED:
 * the capability probes EMIT corpus verdicts that flow through the ONE canonical write
 * path into the C data plane (project_assessments + checklist_verdicts), source='probe'.
 *
 * Checks (throwaway temp db; never touches the real ATLAS db):
 *   1. `probe_runner.py --emit-verdicts` returns a verdict batch with EXPLICIT severities.
 *   2. checklistVerdictWrite persists it as a source='probe' assessment (single scorer).
 *   3. TIER REFLECTS REAL PASS/FAIL (not vacuously inflated): probe_desktop_install is the
 *      CRITICAL gate and currently FAILs, so the derived floor_tier MUST be "none". If
 *      severity were defaulting to medium, critical would be vacuously 1.0 and the tier
 *      would lie — this assertion is the guard against that.
 *   4. Read back via drizzle: assessment.source='probe', verdicts carry source='probe'.
 *
 * Prints VERIFY_OK on success.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const REPO_ROOT = process.cwd();
const SHELL = join(REPO_ROOT, "apps", "frontend", "shell");
const PROBE_RUNNER = join(REPO_ROOT, "platform", "systems", "53_production_readiness", "probes", "probe_runner.py");
const tmp = mkdtempSync(join(tmpdir(), "atlas-probe-assess-"));
const dbPath = join(tmp, "atlas.db");

process.env.ATLAS_RUNTIME = "desktop";
process.env.ATLAS_LOCAL_IDENTITY_ENABLED = "1";
process.env.ATLAS_SQLITE_PATH = dbPath;
process.env.ATLAS_DISCOVER_REPOS = "0";

const imp = (rel) => import(pathToFileURL(join(SHELL, rel)).href);
const impAbs = (abs) => import(pathToFileURL(abs).href);
const eq = (a, e, l) => { if (a !== e) throw new Error(`${l}: expected ${JSON.stringify(e)}, got ${JSON.stringify(a)}`); };

try {
  // 1. emit verdicts from the real probe suite
  const raw = execFileSync("python3", [PROBE_RUNNER, "--emit-verdicts"], { cwd: REPO_ROOT, encoding: "utf8" });
  const batch = JSON.parse(raw);
  if (!Array.isArray(batch.verdicts) || batch.verdicts.length < 5) {
    throw new Error(`expected >=5 emitted verdicts, got ${batch.verdicts?.length}`);
  }
  // every emitted verdict must carry an explicit severity + source=probe
  for (const v of batch.verdicts) {
    if (!v.severity) throw new Error(`emitted verdict ${v.item_id} has no severity (would default to medium and inflate the tier)`);
    if (v.source !== "probe") throw new Error(`emitted verdict ${v.item_id} source != probe`);
  }
  const desktop = batch.verdicts.find((v) => v.item_id === "PRC-DESKTOP-INSTALL");
  if (!desktop) throw new Error("PRC-DESKTOP-INSTALL verdict not emitted");
  eq(desktop.severity, "critical", "desktop_install severity");
  eq(desktop.verdict, "fail", "desktop_install verdict (ATLAS.app not installed -> must be fail)");

  // 2. migrate + ingest the ATLAS connector, then write via the single canonical path
  const { runMigrations } = await imp("src/lib/db/migrate.ts");
  const { resolveLocalTenantId } = await imp("src/lib/auth/local-identity.ts");
  await runMigrations();
  const tenantId = resolveLocalTenantId();
  const { ingestRepoConnectors, connectorId } = await imp("src/lib/live/ingestRepos.ts");
  await ingestRepoConnectors(tenantId, { repoPaths: [REPO_ROOT] });
  const repoId = connectorId(tenantId, REPO_ROOT);

  const { checklistVerdictWrite } = await impAbs(
    join(REPO_ROOT, "apps", "backend", "mcp", "src", "tools", "checklist-verdict-write.ts"),
  );
  const w = checklistVerdictWrite({
    tenantId, repoConnectorId: repoId, corpusVersion: "PRC_v2", profile: "desktop_electron", source: "probe",
    verdicts: batch.verdicts.map((v) => ({
      itemId: v.item_id, category: v.category, severity: v.severity, verdict: v.verdict, source: "probe", evidence: v.evidence,
    })),
  });
  if (!w.written) throw new Error("probe assessment did not persist");

  // 3. TIER REFLECTS REAL PASS/FAIL — critical gate (desktop_install) fails -> floor none.
  eq(w.floorTier, "none", "derived floor_tier (critical probe fail must sink tier to none, not vacuous bronze+)");

  // 4. drizzle read-back: source='probe' on the assessment + its verdicts
  const { getDb } = await imp("src/lib/db/client.ts");
  const schema = await imp("src/lib/db/schema.ts");
  const { scopedSelectWhere } = await imp("src/lib/db/tenant-scope.ts");
  const drizzleUrl = pathToFileURL(join(SHELL, "node_modules", "drizzle-orm", "index.js")).href;
  const { eq: dEq } = await import(drizzleUrl);
  const db = await getDb();
  const pa = await scopedSelectWhere(db, schema.project_assessments, tenantId, dEq(schema.project_assessments.id, w.assessmentId)).all();
  eq(pa.length, 1, "assessment persisted");
  eq(pa[0].source, "probe", "assessment.source");
  eq(pa[0].floor_tier, "none", "persisted floor_tier");
  const cv = await scopedSelectWhere(db, schema.checklist_verdicts, tenantId, dEq(schema.checklist_verdicts.assessment_id, w.assessmentId)).all();
  if (cv.length !== batch.verdicts.length) throw new Error(`persisted ${cv.length} verdicts, emitted ${batch.verdicts.length}`);
  if (!cv.every((v) => v.source === "probe")) throw new Error("a persisted verdict has source != probe");

  console.log(
    `VERIFY_OK probe-assessment: ${batch.verdicts.length} probe verdicts -> source=probe assessment via the ` +
      `single write path; derived floor_tier=none (critical desktop_install fail correctly sinks the tier, ` +
      `not vacuously inflated); drizzle read-back confirms source=probe`,
  );
} catch (e) {
  console.error("VERIFY_FAIL:", e.message);
  process.exitCode = 1;
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
