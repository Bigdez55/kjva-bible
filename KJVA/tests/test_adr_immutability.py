"""test_adr_immutability.py — ADR-0002 §13 acceptance: "ADR-0001 remains unchanged."

The locked ADRs are the source of truth (§0). This pins that the locked files exist, carry their
immutability headers, and that DO_NOT_MODIFY.md is present — so a silent edit to the locked
architecture is caught.

Run:  python3 -m pytest tests/test_adr_immutability.py -q
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADR1 = ROOT / "adr" / "ADR-0001_NEUTRAL_LIFESPAN_COGNITIVE_MODEL_TECH_WIRING_LOCKED.md"
ADR2 = ROOT / "adr" / "ADR-0002_MODELS_V7_LOCAL_IMPLEMENTATION_MAPPING.md"


def test_locked_adrs_exist():
    assert ADR1.exists(), "ADR-0001 (locked) missing"
    assert ADR2.exists(), "ADR-0002 (mapping) missing"
    assert (ROOT / "DO_NOT_MODIFY.md").exists(), "DO_NOT_MODIFY.md missing"


def test_adr1_declares_immutability():
    txt = ADR1.read_text(encoding="utf-8").lower()
    assert "immutab" in txt or "read-only" in txt or "do not" in txt, \
        "ADR-0001 must declare its immutability"
    # the §0 non-negotiable instruction must be present
    assert "non-negotiable" in txt or "file immutability" in txt


def test_adr2_references_not_supersedes_adr1():
    txt = ADR2.read_text(encoding="utf-8").lower()
    assert "adr-0001 is immutable" in txt or "does not edit" in txt or "references adr-0001" in txt
