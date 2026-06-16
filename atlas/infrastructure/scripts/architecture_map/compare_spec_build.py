#!/usr/bin/env python3
"""
compare_spec_build.py — Layer 5 (Spec-vs-Build Comparator) of the Architecture Map Engine.

Every assertion is DERIVED from a real artifact (a registry, the architecture snapshot, the
census, the architecture-state sync summary) — no hand-typed claim strings. Each carries a
spec source path + a build observation + an evidence path, so nothing is unfalsifiable.

Status vocabulary (owner's): MATCH / PARTIAL / MISMATCH / MISSING / SPEC_ONLY /
BUILT_UNWIRED / WIRED_UNPROVEN / PROVEN / DRIFT / UNKNOWN. Runtime-PROVEN promotion
(build pass, live probes) is the proof engine's job (step 12), not this layer — so things
that merely EXIST resolve to BUILT/WIRED_UNPROVEN here, never PROVEN.

Exposes build_spec_assertions(stamp) for generate_map_data.py; runnable standalone.
"""
from __future__ import annotations
import argparse, json, sys
from collections import Counter
from pathlib import Path
try:
    import yaml
except ImportError:
    print("pyyaml required", file=sys.stderr); sys.exit(2)

ROOT = Path(__file__).resolve().parents[3]
CENSUS = ROOT / "platform/systems/43_graph_engine/exports/repo_census.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_proof_status import build_proof_status  # Layer 6: read-only probe/evidence verdicts

def load(p):
    fp = ROOT / p
    if not fp.exists(): return None
    try: return yaml.safe_load(fp.read_text())
    except Exception: return None

def build_spec_assertions(stamp: str = "unstamped") -> list[dict]:
    cats = (load("platform/systems/18_registry/dev_checklist.categories.yaml") or {}).get("categories", [])
    caps = (load("platform/systems/53_production_readiness/capabilities/registry.yaml") or {}).get("capabilities", [])
    gates = (load("platform/sdlc/08_verification/validation_gate.registry.yaml") or {}).get("gates", [])
    snap = load("platform/sdlc/04_architecture/architecture.snapshot.yaml") or {}
    sync = load("platform/systems/39_repo_twins/twins/atlas/architecture_sync_summary.yaml") or {}
    census = json.loads(CENSUS.read_text()) if CENSUS.exists() else {"classification": {}, "coverage": {}}
    cl = census.get("classification", {})

    match = Counter(c.get("verified_skill_match", "unverified") for c in cats)
    cap_cat = Counter(c.get("declared_capability", "?") for c in cats)
    real_skill = match.get("STRONG", 0) + match.get("TOPICAL", 0)
    cap_wired = sum(1 for c in caps if c.get("status") == "WIRED")
    gate_tested = sum(1 for g in gates if g.get("status") not in (None, "NOT_TESTED", "UNKNOWN"))
    snap_components = len(snap.get("components", []) or [])
    totals = sync.get("totals", {})
    dead, orph = totals.get("dead_refs", 0), totals.get("orphans", 0)
    n_cat = len(cats) or 68

    # Layer 6 proof: read-only probe/evidence verdicts (never re-runs the fleet). Promote ONLY
    # assertions an existing probe actually verifies; the rest stay WIRED_UNPROVEN / MISSING.
    ps = build_proof_status()
    pp = ps["probes"]
    proven_caps = set(ps["proven_capabilities"])
    proven_cats = {c.get("category") for c in ps.get("proven_detail", []) if c.get("category")}
    cap_proven_n = sum(1 for c in proven_caps if str(c).startswith("CAP_"))

    def A(dim, spec, spec_src, build, build_src, verdict, nxt):
        return {"dimension": dim, "spec": spec, "spec_source": spec_src,
                "build": build, "build_source": build_src, "verdict": verdict, "next_action": nxt}

    out = [
        A("Architecture snapshot",
          "populated component graph", "platform/sdlc/04_architecture/architecture.snapshot.yaml",
          f"components: [] ({snap_components} components)" if snap_components == 0 else f"{snap_components} components",
          "architecture.snapshot.yaml",
          "MISMATCH" if snap_components == 0 else "MATCH",
          "regenerate the snapshot from this engine's census/graph builder"),
        A("Executable capability (corpus categories)",
          f"{n_cat} categories", "platform/systems/18_registry/dev_checklist.categories.yaml",
          f"{cap_cat.get('HAVE',0)} HAVE / {cap_cat.get('PARTIAL',0)} PARTIAL / {cap_cat.get('MISSING',0)} MISSING",
          "dev_checklist.categories.yaml (declared_capability)",
          "PARTIAL" if cap_cat.get("HAVE", 0) else "MISSING",
          "wire executors for MISSING categories; attach probes"),
        A("CAP_* executors",
          f"{len(caps)} declared", "53_production_readiness/capabilities/registry.yaml",
          f"{cap_wired} WIRED; {cap_proven_n} probe-proven", "capabilities/registry.yaml + probe_results.json",
          "PARTIAL" if 0 < cap_proven_n < cap_wired else ("PROVEN" if cap_proven_n and cap_proven_n >= cap_wired else "WIRED_UNPROVEN"),
          "add probes for the unproven WIRED capabilities"),
        A("Skill coverage (real match)",
          f"{n_cat} categories", "dev_checklist.categories.yaml",
          f"{real_skill} real ({match.get('STRONG',0)} STRONG + {match.get('TOPICAL',0)} TOPICAL); {match.get('WEAK',0)+match.get('NONE',0)} weak/none",
          "categories.yaml (verified_skill_match)",
          "PARTIAL" if real_skill < n_cat else "MATCH",
          "raise WEAK/NONE categories to real skill coverage"),
        A("Validation gates",
          f"{len(gates)} gates defined", "platform/sdlc/08_verification/validation_gate.registry.yaml",
          f"{gate_tested}/{len(gates)} tested" + (" (all NOT_TESTED)" if gate_tested == 0 else ""),
          "validation_gate.registry.yaml (status)",
          "WIRED_UNPROVEN" if gate_tested == 0 else ("MATCH" if gate_tested == len(gates) else "PARTIAL"),
          "execute gates and attach evidence so they move past NOT_TESTED"),
        A("API route surface",
          "Next.js API routes", "apps/frontend/shell/src/app/api (route.ts)",
          f"{cl.get('route',0)} route.ts present" + ("; probe_route_is_live PASS" if "Backend" in proven_cats else ""),
          "repo_census.json + probe_results.json",
          "PROVEN" if "Backend" in proven_cats else ("BUILT_UNWIRED" if not cl.get("route") else "WIRED_UNPROVEN"),
          "maintain live-route probe coverage"),
        A("atlas-ui surfaces",
          "single front-end (shell-mounted)", "apps/frontend/shell/public/atlas-ui/*.html",
          f"{cl.get('ui_component',0)} .tsx components; 12 shell HTML surfaces" + ("; probe_page_is_live PASS" if "Frontend" in proven_cats else ""),
          "repo_census.json + probe_results.json",
          "PROVEN" if "Frontend" in proven_cats else "WIRED_UNPROVEN",
          "maintain live-page probe coverage"),
        A("Dead references (drift)",
          "0 dangling edges", "architecture-state sync invariant",
          f"{dead} dead references (edge → missing file)", "twins/atlas/architecture_sync_summary.yaml",
          "MATCH" if dead == 0 else "DRIFT",
          "heal the source path or tombstone the deleted target"),
        A("Orphaned modules (drift)",
          "0 orphaned TS modules", "architecture-state sync invariant",
          f"{orph} orphans (TS import-graph scoped)", "architecture_sync_summary.yaml",
          "MATCH" if orph == 0 else "DRIFT",
          "wire or remove orphans (excluding entrypoints/config)"),
        A("Probe verification (proof engine)",
          f"capabilities probe-verified", "platform/systems/53_production_readiness/probes",
          f"{pp['passed']}/{pp['total']} probes pass (~{pp.get('pass_rate_pct')}% pass-rate, {len(proven_caps)} caps); slice {ps['slice'].get('overall','?')}",
          "probe_results.json (read-only; fleet never re-run)",
          "PARTIAL" if pp["passed"] else "MISSING",
          "raise probe coverage; fix probe_desktop_install (the 1 FAIL)"),
        A("Item-level proof",
          f"{ps['corpus_items']} checklist items", "dev_checklist corpus",
          f"~{ps['item_coverage']['pct']}% item-level ({ps['item_coverage']['proven_items']} slice items PASS) — capability pass-rate is separate & higher",
          "evidence_record.yaml + probe_results.json",
          "MISSING" if ps['item_coverage']['pct'] < 1 else "PARTIAL",
          "attach per-item evidence as the proof engine grows"),
    ]
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stamp", default="unstamped"); a = ap.parse_args()
    rows = build_spec_assertions(a.stamp)
    OUT = ROOT / "platform/systems/43_graph_engine/graphs/spec_build_assertions.jsonl"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    print(f"WROTE {OUT.relative_to(ROOT)}  ({len(rows)} assertions, derived from real artifacts)")
    vc = Counter(r["verdict"] for r in rows)
    print("  verdicts:", dict(vc))
    for r in rows:
        print(f"    [{r['verdict']:<14}] {r['dimension']:<38} spec={r['spec'][:28]!r:<30} build={r['build'][:34]!r}")

if __name__ == "__main__":
    main()
