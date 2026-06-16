from __future__ import annotations

from atlas_models import read_yaml
from atlas_paths import ROOT, rel


def load() -> dict:
    state = ROOT / "20_drift_detection" / "drift_state.yaml"
    reports = sorted((ROOT / "20_drift_detection" / "drift_reports").glob("*")) if (ROOT / "20_drift_detection" / "drift_reports").exists() else []
    return {
        "status": "present" if state.exists() else "missing",
        "paths": [rel(state)] + [rel(p) for p in reports if p.is_file()],
        "watched": list((read_yaml(state).get("hashes", {}) or {}).keys()),
    }
