from __future__ import annotations

from atlas_paths import ROOT, rel


def load() -> dict:
    paths = [
        ROOT / "platform" / "sdlc" / "04_architecture" / "graphs",
        ROOT / "platform" / "sdlc" / "04_architecture" / "models",
        ROOT / "platform" / "sdlc" / "04_architecture" / "diagrams",
        ROOT / "platform" / "sdlc" / "16_knowledge" / "knowledge_mesh",
    ]
    return {
        "graph_layer": {
            "status": "present" if all(p.exists() for p in paths[:3]) else "partial",
            "paths": [rel(p) for p in paths if p.exists()],
        },
        "knowledge_mesh": {
            "status": "present" if paths[3].exists() else "missing",
            "paths": [rel(paths[3])] if paths[3].exists() else [],
        },
    }
