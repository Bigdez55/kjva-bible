/**
 * Runtime verify probe for CAP_METRICS (observability is REAL, not theater).
 *
 * AUDIT #9 (metrics theater): metrics-registry.ts DEFINED atlas_requests_total,
 * atlas_auth_failures_total, atlas_rate_limit_hits_total, atlas_audit_events_total,
 * atlas_request_duration_seconds — but NOTHING called .inc()/.observe(), so
 * /api/metrics advertised observability it did not have. This probe proves the
 * instrumentation is WIRED: it exercises the REAL increment paths and then reads
 * the SAME prom-client registry /api/metrics serializes, asserting non-zero samples.
 *
 * Two-part proof (recorder is live AND a route actually calls it):
 *
 *   A. RUNTIME — the recorder increments the SAME registry /api/metrics serializes:
 *        1. startRequestMetrics(req) → done(status)   => atlas_requests_total
 *                                                        + atlas_request_duration_seconds
 *        2. authErrorResponse(new UnauthorizedError()) => atlas_auth_failures_total
 *      then metricsRegistry.metrics() MUST contain a NON-ZERO atlas_requests_total
 *      sample. (Honest scope: this calls startRequestMetrics directly, so the PROBE
 *      is a caller — it proves the recorder works against the live registry, not by
 *      itself that a route invokes it.)
 *
 *   B. CALL-SITE — a production route ACTUALLY calls the recorder. The runtime half
 *      cannot prove this because guards.ts (and thus the route's other imports)
 *      transitively imports `next/server`, which does not resolve under raw-node ESM.
 *      So we assert at the source level that src/app/api/repos/route.ts BOTH imports
 *      AND invokes startRequestMetrics — closing the exact "DEFINED but zero callers"
 *      theater AUDIT #9 targets. Runtime-live + has-a-caller together = WIRED.
 *
 * NOTE: atlas_audit_events_total and atlas_rate_limit_hits_total are also wired
 * (middleware/guards.ts auditRequest / enforceRateLimit) but live behind the
 * next/server taint, so they are not exercised at runtime here.
 *
 * Prints "VERIFY_OK metrics: ..." on success. Exits nonzero + VERIFY_FAIL on failure.
 *
 * Run: node platform/systems/53_production_readiness/probes/verify/verify_metrics_wired.mjs
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const SHELL = join(process.cwd(), "apps", "frontend", "shell");

const imp = (rel) => import(pathToFileURL(join(SHELL, rel)).href);

/** Extract a single counter sample value from the prom-client text exposition. */
function sampleValue(text, metricName) {
  let total = 0;
  let seen = false;
  for (const line of text.split("\n")) {
    if (line.startsWith("#")) continue;
    if (!line.startsWith(metricName)) continue;
    // line form: `name{labels} 123`  OR  `name 123`
    const lastSpace = line.lastIndexOf(" ");
    if (lastSpace < 0) continue;
    const head = line.slice(0, lastSpace);
    // Require the metric token to be EXACTLY metricName (not a `_sum`/`_count` suffix
    // of a different metric, and not a longer metric that shares the prefix).
    const token = head.split("{")[0];
    if (token !== metricName) continue;
    const v = Number(line.slice(lastSpace + 1).trim());
    if (Number.isFinite(v)) {
      total += v;
      seen = true;
    }
  }
  return seen ? total : null;
}

try {
  const { metricsRegistry, startRequestMetrics } = await imp(
    "src/lib/logging/metrics-registry.ts",
  );
  const { authErrorResponse, UnauthorizedError } = await imp("src/lib/auth/errors.ts");

  const req = new Request("http://localhost/api/repos/verify-metrics", { method: "GET" });

  // 1. Request metric — the real route-layer recorder (same fn the repos route calls).
  const done = startRequestMetrics(req);
  done(200);

  // 2. Auth-failure metric — the single 401/403 serialization point.
  const res = authErrorResponse(new UnauthorizedError("verify probe"));
  if (res.status !== 401) throw new Error(`expected 401 from authErrorResponse, got ${res.status}`);

  // Read the SAME registry /api/metrics serializes.
  const text = await metricsRegistry.metrics();

  const requests = sampleValue(text, "atlas_requests_total");
  if (requests === null) throw new Error("atlas_requests_total has NO samples — counter never incremented (theater)");
  if (!(requests > 0)) throw new Error(`atlas_requests_total sample is not > 0 (got ${requests})`);

  const authFailures = sampleValue(text, "atlas_auth_failures_total");
  if (authFailures === null || !(authFailures > 0)) {
    throw new Error(`atlas_auth_failures_total not incremented (got ${authFailures})`);
  }

  // Duration histogram must have observed at least one request (count >= 1).
  const durationCount = sampleValue(text, "atlas_request_duration_seconds_count");
  if (durationCount === null || !(durationCount > 0)) {
    throw new Error(`atlas_request_duration_seconds did not observe a request (count=${durationCount})`);
  }

  // B. CALL-SITE proof: a production route must import AND invoke the recorder, or the
  // runtime half above is moot (recorder works but nothing in the app would ever call
  // it — the exact theater AUDIT #9 targets). next/server taint blocks importing the
  // route at runtime, so assert at the source level instead.
  const routeSrc = readFileSync(join(SHELL, "src/app/api/repos/route.ts"), "utf8");
  if (!/import\s*{[^}]*\bstartRequestMetrics\b[^}]*}\s*from\s*["'][^"']*guards["']/.test(routeSrc)) {
    throw new Error("repos/route.ts does not IMPORT startRequestMetrics — counter has no route caller");
  }
  const callCount = (routeSrc.match(/startRequestMetrics\s*\(/g) || []).length;
  if (callCount < 1) {
    throw new Error("repos/route.ts imports but never CALLS startRequestMetrics — DEFINED, not WIRED");
  }

  console.log(
    `VERIFY_OK metrics: live samples ` +
      `requests_total=${requests}, auth_failures=${authFailures}, ` +
      `duration_count=${durationCount}; route call-sites=${callCount} (repos/route.ts)`,
  );
} catch (e) {
  console.error("VERIFY_FAIL:", e && e.message ? e.message : e);
  process.exitCode = 1;
}
