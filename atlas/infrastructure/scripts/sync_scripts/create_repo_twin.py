#!/usr/bin/env python3
"""Scaffold a repo twin and (optionally) register it. Re-runnable; does not overwrite existing files."""
import argparse, yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

TEMPLATE = lambda name, repo: {
    "repo_twin.manifest.yaml": f"repo_twin:\n  name: {name}\n  repo_url: https://github.com/{repo}\n  repository_full_name: {repo}\n  status: initialized\n  last_ingested: null\n  last_verified: null\n",
    "current.truth.yaml": f"truth_id: TRUTH_{name.upper()}_0001\nrepo: {name}\nstatus: initialized\nsummary: Repo twin created. Awaiting ingestion.\n",
    "architecture.snapshot.yaml": "snapshot_id: ARCH_SNAPSHOT_0001\ncomponents: []\nrelationships: []\n",
    "component.graph.yaml": "components: []\nedges: []\n",
    "dependency.graph.yaml": "dependencies: []\n",
    "diagram.registry.yaml": "diagrams: []\n",
    "skill_usage.yaml": "skills_used: []\n",
    "agent_activity.yaml": "activity: []\n",
    "sync_status.yaml": "sync_status: pending_ingestion\n",
    "last_known_state.md": f"# {name} Last Known State\n\nAwaiting first Bookworm ingestion.\n",
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--repo", required=True, help="owner/name format, e.g. Bigdez55/LMOS")
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()
    base = ROOT / "platform" / "systems" / "39_repo_twins" / "twins" / args.name
    if args.remove:
        if base.exists():
            import shutil; shutil.rmtree(base)
            print(f"Removed {base}")
        return
    base.mkdir(parents=True, exist_ok=True)
    for fname, content in TEMPLATE(args.name, args.repo).items():
        p = base / fname
        if not p.exists(): p.write_text(content)
    print(f"Created/updated repo twin at {base}")

if __name__ == "__main__":
    main()
