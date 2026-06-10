"""test_model_materialization.py — the C model-artifact materialization has a Python consumer.

ADR-0002 §8.2 lists "model artifact / weight/tensor materialization" as materialization domains.
The C engine materializes the model from the GGUF, but that materialization was emitted to NO
Python consumer. Now the C side exposes xmind_easy_model_info() and the agent consumes it into a
model_artifact MaterializationRecord (read-only, one owner — no second loop).

SRC-FIRST SUBPROCESS (uses the real C engine; pytest's degraded harness would skip it).

Run:  python3 -m pytest tests/test_model_materialization.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"

_DRIVER = r"""
import json, sys
sys.path.insert(0, ".")
from _xmind import get_client
c = get_client()
out = {"engine": c is not None}
if c is not None:
    out["model_info"] = c.model_info()
    import agent
    hep = agent.HeptagonLayer.build("mat-test")
    a = agent.TokenlessAgentWithHeptagon(agent.AgentConfig(), hep)
    mm = a._model_materialization
    out["emitted"] = mm is not None
    out["type"] = getattr(mm, "materialization_type", None)
    out["facts"] = mm.transforms[0] if (mm is not None and mm.transforms) else {}
    out["status"] = getattr(mm, "status", None)
    # ADR-0002 §8.3 minimum fields
    out["source_hashes"] = list(getattr(mm, "source_hashes", []))
    out["created_at"] = getattr(mm, "created_at", "")
    out["rollback_refs"] = list(getattr(mm, "rollback_refs", []))
    out["tensor_roles"] = out["facts"].get("tensor_roles", [])
    out["model_path"] = getattr(c, "model_path", "")
print(json.dumps(out))
"""

import hashlib


def _file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


@pytest.fixture(scope="module")
def result():
    proc = subprocess.run([sys.executable, "-c", _DRIVER], cwd=str(SRC),
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr[-2000:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_engine_exposes_model_info(result):
    if not result.get("engine"):
        pytest.skip("XMIND C engine not built")
    info = result["model_info"]
    assert info.get("n_layers") == 8 and info.get("vocab_size") == 259, info
    assert info.get("quant") == "q4_0"


def test_agent_consumes_into_materialization_record(result):
    if not result.get("engine"):
        pytest.skip("XMIND C engine not built")
    assert result["emitted"] is True, "no model_artifact MaterializationRecord emitted"
    assert result["type"] == "model_artifact"
    assert result["status"] == "committed"
    # The materialization CONSUMES the C facts (not an empty placeholder).
    assert result["facts"].get("n_layers") == 8, result["facts"]


def test_adr_8_3_source_hash_is_real_and_matches(result):
    """ADR-0002 §8.3 source_hash + 'No model artifact loads without hash verification':
    the record's source_hash must be the REAL sha256 of the materialized GGUF, not the C
    engine's non-crypto fold."""
    if not result.get("engine"):
        pytest.skip("XMIND C engine not built")
    sh = result["source_hashes"]
    assert sh and sh[0].startswith("sha256:"), f"missing §8.3 source_hash, got {sh}"
    assert sh[0] == _file_sha(result["model_path"]), \
        "§8.3 source_hash does not match the actual materialized GGUF (wrong/non-crypto hash)"


def test_adr_8_3_minimum_fields_present(result):
    """ADR-0002 §8.3 minimum fields + Workstream 4 'add rollback pointer': materialized_at,
    tensor_roles, and rollback_pointer must be populated — not just 'a record exists'."""
    if not result.get("engine"):
        pytest.skip("XMIND C engine not built")
    assert result["created_at"], "§8.3 materialized_at (created_at) not populated"
    assert len(result["tensor_roles"]) >= 8 * 7, \
        f"§8.3 tensor_roles incomplete: {len(result['tensor_roles'])}"
    assert result["rollback_refs"], "§8.3 rollback_pointer (Workstream 4) not populated"
