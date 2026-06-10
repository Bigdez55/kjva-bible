"""test_metacognitive_triad.py — the understanding/innerstanding/overstanding triad runs per turn.

heptagon/{metacognition,drift_detector,invariant_engine}.py are a deliberate metacognitive
triad (the lineage_level enum: understanding|innerstanding|overstanding), distinct from the
governance owners — three LEVELS of self-reflection that set the per-turn lineage_level to
improve inference. They were defined but never called. This pins all three as genuinely wired.

SRC-FIRST SUBPROCESS (pytest's degraded heptagon harness would not run the live loop).

Run:  python3 -m pytest tests/test_metacognitive_triad.py -q
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
hep = agent.HeptagonLayer.build("triad")
a = agent.TokenlessAgentWithHeptagon(agent.AgentConfig(), hep)
out = {"wired": all([a._meta_understanding is not None,
                     a._meta_innerstanding is not None,
                     a._meta_overstanding is not None])}
a.chat("s", "Tell me about wisdom and folly")
out["meta"] = a._last_metacognition
out["verdict_level"] = getattr(a._last_memory_verdict, "lineage_level", None)
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def result():
    proc = subprocess.run([sys.executable, "-c", _DRIVER], cwd=str(SRC),
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr[-2000:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_all_three_levels_wired(result):
    assert result["wired"] is True, "metacognitive triad not fully instantiated"


def test_triad_produces_lineage_level(result):
    meta = result["meta"]
    assert meta.get("lineage_level") in ("understanding", "innerstanding", "overstanding")
    # all three modules contributed a real signal
    assert "calibration_error" in meta          # understanding (Metacognition)
    assert "drift_samples" in meta and meta["drift_samples"] >= 1   # innerstanding (DriftDetector)
    assert "invariant_violations" in meta       # overstanding (InvariantEngine)


def test_verdict_uses_triad_lineage(result):
    # the CognitiveMemoryVerdict.lineage_level is driven by the triad, not hardcoded.
    assert result["verdict_level"] == result["meta"]["lineage_level"]
