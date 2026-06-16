from __future__ import annotations

from atlas_models import read_yaml
from atlas_paths import ROOT


def load() -> dict:
    path = ROOT / "19_truth_state" / "current.truth.yaml"
    data = read_yaml(path)
    return {
        "path": "19_truth_state/current.truth.yaml",
        "status": data.get("status", "missing" if not path.exists() else "unknown"),
        "last_verified": data.get("last_verified", ""),
        "summary": data.get("summary", ""),
        "target_identity": data.get("target_identity", ""),
        "skills_stack_v7_status": data.get("skills_stack_v7_status", ""),
    }
