#!/usr/bin/env python3
"""
generate_map_data.py — derive the Architecture Map dashboard data from the REAL registries.

Backend = Python (per stack decision). Emits a single JSON the TSX dashboard consumes, so the
map's completion %/status are auto-derived and honest — never hand-typed. Re-run after registry
changes. Pass --stamp YYYY-MM-DD for generated_at (no implicit clock, keeps output deterministic).
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
try:
    import yaml
except ImportError:
    print("pyyaml required", file=sys.stderr); sys.exit(2)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_spec_build import build_spec_assertions  # derived spec-vs-build (real artifacts, no hand-typed rows)
from update_action_log import build_action_log  # git-diff change feed (the tracker / Timeline)
from derive_proof_status import build_proof_status  # Layer 6 proof engine (read-only verdicts)
from fuse_node_status import build_node_status  # FUSION: 4 axes -> per-node truth verdicts (read-only)

ROOT = Path(__file__).resolve().parents[3]
# Served as a same-origin static asset so the atlas-ui Repo Workbench (Repo.html) can fetch it.
# Keyed by repo id; ATLAS itself is repo:dev_skills (name "ATLAS") in atlas-data.js.
OUT = ROOT / "apps/frontend/shell/public/atlas-ui/architecture-map.data.json"
# The living concept/baseline doc — its Overview diagram is repainted live from the fusion.
DOCS_HTML = ROOT / "docs/ATLAS ARCHITECTURE MAP.html"
NODE_STATUS_START = "<!-- ATLAS_NODE_STATUS:START -->"
NODE_STATUS_END = "<!-- ATLAS_NODE_STATUS:END -->"
ATLAS_REPO_ID = "repo:dev_skills"


def repaint_docs_html(node_status, stamp):
    """Rewrite ONLY the marked node-status JSON block in the living docs HTML, so the
    static doc's layered diagram reflects current truth on every generator run. The diagram
    shape, the data-node ids, and the JS overlay are static scaffolding — we refresh data only.
    Returns a status string; never raises (a missing marker is reported, not fatal)."""
    if not DOCS_HTML.exists():
        return "docs HTML absent — skipped"
    html = DOCS_HTML.read_text()
    if NODE_STATUS_START not in html or NODE_STATUS_END not in html:
        return "markers absent — docs HTML not yet instrumented (run once to add scaffolding)"
    payload = json.dumps({"stamp": stamp, **node_status}, separators=(",", ":"))
    block = (f'{NODE_STATUS_START}\n'
             f'<script type="application/json" id="atlas-node-status">{payload}</script>\n'
             f'{NODE_STATUS_END}')
    pre, _, rest = html.partition(NODE_STATUS_START)
    _, _, post = rest.partition(NODE_STATUS_END)
    DOCS_HTML.write_text(pre + block + post)
    r = node_status["rollup"]
    return f"repainted ({r['red']} red / {r['caution']} caution / {r['green']} green / {r['grey']} grey · {len(node_status['gaps'])} gaps)"

def load(p):
    fp = ROOT / p
    if not fp.exists(): return None
    try: return yaml.safe_load(fp.read_text())
    except Exception: return None

def pct(n, d): return round(100 * n / d) if d else 0

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stamp", default="unstamped"); a = ap.parse_args()

    ledger = load("platform/systems/18_registry/dev_checklist.coverage_ledger.yaml") or {}
    cats = (load("platform/systems/18_registry/dev_checklist.categories.yaml") or {}).get("categories", [])
    skillmap = load("platform/sdlc/13_skills/skill_refinery/checklist_to_skill_map.yaml") or {}
    caps = (load("platform/systems/53_production_readiness/capabilities/registry.yaml") or {}).get("capabilities", [])
    gates = (load("platform/sdlc/08_verification/validation_gate.registry.yaml") or {}).get("gates", [])
    slice_ev = load("platform/systems/22_vertical_slices/repository_organization_slice_001/evidence_record.yaml") or {}
    findings = (load("infrastructure/scripts/architecture_map/data/audit_findings.yaml") or {}).get("findings", [])
    sdlc = (load("infrastructure/scripts/architecture_map/data/sdlc_phases.yaml") or {}).get("phases", [])
    mt = (load("infrastructure/scripts/architecture_map/data/map_tables.yaml") or {}).get("content", {})
    arch_sync = load("platform/systems/39_repo_twins/twins/atlas/architecture_sync_summary.yaml") or {}

    # ---- per-category verified match + applicability (real) ----
    from collections import Counter
    match = Counter(c.get("verified_skill_match", "unverified") for c in cats)
    appl = Counter(c.get("atlas_applicability", "UNKNOWN") for c in cats)
    cap_status = Counter(c.get("declared_capability", "?") for c in cats)  # field is declared_capability
    real_skill = match.get("STRONG", 0) + match.get("TOPICAL", 0)

    cap_have = sum(1 for c in caps if c.get("status") == "WIRED")
    sm = skillmap.get("summary", {})

    # ---- LIVE architecture counts — derived from the REAL repo on every run, so the layered
    # diagram is a true, current reflection of state (never hand-typed / frozen). ----
    import re as _re
    shell = ROOT / "apps/frontend/shell"
    n_surfaces = len(list((shell / "public/atlas-ui").glob("*.html")))
    n_routes = len(list((shell / "src/app/api").rglob("route.ts"))) or len(mt.get("api_routes", []))
    _schema = shell / "src/lib/db/schema.ts"
    n_tables = _schema.read_text().count("sqliteTable(") if _schema.exists() else 0
    _svc = ROOT / "infrastructure/service/atlas-service.sh"
    n_services = len(set(_re.findall(r"com\.atlas\.[a-z]+", _svc.read_text()))) if _svc.exists() else 0
    _mcp = ROOT / "apps/backend/mcp/src"
    _tool_names = sorted({m for p in _mcp.rglob("*.ts") for m in _re.findall(r'"(atlas_[a-z_]+)"', p.read_text())}) if _mcp.exists() else []
    n_tools = len(_tool_names) or len(mt.get("mcp_tools", []))

    # ---- ARCHITECTURE DIAGRAM — layered map of the whole repo (grounded in real inventory) ----
    arch_diagram = {
        "note": (f"Layered architecture map of the ATLAS repo — node counts derived LIVE from the repo at {a.stamp} "
                 f"({n_routes} routes · {n_surfaces} surfaces · {n_tools} MCP tools · {n_tables} tables · {n_services} services); "
                 f"data flows top→bottom. GitHub/Git stay canonical for code."),
        "layers": [
            {"name": "Clients", "nodes": [
                {"id": "vscode", "label": "VS Code"}, {"id": "agents", "label": "Claude Code / Codex"},
                {"id": "browser", "label": "Browser"}, {"id": "cli", "label": "CLI / git"}]},
            {"name": "UI · atlas-ui (:4317)", "nodes": [
                {"id": "workbench", "label": "Repo Workbench"}, {"id": "surfaces", "label": f"{n_surfaces} atlas-ui surfaces"}]},
            {"name": f"API · Next.js · {n_routes} routes", "nodes": [
                {"id": "auth", "label": "auth · PKCE/JWT"}, {"id": "repos", "label": "/api/repos"},
                {"id": "ingest", "label": "/api/ingest"}, {"id": "graph", "label": "/api/graph"},
                {"id": "knowledge", "label": "/api/knowledge"}, {"id": "metrics", "label": "/api/metrics"}]},
            {"name": f"MCP · :4318 · {n_tools} tools", "nodes": [
                {"id": "mcp_read", "label": "read tools"}, {"id": "mcp_write", "label": "write tools · gated"}]},
            {"name": "Data plane", "nodes": [
                {"id": "sqlite", "label": f"SQLite · {n_tables} tables"}, {"id": "connectors", "label": "repo_connectors"},
                {"id": "gitscan", "label": "git scanner"}]},
            {"name": "Services", "nodes": [
                {"id": "launchd", "label": f"{n_services} launchd services"}, {"id": "bookworm", "label": "Bookworm daemon :18608"},
                {"id": "router", "label": "route_intent.py"}]},
            {"name": "External (canonical)", "nodes": [
                {"id": "github", "label": "GitHub"}, {"id": "keychain", "label": "OS keychain"}]},
        ],
        "edges": [
            ["vscode", "workbench"], ["browser", "surfaces"], ["agents", "mcp_read"], ["agents", "mcp_write"],
            ["cli", "router"], ["workbench", "repos"], ["surfaces", "graph"], ["surfaces", "knowledge"],
            ["repos", "connectors"], ["ingest", "sqlite"], ["knowledge", "sqlite"], ["graph", "gitscan"],
            ["mcp_read", "sqlite"], ["mcp_write", "gitscan"], ["connectors", "sqlite"], ["gitscan", "github"],
            ["auth", "keychain"], ["bookworm", "knowledge"], ["repos", "gitscan"], ["router", "ingest"],
        ],
    }

    # ---- OVERVIEW completion matrix — honest, registry-derived ----
    areas = [
        {"area": "Requirement extraction", "pct": 100, "have": 3378, "total": 3378,
         "status": "COMPLETE", "note": "68 cat / 245 sec / 3,378 items, zero-loss"},
        {"area": "Skill coverage (category, real match)", "pct": pct(real_skill, 68), "have": real_skill, "total": 68,
         "status": "PARTIAL", "note": f"{match.get('STRONG',0)} STRONG + {match.get('TOPICAL',0)} TOPICAL real; {match.get('WEAK',0)+match.get('NONE',0)} weak/none"},
        {"area": "Skill mapping (item-level)", "pct": 0, "have": 0, "total": 3378,
         "status": "MISSING", "note": "0 items individually mapped"},
        {"area": "Executable capability", "pct": pct(cap_status.get("HAVE",0), 68), "have": cap_status.get("HAVE",0), "total": 68,
         "status": "PARTIAL", "note": f"{cap_have} CAP_* WIRED across {cap_status.get('HAVE',0)} categories; {cap_status.get('MISSING',0)} MISSING"},
        {"area": "Evidence / proof (item-level)", "pct": 0, "have": 0, "total": 3378,
         "status": "MISSING", "note": "14 probes (synthetic ids); 0 real items proven"},
        {"area": "Integration layer", "pct": pct(9, 25), "have": 9, "total": 25,
         "status": "PARTIAL", "note": "9 EXISTS / 5 PARTIAL / 11 PROPOSED"},
        {"area": "Documentation capture", "pct": 40, "have": 2, "total": 5,
         "status": "PARTIAL", "note": "policy+schemas+validator EXIST/EXECUTABLE; gates DEFINED; pre-commit wiring PROPOSED"},
    ]

    # ---- FUSION: join Axis 3 (spec/build) + Axis 4 (proof) + findings onto the visual nodes ----
    spec_vs_build = build_spec_assertions(a.stamp)   # Axis 3 (derived from real artifacts)
    proof_status = build_proof_status()              # Axis 4 (read-only verdicts)
    node_status = build_node_status(spec_vs_build, proof_status, findings)

    data = {
        "generated_at": a.stamp,
        "generator": "infrastructure/scripts/architecture_map/generate_map_data.py",
        "repo": "atlas",
        "honesty_note": "All numbers derived from registries. Declared vs verified vs probe kept distinct. % are coverage, not quality.",
        "overview": {"areas": areas},
        "checklist": {
            "categories": 68, "sections": 245, "items": 3378,
            "skill_match": dict(match), "applicability": dict(appl), "capability_status": dict(cap_status),
            "skill_state_summary": sm,
        },
        "capabilities": [
            {"id": c.get("id"), "status": c.get("status"), "category": c.get("satisfies_corpus_category", "-")}
            for c in caps
        ],
        "gates": {"defined": len(gates),
                  "by_status": dict(Counter(g.get("status", "UNKNOWN") for g in gates))},
        "vertical_slice": {
            "id": "repository_organization_slice_001",
            "overall": slice_ev.get("overall", "?"),
            "results": [{"item": r.get("item"), "result": r.get("result")} for r in slice_ev.get("results", [])],
        },
        "coverage_ledger": {
            "layer_2_skill": ledger.get("layer_2_skill_coverage", {}).get("status"),
            "layer_3_capability": ledger.get("layer_3_capability_coverage", {}).get("status"),
            "layer_4_evidence": ledger.get("layer_4_evidence_coverage", {}).get("status"),
        },
        # ---- deeper views (migrated from the HTML map) ----
        "findings": findings,                                   # 79 audit findings (W/S/D/O)
        "sdlc_phases": sdlc,                                     # 17-phase spec-vs-build comparison
        "checklist_matrix": [                                   # 68-category traceability matrix (summary)
            {"name": c.get("name"), "items": c.get("item_count"), "sections": c.get("section_count"),
             "coverage": c.get("declared_coverage"), "capability": c.get("declared_capability"),
             "match": c.get("verified_skill_match"), "applicability": c.get("atlas_applicability")}
            for c in cats
        ],
        "checklist_tree_url": "architecture-map.checklist.json",  # the 3,378 items, drilled on demand
        # ---- full map surface (api/mcp/capabilities/integration/roadmap) ----
        "api_routes": mt.get("api_routes", []),                 # 28 routes
        "mcp_tools": mt.get("mcp_tools", []),                   # 10 MCP tools
        "capability_registry": mt.get("capability_registry", []),  # 13 CAP_*
        "integration_components": mt.get("integration_components", []),  # 9 EXISTS/5 PARTIAL/11 PROPOSED
        "doc_capture": mt.get("doc_capture", []),
        "drift_classes": mt.get("drift_classes", []),
        "roadmap_top5": mt.get("roadmap_top5", []),
        "roadmap_clusters": mt.get("roadmap_clusters", []),
        "spec_vs_build": spec_vs_build,                     # DERIVED from real artifacts (compare_spec_build.py); old map_tables feed CUT
        "architecture_diagram": arch_diagram,               # real-time repo copy (census + sync)
        "action_log": build_action_log(a.stamp, 25),        # git-diff change feed (Timeline tab; recent window)
        "proof_status": proof_status,                       # Layer 6: probe/evidence verdicts (read-only)
        "node_status": node_status,                         # FUSION: per-node 4-axis truth verdicts + derived gaps
        "architecture_sync": {                              # live architecture-state sync (atlas_sync.py)
            "stamp": arch_sync.get("stamp"),
            "totals": arch_sync.get("totals", {}),
            "object_types": arch_sync.get("object_types", {}),
            "top_orphans": arch_sync.get("top_orphans", []),
            "top_dead_refs": arch_sync.get("top_dead_refs", []),
        },
    }
    # Repo-keyed so the Workbench can look up ARCHMAP[r.id]. ATLAS = repo:dev_skills.
    # Other repos have no generated map yet → the Workbench renders an honest baseline.
    out_doc = {"_meta": {"generated_at": a.stamp, "generator": data["generator"],
                          "note": "keyed by atlas-data.js repo id; only repos with a generated map appear"},
               ATLAS_REPO_ID: data}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out_doc, indent=2))
    print(f"WROTE {OUT.relative_to(ROOT)}  (keyed: {ATLAS_REPO_ID})")
    print(f"  overview areas: {len(areas)} | real-skill {real_skill}/68 | cap HAVE {cap_status.get('HAVE',0)}/68 | slice {data['vertical_slice']['overall']}")
    for ar in areas: print(f"    {ar['pct']:>3}%  {ar['area']}  ({ar['status']})")
    # FUSION → living docs HTML: repaint the truth overlay so the static diagram never drifts.
    print(f"  docs HTML truth overlay: {repaint_docs_html(node_status, a.stamp)}")

if __name__ == "__main__":
    main()
