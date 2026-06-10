"""test_memory_quality_gate.py — the writeback quality gate rejects low-quality memory.

ADR-0001 §13.15: "no low-quality memory promoted." agent._memory_writeback gates the
ExperienceAtom write on (passed AND quality >= 0.3). Without this, a low-quality or
governance-failed turn would still be consolidated into the lifespan ledger and could be
recalled later as if trustworthy.

This pins the gate directly (no XMIND/engine needed): below-threshold and not-passed turns
must NOT commit; an at/above-threshold passing turn MUST commit (and arm the 'memory'
materialization record via _last_writeback_committed).

Run:  python3 -m pytest tests/test_memory_quality_gate.py -q
"""
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="module")
def agent():
    a_mod = pytest.importorskip("agent")
    a = a_mod.TokenlessAgentWithHeptagon(a_mod.AgentConfig())
    if getattr(a, "_ledger", None) is None:
        pytest.skip("LifespanLedger not wired — memory continuity unavailable (real gap)")
    return a


def _commits(agent, *, quality, passed) -> bool:
    agent._memory_writeback("cue", "response", quality=quality, passed=passed)
    return bool(getattr(agent, "_last_writeback_committed", False))


def test_below_threshold_is_rejected(agent):
    assert _commits(agent, quality=0.29, passed=True) is False, \
        "quality 0.29 < 0.3 must NOT be promoted to memory"
    assert _commits(agent, quality=0.0, passed=True) is False


def test_failed_governance_is_rejected_regardless_of_quality(agent):
    assert _commits(agent, quality=0.99, passed=False) is False, \
        "a governance-failed turn must NOT be promoted even at high quality"


def test_at_and_above_threshold_passing_commits(agent):
    assert _commits(agent, quality=0.3, passed=True) is True, \
        "quality exactly at the 0.3 floor must commit"
    assert _commits(agent, quality=0.85, passed=True) is True
