"""test_sensory_injection.py — the perception→cognition seam (the keystone).

ADR-0001 §6.1 Layer 1 must turn raw input into evidence that REACHES cognition.
Before this seam, the pipeline built an EvidenceEnvelope but only attached its
salience/scope as telemetry — the derived content never entered what the LM reads.
Now a NON-text sense (image caption/OCR, audio transcript, sensor summary) fills
`EvidenceEnvelope.derived_text`, and cognitive_pipeline folds it into the prompt.

Invariants:
  1. A non-text envelope's derived_text appears in the message handed to the agent,
     tagged `[perception:<modality>]`.
  2. Plain text input is unchanged (derived_text="" → no prefix) — no regression.
  3. derived_text is INJECTION-ONLY: excluded from to_dict() so it never reaches
     telemetry/journal (ADR §13 "no raw content").

Run:  PYTHONPATH=ai/tokenless-agent/src python3 -m pytest tests/test_sensory_injection.py -q
"""
import asyncio
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

cp = pytest.importorskip("cognitive_pipeline")
ev = pytest.importorskip("sensory.evidence")


def _run_capturing(modality, derived_text, user_message="what is this?"):
    """Run the pipeline forcing a given envelope; return the message the agent saw."""
    seen = {}

    def _fake_chat(session_id, enriched):
        seen["enriched"] = enriched
        return "ok"

    orig = cp._build_evidence
    cp._build_evidence = lambda msg, session_id="": ev.build_evidence_envelope(
        msg, session_id=session_id, modality=modality, derived_text=derived_text)
    # Force NOMINAL interoception so these external-perception assertions are deterministic
    # regardless of the host's load (the degraded-self-sense injection is tested separately).
    orig_intero = cp.interoceptive_prefix
    cp.interoceptive_prefix = lambda: ("", False)
    try:
        async def _go():
            p = cp.CognitivePipeline()
            await p.execute(session_id="s", user_message=user_message,
                            agent_chat_fn=_fake_chat, heptagon_available=False)
        asyncio.run(_go())
    finally:
        cp._build_evidence = orig
        cp.interoceptive_prefix = orig_intero
    return seen.get("enriched", "")


def test_nontext_perception_reaches_the_model():
    enriched = _run_capturing("visual", "a photo of a sunrise over mountains")
    assert "a photo of a sunrise over mountains" in enriched, "perception not injected"
    assert "[perception:visual]" in enriched, "modality tag missing"
    assert enriched.strip().endswith("what is this?"), "user words must follow the perception"


def test_text_path_is_unchanged():
    enriched = _run_capturing("text", "", user_message="just a normal question")
    assert enriched == "just a normal question", "text path must not gain a perception prefix"


def test_derived_text_is_telemetry_safe():
    d = ev.build_evidence_envelope("x", modality="visual", derived_text="SECRET-CAPTION").to_dict()
    assert "derived_text" not in d, "derived_text must be excluded from to_dict"
    assert "SECRET-CAPTION" not in str(d), "derived content must never reach the serialized envelope"


# ── Interoception: the mandatory self-sense folds into cognition WHEN degraded ──
# Proves the per-turn interoceptive producer is genuinely CALLED (sense() runs every
# turn) and its injection branch fires on real degraded turns — not just in tests, and
# without polluting nominal turns. The degraded flag is forced (not read from the host)
# so the assertions are deterministic regardless of the test machine's actual load.

def _run_with_intero(degraded, user_message="status?"):
    seen = {}

    def _fake_chat(session_id, enriched):
        seen["enriched"] = enriched
        return "ok"

    from sensory import interoception as _io
    st = _io.sense()
    st.degraded = bool(degraded)               # force, override the host's real assessment
    if degraded and not st.notes:
        st.notes = ["high CPU load (forced for test)"]
    orig_sense = _io.sense
    _io.sense = lambda now=None: st
    # Keep external perception empty so we isolate the interoception branch.
    orig_be = cp._build_evidence
    cp._build_evidence = lambda msg, session_id="": ev.build_evidence_envelope(
        msg, session_id=session_id, modality="text", derived_text="")
    try:
        async def _go():
            p = cp.CognitivePipeline()
            await p.execute(session_id="s", user_message=user_message,
                            agent_chat_fn=_fake_chat, heptagon_available=False)
        asyncio.run(_go())
    finally:
        _io.sense = orig_sense
        cp._build_evidence = orig_be
    return seen.get("enriched", "")


def test_degraded_interoception_reaches_cognition():
    enriched = _run_with_intero(degraded=True)
    assert "[perception:interoception]" in enriched, "degraded self-state not injected into cognition"
    assert enriched.strip().endswith("status?"), "user words must follow the self-state perception"


def test_nominal_interoception_stays_silent():
    enriched = _run_with_intero(degraded=False)
    assert "[perception:interoception]" not in enriched, "nominal self-state must not pollute the prompt"
    assert enriched == "status?", "a nominal turn's prompt must be exactly the user's words"
