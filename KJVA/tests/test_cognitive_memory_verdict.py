"""test_cognitive_memory_verdict.py — the CognitiveMemoryVerdict is emitted per turn.

ADR-0001 §8.4 / ADR-0002 §4.6 define CognitiveMemoryVerdict as the cognition→memory
contract record. It was DEFINED but never emitted on a turn (only a __main__ self-test).
This pins it as genuinely emitted from real per-turn state with valid §8.4 fields.

Runs in a SRC-FIRST SUBPROCESS: under `python3 -m pytest` the `heptagon` package resolves
degraded (package-name collision), so the layer records that enrich active_layers are not
populated in-process. The subprocess (cwd=src) runs the real cognitive loop, so the verdict
reflects all layers touched — the only way to prove the live wiring, not a degraded harness.

Run:  python3 -m pytest tests/test_cognitive_memory_verdict.py -q
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
import agent
hep = agent.HeptagonLayer.build("cmv-test")
a = agent.TokenlessAgentWithHeptagon(agent.AgentConfig(), hep)
a.chat("s", "Tell me about wisdom and folly")
mv = a._last_memory_verdict
out = {
    "emitted": mv is not None,
    "route_type": getattr(mv, "route_type", None),
    "invariant_verdict": getattr(mv, "invariant_verdict", None),
    "privacy_verdict": getattr(mv, "privacy_verdict", None),
    "retention_mode": getattr(mv, "retention_mode", None),
    "active_layers": getattr(mv, "active_layers", []),
    "verdict_id": getattr(mv, "verdict_id", ""),
    "request_id": getattr(mv, "request_id", ""),
    "quality_keys": sorted((getattr(mv, "quality_metrics", {}) or {}).keys()),
}
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def result():
    proc = subprocess.run([sys.executable, "-c", _DRIVER], cwd=str(SRC),
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr[-2000:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_verdict_emitted(result):
    assert result["emitted"] is True, "CognitiveMemoryVerdict was not emitted on a turn"


def test_verdict_enums_valid(result):
    assert result["route_type"] in ("direct", "memory_mediated", "salience_routed",
                                    "executive_mediated", "lateral_peer")
    assert result["invariant_verdict"] in ("pass", "warning", "violation", "critical")
    assert result["privacy_verdict"] in ("allow", "redact", "block")
    assert result["retention_mode"] in ("discard", "session", "episodic", "semantic", "archival")


def test_verdict_carries_real_layers(result):
    # The live loop touches L1 (perception) + L2/L4/L5/L6 (records) + L7 (governance).
    assert 1 in result["active_layers"] and 7 in result["active_layers"]
    assert len(result["active_layers"]) >= 3, \
        f"verdict should reflect multiple layers touched, got {result['active_layers']}"


def test_verdict_id_per_turn(result):
    assert result["verdict_id"].startswith("cmv-")
    assert result["request_id"] != ""
