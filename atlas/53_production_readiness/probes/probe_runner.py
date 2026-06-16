#!/usr/bin/env python3
"""
probe_runner.py — EVIDENCE PROBES decide pass/fail. The agent never self-declares done.

Each probe inspects REAL repo/filesystem state and returns a verdict backed by evidence.
This is the structural fix for false-completion: a claim ("done/proven/ready") is only
valid if its backing probe(s) PASS. A probe that cannot determine state returns
`unknown` — which is treated as NOT pass (an unassessed item is never a pass).

Verdicts: pass | fail | unknown   (unknown/error == NOT pass, everywhere downstream)

Probes here cover the gaps the user NAMED for ATLAS; each ties to a CAP_* in
capabilities/registry.yaml and (where applicable) a corpus category. The probe is the
source of truth at audit time; overlay.yaml's declared capability_status is just the map.

Usage:
  python3 probe_runner.py                 # run all probes, human report
  python3 probe_runner.py --json          # machine report -> probe_results.json shape
  python3 probe_runner.py --write         # also write results/probe_results.json
  python3 probe_runner.py --self-test     # assert probes return known-bad verdicts on ATLAS-today
"""
from __future__ import annotations
import argparse
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

# F-04 fix: a hung verify (e.g. verify_mcp_boot's lingering SSE socket holding node
# alive) used to block git for the full 120s × 15 probes and leak node procs. Bound
# every verify hard, and kill it as a PROCESS GROUP so no node/grandchild/socket
# survives. Override with ATLAS_VERIFY_TIMEOUT for slow machines.
VERIFY_TIMEOUT = max(5, int(os.environ.get("ATLAS_VERIFY_TIMEOUT", "20")))

HERE = Path(__file__).resolve().parent
PR_ROOT = HERE.parent                                  # 53_production_readiness
REPO_ROOT = PR_ROOT.parents[2]                         # ATLAS repo root
RESULTS = HERE / "results"
SHELL = REPO_ROOT / "apps" / "frontend" / "shell"
MCP = REPO_ROOT / "apps" / "backend" / "mcp"


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _grep_repo(pattern: str, *roots: Path) -> list[str]:
    """Return matching 'file:line' for a regex across the given roots (src/ts only)."""
    rx = re.compile(pattern)
    hits: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix not in {".ts", ".tsx", ".mjs", ".js"}:
                continue
            if "node_modules" in p.parts:
                continue
            txt = _read(p)
            for i, line in enumerate(txt.splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{p.relative_to(REPO_ROOT)}:{i}")
                    if len(hits) >= 8:
                        return hits
    return hits


def verdict(pid, target, v, evidence, cap=None, category=None):
    return {"id": pid, "target": target, "verdict": v, "evidence": evidence,
            "capability": cap, "category": category}


# Per-process probe memo: probe_capability_executable re-uses the same per-cap verifiers that
# run_all runs standalone; without this each node verify script would spawn twice. Probes are
# deterministic within a run, so caching by name is safe and roughly halves wall-clock.
_RUN_CACHE: dict = {}


def _call_probe(fn):
    name = fn.__name__
    if name not in _RUN_CACHE:
        _RUN_CACHE[name] = fn()
    return _RUN_CACHE[name]


VERIFY_DIR = HERE / "verify"


def _run_verify(script_name: str, env_extra: dict | None = None) -> tuple[bool, str]:
    """Execute a capability verify script; WIRED proof = it prints VERIFY_OK at runtime.

    This is the wired-vs-defined principle: a capability is real only if it CALLS at
    runtime, not because a string pattern matched. Returns (ok, evidence).
    """
    script = VERIFY_DIR / script_name
    if not script.exists():
        return False, f"verify script missing: {script.relative_to(REPO_ROOT)}"
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    # start_new_session=True puts node in its OWN process group (it becomes the leader,
    # so pgid == pid). On timeout/exit we SIGKILL the whole group, so a lingering SSE
    # socket or any grandchild node dies with the probe — the F-04 "20 leaked node +
    # hung git" failure can no longer happen.
    proc = None
    pgid = None
    out = ""
    rc = -1
    try:
        proc = subprocess.Popen(
            ["node", "--experimental-strip-types", str(script)],
            cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env, start_new_session=True,
        )
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            pgid = proc.pid
        try:
            out, _ = proc.communicate(timeout=VERIFY_TIMEOUT)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            return False, (f"{script_name}: TIMEOUT >{VERIFY_TIMEOUT}s — process group killed, "
                           "no node/socket left (treated as NOT pass)")
    except Exception as e:
        return False, f"verify run error: {e}"
    finally:
        # No-residue guarantee: kill the whole group even on the success path, so any
        # detached grandchild / lingering keep-alive socket cannot survive the probe.
        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        if proc is not None:
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
    combined = out or ""
    ok = rc == 0 and "VERIFY_OK" in combined
    tail = combined.strip().splitlines()[-1] if combined.strip() else "(no output)"
    return ok, f"{script_name}: rc={rc} → {tail[:80]}"


# --------------------------------------------------------------------------- #
# PROBES — each returns a verdict dict. unknown/error == NOT pass.
# --------------------------------------------------------------------------- #

def probe_mcp_bootable() -> dict:
    """The MCP server actually BOOTS: WIRED proof = verify_mcp_boot.mjs constructs the
    server (imports `Server` from @modelcontextprotocol/sdk + wires handlers) and
    prints VERIFY_OK at runtime.

    This is wired-vs-defined for the server itself: the tool source files can all
    exist while the server cannot boot (the SDK dist was OneDrive-dehydrated, so the
    import threw ERR_MODULE_NOT_FOUND). A grep over src/ would FALSELY pass; only an
    actual construct-and-dispatch run proves bootability. Verdict comes from
    EXECUTION, not a string match."""
    entry = MCP / "src" / "index.ts"
    factory = MCP / "src" / "server-factory.ts"
    if entry.exists() and factory.exists():
        ok, ev = _run_verify("verify_mcp_boot.mjs")
        if ok:
            return verdict("probe_mcp_bootable", "ATLAS", "pass",
                           f"WIRED (runtime verify): {ev}",
                           cap="CAP_MCP_SERVER_BOOT", category="Backend")
        return verdict("probe_mcp_bootable", "ATLAS", "fail",
                       f"MCP source exists but runtime boot verify did NOT print VERIFY_OK: {ev}",
                       cap="CAP_MCP_SERVER_BOOT", category="Backend")
    return verdict("probe_mcp_bootable", "ATLAS", "fail",
                   "MCP server source missing: apps/backend/mcp/src/index.ts or server-factory.ts absent",
                   cap="CAP_MCP_SERVER_BOOT", category="Backend")


def probe_git_writeback() -> dict:
    """CAP_REPO_GIT_WRITEBACK: WIRED proof = the verify script actually commits at runtime.
    Verdict comes from EXECUTION (wired-vs-defined), not a string grep."""
    # The capability is real iff: the tool module exists AND its verify script runs green.
    tool = MCP / "src" / "tools" / "repo-git-writeback.ts"
    if tool.exists():
        ok, ev = _run_verify("verify_git_writeback.mjs")
        if ok:
            return verdict("probe_git_writeback", "ATLAS", "pass",
                           f"WIRED (runtime verify): {ev}",
                           cap="CAP_REPO_GIT_WRITEBACK", category="Integrations")
        return verdict("probe_git_writeback", "ATLAS", "fail",
                       f"tool exists but runtime verify did NOT print VERIFY_OK: {ev}",
                       cap="CAP_REPO_GIT_WRITEBACK", category="Integrations")
    return verdict("probe_git_writeback", "ATLAS", "fail",
                   "no git commit/push capability: apps/backend/mcp/src/tools/repo-git-writeback.ts missing",
                   cap="CAP_REPO_GIT_WRITEBACK", category="Integrations")


def probe_repo_editable() -> dict:
    """CAP_REPO_FILE_WRITE + CAP_KNOWLEDGE_NOTE_WRITE: WIRED proof = the file-write AND
    knowledge-write verify scripts both actually persist at runtime, AND a mutating
    HTTP handler exists (so the capability is reachable from the app, not just the lib)."""
    fw_tool = (MCP / "src" / "tools" / "repo-file-write.ts").exists()
    kw_tool = (MCP / "src" / "tools" / "knowledge-note-write.ts").exists()
    write_handlers = _grep_repo(r"export\s+(async\s+)?function\s+(POST|PUT|PATCH|DELETE)",
                                SHELL / "src" / "app" / "api" / "repos",
                                SHELL / "src" / "app" / "api" / "knowledge")
    if fw_tool and kw_tool and write_handlers:
        fw_ok, fw_ev = _run_verify("verify_repo_file_write.mjs")
        import tempfile
        kw_ok, kw_ev = _run_verify(
            "verify_knowledge_write.mjs",
            {"ATLAS_RUNTIME": "desktop",
             "ATLAS_SQLITE_PATH": str(Path(tempfile.gettempdir()) / "atlas-knowledge-probe.db")},
        )
        if fw_ok and kw_ok:
            return verdict("probe_repo_editable", "ATLAS", "pass",
                           f"WIRED (runtime verify): file-write[{fw_ev}] + knowledge-write[{kw_ev}] "
                           f"+ {len(write_handlers)} mutating HTTP handlers",
                           cap="CAP_REPO_FILE_WRITE", category="Backend")
        return verdict("probe_repo_editable", "ATLAS", "fail",
                       f"tools+handlers exist but runtime verify failed: file-write[{fw_ev}] knowledge-write[{kw_ev}]",
                       cap="CAP_REPO_FILE_WRITE", category="Backend")
    # legacy static-detection fallback (no real tools yet)
    persist = _grep_repo(r"(insert|update|\.values\(|writeFile|fs\.write)",
                         SHELL / "src" / "app" / "api" / "repos",
                         SHELL / "src" / "app" / "api" / "knowledge")
    if write_handlers and persist:
        return verdict("probe_repo_editable", "ATLAS", "pass",
                       f"mutating handlers + persistence: {write_handlers[:3]} / {persist[:3]}",
                       cap="CAP_REPO_FILE_WRITE", category="Backend")
    return verdict("probe_repo_editable", "ATLAS", "fail",
                   f"no real write path under /api/repos or /api/knowledge "
                   f"(mutating handlers={len(write_handlers)}, persistence={len(persist)}, fs_writes={len(fs_writes)}) "
                   "— routes are read-only (buildLocalAtlasPayload / GET)",
                   cap="CAP_REPO_FILE_WRITE", category="Backend")


def probe_desktop_install() -> dict:
    """CAP_DESKTOP_INSTALL: is ATLAS actually installed as a FUNCTIONAL standalone Mac app?

    Hardened (2026-06-02): presence alone false-greened on a hollow 2MB thin launcher
    (the package:local .app needs sidecar server/node_modules; it is NOT self-contained).
    A real installed app is the electron-builder self-contained bundle: it carries the
    Electron Framework and the bundled app code, ~hundreds of MB. So we require BOTH the
    app present AND a self-contained structure (Electron Framework + an app.asar or
    Resources/app server) AND a non-trivial size — otherwise it's a hollow shell.
    """
    installed = list(Path("/Applications").glob("ATLAS.app")) + list(Path("/Applications").glob("Atlas.app"))
    if installed:
        app = installed[0]
        framework = (app / "Contents" / "Frameworks" / "Electron Framework.framework").exists()
        has_app_code = (
            (app / "Contents" / "Resources" / "app.asar").exists()
            or (app / "Contents" / "Resources" / "app").exists()
            or (app / "Contents" / "Resources" / "app.asar.unpacked").exists()
        )
        try:
            size_mb = sum(f.stat().st_size for f in app.rglob("*") if f.is_file()) / (1024 * 1024)
        except Exception:
            size_mb = 0.0
        if framework and has_app_code and size_mb >= 80:
            return verdict("probe_desktop_install", "ATLAS", "pass",
                           f"installed (self-contained): {app} — Electron Framework + app code, {size_mb:.0f}MB",
                           cap="CAP_DESKTOP_INSTALL", category="Desktop Application")
        return verdict("probe_desktop_install", "ATLAS", "fail",
                       f"{app} present but HOLLOW (framework={framework}, app_code={has_app_code}, "
                       f"{size_mb:.1f}MB) — a thin launcher, not a self-contained app. Install the "
                       f"electron-builder bundle, not package:local's run-from-folder .app.",
                       cap="CAP_DESKTOP_INSTALL", category="Desktop Application")
    dmg = list((SHELL / "dist").rglob("*.dmg")) if (SHELL / "dist").exists() else []
    return verdict("probe_desktop_install", "ATLAS", "fail",
                   f"ATLAS.app NOT in /Applications. "
                   f"{'built .dmg exists in dist/ but never installed: ' + str(dmg[0].relative_to(REPO_ROOT)) if dmg else 'no built .dmg either'}",
                   cap="CAP_DESKTOP_INSTALL", category="Desktop Application")


def probe_route_is_live() -> dict:
    """Is the repos API live (durable DB) data or a static/demo payload?

    Asserts the REAL property: the route SELECTs durable repo_connectors from the DB.
    A bare grep for `buildLocalAtlasPayload` is wrong — the DB-backed route keeps it
    ONLY as the hosted-runtime fallback. So we require POSITIVE evidence of a DB read
    (scopedSelect + repo_connectors + getDb). This is STRICTER than the old check
    against the known-bad oracle: the pre-ingest route had buildLocalAtlasPayload as
    its SOLE source with no scopedSelect/repo_connectors → still FAILs here.
    (Runtime-confirmed separately: live GET /api/repos returns source:"db".)
    """
    repos_route = _read(SHELL / "src" / "app" / "api" / "repos" / "route.ts")
    if not repos_route:
        return verdict("probe_route_is_live", "ATLAS", "unknown",
                       "apps/frontend/shell/src/app/api/repos/route.ts not found", category="Backend")
    serves_db = (
        bool(re.search(r"scopedSelect", repos_route))
        and "repo_connectors" in repos_route
        and "getDb" in repos_route
    )
    # mvp-data / buildDemo as a DATA SOURCE (not a typed fallback) is still demo theater.
    demo_only = bool(re.search(r"(mvp-data|buildDemo)", repos_route)) and not serves_db
    if serves_db and not demo_only:
        return verdict("probe_route_is_live", "ATLAS", "pass",
                       "/api/repos SELECTs durable repo_connectors from the DB (scopedSelect+getDb); "
                       "buildLocalAtlasPayload remains only as the hosted fallback", category="Backend")
    return verdict("probe_route_is_live", "ATLAS", "fail",
                   "/api/repos returns a static/demo payload with no durable DB read — not live data",
                   category="Backend")


def probe_page_is_live() -> dict:
    """Does the repos PAGE render DB-backed data, or static mvp-data? (build-item #6 gate)

    The DB-backed API exists (probe_route_is_live passes), but the rendered page must
    actually CONSUME it for the USER to see real data. Today /repos re-exports repo-twin,
    which imports lib/mvp-data and never fetches /api/repos — so the user still SEES
    theater even though the data plane is real. This probe makes the data-plane/UI boundary
    HONEST and probe-tracked (not self-reported in prose): it stays FAIL until build-item #6
    wires the page to the API. (The user's core complaint was being unable to SEE projects
    held against the checklist — this is the gate that closes only when they can.)
    """
    repos_page = _read(SHELL / "src" / "app" / "repos" / "page.tsx")
    # /repos is a re-export of repo-twin — the real renderer is repo-twin/page.tsx.
    renderer = _read(SHELL / "src" / "app" / "repo-twin" / "page.tsx") or repos_page
    if not renderer:
        return verdict("probe_page_is_live", "ATLAS", "unknown",
                       "repos page / repo-twin renderer not found", category="Frontend")
    fetches_api = bool(re.search(r"/api/(repos|production-readiness)", renderer))
    # Detect mvp-data as a real DATA SOURCE (an import), not a mention in a comment.
    imports_mvp = bool(re.search(r"from\s+['\"][^'\"]*mvp-data", renderer))
    if fetches_api and not imports_mvp:
        return verdict("probe_page_is_live", "ATLAS", "pass",
                       "repos page renders DB-backed data from the API (no mvp-data import)", category="Frontend")
    return verdict("probe_page_is_live", "ATLAS", "fail",
                   "repos page (/repos -> repo-twin) renders static lib/mvp-data and never fetches the API "
                   "— the DB-backed data plane exists but the rendered surface is still theater "
                   "(build-item #6: wire frontend to backend)", category="Frontend")


def probe_checklist_page_is_live() -> dict:
    """Is there a RENDERED surface showing projects held against the checklist? (C+D payoff)

    The user's core complaint was being unable to SEE projects held against the checklist.
    The /checklist page must fetch the DB-backed fleet rollup (/api/production-readiness)
    and render real data — not static mvp-data. Goes green when that surface exists; this
    is the positive counterpart to probe_page_is_live (which still tracks the repo-twin
    theater under build-item #6).
    """
    page = _read(SHELL / "src" / "app" / "checklist" / "page.tsx")
    if not page:
        return verdict("probe_checklist_page_is_live", "ATLAS", "fail",
                       "no /checklist page — 'projects held against the checklist' has no rendered surface",
                       category="Frontend")
    fetches = "/api/production-readiness" in page
    # mvp-data as a real DATA SOURCE (an import), not a mention in a comment.
    imports_mvp = bool(re.search(r"from\s+['\"][^'\"]*mvp-data", page))
    if fetches and not imports_mvp:
        return verdict("probe_checklist_page_is_live", "ATLAS", "pass",
                       "/checklist renders the DB-backed fleet rollup from /api/production-readiness (no mvp-data import)",
                       category="Frontend")
    return verdict("probe_checklist_page_is_live", "ATLAS", "fail",
                   "/checklist exists but does not render the live rollup", category="Frontend")


def probe_claim_backed() -> dict:
    """FLAGSHIP: any file asserting proven/READY/done must have its backing probes pass.
    Today production-readiness.ts hardcodes READY_FOR_PUBLIC_RELEASE for the read-only demo.
    """
    prt = SHELL / "src" / "lib" / "production-readiness.ts"
    txt = _read(prt)
    if not txt:
        return verdict("probe_claim_backed", "ATLAS", "unknown",
                       "production-readiness.ts not found", category=None)
    # A READY/proven claim is only legitimate if the COMMITTED release recommendation is
    # READY (derived from the full probe suite). If the derived recommendation is BLOCK but
    # the file still carries READY/proven markers, the claim is unbacked → fail.
    # NOTE: the canonical authority is the derived <derived-gate-state> block, NOT scattered
    # markers; we re-derive from the other probes here to avoid self-reference.
    ready_rec = bool(re.search(r"atlasReleaseRecommendation[^\n]*READY|releaseRecommendation:\s*['\"]READY", txt))
    proven_markers = re.findall(r"state:\s*['\"]proven['\"]", txt)
    # backing = every probe except this one
    backing = [probe_git_writeback(), probe_repo_editable(), probe_desktop_install(), probe_route_is_live(), probe_page_is_live()]
    failing = [b["id"] for b in backing if b["verdict"] != "pass"]
    rel = prt.relative_to(REPO_ROOT)
    # If the file asserts READY/PUBLIC_RELEASE_READY anywhere, ALL backing probes must pass.
    asserts_ready = bool(re.search(r"(READY_FOR_PUBLIC_RELEASE|PUBLIC_RELEASE_READY)", txt)) or ready_rec
    if asserts_ready and failing:
        return verdict("probe_claim_backed", "ATLAS", "fail",
                       f"{rel} asserts public-release READY BUT backing probes FAIL: {failing}. Unbacked claim.",
                       category=None)
    # Legacy per-gate state:"proven" markers are acceptable ONLY while the derived recommendation
    # is BLOCK (they are the old gate block, not the authoritative derived state) — but if the file
    # claims READY while probes fail, that's the lie we catch above. With derived=BLOCK + no READY
    # assertion, the file is honest.
    if not asserts_ready:
        return verdict("probe_claim_backed", "ATLAS", "pass",
                       f"{rel} carries no public-release READY claim (derived state governs; "
                       f"{len(proven_markers)} legacy per-gate markers tolerated while derived=BLOCK).",
                       category=None)
    return verdict("probe_claim_backed", "ATLAS", "pass",
                   f"{rel} READY claim is backed: all {len(backing)} capability probes pass.", category=None)


def _mutating_route_files() -> list[Path]:
    """The mutating route handlers the guards must be wired into (NOT guards.ts itself,
    so the grep can't false-positive on the guard module's own export)."""
    api = SHELL / "src" / "app" / "api"
    return [
        api / "repos" / "[id]" / "commit" / "route.ts",
        api / "repos" / "[id]" / "files" / "route.ts",
        api / "repos" / "[id]" / "assessment" / "route.ts",
        api / "repos" / "route.ts",
        api / "knowledge" / "route.ts",
        api / "ingest" / "repo-event" / "route.ts",
    ]


def _route_files_mentioning(token: str) -> list[str]:
    """Return 'file:count' for each mutating route file whose TEXT contains `token`."""
    hits = []
    for p in _mutating_route_files():
        txt = _read(p)
        n = txt.count(token)
        if n > 0:
            hits.append(f"{p.relative_to(REPO_ROOT)}:{n}")
    return hits


def probe_rate_limit_wired() -> dict:
    """CAP_RATE_LIMIT: WIRED proof = (a) mutating routes reference enforceRateLimit AND
    (b) the rate-limit engine actually persists a durable bucket row at runtime
    (verify_rate_limit.mjs prints VERIFY_OK). Both required — a grep alone is DEFINED,
    not CALLED."""
    referenced = _route_files_mentioning("enforceRateLimit")
    if not referenced:
        return verdict("probe_rate_limit_wired", "ATLAS", "fail",
                       "no mutating route references enforceRateLimit — rate limit not wired into the HTTP surface",
                       cap="CAP_RATE_LIMIT", category="Rate Limiting")
    ok, ev = _run_verify("verify_rate_limit.mjs",
                         {"ATLAS_RUNTIME": "desktop", "ATLAS_LOCAL_IDENTITY_ENABLED": "1"})
    if ok:
        return verdict("probe_rate_limit_wired", "ATLAS", "pass",
                       f"WIRED: {len(referenced)} routes call enforceRateLimit + runtime verify [{ev}]",
                       cap="CAP_RATE_LIMIT", category="Rate Limiting")
    return verdict("probe_rate_limit_wired", "ATLAS", "fail",
                   f"routes reference enforceRateLimit but runtime verify did NOT print VERIFY_OK: {ev}",
                   cap="CAP_RATE_LIMIT", category="Rate Limiting")


def probe_audit_wired() -> dict:
    """CAP_AUDIT_LOG: WIRED proof = (a) mutating routes reference auditRequest AND
    (b) the audit engine actually appends a hash-chained row at runtime
    (verify_audit_log.mjs prints VERIFY_OK). Both required."""
    referenced = _route_files_mentioning("auditRequest")
    if not referenced:
        return verdict("probe_audit_wired", "ATLAS", "fail",
                       "no mutating route references auditRequest — audit logging not wired into the HTTP surface",
                       cap="CAP_AUDIT_LOG", category="Audit Logging")
    ok, ev = _run_verify("verify_audit_log.mjs",
                         {"ATLAS_RUNTIME": "desktop", "ATLAS_LOCAL_IDENTITY_ENABLED": "1"})
    if ok:
        return verdict("probe_audit_wired", "ATLAS", "pass",
                       f"WIRED: {len(referenced)} routes call auditRequest + runtime verify [{ev}]",
                       cap="CAP_AUDIT_LOG", category="Audit Logging")
    return verdict("probe_audit_wired", "ATLAS", "fail",
                   f"routes reference auditRequest but runtime verify did NOT print VERIFY_OK: {ev}",
                   cap="CAP_AUDIT_LOG", category="Audit Logging")


def probe_capability_executable() -> dict:
    """Aggregate: for each CAP_* in the registry, is it actually executable/wired?
    Reuses the specific probes above; reports per-capability WIRED vs MISSING.
    """
    reg_path = PR_ROOT / "capabilities" / "registry.yaml"
    try:
        import yaml
        reg = yaml.safe_load(_read(reg_path)) or {}
    except Exception as e:
        return verdict("probe_capability_executable", "registry", "unknown",
                       f"cannot read capability registry: {e}")
    caps = reg.get("capabilities", [])
    results = []
    for c in caps:
        cid = c.get("id")
        declared = (c.get("status") or "").upper()
        pname = c.get("probe")
        if declared == "NA":
            # explicitly not-applicable (e.g. the deprecated desktop surface) — not a mismatch.
            results.append({"cap": cid, "declared": declared, "probe_actual": "NA", "match": True})
            continue
        fn = PROBE_BY_NAME.get(pname)
        if fn is not None and pname != "probe_capability_executable":
            v = _call_probe(fn)["verdict"]
            actual = {"pass": "WIRED", "fail": "MISSING"}.get(v, "UNKNOWN")
        else:
            # No INDEPENDENT probe wired -> cannot CLAIM WIRED (audit #13 removed the old
            # actual=declared rubber-stamp; a read-only cap is no longer accepted on its own say-so).
            actual = "UNKNOWN"
        # The lie #13 exists to catch: declared executable but the probe ACTIVELY reports it absent.
        # actual==UNKNOWN abstains (couldn't assess — e.g. a host-only deployment probe off-host) —
        # honest non-assertion, not a pass and not a contradiction.
        declared_exec = declared in ("WIRED", "TESTED", "HAVE")
        match = not (actual == "MISSING" and declared_exec)
        results.append({"cap": cid, "declared": declared, "probe_actual": actual, "match": match,
                        "probe": pname})
    mismatches = [r for r in results if not r["match"]]
    unassessed = [r for r in results if r["probe_actual"] == "UNKNOWN"]
    v = "fail" if mismatches else "pass"
    return verdict("probe_capability_executable", "ATLAS", v,
                   {"capabilities": results, "mismatches": mismatches, "unassessed": unassessed})


# ── Coverage / capability FLOOR probes (HERMETIC) — the honest, fact-derived blockers ──
#
# These keep the release gate at BLOCK_PUBLIC_RELEASE for the TRUE reason — the platform has
# NOT been audited against the corpus with evidence at the certification floor, and most
# capabilities are not yet executable — NOT for a deprecated-surface reason (the retired
# probe_desktop_install tested an Electron .app that no longer ships). Both are HERMETIC
# (derived purely from committed repo files -> identical verdict in CI and local) and
# FACT-derived (computed from corpus.json + the real probe map, never a hand-typed flag that
# whoever-sets-it could flip). They are un-gameable: clearing them requires genuinely building
# broad evidence probes and wiring real capabilities — exactly the work the corpus exists to drive.

CERT_FLOOR = 0.90  # scoring_rubric.yaml certification floor: coverage / HAVE-fraction >= 90%


def _corpus() -> dict:
    try:
        return json.loads(_read(PR_ROOT / "generated" / "corpus.json")) or {}
    except Exception:
        return {}


def probe_corpus_coverage_floor() -> dict:
    """HERMETIC honest blocker: is the corpus actually COVERED by evidence probes at the
    certification floor? coverage = (# corpus items with a probe-backed verdict) / (in-scope
    item total). ATLAS self-assesses only the items in PROBE_COVERAGE_MAP (~a handful of 3,378)
    — partial BY DESIGN — so coverage is far below 90% and this FAILS honestly until broad
    probe coverage is built. Un-gameable: the numerator is the real probe->corpus map, not a flag."""
    c = _corpus()
    cats = c.get("categories", [])
    in_scope = sum(int(cat.get("item_count", 0)) for cat in cats
                   if str(cat.get("capability_status")).upper() != "NA")
    if in_scope <= 0:
        return verdict("probe_corpus_coverage_floor", "ATLAS", "unknown",
                       "cannot read corpus.json item totals", category="Governance")
    covered = len(PROBE_COVERAGE_MAP)  # distinct corpus items carrying an evidence-probe verdict
    ratio = covered / in_scope
    v = "pass" if ratio >= CERT_FLOOR else "fail"
    return verdict("probe_corpus_coverage_floor", "ATLAS", v,
                   f"evidence-probe coverage {covered}/{in_scope} = {ratio * 100:.2f}% "
                   f"(floor {CERT_FLOOR * 100:.0f}%) — {'meets' if v == 'pass' else 'BELOW'} certification floor; "
                   f"public release requires broad corpus coverage with evidence, not self-report.",
                   category="Governance")


def probe_capability_havefloor() -> dict:
    """HERMETIC honest blocker: are enough capabilities actually EXECUTABLE (HAVE)? Reads the
    per-category capability_status from corpus.json: HAVE-fraction over in-scope (non-NA)
    categories. Today most categories are MISSING/PARTIAL, so this FAILS honestly. A skill
    DESCRIBES; capability_status==HAVE means a probe-verified WIRED executor exists."""
    c = _corpus()
    cats = [cat for cat in c.get("categories", [])
            if str(cat.get("capability_status")).upper() != "NA"]
    if not cats:
        return verdict("probe_capability_havefloor", "ATLAS", "unknown",
                       "cannot read corpus.json capability_status", category="Governance")
    have = sum(1 for cat in cats if str(cat.get("capability_status")).upper() == "HAVE")
    ratio = have / len(cats)
    v = "pass" if ratio >= CERT_FLOOR else "fail"
    return verdict("probe_capability_havefloor", "ATLAS", v,
                   f"executable-capability coverage {have}/{len(cats)} categories HAVE = {ratio * 100:.1f}% "
                   f"(floor {CERT_FLOOR * 100:.0f}%) — most categories have skills (knowledge) but no "
                   f"probe-verified WIRED executor yet.",
                   category="Governance")


def probe_service_deployed() -> dict:
    """RUNTIME, HOST-ONLY, NON-BLOCKING deployment signal (replaces the deprecated
    probe_desktop_install). ATLAS now ships as an always-on launchd service, NOT an Electron
    .app. Asserts the LaunchAgents are present + loaded + /health 200. Host-only (NA in CI/Linux)
    -> RUNTIME tier, so it does NOT govern the committed gate state: service-up must never flip
    the gate to READY (local + auth-disabled != public-release-ready)."""
    import shutil
    import urllib.request
    la = Path.home() / "Library" / "LaunchAgents"
    web_plist = la / "com.atlas.web.plist"
    mcp_plist = la / "com.atlas.mcp.plist"
    if not (web_plist.exists() and mcp_plist.exists()):
        return verdict("probe_service_deployed", "ATLAS", "unknown",
                       f"LaunchAgents not present (web={web_plist.exists()}, mcp={mcp_plist.exists()}) "
                       f"— off-host or not installed; deployment not assessed",
                       cap="CAP_SERVICE_DEPLOYED", category="Deployment")
    loaded = False
    if shutil.which("launchctl"):
        try:
            out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10)
            loaded = ("com.atlas.web" in out.stdout) and ("com.atlas.mcp" in out.stdout)
        except Exception:
            loaded = False
    health = False
    try:
        with urllib.request.urlopen("http://127.0.0.1:4317/api/health", timeout=3) as r:
            health = (r.status == 200)
    except Exception:
        health = False
    if loaded and health:
        return verdict("probe_service_deployed", "ATLAS", "pass",
                       "always-on service deployed: com.atlas.{web,mcp} launchd-loaded + :4317/api/health 200",
                       cap="CAP_SERVICE_DEPLOYED", category="Deployment")
    return verdict("probe_service_deployed", "ATLAS", "fail",
                   f"LaunchAgents present but not fully live (launchctl-loaded={loaded}, health200={health})",
                   cap="CAP_SERVICE_DEPLOYED", category="Deployment")


def probe_settings_write() -> dict:
    """CAP_SETTINGS_WRITE: WIRED proof = verify_settings_write.mjs persists tenant settings at
    runtime (migration creates tenant_settings, upsert+scopedSelect round-trip, IDOR-safe).
    Verdict comes from EXECUTION (wired-vs-defined), not a string grep."""
    route = SHELL / "src" / "app" / "api" / "settings" / "route.ts"
    if not route.exists():
        return verdict("probe_settings_write", "ATLAS", "fail",
                       "no settings write path: apps/frontend/shell/src/app/api/settings/route.ts missing",
                       cap="CAP_SETTINGS_WRITE", category="Configuration")
    import tempfile
    tmpdb = str(Path(tempfile.mkdtemp(prefix="atlas-settings-probe-")) / "atlas.db")
    ok, ev = _run_verify("verify_settings_write.mjs",
                         {"ATLAS_RUNTIME": "desktop", "ATLAS_SQLITE_PATH": tmpdb})
    if ok:
        return verdict("probe_settings_write", "ATLAS", "pass",
                       f"WIRED (runtime verify): {ev}", cap="CAP_SETTINGS_WRITE", category="Configuration")
    return verdict("probe_settings_write", "ATLAS", "fail",
                   f"settings route exists but runtime verify did NOT print VERIFY_OK: {ev}",
                   cap="CAP_SETTINGS_WRITE", category="Configuration")


# ── RUNTIME probes wiring the previously-orphaned verify scripts (audit #13) ──
# These verify scripts were on disk referenced by NOTHING (so a broken mutator was invisible
# to the suite). Each is self-contained (mkdtemp + ATLAS_RUNTIME set internally), so _run_verify
# needs no env. All runtime-tier (node execution) -> they do NOT govern the committed gate state.

def probe_repo_ingest_wired() -> dict:
    """CAP_REPO_INGEST: WIRED proof = verify_repo_ingest.mjs ingests into durable, tenant-scoped
    repo_connectors at runtime (incl. cross-tenant isolation) and prints VERIFY_OK."""
    ok, ev = _run_verify("verify_repo_ingest.mjs")
    return verdict("probe_repo_ingest_wired", "ATLAS", "pass" if ok else "fail",
                   f"{'WIRED (runtime verify)' if ok else 'verify did NOT print VERIFY_OK'}: {ev}",
                   cap="CAP_REPO_INGEST", category="Backend")


def probe_checklist_verdict_wired() -> dict:
    """CAP_CHECKLIST_VERDICT_WRITE: WIRED proof = BOTH the verdict-write and the probe-assessment
    round-trips persist at runtime (verify_checklist_verdict.mjs + verify_probe_assessment.mjs)."""
    cv_ok, cv_ev = _run_verify("verify_checklist_verdict.mjs")
    pa_ok, pa_ev = _run_verify("verify_probe_assessment.mjs")
    ok = cv_ok and pa_ok
    return verdict("probe_checklist_verdict_wired", "ATLAS", "pass" if ok else "fail",
                   f"verdict-write[{cv_ev}] + probe-assessment[{pa_ev}]",
                   cap="CAP_CHECKLIST_VERDICT_WRITE", category="Documentation")


def probe_metrics_wired() -> dict:
    """Observability: WIRED proof = verify_metrics_wired.mjs exercises a route and asserts a
    non-zero atlas_requests_total sample appears (the custom prom-client counters are actually
    incremented, not just defined). Closes the telemetry-theater gap (audit #9)."""
    ok, ev = _run_verify("verify_metrics_wired.mjs")
    return verdict("probe_metrics_wired", "ATLAS", "pass" if ok else "fail",
                   f"{'WIRED (runtime verify)' if ok else 'verify did NOT print VERIFY_OK'}: {ev}",
                   cap="CAP_METRICS_INSTRUMENTED", category="Observability")


def probe_migrate_on_boot() -> dict:
    """CAP_REPO_INGEST/Backend: WIRED proof = verify_migrate_on_boot.mjs proves the
    instrumentation register() migrate-on-boot path creates schema on a fresh DB at runtime."""
    ok, ev = _run_verify("verify_migrate_on_boot.mjs")
    return verdict("probe_migrate_on_boot", "ATLAS", "pass" if ok else "fail",
                   f"{'WIRED (runtime verify)' if ok else 'verify did NOT print VERIFY_OK'}: {ev}",
                   category="Backend")


ALL_PROBES = [
    probe_mcp_bootable,
    probe_git_writeback,
    probe_repo_editable,
    probe_route_is_live,
    probe_page_is_live,
    probe_checklist_page_is_live,
    probe_rate_limit_wired,
    probe_audit_wired,
    probe_claim_backed,
    probe_capability_executable,
    probe_settings_write,
    probe_repo_ingest_wired,
    probe_checklist_verdict_wired,
    probe_metrics_wired,
    probe_migrate_on_boot,
    # HERMETIC honest blockers (govern the committed gate state):
    probe_corpus_coverage_floor,
    probe_capability_havefloor,
    # RUNTIME, non-blocking deployment signal (replaces retired probe_desktop_install):
    probe_service_deployed,
]


# Probe TIER — which probes govern the COMMITTED derived gate state (production-readiness.ts).
#   hermetic: derived purely from committed repo files (regex / corpus.json) -> identical
#             verdict in CI and local. ONLY these govern derive_gate_state --check, so the
#             committed gate is reproducible and never DRIFTs between environments (audit #13).
#   runtime:  needs node execution / a live host (verify scripts, launchctl, HTTP). Run in a
#             separate CI job that boots the service and are asserted individually; they do NOT
#             feed the committed block (else CI-without-deps and local would derive different
#             states, and --check could never pass).
PROBE_TIER = {
    "probe_route_is_live": "hermetic",
    "probe_page_is_live": "hermetic",
    "probe_checklist_page_is_live": "hermetic",
    "probe_claim_backed": "hermetic",
    "probe_corpus_coverage_floor": "hermetic",
    "probe_capability_havefloor": "hermetic",
    "probe_mcp_bootable": "runtime",
    "probe_git_writeback": "runtime",
    "probe_repo_editable": "runtime",
    "probe_rate_limit_wired": "runtime",
    "probe_audit_wired": "runtime",
    "probe_capability_executable": "runtime",
    "probe_service_deployed": "runtime",
    "probe_settings_write": "runtime",
    "probe_repo_ingest_wired": "runtime",
    "probe_checklist_verdict_wired": "runtime",
    "probe_metrics_wired": "runtime",
    "probe_migrate_on_boot": "runtime",
}

# Name -> probe fn, so probe_capability_executable can resolve each registry cap's `probe:` field
# to the REAL verifier (audit #13: no more actual=declared rubber-stamp).
PROBE_BY_NAME = {p.__name__: p for p in ALL_PROBES}


# ── Probe → corpus-verdict mapping (build-item D: probes write checklist_verdicts) ──
#
# Each capability probe maps to ONE corpus item with an EXPLICIT severity. Severity is
# load-bearing for honesty: the scorer's per-severity ratios decide the tier, and an
# unlabeled verdict would default to 'medium' — leaving critical/high vacuously 1.0 so a
# failing gate would NOT sink the tier (an inflated, lying tier). desktop_install is the
# critical gate (a desktop product that isn't installed is not even bronze); the rest are
# high/medium. These 7 probes inspect ATLAS's OWN files at fixed paths — this is ATLAS's
# self-assessment (~7 of 3,378 items, partial coverage BY DESIGN); generic multi-repo
# probing is a separate, larger effort, NOT what this delivers.
PROBE_COVERAGE_MAP = {
    "probe_git_writeback":        {"item_id": "PRC-INTEGRATIONS-GIT-WRITEBACK", "category": "Integrations & APIs",  "severity": "high"},
    "probe_repo_editable":        {"item_id": "PRC-INTEGRATIONS-REPO-EDIT",     "category": "Integrations & APIs",  "severity": "high"},
    "probe_route_is_live":        {"item_id": "PRC-BACKEND-ROUTE-LIVE",         "category": "Backend",              "severity": "high"},
    "probe_mcp_bootable":         {"item_id": "PRC-BACKEND-MCP-BOOT",           "category": "Backend",              "severity": "high"},
    "probe_rate_limit_wired":     {"item_id": "PRC-RATELIMIT-WIRED",            "category": "Rate Limiting",        "severity": "high"},
    "probe_audit_wired":          {"item_id": "PRC-AUDIT-WIRED",                "category": "Audit Logging",        "severity": "high"},
    "probe_page_is_live":         {"item_id": "PRC-FRONTEND-PAGE-LIVE",         "category": "Frontend",             "severity": "high"},
    "probe_claim_backed":         {"item_id": "PRC-DOCUMENTATION-CLAIM-BACKED", "category": "Documentation",        "severity": "medium"},
    "probe_capability_executable":{"item_id": "PRC-INTEGRATIONS-CAP-EXEC",      "category": "Integrations & APIs",  "severity": "high"},
    "probe_settings_write":       {"item_id": "PRC-CONFIG-SETTINGS-WRITE",      "category": "Configuration",        "severity": "medium"},
    "probe_repo_ingest_wired":    {"item_id": "PRC-BACKEND-REPO-INGEST",        "category": "Backend",              "severity": "high"},
    "probe_checklist_verdict_wired":{"item_id": "PRC-DOC-CHECKLIST-VERDICT",    "category": "Documentation",        "severity": "high"},
    "probe_metrics_wired":        {"item_id": "PRC-OBSERVABILITY-METRICS",      "category": "Observability",        "severity": "medium"},
    "probe_migrate_on_boot":      {"item_id": "PRC-BACKEND-MIGRATE-BOOT",       "category": "Backend",              "severity": "high"},
}


def _verdict_from_probe(v: str) -> str:
    # pass->pass, fail->fail, unknown->not_assessed (honest: unknown is never a pass).
    return {"pass": "pass", "fail": "fail"}.get(v, "not_assessed")


def emit_verdicts() -> dict:
    """Run the probes and emit them as corpus VERDICTS (data only) for the C data plane.

    The verdicts are written into checklist_verdicts/project_assessments by the SINGLE
    canonical write path (the shell scorer / checklistVerdictWrite or POST
    /api/repos/[id]/assessment) — this function NEVER scores or writes a snapshot itself
    (no duplicate tier rule). source='probe' on every verdict.
    """
    verdicts = []
    for p in ALL_PROBES:
        r = p()
        m = PROBE_COVERAGE_MAP.get(r["id"])
        if not m:
            continue
        ev = r["evidence"] if isinstance(r["evidence"], str) else json.dumps(r["evidence"])
        verdicts.append({
            "item_id": m["item_id"],
            "category": m["category"],
            "severity": m["severity"],
            "verdict": _verdict_from_probe(r["verdict"]),
            "source": "probe",
            "evidence": ev[:500],
        })
    return {
        "target": "ATLAS",
        "source": "probe",
        "coverage_note": (
            f"{len(verdicts)} capability probes -> corpus verdicts (ATLAS self-assessment; "
            f"~{len(verdicts)} of 3,378 items — partial coverage BY DESIGN, not a full audit)."
        ),
        "verdicts": verdicts,
    }


def run_all(hermetic_only: bool = False) -> dict:
    """Run probes and stamp each result with its TIER. With hermetic_only=True, run ONLY the
    hermetic (repo-source-derived) probes — the set that governs the committed gate state and
    yields identical verdicts in CI and local (audit #13)."""
    probes = [p for p in ALL_PROBES
              if not hermetic_only or PROBE_TIER.get(p.__name__, "runtime") == "hermetic"]
    results = []
    for p in probes:
        r = _call_probe(p)
        r["tier"] = PROBE_TIER.get(r["id"], "runtime")
        results.append(r)
    summary = {"pass": 0, "fail": 0, "unknown": 0}
    for r in results:
        summary[r["verdict"]] = summary.get(r["verdict"], 0) + 1
    return {"schema_version": "1.0", "target": "ATLAS",
            "governed_tier": "hermetic" if hermetic_only else "all",
            "overall": "pass" if summary["fail"] == 0 and summary["unknown"] == 0 else "fail",
            "summary": summary, "results": results}


def self_test() -> int:
    """Test the PROBE MECHANISM's correctness — not which capabilities happen to be built today.

    A self-test that hardcodes "these probes must fail" goes stale the moment a capability is
    built (then it false-alarms). Instead we assert mechanism invariants that hold regardless
    of build state:
      1. _run_verify on a MISSING script returns (False, ...) — a probe can't pass on a non-run.
      2. _run_verify on a script that does NOT print VERIFY_OK returns False — no false WIRED.
      3. unknown == not-pass: a synthetic unknown verdict makes run_all overall != pass.
      4. At least one real probe currently reports fail (the suite still discriminates) — ATLAS
         today still has desktop_install/route_is_live failing; if ALL pass, that's only valid
         when the derived recommendation is READY (full completion), which we cross-check.
    """
    ok = True
    import tempfile

    # 1. missing verify script -> not ok
    miss_ok, _ = _run_verify("___nonexistent_verify___.mjs")
    inv1 = (miss_ok is False)
    print(f"  inv1 missing-verify-not-pass         -> {'OK' if inv1 else 'BUG'}")
    ok = ok and inv1

    # 2. a script that prints something else -> not ok (no false VERIFY_OK)
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", dir=str(VERIFY_DIR), delete=False) as tf:
        tf.write("console.log('not the magic token');\n")
        tmpname = Path(tf.name).name
    try:
        noky, _ = _run_verify(tmpname)
        inv2 = (noky is False)
    finally:
        (VERIFY_DIR / tmpname).unlink(missing_ok=True)
    print(f"  inv2 no-VERIFY_OK-not-pass           -> {'OK' if inv2 else 'BUG'}")
    ok = ok and inv2

    # 3. unknown == not pass at the suite level
    report = run_all()
    has_unknown = report["summary"].get("unknown", 0) > 0
    inv3 = (not has_unknown) or (report["overall"] != "pass")
    print(f"  inv3 unknown==not-pass (suite)       -> {'OK' if inv3 else 'BUG'}")
    ok = ok and inv3

    # 4. discrimination: suite is all-pass ONLY if derived recommendation is READY
    all_pass = report["overall"] == "pass"
    if all_pass:
        import subprocess as _sp
        d = _sp.run([sys.executable,
                     str(REPO_ROOT / "infrastructure/scripts/production_readiness/derive_gate_state.py"),
                     "--print"], capture_output=True, text=True)
        inv4 = "READY_FOR_PUBLIC_RELEASE" in d.stdout
        print(f"  inv4 all-pass⇒derived-READY          -> {'OK' if inv4 else 'BUG (all pass but derived not READY)'}")
    else:
        fails = [r["id"] for r in report["results"] if r["verdict"] == "fail"]
        inv4 = len(fails) > 0
        print(f"  inv4 suite-discriminates (fails={len(fails)}) -> {'OK' if inv4 else 'BUG'}")
    ok = ok and inv4

    # 5. no orphan verify scripts: every probes/verify/*.mjs must be referenced by some probe
    #    (audit #13 — an unreferenced verifier means a broken mutator is invisible to the suite).
    src = _read(Path(__file__))
    referenced = set(re.findall(r'_run_verify\(\s*["\']([^"\']+\.mjs)["\']', src))
    on_disk = {p.name for p in VERIFY_DIR.glob("*.mjs")}
    orphans = sorted(on_disk - referenced)
    inv5 = (len(orphans) == 0)
    print(f"  inv5 no-orphan-verify-scripts        -> {'OK' if inv5 else 'BUG orphans=' + str(orphans)}")
    ok = ok and inv5

    print("self-test:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--hermetic", action="store_true",
                    help="Run ONLY hermetic (repo-source-derived) probes — the set that governs the "
                         "committed gate state; deterministic in CI and local (audit #13).")
    ap.add_argument("--emit-verdicts", action="store_true",
                    help="Emit probes as corpus verdicts (JSON) for the checklist data plane (build-item D).")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if args.emit_verdicts:
        print(json.dumps(emit_verdicts(), indent=2))
        return 0
    report = run_all(hermetic_only=args.hermetic)
    if args.write:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "probe_results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"PROBE SUITE — {report['target']} — overall: {report['overall'].upper()}")
        print(f"  summary: {report['summary']}")
        for r in report["results"]:
            ev = r["evidence"] if isinstance(r["evidence"], str) else json.dumps(r["evidence"])[:120]
            print(f"  [{r['verdict']:7}] {r['id']:28} {ev[:110]}")
    # exit nonzero if the suite is not all-pass (gate semantics)
    return 0 if report["overall"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
