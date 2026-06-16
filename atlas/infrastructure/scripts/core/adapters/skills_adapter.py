from __future__ import annotations

from atlas_models import read_yaml
from atlas_paths import ROOT


def load() -> dict:
    registry = ROOT / "platform" / "sdlc" / "13_skills" / "skills.registry.yaml"
    data = read_yaml(registry)
    return {
        "status": "present" if registry.exists() else "missing",
        "count": data.get("total", 0),
        "registry": "platform/sdlc/13_skills/skills.registry.yaml",
        "active_yaml_count": len(list((ROOT / "platform" / "sdlc" / "13_skills" / "active").glob("*.yaml"))),
    }
