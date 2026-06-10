"""
ai/tts/tts_bridge.py -- Import-safe Python bridge for the XTTS formant engine.

Copyright (c) 2026 Tokenless Models Project. All rights reserved.
SPDX-License-Identifier: LicenseRef-Proprietary

WHY THIS EXISTS
  ai/tts/tts_engine.c is a complete DECTalk-style formant synthesizer with
  *zero* Python integration (Ledger D32). This module is the thin bridge that
  makes it callable from the agent runtime without ever crashing the import:

    * If a built shared library (build/libtts.{dylib,so}) is present, the
      bridge wraps it via ctypes and `speak(text)` returns 16-bit mono WAV
      bytes synthesized by the C engine.
    * If no library is present (the default state of a fresh checkout — the
      binary is a gitignored artifact), the bridge logs ONCE and degrades to
      a disabled stub: `speak(text)` returns None. No exception, no crash.

  The spine (api.py) owns the call site; this module never imports or edits it.

CONCURRENCY
  The underlying C engine is PROCESS-GLOBAL: a single `static xtts_state_block_t
  s_tts` plus a single static PCM scratch buffer reused per phoneme. It is NOT
  reentrant. Because the spine is an HTTP server (concurrent requests), this
  bridge serializes every synthesis call behind a module-level lock so two
  callers can never tear each other's PCM or race xtts_init(). `wpm`/`voice`
  set sticky global engine state and are applied inside the locked region.

AUTHORITY
  Implements the TTS wiring locked by ADR-0001 (Neutral Lifespan Cognitive
  Model — Tech Wiring Locked) and the local implementation mapping in
  ADR-0002 (Models V7 Local Implementation Mapping). This bridge is the
  additive D32 integration layer; it does not alter the spine contract.

PUBLIC API
  speak(text, voice="default", *, wpm=None) -> bytes | None
      Returns WAV bytes (live) or None (disabled). Never raises for ordinary
      input; on an unexpected engine fault it logs and returns None.

  is_available() -> bool          # True iff the C engine is loaded and live.
  status() -> dict                # Introspection: mode, lib path, sample rate.

  VOICE_DEFAULT / VOICE_MALE / VOICE_FEMALE  # voice id constants.

BUILD
  Run `make` in this directory (ai/tts/) to produce build/libtts.<soext>.
  No build tool / no library == permanent clean stub mode.
"""
from __future__ import annotations

import ctypes
import io
import logging
import os
import sys
import threading
import wave
from ctypes.util import find_library  # noqa: F401  (kept for future fallbacks)
from typing import Optional

logger = logging.getLogger("tts_bridge")

# ── Engine constants (mirror tts_engine.h; keep in sync) ───────────────────
SAMPLE_RATE = 22050          # XTTS_SAMPLE_RATE
_BYTES_PER_SAMPLE = 2        # int16_t mono
_CHANNELS = 1

VOICE_DEFAULT = 0            # XTTS_VOICE_DEFAULT
VOICE_MALE = 1               # XTTS_VOICE_MALE
VOICE_FEMALE = 2             # XTTS_VOICE_FEMALE

_VOICE_BY_NAME = {
    "default": VOICE_DEFAULT,
    "male": VOICE_MALE,
    "female": VOICE_FEMALE,
}

# The C engine is process-global and non-reentrant; serialize all synthesis.
_engine_lock = threading.Lock()

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB_BASENAMES = ("libtts.dylib", "libtts.so")
# Search the conventional build dir, then this dir, then an env override.
_LIB_SEARCH_DIRS = (
    os.path.join(_HERE, "build"),
    _HERE,
)


# ── ctypes callback signature: void(const int16_t*, uint32_t, void*) ───────
_PCM_CALLBACK = ctypes.CFUNCTYPE(
    None,
    ctypes.POINTER(ctypes.c_int16),  # samples
    ctypes.c_uint32,                 # count
    ctypes.c_void_p,                 # userdata (unused)
)


def _candidate_lib_paths():
    """Yield possible shared-library paths, env override first."""
    override = os.environ.get("TTS_ENGINE_LIB")
    if override:
        yield override
    for d in _LIB_SEARCH_DIRS:
        for base in _LIB_BASENAMES:
            yield os.path.join(d, base)


class _Engine:
    """Holds the loaded ctypes handle and bound, type-annotated functions.

    Constructed lazily exactly once. If construction fails for any reason the
    bridge stays in disabled stub mode for the life of the process.
    """

    def __init__(self) -> None:
        self.lib_path: Optional[str] = None
        self._handle: Optional[ctypes.CDLL] = None
        self._initialized = False

        path = next((p for p in _candidate_lib_paths() if os.path.exists(p)), None)
        if path is None:
            raise FileNotFoundError("no libtts shared library found")

        handle = ctypes.CDLL(path)

        # Bind ONLY what we use, with explicit argtypes/restype. Without these
        # ctypes assumes int returns and truncates 64-bit pointers.
        handle.xtts_init.argtypes = []
        handle.xtts_init.restype = None

        handle.xtts_speak_cb.argtypes = [
            ctypes.c_char_p,     # text
            ctypes.c_int,        # voice (enum -> int)
            _PCM_CALLBACK,       # callback
            ctypes.c_void_p,     # userdata
        ]
        handle.xtts_speak_cb.restype = None

        # Optional knobs — bind defensively (present in this engine build).
        if hasattr(handle, "xtts_set_rate_wpm"):
            handle.xtts_set_rate_wpm.argtypes = [ctypes.c_uint32]
            handle.xtts_set_rate_wpm.restype = None

        self._handle = handle
        self.lib_path = path

    def _ensure_init(self) -> None:
        # xtts_speak_cb() has `if (!s_tts.initialized) return;` — it produces
        # ZERO output until xtts_init() runs. Do it once, lazily.
        if not self._initialized:
            self._handle.xtts_init()  # type: ignore[union-attr]
            self._initialized = True

    def synth_pcm(self, text: str, voice: int, wpm: Optional[int]) -> bytes:
        """Drive xtts_speak_cb and accumulate raw little-endian int16 PCM.

        Holds the module lock for the entire native interaction: init, the
        sticky wpm/voice config, the static scratch buffer, and the global
        engine state are all process-shared and must not be touched by a
        second thread mid-synthesis.
        """
        pcm = bytearray()

        def _on_pcm(samples, count, _userdata):  # matches _PCM_CALLBACK
            if samples and count:
                # int16 -> 2 bytes each; macOS/x86/arm are little-endian =>
                # already WAV byte order. string_at copies a private snapshot.
                pcm.extend(ctypes.string_at(samples, int(count) * _BYTES_PER_SAMPLE))

        cb = _PCM_CALLBACK(_on_pcm)  # keep referenced for the whole call

        with _engine_lock:
            self._ensure_init()
            if wpm is not None and hasattr(self._handle, "xtts_set_rate_wpm"):
                self._handle.xtts_set_rate_wpm(ctypes.c_uint32(int(wpm)))
            self._handle.xtts_speak_cb(  # type: ignore[union-attr]
                text.encode("utf-8"),
                ctypes.c_int(int(voice)),
                cb,
                None,
            )
        return bytes(pcm)


# ── Lazy singleton + one-time disabled-mode log ────────────────────────────
_engine: Optional[_Engine] = None
_load_attempted = False
_disabled_logged = False


def _get_engine() -> Optional[_Engine]:
    global _engine, _load_attempted, _disabled_logged
    if _load_attempted:
        return _engine
    _load_attempted = True
    try:
        _engine = _Engine()
        logger.info("[tts_bridge] live — engine loaded from %s", _engine.lib_path)
    except Exception as exc:
        _engine = None
        if not _disabled_logged:
            logger.info(
                "[tts_bridge] disabled (stub) — %s; run `make` in ai/tts/ to enable",
                exc,
            )
            _disabled_logged = True
    return _engine


def _pcm_to_wav(pcm: bytes) -> bytes:
    """Wrap raw int16 mono PCM as a self-describing WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(_CHANNELS)
        w.setsampwidth(_BYTES_PER_SAMPLE)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


# ── Public API ─────────────────────────────────────────────────────────────
def is_available() -> bool:
    """True iff the C engine is loaded and the live synthesis path is usable."""
    return _get_engine() is not None


def status() -> dict:
    """Introspection dict for health checks / spine wiring."""
    eng = _get_engine()
    return {
        "mode": "live" if eng else "disabled",
        "lib_path": eng.lib_path if eng else None,
        "sample_rate": SAMPLE_RATE,
        "channels": _CHANNELS,
        "sample_format": "int16-le",
        "container": "wav",
    }


def speak(text: str, voice: str | int = "default", *, wpm: Optional[int] = None) -> Optional[bytes]:
    """Synthesize `text` to speech.

    Returns:
        WAV bytes (16-bit mono PCM @ 22050 Hz) when the engine is live, or
        None when disabled / on empty input / on an unexpected engine fault.
        None is the spine's "skip audio" signal — callers must handle it.
    """
    if not text or not str(text).strip():
        return None

    eng = _get_engine()
    if eng is None:
        return None  # disabled stub — already logged once at load time.

    if isinstance(voice, str):
        voice_id = _VOICE_BY_NAME.get(voice.lower(), VOICE_DEFAULT)
    else:
        voice_id = int(voice)

    try:
        pcm = eng.synth_pcm(str(text), voice_id, wpm)
    except Exception as exc:  # never let a native fault propagate to the spine
        logger.warning("[tts_bridge] synthesis fault, returning None: %s", exc)
        return None

    if not pcm:
        # Engine ran but produced no samples (e.g. all-punctuation input).
        return None
    return _pcm_to_wav(pcm)


# ── Self-test: must exit 0 in BOTH live and disabled modes ─────────────────
def _selftest() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    st = status()
    sample = "Hello Nexus, this is a test of the formant synthesizer."

    if not is_available():
        # Disabled is the *designed* state of a fresh checkout (no lib).
        assert speak(sample) is None, "stub speak() must return None"
        assert speak("") is None, "empty input must return None"
        print(f"[tts_bridge SELFTEST] DISABLED — no lib found "
              f"(searched build/ + cwd; set TTS_ENGINE_LIB or run `make`). status={st}")
        return 0

    wav = speak(sample)
    assert isinstance(wav, (bytes, bytearray)) and len(wav) > 44, \
        f"live speak() must return WAV bytes, got {type(wav)} len={len(wav) if wav else 0}"
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE", "output must be a WAV container"
    # Voice variants and empty-input contract.
    assert speak(sample, voice="female") is not None
    assert speak("") is None, "empty input must return None even when live"
    print(f"[tts_bridge SELFTEST] LIVE — {len(wav)} WAV bytes "
          f"({(len(wav) - 44) // (_BYTES_PER_SAMPLE)} samples @ {SAMPLE_RATE}Hz). "
          f"lib={st['lib_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(_selftest())
