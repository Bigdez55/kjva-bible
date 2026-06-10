"""sensory/asr.py — Auditory/Speech perception: a PORTABLE, pluggable ASR seam.

ADR-0001 §7.1 Auditory (hearing) + Speech/Vocal. Turns inbound audio into a transcript
that becomes the turn's message, completing the voice loop:

    audio -> [ASR] -> transcript -> cognition -> [TTS] -> audio

PORTABILITY ("use it anywhere on anything"). This module is **pure stdlib and always
importable** — the seam exists on every platform. The actual speech engine is
**pluggable**: a host registers whatever ASR it has (Apple Speech, Android
SpeechRecognizer, whisper.cpp, a remote relay, …) via :func:`register_engine`. If none
is registered, the resolver best-effort auto-tries common portable engines
(faster-whisper, then openai-whisper). If nothing is available it degrades gracefully
(``ok=False``) — perception never hard-fails, and any engine slots into the same seam.

An engine is just a callable ``(audio_bytes: bytes, sample_rate: int, fmt: str) -> str``.
"""
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger("tokenless.sensory.asr")

# An ASR engine: raw audio bytes + sample rate + container fmt -> transcript text.
AsrEngine = Callable[[bytes, int, str], str]

_registered_engine: Optional[AsrEngine] = None
_registered_name: str = ""
_auto_engine: Optional[AsrEngine] = None
_auto_name: str = ""
_auto_tried: bool = False


@dataclass
class AsrResult:
    """Result of a transcription attempt."""
    transcript: str       # the recognized words ("" if none / no engine)
    engine: str           # engine that produced it ("" if none ran)
    ok: bool              # True iff an engine actually ran (text may still be "")


def register_engine(fn: AsrEngine, *, name: str = "custom") -> None:
    """Plug a platform-native ASR engine (last registration wins).

    This is the portable seam: a host on ANY OS/runtime supplies its own
    speech-to-text here, and the rest of the model is unchanged.
    """
    global _registered_engine, _registered_name
    _registered_engine = fn
    _registered_name = name
    logger.info("ASR engine registered: %s", name)


def reset_engine() -> None:
    """Clear a registered engine (mainly for tests)."""
    global _registered_engine, _registered_name
    _registered_engine = None
    _registered_name = ""


# ── Best-effort portable auto-engines (only used if nothing is registered) ────────

def _build_auto_engine() -> tuple[Optional[AsrEngine], str]:
    """Resolve a portable engine, SELF-INSTALLING it if missing (no manual setup).
    Never raises."""
    from . import provision
    # faster-whisper (CTranslate2 — fast, CPU/GPU, portable wheels, auto model download).
    if provision.ensure("faster_whisper", "faster-whisper"):
        try:
            from faster_whisper import WhisperModel  # type: ignore

            _model = WhisperModel("base", device="cpu", compute_type="int8")

            def _fw(audio_bytes: bytes, sample_rate: int, fmt: str) -> str:
                with tempfile.NamedTemporaryFile(suffix="." + (fmt or "wav")) as fh:
                    fh.write(audio_bytes); fh.flush()
                    segments, _info = _model.transcribe(fh.name)
                    return " ".join(s.text for s in segments).strip()

            logger.info("ASR auto-engine: faster-whisper (base)")
            return _fw, "faster-whisper"
        except Exception:  # noqa: BLE001
            pass
    # openai-whisper (reference implementation; pip-installable anywhere).
    if provision.ensure("whisper", "openai-whisper"):
        try:
            import whisper  # type: ignore

            _model = whisper.load_model("base")

            def _w(audio_bytes: bytes, sample_rate: int, fmt: str) -> str:
                with tempfile.NamedTemporaryFile(suffix="." + (fmt or "wav")) as fh:
                    fh.write(audio_bytes); fh.flush()
                    return str(_model.transcribe(fh.name).get("text", "")).strip()

            logger.info("ASR auto-engine: openai-whisper (base)")
            return _w, "openai-whisper"
        except Exception:  # noqa: BLE001
            pass
    return None, ""


def _resolve() -> tuple[Optional[AsrEngine], str]:
    if _registered_engine is not None:
        return _registered_engine, _registered_name
    global _auto_engine, _auto_name, _auto_tried
    if not _auto_tried:
        _auto_tried = True
        _auto_engine, _auto_name = _build_auto_engine()
    return _auto_engine, _auto_name


def present() -> bool:
    """Pure, CHEAP readiness check for status reporting: a registered engine, or the default
    package already importable — WITHOUT provisioning/installing or building a model. Use this
    on hot/status paths (e.g. GET /v1/senses) so a status read never triggers a heavy install."""
    if _registered_engine is not None:
        return True
    import importlib.util
    return any(importlib.util.find_spec(m) is not None
               for m in ("faster_whisper", "whisper"))


def available() -> bool:
    """True if some ASR engine (registered or auto-resolved) is ready. May auto-provision —
    use present() on status/hot paths."""
    return _resolve()[0] is not None


def engine_name() -> str:
    return _resolve()[1]


def transcribe(audio_bytes: bytes, sample_rate: int = 16000, fmt: str = "wav") -> AsrResult:
    """Transcribe inbound audio. FAIL-OPEN: returns ok=False (never raises) if no
    engine is available or the engine errors — the caller treats that as 'didn't hear'."""
    if not audio_bytes:
        return AsrResult("", "", False)
    engine, name = _resolve()
    if engine is None:
        return AsrResult("", "", False)
    try:
        text = engine(audio_bytes, int(sample_rate or 16000), fmt or "wav") or ""
        return AsrResult(text.strip(), name, True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ASR engine '%s' failed (treated as not-heard): %s", name, exc)
        return AsrResult("", name, False)
