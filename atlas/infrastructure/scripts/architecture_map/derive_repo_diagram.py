#!/usr/bin/env python3
"""
derive_repo_diagram.py — build the architecture DIAGRAM as a real-time copy of the repo.

Consumes the ONE census (repo_census.json: structure, 100%-coverage) + the ONE sync
inventory (edge_inventory.yaml: dependency edges). No second scanner, no re-derived edges.
Each area's ROLE is derived from its real object-type composition (not hand-typed); per-file
PROOF status is deferred to the proof engine (a later phase) — no green without proof.

Exposes build_diagram(stamp) for generate_map_data.py; also runnable standalone.
Output matches Repo.html archDiagram()'s contract: {layers:[{name,nodes:[{id,label}]}], edges}.
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
TWIN = ROOT / "platform/systems/39_repo_twins/twins/atlas"
DEP_EDGE_TYPES = {"imports", "documents", "references", "routes", "calls"}  # NOT "contains"

# Well-known top-level areas whose role is a structural FACT, not a guess from file types.
KNOWN_ROLE = {
    ".claude": "Claude Code config", ".codex": "Codex config", ".gemini": "Gemini config",
    ".github": "GitHub CI / workflows", "backups": "archive snapshots",
    ".pytest_cache": "pytest cache", "(root files)": "governance & config",
}

def _role(name: str, types: dict) -> str:
    """Role from real composition; corpus artifacts (skills/playbooks/registries/ADRs) win
    over raw doc count, since they DEFINE the spec corpus even when .md files dominate by volume."""
    if name in KNOWN_ROLE:
        return KNOWN_ROLE[name]
    c = Counter(types)
    corpus = c.get("skill", 0) + c.get("skill_playbook", 0) + c.get("registry", 0) + c.get("adr", 0)
    if corpus >= 100:
        return "spec & knowledge corpus"
    runtime = c.get("source_file", 0) + c.get("ui_component", 0) + c.get("route", 0)
    tooling = c.get("script", 0)
    contracts = c.get("schema", 0)
    docs = c.get("documentation_file", 0) + c.get("readme", 0)
    top = max([(runtime, "runtime app"), (tooling, "tooling / automation"),
               (contracts, "contracts / schemas"), (corpus, "spec & knowledge corpus"),
               (docs, "documentation")], key=lambda kv: kv[0])
    return top[1] if top[0] else "files"

def top_of(p: str) -> str:
    return p.split("/", 1)[0] if "/" in p else "(root files)"

def build_diagram(stamp: str = "unstamped") -> dict:
    if not CENSUS.exists():
        return {"note": "run scan_repo_census.py first", "layers": [], "edges": []}
    census = json.loads(CENSUS.read_text())

    # ---- LAYERS: one band per top-level area (census = source of structure) ----
    layers = []
    for t in census.get("top_level", []):
        nodes = [{"id": f"{t['name']}/{c['name']}", "label": c["name"],
                  "count": c["files"], "kind": c.get("kind", "dir")}
                 for c in t.get("children", [])]
        layers.append({
            "name": t["name"], "scope": t["scope"], "git": t.get("git", "tracked"),
            "files": t["files"], "role": _role(t["name"], t.get("types", {})), "nodes": nodes,
        })
    # untracked/ignored present dirs — shown, flagged, NOT in the 1:1 denominator
    for u in census.get("untracked_present", []):
        layers.append({"name": u["name"], "scope": "shallow", "git": "untracked/ignored",
                       "files": u["files"], "role": "present — not tracked/indexed", "nodes": []})

    # ---- EDGES: cross-area dependencies from the ONE sync inventory (aggregated) ----
    edges, edge_note = [], "no edge_inventory (run atlas_sync.py scan)"
    ei = TWIN / "edge_inventory.yaml"
    if ei.exists():
        raw = (yaml.safe_load(ei.read_text()) or {}).get("edges", [])
        agg = Counter()
        for e in raw:
            if e.get("type") in DEP_EDGE_TYPES:
                fa, tb = top_of(e.get("from", "")), top_of(e.get("to", ""))
                if fa != tb:
                    agg[(fa, tb)] += 1
        edges = [[fa, tb, n] for (fa, tb), n in sorted(agg.items(), key=lambda kv: -kv[1])]
        edge_note = f"{len(raw)} inventory edges -> {len(edges)} cross-area deps (imports/doc-links; 'contains' excluded)"

    cov = census.get("coverage", {})
    return {
        "generated_at": stamp,
        "commit": census.get("commit", "unknown"),
        "source": "scan_repo_census.py (structure) + architecture-state sync edge_inventory (edges)",
        "model": "real-time copy of the repo: every tracked file is a node; bands = top-level areas; drill to files.",
        "coverage": cov,
        "legend": {
            "deep": "deep-scanned for objects + dependency edges (apps, infrastructure, schemas, docs, platform)",
            "shallow": "tracked + counted but NOT in the deep dependency graph (.claude/.codex/.gemini/.github)",
            "untracked": "present on disk but git-untracked/ignored (.pytest_cache) — shown, excluded from the 100% gate",
            "edges": edge_note,
            "proof": "area ROLE derived from object-type composition; per-file PROVEN/WIRED status is DEFERRED to the proof engine (no green without proof).",
        },
        "layers": layers,
        "edges": edges,
    }

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stamp", default="unstamped"); a = ap.parse_args()
    d = build_diagram(a.stamp)
    OUT = Path(__file__).parent / "data" / "repo_diagram.json"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(d, indent=2))
    print(f"WROTE {OUT.relative_to(ROOT)}  ({len(d['layers'])} bands, {len(d['edges'])} cross-area edges)")
    cov = d.get("coverage", {})
    print(f"  coverage: {cov.get('tracked_nodes')} nodes == {cov.get('tracked_files')} tracked files (gate {'PASS' if cov.get('match') else 'FAIL'})")
    for L in d["layers"]:
        print(f"    {L['name']:<16} {L['files']:>6} files  {len(L['nodes']):>3} nodes  [{L['scope']}] {L['role']}")
    for fa, tb, n in d["edges"][:6]:
        print(f"    edge {fa} -> {tb} ({n})")

if __name__ == "__main__":
    main()
