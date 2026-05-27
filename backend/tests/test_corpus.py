"""
test_corpus.py — Tests for backend/corpus.py retrieval functions.

Covers the SLICE-0001 retrieval surface:
  - VerseIndex.load() builds book/chapter/verse maps from data/verses.jsonl
  - lookup_ref handles direct refs ("John 3:16"), partial book names
    ("prov 31:10"), and chapter-only refs ("Prov 31")
  - lookup_ref_range expands "Numbers 15:37-41" into 5 verse records
  - search_prefix tier 1 (>=8 char prefix) and tier 3 (multi-word) work
  - build_corpus_context produces a training-format block for the AI path
"""
import pytest

from corpus import VerseIndex


@pytest.fixture(scope="module")
def index():
    idx = VerseIndex()
    idx.load()
    return idx


# --- TEST-corpus-lookup-ref ---

def test_lookup_ref_direct_full_name(index):
    v = index.lookup_ref("John 3:16")
    assert v is not None
    assert v["book"] == "JHN"
    assert v["chapter"] == 3
    assert v["verse"] == 16
    assert "God so loved the world" in v["text"]


def test_lookup_ref_code(index):
    v = index.lookup_ref("GEN 1:1")
    assert v is not None
    assert v["book"] == "GEN"
    assert v["chapter"] == 1
    assert v["verse"] == 1
    assert v["text"].startswith("In the beginning")


def test_lookup_ref_partial_book_name(index):
    v = index.lookup_ref("prov 31:10")
    assert v is not None
    assert v["book"] == "PRO"
    assert v["chapter"] == 31
    assert v["verse"] == 10


def test_lookup_ref_chapter_only(index):
    v = index.lookup_ref("Prov 31")
    assert v is not None
    assert v["book"] == "PRO"
    assert v["chapter"] == 31
    assert v["verse"] == 1


def test_lookup_ref_unknown_book(index):
    assert index.lookup_ref("Hogwarts 1:1") is None


def test_lookup_ref_garbage(index):
    assert index.lookup_ref("this is not a reference") is None


# --- TEST-corpus-lookup-range ---

def test_lookup_ref_range_multi_verse(index):
    verses = index.lookup_ref_range("Numbers 15:37-41")
    assert len(verses) == 5
    assert verses[0]["verse"] == 37
    assert verses[-1]["verse"] == 41
    assert all(v["book"] == "NUM" and v["chapter"] == 15 for v in verses)


def test_lookup_ref_range_single_verse_fallthrough(index):
    # "John 3:16" has no range suffix → falls through to single-verse lookup_ref
    verses = index.lookup_ref_range("John 3:16")
    assert len(verses) == 1
    assert verses[0]["book"] == "JHN"
    assert verses[0]["verse"] == 16


def test_lookup_ref_range_miss(index):
    assert index.lookup_ref_range("Bogus 99:1-3") == []


# --- TEST-corpus-search-prefix ---

def test_search_prefix_tier1_prefix_match(index):
    # "In the beginning" is the literal opening of GEN 1:1
    v = index.search_prefix("In the beginning God")
    assert v is not None
    assert v["book"] == "GEN" and v["chapter"] == 1 and v["verse"] == 1


def test_search_prefix_tier3_multi_word(index):
    # Multi-word keyword set; expect 2TI 2:15 ("Study to shew thyself approved")
    v = index.search_prefix("Study and shew thyself")
    assert v is not None
    # Verse text must contain the content words
    text_lower = v["text"].lower()
    assert "study" in text_lower
    assert "shew" in text_lower


def test_search_prefix_too_short_returns_none(index):
    assert index.search_prefix("the") is None


# --- build_corpus_context smoke ---

def test_build_corpus_context_includes_target_verse(index):
    verse = index.lookup_ref("Psalm 23:1")
    assert verse is not None
    ctx = index.build_corpus_context(verse, partial_text="The LORD")
    assert "<|source:kjv:" in ctx
    assert "PSA 23:1 The LORD" in ctx
    # Target is the LAST line (per docstring)
    assert ctx.rstrip().endswith("PSA 23:1 The LORD")
