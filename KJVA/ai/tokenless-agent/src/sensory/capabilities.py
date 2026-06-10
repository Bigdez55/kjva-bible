"""sensory/capabilities.py — explicit sense manifest (ADR-0001 §16.4 conformance).

ADR-0001 §16.4: every spec-optional sense must either EXIST or be EXPLICITLY marked
"unsupported" — silent gaps are non-conformant. This module is that explicit declaration:
the live status of all 13 ADR-0001 §7.1 sensory classes. Interoceptive is mandatory
(no opt-out) and is built; text is native; speech/vision are pluggable, self-provisioning
seams; the rest are declared unsupported-but-pluggable (a host can register an engine).

Status values:
  native       — the model's intrinsic channel (no engine needed)
  built        — implemented in-tree (always available)
  seam         — pluggable adapter present; `available` reflects a live/auto-provisionable engine
  unsupported  — explicitly NOT implemented (declared, not silent); pluggable via register_engine
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class SenseStatus:
    sense: str            # ADR-0001 §7.1 class name
    analogue: str         # human analogue
    status: str           # native | built | seam | unsupported
    mandatory: bool       # §16.4 no-opt-out
    available: bool       # is it usable on this turn right now?
    mechanism: str        # how it is realized / how to enable

    def to_dict(self) -> dict:
        return asdict(self)


def _seam_available(mod_name: str) -> bool:
    # Use present() (pure import-check) NOT available() — reporting the manifest must never
    # trigger a heavy engine build / pip install on the status path (GET /v1/senses).
    try:
        from importlib import import_module
        return bool(import_module("sensory." + mod_name).present())
    except Exception:  # noqa: BLE001
        return False


def _intero_available() -> bool:
    """Live probe of the MANDATORY interoceptive sense — produced-without-raising, so
    mandatory_satisfied can actually be FALSE if the sense breaks (was hardcoded True)."""
    try:
        from . import interoception
        return interoception.sense() is not None
    except Exception:  # noqa: BLE001
        return False


def _tts_available() -> bool:
    """Live probe of voice-out: reflect api._TTS_AVAILABLE (was hardcoded True)."""
    try:
        import sys
        api = sys.modules.get("api")
        if api is not None and hasattr(api, "_TTS_AVAILABLE"):
            return bool(api._TTS_AVAILABLE)
        from importlib import import_module          # standalone fallback
        return callable(getattr(import_module("tts_bridge"), "speak", None))
    except Exception:  # noqa: BLE001
        return False


def manifest() -> list[dict]:
    """The live status of every ADR §7.1 sense. `available` is evaluated now (seam-aware)."""
    asr_ok = _seam_available("asr")
    vis_ok = _seam_available("vision")
    rows = [
        SenseStatus("Speech/Vocal-text", "language (read/write)", "native", False, True,
                    "byte-level model; the intrinsic channel"),
        SenseStatus("Speech/Vocal-out", "spoken language (out)", "built", False, _tts_available(),
                    "ai/tts formant synthesizer; ChatRequest.speak=true -> WAV"),
        SenseStatus("Auditory/Speech-in", "hearing", "seam", False, asr_ok,
                    "sensory/asr pluggable seam; register_engine or self-provision faster-whisper"),
        SenseStatus("Visual", "sight", "seam", False, vis_ok,
                    "sensory/vision pluggable seam; register_engine or self-provision rapidocr (OCR)"),
        SenseStatus("Interoceptive", "internal body state", "built", True, _intero_available(),
                    "sensory/interoception; mandatory, pure-stdlib baseline + psutil enrichment"),
        SenseStatus("Tactile/Contact", "touch", "unsupported", False, False,
                    "declared unsupported; host may register a contact-sensor adapter"),
        SenseStatus("Proprioceptive", "body position", "unsupported", False, False,
                    "declared unsupported; host may register a device-pose adapter"),
        SenseStatus("Vestibular", "balance/motion", "unsupported", False, False,
                    "declared unsupported; host may register an IMU adapter"),
        SenseStatus("Thermal", "temperature", "unsupported", False, False,
                    "declared unsupported; host may register a thermal adapter"),
        SenseStatus("Chemical/Olfactory", "smell/air", "unsupported", False, False,
                    "declared unsupported; host may register an air-quality adapter"),
        SenseStatus("Gustatory", "taste", "unsupported", False, False,
                    "declared unsupported; host may register a chemical-sampling adapter"),
        SenseStatus("Nociceptive", "pain/damage", "unsupported", False, False,
                    "declared unsupported; fault/impact signals map via register_engine"),
        SenseStatus("Temporal/Rhythm", "time perception", "unsupported", False, False,
                    "declared unsupported; clock/cadence adapter can be registered"),
        SenseStatus("Proximity", "spatial nearness", "unsupported", False, False,
                    "declared unsupported; host may register a radar/PIR/BLE adapter"),
    ]
    return [r.to_dict() for r in rows]


def summary() -> dict:
    """Compact conformance summary: counts by status + the mandatory-sense check."""
    rows = manifest()
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    mandatory_ok = all(r["available"] for r in rows if r["mandatory"])
    return {
        "adr": "ADR-0001 §7.1 / §16.4",
        "total_classes": len(rows),
        "by_status": by_status,
        "available_now": sum(1 for r in rows if r["available"]),
        "mandatory_satisfied": mandatory_ok,   # interoceptive must be available
        "unsupported_explicitly_declared": True,
    }
