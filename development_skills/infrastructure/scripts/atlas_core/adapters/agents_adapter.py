from __future__ import annotations

from atlas_models import read_yaml
from atlas_paths import ROOT


def load() -> dict:
    registry = ROOT / "platform" / "sdlc" / "12_agents" / "agents.registry.yaml"
    data = read_yaml(registry)
    universal = ROOT / ".codex" / "universal" / "agents"
    return {
        "status": "present" if registry.exists() or universal.exists() else "missing",
        "registry": "platform/sdlc/12_agents/agents.registry.yaml" if registry.exists() else "",
        "registry_count": data.get("total", 0),
        "codex_universal_count": len(list(universal.glob("*.md"))) if universal.exists() else 0,
    }
