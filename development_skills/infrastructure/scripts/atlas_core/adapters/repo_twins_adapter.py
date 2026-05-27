from __future__ import annotations

from atlas_models import read_yaml
from atlas_paths import ROOT


def load() -> dict:
    registry = ROOT / "39_repo_twins" / "repo_twins.registry.yaml"
    twins_dir = ROOT / "39_repo_twins" / "twins"
    data = read_yaml(registry)
    return {
        "status": "present" if registry.exists() and twins_dir.exists() else "missing",
        "count": data.get("total", 0),
        "registry": "39_repo_twins/repo_twins.registry.yaml",
        "directory_count": len([p for p in twins_dir.iterdir() if p.is_dir()]) if twins_dir.exists() else 0,
    }
