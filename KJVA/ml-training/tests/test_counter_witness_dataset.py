"""
Tests for the Scripture Counter-Witness dataset (alignment_counter_witness_v1.jsonl).

These lock the OWNER-directed counter-witness design at the DATA layer (the
runtime retriever + router that maps intent->category->scripture is a separate
piece). The load-bearing discipline: NO fabricated scripture — every cited
counter-witness reference must resolve to a real verse in the corpus.

Owner test intents covered here at dataset level:
  - false-witness / theft / exploitation / harm categories each carry scripture
  - no generated scripture without retrieval provenance (every ref exists)
  - response includes category, citation, basis, and safe redirect
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent


def _first_existing(*cands: Path) -> Path:
    """Resolve a file across layouts (substrate nested as 'models v7/' vs deployed flat)."""
    for c in cands:
        if c.exists():
            return c
    return cands[0]  # report the canonical candidate in the failure message


# dataset lives under the substrate tree: 'models v7/training/...' (nested repo)
# or 'training/...' (deployed flat KJVA root)
_DATASET = _first_existing(
    _REPO / "models v7/training/corpus/programs/alignment_counter_witness_v1.jsonl",
    _REPO / "training/corpus/programs/alignment_counter_witness_v1.jsonl",
)
# retrieval index lives under ml-training/ in both layouts (sibling of the tree)
_INDEX = _first_existing(
    _REPO / "ml-training/corpus/eng_kjv_apocrypha_v1/retrieval_index.json",
    _REPO / "corpus/eng_kjv_apocrypha_v1/retrieval_index.json",
)

ABSOLUTE_CATEGORIES = {
    "harm_prevention", "false_witness", "manipulation", "identity_integrity",
    "oppression_or_exploitation", "theft_or_fraud",
}


def _rows():
    return [json.loads(l) for l in _DATASET.read_text().splitlines() if l.strip()]


def _corpus_ids():
    idx = json.loads(_INDEX.read_text())
    return {d["id"] for d in idx["documents"]}


def _ref_to_id(ref: str) -> str:
    """'EXO 20:13' -> 'EXO.20.13'; '2TI 2:15' -> '2TI.2.15'."""
    book, cv = ref.split(" ", 1)
    ch, vs = cv.split(":")
    return f"{book}.{ch}.{vs}"


def test_dataset_exists_and_nonempty():
    assert _DATASET.exists()
    assert len(_rows()) >= 7  # at least one per owner category


def test_every_counter_witness_reference_is_grounded():
    """No fabricated scripture: every cited reference resolves in the corpus."""
    ids = _corpus_ids()
    bad = []
    for r in _rows():
        for cw in r.get("counter_witnesses", []):
            cid = _ref_to_id(cw["reference"])
            if cid not in ids:
                bad.append((r["category"], cw["reference"], cid))
    assert not bad, f"ungrounded counter-witness references: {bad}"


def test_each_row_has_structure_category_citation_basis_redirect():
    """Response must carry category, >=1 citation, constitutional_basis, safe_redirect."""
    for r in _rows():
        assert r.get("category"), f"missing category: {r}"
        assert r.get("counter_witnesses"), f"no counter_witnesses: {r['category']}"
        assert r.get("constitutional_basis"), f"no basis: {r['category']}"
        assert r.get("safe_redirect"), f"no safe_redirect: {r['category']}"
        out = r["expected_output"]
        # citation may appear in abbrev ('EXO 20:13') or full-name ('Exodus 20:13')
        # form; assert the chapter:verse anchor is present.
        cv = r["counter_witnesses"][0]["reference"].split(" ", 1)[1]  # '20:13'
        assert cv in out, (
            f"expected_output omits its first citation ({cv}): {r['category']}")


def test_absolute_categories_hard_stop_no_open_authority():
    """ABSOLUTE-covenant rows must hard_stop and never allow any/owner authority."""
    for r in _rows():
        if r["category"] in ABSOLUTE_CATEGORIES:
            assert r["required_action"] == "hard_stop", r["category"]
            assert r["allowed_authority"] in ("none",), (
                f"{r['category']} allows {r['allowed_authority']}")


def test_owner_categories_have_counter_witness_coverage():
    """Each owner-named governance category is represented with scripture."""
    cats = {r["category"] for r in _rows()}
    for required in ("harm_prevention", "false_witness", "theft_or_fraud",
                     "oppression_or_exploitation", "manipulation",
                     "identity_integrity", "canonical_weight_authority"):
        assert required in cats, f"counter-witness coverage missing: {required}"


def test_no_verbatim_scripture_emission_uses_function_glosses():
    """Counter-witness 'use' fields are functional glosses, not verbatim verses
    (adapter routes/cites; retrieval supplies exact text)."""
    for r in _rows():
        for cw in r["counter_witnesses"]:
            assert "use" in cw and cw["use"], f"missing use gloss: {cw}"
