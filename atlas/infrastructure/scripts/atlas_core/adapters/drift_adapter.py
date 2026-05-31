from __future__ import annotations

from atlas_models import read_yaml
from atlas_paths import ROOT, rel


def load() -> dict:
    state = ROOT / "platform" / "systems" / "20_drift_detection" / "drift_state.yaml"
    reports_dir = ROOT / "platform" / "systems" / "20_drift_detection" / "drift_reports"
    reports = sorted(reports_dir.glob("*")) if reports_dir.exists() else []
    return {
        "status": "present" if state.exists() else "missing",
        "paths": [rel(state)] + [rel(p) for p in reports if p.is_file()],
        "watched": list((read_yaml(state).get("hashes", {}) or {}).keys()),
    }
