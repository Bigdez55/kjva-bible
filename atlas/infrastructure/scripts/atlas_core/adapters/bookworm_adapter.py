from __future__ import annotations

from atlas_models import read_yaml
from atlas_paths import ROOT, rel


def load() -> dict:
    manifest = ROOT / "platform" / "systems" / "38_bookworm_engine" / "bookworm.manifest.yaml"
    indexes = sorted((ROOT / "platform" / "systems" / "38_bookworm_engine" / "indexing").glob("*.yaml"))
    bridge = ROOT / "platform" / "systems" / "38_bookworm_canonical_bridge"
    return {
        "status": "present" if manifest.exists() and indexes else "missing",
        "paths": [
            "platform/systems/38_bookworm_engine",
            "platform/systems/38_bookworm_canonical_bridge",
        ],
        "manifest": read_yaml(manifest),
        "index_count": len(indexes),
        "indexes": [rel(p) for p in indexes],
        "canonical_bridge_present": bridge.exists(),
    }
