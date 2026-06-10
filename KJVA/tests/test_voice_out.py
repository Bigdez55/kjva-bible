"""test_voice_out.py — voice-first: the model SPEAKS its responses (TTS wiring).

ai/tts/ is a working formant synthesizer (tts_bridge.speak -> WAV bytes). It existed
but was never called by the runtime. /v1/chat now synthesizes speech when the client
sets `speak=true`, returning {format, sample_rate, base64} audio; text-only otherwise.

Invariants:
  1. speak=true  -> response.audio carries real (>1KB) WAV bytes; provenance.spoken True.
  2. speak=false -> response.audio is None; provenance.spoken False (text unaffected).
  3. Fail-open: if TTS is unavailable in this environment, skip (never hard-fail).

Run:  PYTHONPATH=ai/tokenless-agent/src python3 -m pytest tests/test_voice_out.py -q
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


def _chat(**kw):
    return asyncio.run(api.chat(api.ChatRequest(**kw), _auth=None))


def test_model_speaks_when_asked():
    if not api._TTS_AVAILABLE:
        pytest.skip("TTS engine not built in this environment (ai/tts/build/libtts.*)")
    r = _chat(session_id="s", message="Psalm 23:1", speak=True)
    assert r.audio is not None, "speak=true must return audio"
    assert r.audio["format"] == "wav" and r.audio["sample_rate"] == 22050
    wav = base64.b64decode(r.audio["base64"])
    assert len(wav) > 1000, f"expected real WAV bytes, got {len(wav)}"
    assert wav[:4] == b"RIFF", "not a WAV container"
    assert r.provenance.get("spoken") is True


def test_text_only_by_default():
    r = _chat(session_id="s", message="Psalm 23:1", speak=False)
    assert r.audio is None, "no audio unless speak=true"
    assert r.provenance.get("spoken") is False
    assert isinstance(r.response, str) and r.response, "text response must still be present"
