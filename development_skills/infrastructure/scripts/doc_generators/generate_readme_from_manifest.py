#!/usr/bin/env python3
"""Generate README, SYSTEMS_INDEX, and CHANGELOG from manifest + ledgers."""
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "11_documentation" / "generated"
OUT.mkdir(parents=True, exist_ok=True)

def load(rel): return yaml.safe_load((ROOT/rel).read_text())

def tracked_system_dirs():
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    roots = set()
    for line in proc.stdout.splitlines():
        root = line.split("/", 1)[0]
        if len(root) >= 3 and root[:2].isdigit() and root[2] == "_":
            roots.add(root)
    return sorted(roots)

def main():
    manifest = load("18_registry/project.manifest.yaml")["project"]
    repo_ledger = load("18_registry/repo_ledger.yaml")["repo_ledger"]
    decision_ledger = load("18_registry/decision_ledger.yaml")
    change_ledger = load("18_registry/change_ledger.yaml")
    sysdirs = tracked_system_dirs()

    # README.generated
    readme = [f"# {manifest['name']} (generated)\n",
              f"Version: {manifest.get('version','')}",
              f"Owner: {manifest['owner']}",
              f"Last updated: {manifest.get('last_updated','')}\n",
              f"## {len(sysdirs)} Tracked Numbered Roots"]
    for s in sysdirs: readme.append(f"- [{s}]({s}/)")
    readme.append(f"\n## Stats")
    for k in (
        "systems_count",
        "tracked_numbered_roots_count",
        "local_numbered_directories_observed",
        "schemas_count",
        "templates_count",
        "skills_count",
        "adrs_count",
        "twins_count",
        "commands_count",
        "command_playbooks_count",
    ):
        if k in manifest: readme.append(f"- {k}: {manifest[k]}")
    (OUT/"README.generated.md").write_text("\n".join(readme))

    # SYSTEMS_INDEX.generated
    idx = ["# Systems Index (generated)\n"]
    for s in sysdirs:
        idx.append(f"## {s}\nSee [{s}/]({'../../'+s}/) and ledger entries in [18_registry/](../../18_registry/).\n")
    (OUT/"SYSTEMS_INDEX.generated.md").write_text("\n".join(idx))

    # CHANGELOG.generated
    cl = ["# Changelog (generated)\n"]
    for c in change_ledger.get("changes", []):
        cl.append(f"- {c.get('date')}: {c.get('summary')} ({c.get('sha','')})")
    (OUT/"CHANGELOG.generated.md").write_text("\n".join(cl))

    print(f"Generated 3 files in {OUT}")

if __name__ == "__main__":
    main()
