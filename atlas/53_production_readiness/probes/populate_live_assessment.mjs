/**
 * populate_live_assessment.mjs — write a REAL, probe-driven assessment into the LIVE
 * ATLAS db so /checklist shows a project held against the corpus on first launch
 * (instead of the empty state). This is the app's own behavior with real evidence —
 * NOT fabricated: the verdicts come from the actual probe suite (--emit-verdicts) and
 * are scored by the ONE canonical scorer.
 *
 * Target db: ATLAS_SQLITE_PATH if set, else the default desktop app db
 * (~/Library/Application Support/ATLAS/atlas.db — the path the shipped app uses).
 *
 * Reusable: CI / a cron / the user can re-run it to refresh the assessment. Run from
 * the repo root:
 *   node platform/systems/53_production_readiness/probes/populate_live_assessment.mjs
 */
import { execFileSync } from "node:child_process";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const REPO_ROOT = process.cwd();
const SHELL = join(REPO_ROOT, "apps", "frontend", "shell");
const PROBE_RUNNER = join(REPO_ROOT, "platform", "systems", "53_production_readiness", "probes", "probe_runner.py");

process.env.ATLAS_RUNTIME = "desktop";
if (!process.env.ATLAS_LOCAL_IDENTITY_ENABLED) process.env.ATLAS_LOCAL_IDENTITY_ENABLED = "1";

const imp = (rel) => import(pathToFileURL(join(SHELL, rel)).href);
const impAbs = (abs) => import(pathToFileURL(abs).href);

const { runMigrations } = await imp("src/lib/db/migrate.ts");
const { resolveLocalTenantId } = await imp("src/lib/auth/local-identity.ts");
const { ingestRepoConnectors, connectorId } = await imp("src/lib/live/ingestRepos.ts");
const { checklistVerdictWrite } = await impAbs(
  join(REPO_ROOT, "apps", "backend", "mcp", "src", "tools", "checklist-verdict-write.ts"),
);

// 1. ensure schema + the local tenant exist on the live db (same as app boot).
await runMigrations();
const tenantId = resolveLocalTenantId();

// 2. ensure the ATLAS repo is a durable connector (the FK target for the assessment).
await ingestRepoConnectors(tenantId, { repoPaths: [REPO_ROOT] });
const repoId = connectorId(tenantId, REPO_ROOT);

// 3. run the REAL probe suite as corpus verdicts.
const batch = JSON.parse(execFileSync("python3", [PROBE_RUNNER, "--emit-verdicts"], { cwd: REPO_ROOT, encoding: "utf8" }));

// 4. write the scored assessment via the single canonical write path (source=probe).
const w = checklistVerdictWrite({
  tenantId,
  repoConnectorId: repoId,
  corpusVersion: "PRC_v2",
  profile: "desktop_electron",
  source: "probe",
  verdicts: batch.verdicts.map((v) => ({
    itemId: v.item_id, category: v.category, severity: v.severity,
    verdict: v.verdict, source: "probe", evidence: v.evidence,
  })),
});

console.log(
  `POPULATED ${process.env.ATLAS_SQLITE_PATH || "(default app db)"}: tenant=${tenantId} repo=${repoId} ` +
    `assessment=${w.assessmentId} overall_tier="${w.overallTier}" verdicts=${w.verdictCount} ` +
    `coverage=${w.coverageDepth}% pass-rate=${w.assessedPassRate}%`,
);
