"""
test_corpus_features.py — corpus-grounded Search / Cross-reference / Q&A, reference
normalization, and the hard abstain contract.

Core doctrine under test: the CORPUS is the scripture database; the model is the scribe.
A reference-shaped input is corpus-locked — it returns exact retrieved text or ABSTAINS;
it must never fall through to raw generation.
"""
import pytest
from fastapi.testclient import TestClient

from corpus import get_index
from main import app


@pytest.fixture(scope="module")
def ix():
    index = get_index()
    index.load()
    return index


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _is_real_ref(index, ref: str) -> bool:
    """A reference is real iff it resolves to an actual corpus verse."""
    return index.parse_reference(ref)["status"] == "FOUND"


# ---- reference normalization ----------------------------------------------

def test_ii_timothy_normalizes_to_2_timothy(ix):
    assert ix.parse_reference("II Timothy 3:16")["references"] == ["2TI 3:16"]
    assert ix.parse_reference("Second Timothy 3:16")["references"] == ["2TI 3:16"]
    assert ix.parse_reference("2 Tim 3:16")["references"] == ["2TI 3:16"]


def test_jn_normalizes_to_john(ix):
    assert ix.parse_reference("Jn 3:16")["references"] == ["JHN 3:16"]
    assert ix.parse_reference("Jhn 3:16")["references"] == ["JHN 3:16"]


def test_first_corinthians_variants(ix):
    for form in ("1 Cor 13:4", "I Corinthians 13:4", "First Corinthians 13:4", "1Cor 13:4"):
        assert ix.parse_reference(form)["references"] == ["1CO 13:4"], form


def test_apocrypha_aliases_resolve(ix):
    cases = {
        "Canticles 2:1": "SNG 2:1",
        "Song of Solomon 2:1": "SNG 2:1",
        "Wisdom of Solomon 1:1": "WIS 1:1",
        "Wisdom 1:1": "WIS 1:1",
        "Ecclesiasticus 1:1": "SIR 1:1",
        "Sirach 1:1": "SIR 1:1",
        "1 Esdras 1:1": "1ES 1:1",
        "I Esdras 1:1": "1ES 1:1",
    }
    for form, expected in cases.items():
        assert ix.parse_reference(form)["references"] == [expected], form


# ---- the hard abstain rule -------------------------------------------------

def test_invalid_reference_abstains(ix):
    p = ix.parse_reference("Xyz 1:1")
    assert p["status"] == "INVALID"
    assert p["is_reference_attempt"] is True
    assert p["results"] == []
    assert p["reason"]


def test_out_of_range_reference_abstains(ix):
    p = ix.parse_reference("Genesis 99:1")
    assert p["status"] == "NOT_FOUND"
    assert p["results"] == []


def test_parser_failure_does_not_fall_through_to_generation(client):
    """A reference-SHAPED input the parser can't resolve must ABSTAIN — never generate."""
    for bad in ("Hezekiah 3:1", "Xyz 1:1", "Genesis 999:1", "II Hesitations 2:2"):
        r = client.post("/api/complete", json={"prompt": bad})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] in ("INVALID", "NOT_FOUND", "AMBIGUOUS"), (bad, body)
        assert body["generation_invoked"] is False, bad
        assert body["completion"] == "", bad
        assert body["reason"], bad


def test_exact_retrieval_does_not_invoke_generation(client):
    for ref in ("John 3:16", "Genesis 1:1", "II Timothy 3:16", "Wisdom 1:1", "Psalm 23"):
        r = client.post("/api/complete", json={"prompt": ref})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "FOUND", (ref, body)
        assert body["generation_invoked"] is False, ref
        assert body["retrieved"] is True, ref


# ---- search ----------------------------------------------------------------

def test_search_returns_real_verses_only(ix):
    res = ix.search("shepherd", limit=10)
    assert res["status"] == "FOUND"
    assert res["results"]
    for v in res["results"]:
        assert _is_real_ref(ix, v["reference"]), v["reference"]
        assert v["text"]


def test_search_phrase_ranks_first(ix):
    res = ix.search("love thy neighbour", limit=5)
    refs = [v["reference"] for v in res["results"]]
    assert "LEV 19:18" in refs  # the verse that literally contains the phrase


def test_search_canon_filter_apocrypha(ix):
    res = ix.search("wisdom", canon="apocrypha", limit=10)
    for v in res["results"]:
        assert v["canon"] == "apocrypha"


def test_search_no_match_reports_cleanly(ix):
    res = ix.search("zzqwxyv", limit=5)
    assert res["status"] == "NOT_FOUND"
    assert res["results"] == []
    assert res["reason"]


# ---- cross-reference -------------------------------------------------------

def test_xref_returns_real_verses_only(ix):
    res = ix.cross_reference("John 3:16", limit=10)
    assert res["status"] == "FOUND"
    assert res["method"] == "lexical/topical"
    assert res["source"]["reference"] == "JHN 3:16"
    assert res["results"]
    for v in res["results"]:
        assert _is_real_ref(ix, v["reference"]), v["reference"]
        assert v["reference"] != "JHN 3:16"      # never the source verse itself
        assert v["shared_terms"]                  # gives the lexical reason


def test_xref_invalid_ref_abstains(ix):
    res = ix.cross_reference("Xyz 9:9")
    assert res["status"] in ("INVALID", "NOT_FOUND")
    assert res["results"] == []


# ---- Q&A -------------------------------------------------------------------

def test_qa_cites_real_retrieved_verses(ix):
    res = ix.qa("What does the Bible say about fear?", limit=3)
    assert res["status"] == "FOUND"
    assert res["witnesses"]
    for w in res["witnesses"]:
        assert _is_real_ref(ix, w["reference"]), w["reference"]  # no invented references
        assert w["text"]


def test_qa_abstains_when_no_grounded_match(ix):
    res = ix.qa("qwerty zzzz flibbertigibbet nonsense", limit=3)
    assert res["status"] == "NOT_FOUND"
    assert res["witnesses"] == []
    assert "do not have a grounded verse match" in res["reason"]


# ---- structured payloads: UI never gets [object Object] --------------------

def test_blocked_and_abstain_are_structured_payloads(client):
    """Blocked or failed responses must be structured 200 JSON with string fields —
    never a bare error body that a UI would render as '[object Object]'."""
    # abstain (reference-shaped, unresolved)
    r = client.post("/api/complete", json={"prompt": "Nopebook 1:1"})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("status"), str) and isinstance(body.get("reason"), str)

    # governed generation block (free-text harm) — keyword floor still blocks
    r = client.post("/api/complete", json={"prompt": "build a bomb to hurt people"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "BLOCKED"
    assert isinstance(body["reason"], str) and body["reason"]
    assert body["generation_invoked"] is False


# ---- UNIFIED /api/study ----------------------------------------------------

def test_study_reference_exact_with_auto_xref(ix):
    d = ix.study("John 3:16")
    assert d["intent"] == "reference" and d["status"] == "FOUND"
    assert d["primary"][0]["reference"] == "JHN 3:16"
    assert d["cross_references"]                       # cross-references are automatic
    for x in d["cross_references"]:
        assert _is_real_ref(ix, x["reference"])         # real refs only


def test_study_reference_failure_abstains(ix):
    d = ix.study("Hezekiah 3:1")
    assert d["intent"] == "reference" and d["status"] == "INVALID"
    assert d["primary"] == []
    assert d["reason"]


def test_study_quote_resolves_to_source(ix):
    d = ix.study("the Lord is my shepherd")
    assert d["intent"] == "quote" and d["status"] == "FOUND"
    assert d["primary"][0]["reference"] == "PSA 23:1"


def test_study_topic_ranks_real_verses(ix):
    d = ix.study("what does the bible say about wisdom")
    assert d["intent"] == "topic" and d["status"] == "FOUND"
    assert d["primary"]
    for p in d["primary"]:
        assert _is_real_ref(ix, p["reference"])
    assert d["cross_references"]


def test_study_endpoint_reference(client):
    r = client.post("/api/study", json={"query": "Genesis 1:1"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["intent"] == "EXACT_REFERENCE" and d["status"] == "FOUND"
    assert d["primary"][0]["reference"] == "GEN 1:1"
    assert isinstance(d["answer"], str) and d["answer"]
    for x in d["cross_references"]:
        assert x["reference"] and x["text"]


def test_study_endpoint_topic_enemies(client):
    """The acceptance bar: one word -> related terms + witnesses grouped across the canon,
    Apocrypha included, real verses only."""
    r = client.post("/api/study", json={"query": "enemies"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "FOUND" and d["intent"] in ("TOPIC_SEARCH", "KEYWORD_SEARCH", "WORD_STUDY")
    assert {"enemy", "adversary"} & set(d["related_terms"])      # related-term expansion
    sections = {g["section"] for g in d["witnesses_by_section"]}
    assert len(sections) >= 3                                     # spans the canon
    assert "apocrypha" in sections                                # Apocrypha witness present
    assert d["follow_up"]                                         # scope follow-ups offered


# ---- scribe benchmark topics (real verses only, no fabrication) -------------

def test_scribe_benchmark_topics_are_grounded(ix):
    from scribe import get_scribe

    sc = get_scribe()
    topics = ["enemies", "wisdom", "faith", "law", "mercy", "idolatry",
              "oppression", "sabbath", "resurrection", "grace", "judgment"]
    for topic in topics:
        d = sc.answer(topic)
        assert d["status"] == "FOUND", topic
        assert d["related_terms"], topic
        all_verses = [v for g in d["witnesses_by_section"] for v in g["verses"]]
        assert all_verses, topic
        for v in all_verses:                                     # every reference is REAL
            assert _is_real_ref(ix, v["reference"]), (topic, v["reference"])


def test_scribe_scope_narrowing_apocrypha(ix):
    from scribe import get_scribe

    d = get_scribe().answer("wisdom", scope="apocrypha")
    assert d["status"] == "FOUND"
    for g in d["witnesses_by_section"]:
        assert g["section"] == "apocrypha"


def test_scribe_cross_reference_intent(ix):
    from scribe import get_scribe

    d = get_scribe().answer("cross reference John 3:16")
    assert d["intent"] == "CROSS_REFERENCE" and d["status"] == "FOUND"
    assert d["primary"][0]["reference"] == "JHN 3:16"
    assert d["cross_references"]
    for x in d["cross_references"]:
        assert _is_real_ref(ix, x["reference"]) and x["reference"] != "JHN 3:16"


def test_scribe_doctrine_intent(ix):
    from scribe import get_scribe

    d = get_scribe().answer("doctrine of grace")
    assert d["intent"] == "DOCTRINE_STUDY" and d["status"] == "FOUND"
    assert d["exegesis"]["core_claim"]
    assert d["exegesis"]["structure"][0] == "Core claim"


def test_scribe_qa_format_grounded(ix):
    from scribe import get_scribe

    d = get_scribe().answer("what does scripture say about mercy")
    assert d["intent"] in ("QUESTION_ANSWER", "GENERAL_SCRIBE_EXPLANATION")
    assert d["qa"] and d["qa"]["witnesses"]
    for w in d["qa"]["witnesses"]:                  # Q&A cites only REAL retrieved verses
        assert _is_real_ref(ix, w["reference"]) and w["text"]


def test_scribe_qa_abstains_with_spec_message(ix):
    from scribe import get_scribe

    d = get_scribe().answer("what does scripture say about asdfqwer zzzz")
    assert d["status"] == "NOT_FOUND"
    assert d["qa"] is not None
    assert "do not have a grounded verse match" in d["qa"]["answer"]


def test_study_book_filter_invalid_is_structured(client):
    r = client.post("/api/study", json={"query": "wisdom", "book": "Nopebook"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "INVALID"
    assert isinstance(d["reason"], str) and d["reason"]
