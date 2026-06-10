"""test_vision.py — vision: the model SEES (pluggable image→text seam + perception injection).

sensory/vision.py is a portable, pluggable image→text seam: a host registers any captioner/OCR
via register_engine(); /v1/chat captions `image_in` and injects it as visual context
(modality="visual") ALONGSIDE the text/voice message, through the cognitive_pipeline
perception seam — so the caption actually reaches what the model reads.

Tested WITHOUT a real vision engine by registering a fake one — proving the seam + injection
are correct and engine-agnostic ("anywhere on anything").

Run:  PYTHONPATH=ai/tokenless-agent/src python3 -m pytest tests/test_vision.py -q
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
vision = pytest.importorskip("sensory.vision")

_DUMMY_IMAGE = {"format": "png", "base64": base64.b64encode(b"\x89PNG\r\n....fake....").decode("ascii")}


def _chat_capturing(**kw):
    """Run a chat turn, returning (response, message_the_model_saw)."""
    seen = {}
    orig = api._agent.chat

    def _spy(session_id, enriched):
        seen["enriched"] = enriched
        return orig(session_id, enriched)

    api._agent.chat = _spy
    try:
        r = asyncio.run(api.chat(api.ChatRequest(**kw), _auth=None))
    finally:
        api._agent.chat = orig
    return r, seen.get("enriched", "")


@pytest.fixture(autouse=True)
def _clean_engine():
    vision.reset_engine()
    yield
    vision.reset_engine()


def test_caption_reaches_the_model_alongside_the_question():
    vision.register_engine(lambda b, fmt: "a photo of a mountain at sunrise", name="fake-vision")
    r, enriched = _chat_capturing(session_id="s", message="what is this?", image_in=_DUMMY_IMAGE)
    assert "a photo of a mountain at sunrise" in enriched, "caption not injected into the model input"
    assert "[perception:visual]" in enriched, "visual modality tag missing"
    assert "what is this?" in enriched, "the user's question must still be present"
    assert r.provenance.get("saw") is True
    assert r.provenance.get("vision_engine") == "fake-vision"


def test_image_only_turn_describes_what_it_sees():
    vision.register_engine(lambda b, fmt: "text in image: HOLY BIBLE", name="fake-vision")
    r, enriched = _chat_capturing(session_id="s", image_in=_DUMMY_IMAGE)  # no message
    assert "text in image: HOLY BIBLE" in enriched
    assert "Describe what you see" in enriched, "image-only turn should prompt a description"
    assert r.provenance.get("saw") is True


def test_no_engine_is_fail_open_not_silent():
    # No engine registered; if the env also lacks auto-OCR, an image alone can't be seen.
    if vision.available():
        pytest.skip("a vision engine is actually available in this env")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        asyncio.run(api.chat(api.ChatRequest(session_id="s", image_in=_DUMMY_IMAGE), _auth=None))
    assert ei.value.status_code == 422
    # But WITH a text question, the turn still proceeds (vision just adds nothing).
    r = asyncio.run(api.chat(api.ChatRequest(session_id="s", message="hello", image_in=_DUMMY_IMAGE), _auth=None))
    assert r.provenance.get("saw") is False and isinstance(r.response, str)


def test_vision_seam_describe_is_fail_open():
    vision.reset_engine()
    if not vision.available():
        res = vision.describe(b"\x89PNG fake", "png")
        assert res.ok is False and res.derived_text == "", "no-engine must degrade, not raise"
