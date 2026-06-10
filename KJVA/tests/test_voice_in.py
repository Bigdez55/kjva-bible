"""test_voice_in.py — voice-in: the model HEARS (pluggable ASR seam + the full voice loop).

sensory/asr.py is a portable, pluggable ASR seam: a host registers any speech engine via
register_engine(); /v1/chat transcribes `audio_in` into the turn's message BEFORE the
covenant gate. This completes the loop: audio -> transcript -> cognition -> (TTS) -> audio.

Tested WITHOUT a real ASR engine by registering a fake one — proving the seam + wiring
are correct and engine-agnostic ("anywhere on anything").

Invariants:
  1. A registered ASR engine's transcript becomes the turn's message; provenance.heard
     True + asr_engine recorded; a real response comes back.
  2. Full voice loop: audio_in + speak=true -> heard transcript in, spoken audio out.
  3. audio_in with NO engine available + no text -> 422 (fail-open, never silent).
  4. The seam is engine-agnostic: register_engine swaps the backend with no other change.

Run:  PYTHONPATH=ai/tokenless-agent/src python3 -m pytest tests/test_voice_in.py -q
"""
import asyncio
import base64
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

pytest.importorskip("fastapi", reason="FastAPI not installed")
api = pytest.importorskip("api")
asr = pytest.importorskip("sensory.asr")

_DUMMY_AUDIO = {"format": "wav", "sample_rate": 16000,
                "base64": base64.b64encode(b"RIFF....fake-pcm....").decode("ascii")}


def _chat(**kw):
    return asyncio.run(api.chat(api.ChatRequest(**kw), _auth=None))


@pytest.fixture(autouse=True)
def _clean_engine():
    asr.reset_engine()
    yield
    asr.reset_engine()


def test_model_hears_registered_engine():
    asr.register_engine(lambda b, sr, fmt: "What does Psalm 23 verse 1 say", name="fake-asr")
    r = _chat(session_id="s", audio_in=_DUMMY_AUDIO)
    assert r.provenance.get("heard") is True, "model did not register hearing the audio"
    assert r.provenance.get("asr_engine") == "fake-asr"
    assert isinstance(r.response, str) and r.response, "no response produced from the transcript"


def test_full_voice_loop_in_and_out():
    if not api._TTS_AVAILABLE:
        pytest.skip("TTS engine not built — voice-out half unavailable")
    asr.register_engine(lambda b, sr, fmt: "Psalm 23:1", name="fake-asr")
    r = _chat(session_id="s", audio_in=_DUMMY_AUDIO, speak=True)
    # heard in...
    assert r.provenance.get("heard") is True
    # ...and spoke out
    assert r.audio is not None and r.audio["format"] == "wav"
    assert base64.b64decode(r.audio["base64"])[:4] == b"RIFF"
    assert r.provenance.get("spoken") is True


def test_audio_with_no_engine_fails_open_not_silent():
    # No engine registered, and the auto-resolver has no whisper here -> can't hear.
    if asr.available():
        pytest.skip("an ASR engine is actually available in this env; can't test the no-engine path")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        _chat(session_id="s", audio_in=_DUMMY_AUDIO)  # no text, can't transcribe
    assert ei.value.status_code == 422, "no-input must 422, never silently proceed"


def test_text_still_wins_when_both_present():
    asr.register_engine(lambda b, sr, fmt: "SHOULD-NOT-BE-USED", name="fake-asr")
    r = _chat(session_id="s", message="Psalm 23:1", audio_in=_DUMMY_AUDIO)
    assert r.provenance.get("heard") is False, "text was provided; audio must not be transcribed"
