#!/usr/bin/env python3
"""
atlas_sync.py — Atlas Architecture-State Sync dispatcher (repo-native, CLI-driven).

Subcommands (run via atlas_run.py):
  scan       — extract objects + edges into the repo twin (Phase A+B)
  reconcile  — diff vs previous, detect dead/orphan/deleted, emit graph + reports (Phase C+D)
  sync       — scan then reconcile
  map        — print the architecture summary (what the TSX map consumes)

Watch mode (Phase F) and VS Code/GitHub integration (Phase G) are deferred by design.
"""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent

def run(script, repo, stamp):
    return subprocess.run([sys.executable, str(HERE / script), "--repo", repo, "--stamp", stamp]).returncode

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scan", "reconcile", "sync", "map"])
    ap.add_argument("--repo", default="atlas")
    ap.add_argument("--stamp", default="unstamped")
    a = ap.parse_args()
    if a.cmd in ("scan", "sync"):
        rc = run("extract_repo_objects.py", a.repo, a.stamp)
        if rc: return rc
    if a.cmd in ("reconcile", "sync"):
        rc = run("reconcile_architecture_graph.py", a.repo, a.stamp)
        if rc: return rc
    if a.cmd == "map":
        import yaml
        s = Path(f"{HERE.parents[2]}/platform/systems/39_repo_twins/twins/{a.repo}/architecture_sync_summary.yaml")
        print(s.read_text() if s.exists() else "(no summary — run `sync` first)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
