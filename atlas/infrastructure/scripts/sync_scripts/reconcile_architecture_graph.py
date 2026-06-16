#!/usr/bin/env python3
"""
reconcile_architecture_graph.py — Architecture-State Sync, Phase C+D.

Compares the current inventory (from extract_repo_objects.py) to the previous snapshot and
produces the architecture DIFF, not just a git diff:
  architecture_delta.yaml     — added / modified / deleted / renamed objects + edge changes
  orphan_report.md            — objects with no relationships (scoped to parsed TS, honest)
  dead_reference_report.md    — edges whose target file is missing (e.g. import of a deleted file)
  architecture_sync_summary.yaml — compact summary the TSX map consumes
  + 43_graph_engine/graphs/repo.graph.json (Graphify) + drift reports + change ledger entry

Deleted objects are TOMBSTONED (history preserved), removed from the active graph, and every
stale reference to them is surfaced. Run via atlas_run.py.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from collections import Counter
try:
    import yaml
except ImportError:
    print("pyyaml required", file=sys.stderr); sys.exit(2)

ROOT = Path(__file__).resolve().parents[3]
INTENTIONAL = ("README", "LICENSE", "CHANGELOG", "manifest", ".registry.yaml",
               "AGENTS.md", "CLAUDE.md", "CODEX.md", "index.", ".gitkeep")

def load(p, key, default=None):
    fp = Path(p)
    if not fp.exists(): return default if default is not None else []
    return (yaml.safe_load(fp.read_text()) or {}).get(key, default if default is not None else [])

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--repo", default="atlas")
    ap.add_argument("--stamp", default="unstamped"); a = ap.parse_args()
    TWIN = ROOT / f"platform/systems/39_repo_twins/twins/{a.repo}"
    SNAP = TWIN / ".snapshot"; SNAP.mkdir(parents=True, exist_ok=True)
    GRAPHS = ROOT / "platform/systems/43_graph_engine/graphs"; GRAPHS.mkdir(parents=True, exist_ok=True)
    DRIFT = ROOT / "platform/systems/20_drift_detection"
    LEDGER = ROOT / "platform/sdlc/11_documentation/change_capture/architecture_change_ledger.jsonl"

    files = load(TWIN / "file_inventory.yaml", "files")
    objects = load(TWIN / "object_inventory.yaml", "objects")
    edges = load(TWIN / "edge_inventory.yaml", "edges")
    cur = {f["path"]: f.get("sha8", "") for f in files}
    fileset = set(cur)

    prev_files = load(SNAP / "file_inventory.prev.yaml", "files")
    prev = {f["path"]: f.get("sha8", "") for f in prev_files}
    baseline = not prev

    added = sorted(set(cur) - set(prev))
    deleted = sorted(set(prev) - set(cur))
    modified = sorted(p for p in (set(cur) & set(prev)) if cur[p] != prev[p])

    # rename heuristic: a deleted + an added file sharing sha8
    prev_by_sha = {}; [prev_by_sha.setdefault(prev[p], p) for p in deleted if prev.get(p)]
    renames = []
    for ap_ in list(added):
        s = cur.get(ap_)
        if s and s in prev_by_sha:
            frm = prev_by_sha[s]
            if frm in deleted:
                renames.append({"from": frm, "to": ap_})
                deleted.remove(frm); added.remove(ap_)

    # dead references: import/documents edges whose target file is missing
    rel_edges = [e for e in edges if e.get("type") in ("imports", "documents", "references", "validates", "uses_tool")]
    dead_refs = [e for e in rel_edges if e["to"] not in fileset and "." in Path(e["to"]).name]

    # orphans (honest scope): TS source/ui/route files with no parsed import edge in OR out
    parsed_types = {"source_file", "ui_component", "route", "test_file"}
    indeg, outdeg = Counter(), Counter()
    for e in edges:
        if e.get("type") == "contains": continue
        outdeg[e["from"]] += 1; indeg[e["to"]] += 1
    orphans = [o["object_id"] for o in objects
               if o["object_type"] in parsed_types
               and indeg[o["object_id"]] == 0 and outdeg[o["object_id"]] == 0
               and not any(k in o["object_id"] for k in INTENTIONAL)]

    delta = {
        "schema_version": "1.0", "delta_id": f"DELTA-{a.repo}-{a.stamp}", "repo": a.repo, "captured_at": a.stamp,
        "baseline_run": baseline,
        "added_objects": added, "modified_objects": modified, "deleted_objects": deleted,
        "renamed_objects": renames,
        "dead_references": [{"from": e["from"], "to": e["to"], "type": e["type"]} for e in dead_refs],
        "orphaned_objects": orphans,
        "totals": {"files": len(files), "objects": len(objects), "edges": len(edges),
                   "added": len(added), "modified": len(modified), "deleted": len(deleted),
                   "renamed": len(renames), "dead_refs": len(dead_refs), "orphans": len(orphans)},
    }
    yaml.safe_dump(delta, open(TWIN / "architecture_delta.yaml", "w"), sort_keys=False, allow_unicode=True)

    # tombstones for deleted objects (history preserved)
    if deleted:
        with open(LEDGER, "a") as f:
            for d in deleted:
                f.write(json.dumps({"event": "object_deleted", "repo": a.repo, "object_id": d,
                                    "stamp": a.stamp, "status": "TOMBSTONED",
                                    "stale_refs": [e["from"] for e in dead_refs if e["to"] == d]}) + "\n")

    # reports
    def md(path, title, lines):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(f"# {title}\n\n_repo: {a.repo} · {a.stamp}_\n\n" + ("\n".join(lines) if lines else "_none_\n"))
    md(TWIN / "orphan_report.md", "Orphaned objects (TS files with no import in/out)",
       [f"- `{o}`" for o in orphans] or ["_No orphaned TS source/ui/route files._"])
    md(TWIN / "dead_reference_report.md", "Dead references (edge target missing)",
       [f"- `{e['from']}` → `{e['to']}` ({e['type']})" for e in dead_refs] or ["_No dead references._"])
    md(DRIFT / "dead_references_report.md", "Dead references (architecture sync)",
       [f"- `{e['from']}` → `{e['to']}`" for e in dead_refs] or ["_none_"])
    md(DRIFT / "orphaned_objects_report.md", "Orphaned objects (architecture sync)",
       [f"- `{o}`" for o in orphans] or ["_none_"])

    # Graphify: active graph (drop deleted; mark dead-ref edges)
    deadset = {(e["from"], e["to"]) for e in dead_refs}
    nodes = [{"id": o["object_id"], "type": o["object_type"]} for o in objects]
    gedges = [{"from": e["from"], "to": e["to"], "type": e["type"],
               "status": "broken" if (e["from"], e["to"]) in deadset else e.get("status", "active")}
              for e in edges]
    json.dump({"_meta": {"repo": a.repo, "stamp": a.stamp, "nodes": len(nodes), "edges": len(gedges),
                         "dead_edges": len(dead_refs), "orphans": len(orphans)},
               "nodes": nodes, "edges": gedges},
              open(GRAPHS / "repo.graph.json", "w"))

    # compact summary for the TSX map
    yaml.safe_dump({"schema_version": "1.0", "repo": a.repo, "stamp": a.stamp,
                    "totals": delta["totals"],
                    "object_types": dict(Counter(o["object_type"] for o in objects).most_common()),
                    "top_orphans": orphans[:15], "top_dead_refs": delta["dead_references"][:15],
                    "recent_added": added[:10], "recent_deleted": deleted[:10]},
                   open(TWIN / "architecture_sync_summary.yaml", "w"), sort_keys=False, allow_unicode=True)

    # save snapshot for next reconcile
    yaml.safe_dump({"files": files}, open(SNAP / "file_inventory.prev.yaml", "w"), sort_keys=False, allow_unicode=True)

    print(f"[{a.repo}] delta: +{len(added)} ~{len(modified)} -{len(deleted)} renamed {len(renames)} "
          f"| dead_refs {len(dead_refs)} | orphans {len(orphans)} | baseline={baseline}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
