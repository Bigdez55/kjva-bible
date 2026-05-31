"""Repository inventory model for Atlas Platform Core."""

from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from atlas_models import write_json
from atlas_paths import INVENTORY_DIR, ROOT


def git_files() -> list[str]:
    proc = subprocess.run(["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=True)
    return [line for line in proc.stdout.splitlines() if line]


def build_inventory() -> dict[str, Any]:
    files = git_files()
    root_counts = Counter(path.split("/", 1)[0] for path in files)
    numbered_roots = sorted(root for root in root_counts if len(root) >= 3 and root[:2].isdigit() and root[2] == "_")
    local_numbered_dirs = sorted(
        p.name for p in ROOT.iterdir() if p.is_dir() and len(p.name) >= 3 and p.name[:2].isdigit() and p.name[2] == "_"
    )
    protected = [
        "New updates/",
        "backups/",
        "platform/systems/28_archive/",
        "platform/systems/38_bookworm_engine/original_import/",
        "platform/systems/38_bookworm_canonical_bridge/",
    ]
    return {
        "atlas_inventory": {
            "tracked_files_total": len(files),
            "tracked_roots": dict(sorted(root_counts.items())),
            "tracked_numbered_roots_count": len(numbered_roots),
            "tracked_numbered_roots": numbered_roots,
            "local_numbered_directories_count": len(local_numbered_dirs),
            "local_numbered_directories": local_numbered_dirs,
            "protected_paths": protected,
            "subsystem_paths": {
                "truth_state": ["platform/systems/19_truth_state/current.truth.yaml", "platform/systems/19_truth_state/source_of_truth_ranking.yaml"],
                "manifests": ["atlas.manifest.yaml", "platform/systems/18_registry/project.manifest.yaml", "APEX_VERSION.md"],
                "skills": ["platform/sdlc/13_skills/active", "platform/sdlc/13_skills/skills.registry.yaml"],
                "command_protocol": ["platform/systems/37_command_protocol"],
                "bookworm": ["platform/systems/38_bookworm_canonical_bridge", "platform/systems/38_bookworm_engine"],
                "repo_twins": ["platform/systems/39_repo_twins"],
                "context_compiler": ["platform/systems/42_context_compiler"],
                "proof_matrix": ["platform/systems/36_proof_matrix"],
                "drift_detection": ["platform/systems/20_drift_detection"],
                "graph_layer": ["platform/sdlc/04_architecture/graphs", "platform/sdlc/04_architecture/models", "platform/sdlc/16_knowledge/knowledge_mesh"],
            },
        }
    }


def inventory_markdown(inventory: dict[str, Any]) -> str:
    data = inventory["atlas_inventory"]
    lines = [
        "# SUPER C Atlas Inventory",
        "",
        f"- Tracked files: {data['tracked_files_total']}",
        f"- Tracked numbered roots: {data['tracked_numbered_roots_count']}",
        f"- Local numbered directories observed: {data['local_numbered_directories_count']}",
        "",
        "## Tracked Numbered Roots",
        "",
    ]
    for root in data["tracked_numbered_roots"]:
        lines.append(f"- `{root}`")
    lines.extend(["", "## Subsystem Paths", ""])
    for name, paths in data["subsystem_paths"].items():
        lines.append(f"- `{name}`: {', '.join(f'`{p}`' for p in paths)}")
    lines.append("")
    return "\n".join(lines)


def write_inventory(inventory: dict[str, Any]) -> None:
    INVENTORY_DIR.mkdir(parents=True, exist_ok=True)
    write_json(INVENTORY_DIR / "atlas_inventory.json", inventory)
    (INVENTORY_DIR / "atlas_inventory.md").write_text(inventory_markdown(inventory))
