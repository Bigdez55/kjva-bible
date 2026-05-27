from __future__ import annotations

from atlas_paths import ROOT, rel


def load() -> dict:
    output = ROOT / "platform" / "systems" / "42_context_compiler" / "output" / "generated"
    packets = sorted(output.glob("CP-*.yaml")) if output.exists() else []
    return {
        "status": "present" if output.exists() else "missing",
        "outputs": [rel(p) for p in packets],
    }
