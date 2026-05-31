from __future__ import annotations

from atlas_paths import iter_canonical_registries, rel


def load() -> dict:
    registries = iter_canonical_registries()
    return {
        "status": "present" if registries else "missing",
        "count": len(registries),
        "paths": [rel(p) for p in registries],
    }
