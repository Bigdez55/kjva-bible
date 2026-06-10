"""Scripture must be RETRIEVAL-GROUNDED, never LM-confabulated (ADR P0 / D01,D02).

Guards the product requirement: a verse query returns the EXACT corpus verse
(generation_invoked=False). Regression target: the model once "generated"
'PSA 105:1 The LORD is my strength' (a hallucination); the true verse is
'O give thanks unto the LORD; call upon his name: make known his deeds...'.
"""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ai" / "tokenless-agent" / "src"
sys.path.insert(0, str(SRC))

KNOWN = {
    "Psalm 105:1": ("PSA 105:1", "O give thanks unto the LORD"),
    "What does John 3:16 say?": ("JHN 3:16", "For God so loved the world"),
    "Genesis 1:1": ("GEN 1:1", "In the beginning God created"),
    "1 Corinthians 13:4": ("1CO 13:4", "Charity suffereth long"),
    "Romans 8:28": ("ROM 8:28", "all things work together for good"),
}


@pytest.fixture(scope="module")
def retriever():
    from retrieval import get_retriever
    return get_retriever()


def test_corpus_loaded(retriever):
    assert retriever.verse_count == 36822


@pytest.mark.parametrize("query,expected", list(KNOWN.items()))
def test_exact_citation(retriever, query, expected):
    ref, snippet = expected
    ans = retriever.answer(query)
    assert ans is not None and ans["generation_invoked"] is False
    assert ref in ans["citations"], f"{query} -> {ans['citations']}"
    assert snippet in ans["text"]


def test_user_correction_psalm_105(retriever):
    """The exact regression the user flagged."""
    c = retriever.cite("Psalm 105:1")
    assert c.text == ("O give thanks unto the LORD; call upon his name: "
                      "make known his deeds among the people.")
    assert "strength" not in c.text  # the hallucinated version said 'strength'


def test_non_scripture_routes_elsewhere(retriever):
    assert retriever.answer("what is the weather today") is None
    assert retriever.answer("hello there") is None


@pytest.mark.parametrize("bad_ref", [
    "Matthew 35:7",    # Matthew has 28 chapters
    "Genesis 51:1",    # Genesis has 50 chapters
    "Revelation 23:1", # Revelation has 22 chapters
])
def test_invalid_citation_rejected(retriever, bad_ref):
    """Non-existent refs must return a corpus-rejection string, never LM confabulation."""
    ans = retriever.answer(bad_ref)
    # Either detect+reject or detect+none — must not hallucinate verse text
    if ans is not None:
        assert "not in the KJV" in ans["text"]
        assert ans["generation_invoked"] is False
        assert ans["citations"] == []


def test_invalid_citation_cite_returns_none(retriever):
    """cite() for out-of-range refs must return None (no hallucination)."""
    assert retriever.cite("Matthew 35:7") is None
    assert retriever.cite("Genesis 51:1") is None
    assert retriever.cite("Revelation 23:1") is None


def test_agent_grounds_scripture():
    from agent import TokenlessAgent, AgentConfig
    ag = TokenlessAgent(AgentConfig())
    r = ag.chat("t", "Psalm 105:1")
    assert "O give thanks unto the LORD" in r
    # meta queries still answered
    assert "covenant" in ag.chat("t", "what are the covenant rules").lower()


def test_agent_rejects_invalid_citation():
    """agent.chat() with an out-of-range reference must reject, not confabulate."""
    from agent import TokenlessAgent, AgentConfig
    ag = TokenlessAgent(AgentConfig())
    r = ag.chat("t", "What does Matthew 35:7 say?")
    assert "not in the KJV" in r
