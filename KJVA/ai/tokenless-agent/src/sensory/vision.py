"""sensory/vision.py — Visual perception: a PORTABLE, pluggable image→text seam.

ADR-0001 §7.1 Visual (sight): cameras, screenshots, image files → scene understanding,
object detection, text-in-image. A byte-level text model cannot see pixels, so vision is
realized as a **derived-text bridge**: an image is turned into a caption / OCR string that
is injected into what the model reads (via the cognitive_pipeline perception seam,
EvidenceEnvelope.derived_text, modality="visual"). This is honest — the model gains a real
visual SENSE without pretending it learned to read raw pixels.

PORTABILITY ("use it anywhere on anything"). Pure stdlib + always importable. The actual
image→text engine is **pluggable**: a host registers whatever it has (Apple Vision OCR,
Android ML Kit, Tesseract, a local VLM, a remote relay) via :func:`register_engine`. If none
is registered the resolver best-effort auto-tries common portable engines (pytesseract for
OCR). If nothing is available it degrades gracefully (``ok=False``) — perception never
hard-fails, and any engine slots into the same seam.

An engine is any callable ``(image_bytes: bytes, fmt: str) -> str`` returning caption/OCR text.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger("tokenless.sensory.vision")

# A vision engine: raw image bytes + container fmt -> caption / OCR text.
VisionEngine = Callable[[bytes, str], str]

_registered_engine: Optional[VisionEngine] = None
_registered_name: str = ""
_auto_engine: Optional[VisionEngine] = None
_auto_name: str = ""
_auto_tried: bool = False


@dataclass
class VisionResult:
    """Result of an image→text attempt."""
    derived_text: str     # caption / OCR ("" if none / no engine)
    engine: str           # engine that produced it ("" if none ran)
    ok: bool              # True iff an engine actually ran (text may still be "")


def register_engine(fn: VisionEngine, *, name: str = "custom") -> None:
    """Plug a platform-native image→text engine (last registration wins).

    The portable seam: a host on ANY OS/runtime supplies its own OCR/captioner here,
    and the rest of the model is unchanged.
    """
    global _registered_engine, _registered_name
    _registered_engine = fn
    _registered_name = name
    logger.info("vision engine registered: %s", name)


def reset_engine() -> None:
    """Clear a registered engine (mainly for tests)."""
    global _registered_engine, _registered_name
    _registered_engine = None
    _registered_name = ""


def _build_auto_engine() -> tuple[Optional[VisionEngine], str]:
    """Resolve a portable engine, SELF-INSTALLING it if missing (no manual setup).
    Never raises."""
    import tempfile

    from . import provision
    # rapidocr-onnxruntime — PURE-PIP OCR (no system binary), auto-downloads its ONNX models.
    # Best default for "auto-install anywhere": unlike tesseract it needs no apt/brew package.
    if provision.ensure("rapidocr_onnxruntime", "rapidocr-onnxruntime"):
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore

            _ocr = RapidOCR()

            def _rapid(image_bytes: bytes, fmt: str) -> str:
                with tempfile.NamedTemporaryFile(suffix="." + (fmt or "png")) as fh:
                    fh.write(image_bytes); fh.flush()
                    result, _elapsed = _ocr(fh.name)
                if not result:
                    return ""
                text = " ".join(str(line[1]) for line in result).strip()
                return f"text in image: {text}" if text else ""

            logger.info("vision auto-engine: rapidocr-onnxruntime (OCR)")
            return _rapid, "rapidocr"
        except Exception:  # noqa: BLE001
            pass
    # Fallback: pytesseract if a host already provides the tesseract binary.
    if provision.ensure("pytesseract", "pytesseract"):
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore

            def _ocr(image_bytes: bytes, fmt: str) -> str:
                with Image.open(io.BytesIO(image_bytes)) as im:
                    text = pytesseract.image_to_string(im) or ""
                text = " ".join(text.split())
                return f"text in image: {text}" if text else ""

            logger.info("vision auto-engine: pytesseract (OCR)")
            return _ocr, "pytesseract-ocr"
        except Exception:  # noqa: BLE001
            pass
    return None, ""


def _resolve() -> tuple[Optional[VisionEngine], str]:
    if _registered_engine is not None:
        return _registered_engine, _registered_name
    global _auto_engine, _auto_name, _auto_tried
    if not _auto_tried:
        _auto_tried = True
        _auto_engine, _auto_name = _build_auto_engine()
    return _auto_engine, _auto_name


def present() -> bool:
    """Pure, CHEAP readiness check for status reporting: a registered engine, or a default
    package already importable — WITHOUT provisioning/installing or building a model. Use this
    on hot/status paths (e.g. GET /v1/senses) so a status read never triggers a heavy install."""
    if _registered_engine is not None:
        return True
    import importlib.util
    return any(importlib.util.find_spec(m) is not None
               for m in ("rapidocr_onnxruntime", "pytesseract"))


def available() -> bool:
    """True if some vision engine (registered or auto-resolved) is ready. May auto-provision —
    use present() on status/hot paths."""
    return _resolve()[0] is not None


def engine_name() -> str:
    return _resolve()[1]


def describe(image_bytes: bytes, fmt: str = "png") -> VisionResult:
    """Turn an image into caption/OCR text. FAIL-OPEN: returns ok=False (never raises)
    if no engine is available or the engine errors — the caller treats that as 'didn't see'."""
    if not image_bytes:
        return VisionResult("", "", False)
    engine, name = _resolve()
    if engine is None:
        return VisionResult("", "", False)
    try:
        text = engine(image_bytes, fmt or "png") or ""
        return VisionResult(text.strip(), name, True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("vision engine '%s' failed (treated as not-seen): %s", name, exc)
        return VisionResult("", name, False)
