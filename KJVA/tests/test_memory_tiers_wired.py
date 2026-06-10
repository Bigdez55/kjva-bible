"""test_memory_tiers_wired.py — the episodic + session memory tiers are CALLED per turn.

ADR-0002 §3 maps memory/episodic.py + memory/session.py as Memory Continuity components, and
§7.1 specifies the jog-my-memory cascade (session recall → episodic recall). These were defined
but never called on a turn. This pins them as genuinely wired: a quality turn records an Episode
(writeback) and a later cue searches the episodic tier (recall); SessionMemory accrues turns.

SRC-FIRST SUBPROCESS (pytest's degraded heptagon harness would skip the cognitive loop).

Run:  python3 -m pytest tests/test_memory_tiers_wired.py -q
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
hep = agent.HeptagonLayer.build("mem-test")
a = agent.TokenlessAgentWithHeptagon(agent.AgentConfig(), hep)
a.chat("s1", "Tell me about the wisdom of Solomon and the temple")
a.chat("s1", "Solomon temple")
sm = a._session_mem.get("s1")
hits = a._episodic.search("Solomon", max_results=5)
out = {
    "episodes_recorded": len(a._episodic._episodes),
    "episodic_search_hits": len(hits),
    "session_turns": sm.turn_count() if sm is not None else 0,
    "recall_packet_ids": len(a._last_memory_packet.retrieved_experience_ids) if a._last_memory_packet else 0,
}
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def result():
    proc = subprocess.run([sys.executable, "-c", _DRIVER], cwd=str(SRC),
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr[-2000:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_episodic_recorded_on_writeback(result):
    assert result["episodes_recorded"] >= 1, "no Episode recorded — episodic writeback not wired"


def test_episodic_searched_on_recall(result):
    assert result["episodic_search_hits"] >= 1, "episodic search found nothing for a recorded cue"
    assert result["recall_packet_ids"] >= 1, "recall packet did not fold in episodic ids"


def test_session_continuity_accrues(result):
    # 2 chats × (user + assistant) = 4 turns recorded in SessionMemory.
    assert result["session_turns"] >= 4, f"session continuity not accruing, got {result['session_turns']}"
