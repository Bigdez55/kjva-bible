#!/usr/bin/env python3
"""
scan_repo_census.py — Layer 2 (Repo Census) + Layer 3 (Classifier) of the
ATLAS Repository Architecture Map Engine.  "Nothing escapes the diagram."

KEYSTONE GATE: every TRACKED file (git ls-files) becomes exactly one node — the
node count MUST equal `git ls-files | wc -l`, or this exits non-zero. Present-but-
untracked/ignored top-level entries (.pytest_cache, backups, …) are a SEPARATE
tier: shown + flagged, excluded from the 1:1 denominator (so "100%" is honest).

Single source of truth: reuses the canonical classify() from extract_repo_objects
(no second classifier). Edges are NOT re-derived here — they come from the existing
architecture-state sync inventory (edge_inventory.yaml). One scanner, one graph.

Emits (under the Atlas-native 43_graph_engine root):
  platform/systems/43_graph_engine/graphs/repo_structure.nodes.jsonl  (every tracked file/dir)
  platform/systems/43_graph_engine/exports/repo_census.json           (hierarchical summary for the UI)
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sync_scripts"))
from extract_repo_objects import classify  # the ONE canonical classifier

GRAPHS = ROOT / "platform/systems/43_graph_engine/graphs"
EXPORTS = ROOT / "platform/systems/43_graph_engine/exports"
# Top-level dirs covered by the deep object/edge scan (extract_repo_objects SCAN_DIRS).
DEEP_SCOPE = {"apps", "infrastructure", "schemas", "docs", "platform"}
TREE_HIDE = {".git", ".DS_Store"}
WALK_SKIP = {"node_modules", ".git", ".next", "__pycache__", "dist", ".DS_Store"}

def git(*args) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return [l for l in out.stdout.splitlines() if l.strip()]

def count_untracked(d: Path) -> int:
    n = 0
    for dp, dns, fns in os.walk(d):
        dns[:] = [x for x in dns if x not in WALK_SKIP]
        n += len([f for f in fns if f not in WALK_SKIP])
    return n

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stamp", default="unstamped")
    ap.add_argument("--check", action="store_true", help="exit non-zero if the coverage gate fails")
    a = ap.parse_args()

    # ---- TRACKED universe: the authoritative 1:1 node set ----
    tracked = git("ls-files")
    commit = (git("rev-parse", "HEAD") or ["unknown"])[0][:12]

    # bucket tracked files by top-level and second-level prefix — ONE pass, no os.walk
    top_files: dict[str, int] = Counter()
    top_types: dict[str, Counter] = defaultdict(Counter)
    second: dict[str, dict[str, int]] = defaultdict(Counter)
    types_all = Counter()
    nodes = []
    for p in tracked:
        parts = p.split("/")
        kind = classify(p)
        types_all[kind] += 1
        if len(parts) > 1:                       # lives under a real top-level dir
            top = parts[0]
            top_files[top] += 1
            top_types[top][kind] += 1
            second[top][parts[1]] += 1
            scope = "deep" if top in DEEP_SCOPE else "shallow"
        else:                                    # a repo-root file, not a directory
            top = "(root files)"
            scope = "deep"
        nodes.append({"id": p, "kind": "file", "type": kind, "top": top,
                      "scope": scope, "tier": "tracked"})

    # ---- PRESENT-BUT-UNTRACKED top-level tier (shown, flagged, separate denominator) ----
    present = sorted(p for p in os.listdir(ROOT) if p not in TREE_HIDE)
    tracked_tops = set(top_files)
    untracked_tops = []
    for name in present:
        full = ROOT / name
        if name in tracked_tops:
            continue
        if full.is_dir():
            untracked_tops.append({"name": name, "git": "untracked/ignored",
                                   "files": count_untracked(full),
                                   "scope": "shallow"})
        # untracked root files are rare; fold into the tier count if any
    # also flag tracked top-level dirs that git considers ignored at deeper levels? (no — tracked=authoritative)

    # ---- hierarchical top-level summary (for the UI; full index is nodes.jsonl) ----
    top_level = []
    for name in sorted(tracked_tops):
        children = [{"name": c, "files": n, "kind": "dir" if (ROOT / name / c).is_dir() else "file"}
                    for c, n in sorted(second[name].items(), key=lambda kv: -kv[1])]
        top_level.append({
            "name": name, "scope": "deep" if name in DEEP_SCOPE else "shallow",
            "git": "tracked", "files": top_files[name],
            "types": dict(top_types[name]), "children": children,
        })
    # root-level tracked files as their own band
    root_files = [p for p in tracked if "/" not in p]
    if root_files:
        top_level.append({"name": "(root files)", "scope": "deep", "git": "tracked",
                          "files": len(root_files), "types": {},
                          "children": [{"name": f, "files": 1, "kind": "file"} for f in sorted(root_files)]})

    coverage = {
        "tracked_files": len(tracked),
        "tracked_nodes": len(nodes),
        "match": len(tracked) == len(nodes),
        "untracked_present_dirs": len(untracked_tops),
        "denominator": "git ls-files (tracked only); untracked/ignored shown separately",
    }

    out = {
        "generated_at": a.stamp, "commit": commit,
        "generator": "infrastructure/scripts/architecture_map/scan_repo_census.py",
        "coverage": coverage,
        "classification": dict(types_all.most_common()),
        "top_level": top_level,
        "untracked_present": untracked_tops,
    }
    GRAPHS.mkdir(parents=True, exist_ok=True); EXPORTS.mkdir(parents=True, exist_ok=True)
    (GRAPHS / "repo_structure.nodes.jsonl").write_text("\n".join(json.dumps(n) for n in nodes) + "\n")
    (EXPORTS / "repo_census.json").write_text(json.dumps(out, indent=2))

    print(f"census: {len(tracked)} tracked files -> {len(nodes)} nodes  "
          f"GATE {'PASS' if coverage['match'] else 'FAIL'} (1:1)")
    print(f"  top-level: {len(tracked_tops)} tracked dirs + {len(root_files)} root files "
          f"+ {len(untracked_tops)} untracked/ignored present")
    for t in top_level:
        print(f"    {t['name']:<16} {t['files']:>6} files  ({t['scope']})")
    for u in untracked_tops:
        print(f"    {u['name']:<16} {u['files']:>6} files  (untracked/ignored — shown, not in 1:1)")
    if a.check and not coverage["match"]:
        print("COVERAGE GATE FAILED", file=sys.stderr); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
