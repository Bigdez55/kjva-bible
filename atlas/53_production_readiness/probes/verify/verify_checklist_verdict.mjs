/**
 * verify_checklist_verdict.mjs — proves build-item C (project↔checklist data plane) is WIRED:
 * a project's verdicts are recorded against the corpus, scored by the ONE canonical scorer,
 * snapshot into durable tenant-scoped tables, and read back.
 *
 * Checks (throwaway temp db; never touches the real ATLAS db):
 *   1. MIGRATION APPLIES: runMigrations creates project_assessments + checklist_verdicts.
 *   2. SCORER ORACLE: scoreVerdicts on KNOWN inputs yields INDEPENDENTLY-KNOWN tiers/counts
 *      — including the honest-metrics invariant (assessed_pass_rate and coverage_depth are
 *      never conflated; unknown counts as not-passed; tier 'incomplete' until coverage>=90%).
 *   3. THRESHOLD SYNC: the TS TIER_RULES match scoring_rubric.yaml (no divergent scorer).
 *   4. ROUND-TRIP via the MCP tool checklistVerdictWrite (node:sqlite write) -> drizzle read
 *      (cross-driver), with derived counts persisted.
 *   5. IDOR: a write under the wrong tenant is rejected ("not found in tenant scope").
 *
 * Prints VERIFY_OK on success.
 */
import { mkdtempSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const REPO_ROOT = process.cwd();
const SHELL = join(REPO_ROOT, "apps", "frontend", "shell");
const RUBRIC = join(REPO_ROOT, "platform", "systems", "53_production_readiness", "rubric", "scoring_rubric.yaml");
const tmp = mkdtempSync(join(tmpdir(), "atlas-checklist-verify-"));
const dbPath = join(tmp, "atlas.db");

process.env.ATLAS_RUNTIME = "desktop";
process.env.ATLAS_LOCAL_IDENTITY_ENABLED = "1";
process.env.ATLAS_SQLITE_PATH = dbPath;
process.env.ATLAS_DISCOVER_REPOS = "0";

const imp = (rel) => import(pathToFileURL(join(SHELL, rel)).href);
const impAbs = (abs) => import(pathToFileURL(abs).href);

function eq(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

try {
  // 1. migrate + assert new tables exist
  const { runMigrations, /* */ } = await imp("src/lib/db/migrate.ts");
  const { resolveLocalTenantId } = await imp("src/lib/auth/local-identity.ts");
  await runMigrations();
  const tenantId = resolveLocalTenantId();

  const { getDb } = await imp("src/lib/db/client.ts");
  const schema = await imp("src/lib/db/schema.ts");
  const { scopedSelectWhere } = await imp("src/lib/db/tenant-scope.ts");
  const drizzleUrl = pathToFileURL(join(SHELL, "node_modules", "drizzle-orm", "index.js")).href;
  const { eq: dEq, and: dAnd } = await import(drizzleUrl);
  const db = await getDb();
  const tableNames = db.raw.prepare("SELECT name FROM sqlite_master WHERE type='table'").all().map((t) => t.name);
  for (const need of ["project_assessments", "checklist_verdicts"]) {
    if (!tableNames.includes(need)) throw new Error(`migration did not create table ${need}`);
  }

  // 2. SCORER ORACLE — known inputs -> known outputs
  const { scoreVerdicts, TIER_RULES, MIN_COVERAGE_DEPTH_PERCENT } = await imp("src/lib/checklist/scoring.ts");

  // Case A: one of each severity, all pass, full coverage -> platinum
  const A = scoreVerdicts([
    { severity: "critical", verdict: "pass" }, { severity: "high", verdict: "pass" },
    { severity: "medium", verdict: "pass" }, { severity: "low", verdict: "pass" },
  ]);
  eq(A.floor_tier, "platinum", "A.floor_tier");
  eq(A.overall_tier, "platinum", "A.overall_tier");
  eq(A.coverage_depth, 100, "A.coverage_depth");
  eq(A.assessed_pass_rate, 100, "A.assessed_pass_rate");

  // Case B: 1 critical pass + 9 critical not_assessed -> honest: unknown not a pass,
  // coverage gate trips. assessed_pass_rate(100) and coverage_depth(10) NOT conflated.
  const B = scoreVerdicts([
    { severity: "critical", verdict: "pass" },
    ...Array.from({ length: 9 }, () => ({ severity: "critical", verdict: "not_assessed" })),
  ]);
  eq(B.floor_tier, "none", "B.floor_tier");
  eq(B.coverage_depth, 10, "B.coverage_depth");
  eq(B.assessed_pass_rate, 100, "B.assessed_pass_rate");
  if (!B.overall_tier.startsWith("incomplete")) throw new Error(`B.overall_tier should be incomplete, got ${B.overall_tier}`);

  // Case C: crit1 high1 medium=0.90 low1 -> gold (not platinum: med<0.95)
  const C = scoreVerdicts([
    { severity: "critical", verdict: "pass" }, { severity: "high", verdict: "pass" },
    ...Array.from({ length: 9 }, () => ({ severity: "medium", verdict: "pass" })),
    { severity: "medium", verdict: "fail" },
    { severity: "low", verdict: "pass" },
  ]);
  eq(C.floor_tier, "gold", "C.floor_tier");
  eq(C.overall_tier, "gold", "C.overall_tier");
  eq(C.pass_count, 12, "C.pass_count");
  eq(C.fail_count, 1, "C.fail_count");
  eq(C.assessed_pass_rate, 92.3, "C.assessed_pass_rate");

  // Case D — AUDIT-#2 EXPLOIT GUARD: a 1-item all-pass submission scored against the
  // FULL Production-Readiness Corpus (the write APIs ALWAYS pass corpusInScope) must
  // NEVER certify. coverage_depth must be far below 90 (1 judged / ~3378 in-scope) and
  // overall_tier must be 'incomplete' — never 'platinum'. This case FAILS against the
  // pre-fix scorer (which ignored the corpus and read 100% coverage off the lone item)
  // and PASSES only with the corpus-anchored coverage_depth.
  const { loadCorpusInScope, resolveCorpusPath } = await impAbs(
    join(REPO_ROOT, "apps", "frontend", "shell", "src", "lib", "checklist", "corpus-in-scope.ts"),
  );
  const corpusJson = JSON.parse(readFileSync(resolveCorpusPath(), "utf8"));
  const corpusItemCount = corpusJson.item_count;
  const corpusInScope = loadCorpusInScope();
  const inScopeSum = corpusInScope.critical + corpusInScope.high + corpusInScope.medium + corpusInScope.low;
  if (inScopeSum !== corpusItemCount) {
    throw new Error(`corpus in-scope split ${inScopeSum} != corpus item_count ${corpusItemCount}`);
  }
  const D = scoreVerdicts([{ severity: "critical", verdict: "pass" }], corpusInScope);
  if (D.coverage_depth >= 90) {
    throw new Error(`AUDIT-#2 EXPLOIT OPEN: 1-item assessment coverage_depth=${D.coverage_depth} >= 90 (must be far below)`);
  }
  if (!D.overall_tier.startsWith("incomplete")) {
    throw new Error(`AUDIT-#2 EXPLOIT OPEN: 1-item assessment overall_tier=${D.overall_tier} (must be 'incomplete')`);
  }
  if (D.overall_tier.startsWith("platinum") || D.floor_tier === "platinum") {
    throw new Error(`AUDIT-#2 EXPLOIT OPEN: 1-item assessment reads platinum (overall=${D.overall_tier} floor=${D.floor_tier})`);
  }
  // assessed_pass_rate is still 100 (the ONE judged item passed) — coverage and pass-rate
  // are never conflated. total_items stays the SUBMITTED count (1), not the corpus size.
  eq(D.assessed_pass_rate, 100, "D.assessed_pass_rate");
  eq(D.total_items, 1, "D.total_items");
  eq(D.judged, 1, "D.judged");
  eq(D.in_scope, corpusItemCount, "D.in_scope (corpus-anchored)");

  // 3. THRESHOLD SYNC — TS TIER_RULES must match scoring_rubric.yaml
  const yaml = readFileSync(RUBRIC, "utf8");
  const reqOf = (tier) => (yaml.match(new RegExp(tier + ":\\s*\\n\\s*requires:\\s*\\{([^}]*)\\}")) || [, ""])[1];
  const num = (block, sev) => { const m = block.match(new RegExp(sev + ":\\s*([\\d.]+)")); return m ? parseFloat(m[1]) : null; };
  eq(num(reqOf("bronze"), "critical"), TIER_RULES.bronze.critical, "yaml bronze.critical");
  eq(num(reqOf("silver"), "high"), TIER_RULES.silver.high, "yaml silver.high");
  eq(num(reqOf("gold"), "medium"), TIER_RULES.gold.medium, "yaml gold.medium");
  eq(num(reqOf("platinum"), "medium"), TIER_RULES.platinum.medium, "yaml platinum.medium");
  eq(num(reqOf("platinum"), "low"), TIER_RULES.platinum.low, "yaml platinum.low");
  const cov = parseInt((yaml.match(/min_coverage_depth_percent:\s*(\d+)/) || [, ""])[1], 10);
  eq(cov, MIN_COVERAGE_DEPTH_PERCENT, "yaml min_coverage_depth_percent");

  // 4. ROUND-TRIP via the MCP tool (node:sqlite write) -> drizzle read (cross-driver)
  const { ingestRepoConnectors, connectorId } = await imp("src/lib/live/ingestRepos.ts");
  await ingestRepoConnectors(tenantId, { repoPaths: [REPO_ROOT] });
  const repoId = connectorId(tenantId, REPO_ROOT);

  const { checklistVerdictWrite } = await impAbs(
    join(REPO_ROOT, "apps", "backend", "mcp", "src", "tools", "checklist-verdict-write.ts"),
  );
  const w = checklistVerdictWrite({
    tenantId, repoConnectorId: repoId, corpusVersion: "PRC_v2", profile: "desktop_electron", source: "agent",
    verdicts: [
      { itemId: "PRC-BACKEND-001", category: "Database", severity: "critical", verdict: "pass" },
      { itemId: "PRC-BACKEND-002", category: "Database", severity: "high", verdict: "fail", evidence: "no pooling" },
      { itemId: "PRC-SEC-001", category: "Security & Authentication", severity: "critical", verdict: "not_assessed" },
    ],
  });
  if (!w.written) throw new Error("MCP write did not persist");

  // drizzle read-back: the assessment row + its verdicts, tenant-scoped
  const pa = await scopedSelectWhere(db, schema.project_assessments, tenantId, dEq(schema.project_assessments.repo_connector_id, repoId)).all();
  if (pa.length !== 1) throw new Error(`expected 1 assessment, got ${pa.length}`);
  const row = pa[0];
  eq(row.id, w.assessmentId, "assessment id round-trip");
  eq(row.pass_count, 1, "persisted pass_count");
  eq(row.fail_count, 1, "persisted fail_count");
  eq(row.unknown_count, 1, "persisted unknown_count");
  // floor: critical has a not_assessed (ratio crit = 1 pass / 2 in-scope = 0.5 < 1) -> none
  eq(row.floor_tier, "none", "persisted floor_tier");
  // CORPUS-ANCHORED via the MCP path too: 2 judged of ~3378 in-scope -> coverage far
  // below 90, so the persisted overall_tier is 'incomplete', never a certified medal.
  if (row.coverage_depth >= 90) {
    throw new Error(`MCP write not corpus-anchored: persisted coverage_depth=${row.coverage_depth} >= 90`);
  }
  if (!String(row.overall_tier).startsWith("incomplete")) {
    throw new Error(`MCP write not corpus-anchored: persisted overall_tier=${row.overall_tier} (expected incomplete)`);
  }
  const cv = await scopedSelectWhere(db, schema.checklist_verdicts, tenantId, dEq(schema.checklist_verdicts.assessment_id, w.assessmentId)).all();
  eq(cv.length, 3, "persisted verdict count");

  // 5. IDOR — a write under a DIFFERENT tenant must be rejected (repo not in its scope)
  let idorRejected = false;
  try {
    checklistVerdictWrite({ tenantId: "local-someone-else", repoConnectorId: repoId, verdicts: [{ itemId: "x", verdict: "pass" }] });
  } catch (e) {
    idorRejected = /not found in tenant scope/.test(e.message);
  }
  if (!idorRejected) throw new Error("IDOR gate failed: cross-tenant write was not rejected");

  console.log(
    `VERIFY_OK checklist-verdict: migration applied (project_assessments+checklist_verdicts), ` +
      `scorer oracle A=platinum/B=incomplete(cov10,apr100)/C=gold(apr92.3), ` +
      `D=audit-#2 guard (1-item all-pass vs full corpus -> coverage ${D.coverage_depth}% < 90, overall incomplete, NOT platinum), ` +
      `TS rules match scoring_rubric.yaml, ` +
      `MCP write->drizzle read round-trip corpus-anchored (cov ${row.coverage_depth}% < 90, overall incomplete, floor none, 3 verdicts), IDOR rejected`,
  );
} catch (e) {
  console.error("VERIFY_FAIL:", e.message);
  process.exitCode = 1;
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
