from __future__ import annotations

from atlas_paths import ROOT, rel


def load() -> dict:
    registries = sorted(ROOT.glob("**/*.registry.yaml"))
    return {
        "status": "present" if registries else "missing",
        "count": len(registries),
        "paths": [rel(p) for p in registries if ".git" not in p.parts],
    }
