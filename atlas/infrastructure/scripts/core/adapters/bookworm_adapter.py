from __future__ import annotations

from atlas_models import read_yaml
from atlas_paths import ROOT, rel


def load() -> dict:
    manifest = ROOT / "38_bookworm_engine" / "bookworm.manifest.yaml"
    indexes = sorted((ROOT / "38_bookworm_engine" / "indexing").glob("*.yaml"))
    bridge = ROOT / "38_bookworm_canonical_bridge"
    return {
        "status": "present" if manifest.exists() and indexes else "missing",
        "paths": [
            "38_bookworm_engine",
            "38_bookworm_canonical_bridge",
        ],
        "manifest": read_yaml(manifest),
        "index_count": len(indexes),
        "indexes": [rel(p) for p in indexes],
        "canonical_bridge_present": bridge.exists(),
    }
