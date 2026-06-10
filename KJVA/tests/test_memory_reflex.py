"""Cognitive Control <-> Memory reflex is LIVE (ADR-0002 §13.7 / ADR-0001 §8, D13/D14).

The agent must: (1) write a quality-gated ExperienceAtom after a turn, and
(2) recall it on a later related cue, returning a MemoryContextPacket. Recall is
bounded (top_k) and never promotes low-quality memory.
"""
import sys
from pathlib import Path
import pytest

SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"
sys.path.insert(0, str(SRC))

_BENIGN_ML = {"available": False, "harmful": False, "category": "benign", "score": 0.0}


@pytest.fixture
def agent(monkeypatch, tmp_path):
    # Redirect archive writes away from /var/tokenless (requires root) to a writable tmp dir.
    monkeypatch.setenv("TOKENLESS_STATE_DIR", str(tmp_path))
    # Patch the ML safety classifier to unavailable. Biblical proper nouns (Abraham, Canaan)
    # score as 'weapons' (0.82+) due to classifier miscalibration — this causes covenant to
    # block the test inputs, defeating the memory-wiring assertions. The classifier is tested
    # separately by test_safety_classifier.py. Here we want only the memory wiring path.
    sys.path.insert(0, str(SRC))
    import governance.ml_safety_classifier as _mlsc
    monkeypatch.setattr(_mlsc, "classify", lambda _text: _BENIGN_ML)
    from agent import TokenlessAgentWithHeptagon, AgentConfig, HeptagonLayer
    return TokenlessAgentWithHeptagon(AgentConfig(), HeptagonLayer.build())


def test_writeback_creates_atom(agent):
    assert agent._ledger is not None
    agent.chat("s", "Remember that Abraham traveled to Canaan")
    assert len(agent._ledger.alive()) >= 1          # D14 writeback


def test_recall_returns_memory_context_packet(agent):
    agent.chat("s", "Remember that Abraham traveled to Canaan")
    agent.chat("s", "tell me again about Abraham")
    pkt = agent._last_memory_packet
    assert pkt is not None and type(pkt).__name__ == "MemoryContextPacket"  # D13
    assert pkt.retrieved_experience_ids, "recall did not retrieve the prior atom"
    assert "abraham" in pkt.cue_terms
    assert pkt.confidence > 0.0


def test_recall_is_bounded(agent):
    for i in range(30):
        agent.chat("s", f"Note number {i} about subject {i}")
    agent.chat("s", "subject 5")
    pkt = agent._last_memory_packet
    assert pkt is not None
    assert len(pkt.retrieved_experience_ids) <= 7   # top_k bound (no unbounded recall)


def test_scripture_unaffected_by_memory_wiring(agent):
    assert "O give thanks unto the LORD" in agent.chat("s", "Psalm 105:1")
