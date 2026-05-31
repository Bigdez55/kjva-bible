from __future__ import annotations

from atlas_models import read_yaml
from atlas_paths import ROOT


def load() -> dict:
    generated = ROOT / "platform" / "systems" / "36_proof_matrix" / "proof_matrix.generated.yaml"
    proof = read_yaml(generated)
    return {
        "status": "present" if generated.exists() else "missing",
        "paths": [
            "platform/systems/36_proof_matrix/proof_matrix.generated.yaml",
            "platform/systems/36_proof_matrix/proof_matrix.yaml",
            "platform/systems/36_proof_matrix/proof.registry.yaml",
        ],
        "rows": proof.get("total", len(proof.get("rows", []) or [])),
    }
