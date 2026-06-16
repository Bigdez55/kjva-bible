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


def _is_numbered(name: str) -> bool:
    return len(name) >= 3 and name[:2].isdigit() and name[2] == "_"


def _numbered_root_of(path: str) -> str | None:
    """Return the numbered subsystem root for a tracked path, or None.

    Post-restructure the numbered SDLC/systems dirs live under
    ``platform/sdlc/NN_*`` and ``platform/systems/NN_*`` (only the segment
    immediately under sdlc/systems counts -- deeper numbered dirs such as
    ``44_knowledge_vault/07_skills`` must NOT be counted). The legacy
    top-level ``NN_*`` layout is still recognised for backwards compatibility.
    """
    parts = path.split("/")
    if _is_numbered(parts[0]):
        return parts[0]
    if len(parts) >= 3 and parts[0] == "platform" and parts[1] in ("sdlc", "systems") and _is_numbered(parts[2]):
        return f"{parts[0]}/{parts[1]}/{parts[2]}"
    return None


def build_inventory() -> dict[str, Any]:
    files = git_files()
    root_counts = Counter(path.split("/", 1)[0] for path in files)
    numbered_root_counts = Counter(
        root for root in (_numbered_root_of(path) for path in files) if root is not None
    )
    numbered_roots = sorted(numbered_root_counts)

    def _local_numbered(base: Path) -> list[str]:
        if not base.is_dir():
            return []
        return [p.name for p in base.iterdir() if p.is_dir() and _is_numbered(p.name)]

    local_numbered_dirs = sorted(
        _local_numbered(ROOT)
        + [f"platform/sdlc/{n}" for n in _local_numbered(ROOT / "platform" / "sdlc")]
        + [f"platform/systems/{n}" for n in _local_numbered(ROOT / "platform" / "systems")]
    )
    protected = [
        "New updates/",
        "backups/",
        "28_archive/",
        "platform/systems/38_bookworm_engine/original_import/",
        "38_bookworm_canonical_bridge/",
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
                "truth_state": ["19_truth_state/current.truth.yaml", "19_truth_state/source_of_truth_ranking.yaml"],
                "manifests": ["atlas.manifest.yaml", "18_registry/project.manifest.yaml", "APEX_VERSION.md"],
                "skills": ["platform/sdlc/13_skills/active", "platform/sdlc/13_skills/skills.registry.yaml"],
                "command_protocol": ["37_command_protocol"],
                "bookworm": ["38_bookworm_canonical_bridge", "38_bookworm_engine"],
                "repo_twins": ["39_repo_twins"],
                "context_compiler": ["42_context_compiler"],
                "proof_matrix": ["36_proof_matrix"],
                "drift_detection": ["20_drift_detection"],
                "graph_layer": ["04_architecture/graphs", "04_architecture/models", "16_knowledge/knowledge_mesh"],
            },
        }
    }


def inventory_markdown(inventory: dict[str, Any]) -> str:
    data = inventory["atlas_inventory"]
    lines = [
        "# ATLAS Inventory",
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
