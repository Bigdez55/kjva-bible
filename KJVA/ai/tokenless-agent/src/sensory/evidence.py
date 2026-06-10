"""sensory/evidence.py — Level-1 perception: build the evidence envelope (§12, §11.2 step 9).

The §12 runtime algorithm opens with `evidence = build_evidence_envelope(request)`. For a
byte-level text model the "sensory channels" are the input byte classes; the envelope wraps
the raw request with extracted entities, byte-channel profile, sensory anchors, and a salience
score that downstream stages (governance, memory retrieval, adapter routing) consume.

Pure stdlib — no torch/mlx; PII-safe (raw text is not persisted by this module).
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field, asdict

_BYTE_CHANNELS = ("control", "ascii_printable", "utf8_lead", "utf8_cont", "high")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_'-]+")


def _channel_of(b: int) -> str:
    if b < 32 or b == 127:
        return "control"
    if 32 <= b < 127:
        return "ascii_printable"
    if 0xC0 <= b <= 0xF4:
        return "utf8_lead"
    if 0x80 <= b < 0xC0:
        return "utf8_cont"
    return "high"


def _byte_profile(text: str) -> dict[str, float]:
    counts = {c: 0 for c in _BYTE_CHANNELS}
    raw = text.encode("utf-8", errors="ignore")
    for b in raw:
        counts[_channel_of(b)] += 1
    total = sum(counts.values()) or 1
    return {c: counts[c] / total for c in _BYTE_CHANNELS}


def _extract_entities(text: str, cap: int = 16) -> list[str]:
    # Capitalized tokens + distinct content words (cheap, deterministic, PII-light).
    caps = [w for w in _WORD.findall(text) if w[:1].isupper()]
    seen, out = set(), []
    for w in caps:
        k = w.lower()
        if k not in seen:
            seen.add(k); out.append(w)
        if len(out) >= cap:
            break
    return out


@dataclass
class EvidenceEnvelope:
    session_hash: str
    modality: str                      # "text" | "byte" | "sensor"
    entities: list[str] = field(default_factory=list)
    sensory_anchors: list[str] = field(default_factory=list)
    byte_profile: dict[str, float] = field(default_factory=dict)
    salience: float = 0.0
    length: int = 0
    metadata: dict = field(default_factory=dict)
    # ADR-0001 §6.3 / ADR-0002 §6.3 required fields (D19) — content-free.
    evidence_id: str = ""
    payload_hash: str = ""             # sha256 of input; never raw bytes
    risk_class: str = "standard"
    privacy_class: str = "private"
    materialization_state: str = "envelope"
    # ADR-0002 §6.3 minimum fields completed: source provenance + time + retention + confidence.
    source_kind: str = "user"          # user|sensor|file|environment|system-signal
    source_id_hash: str = ""           # hashed source id (never raw)
    timestamp_ns: int = 0
    retention_hint: str = "session"    # ephemeral|session|episodic|semantic|archival|discard
    confidence: float = 0.0            # §6.3 confidence (mirrors salience)
    # Perception→cognition bridge: the LM-readable rendering of a NON-text sense
    # (image caption / OCR text, audio transcript, sensor summary). For text input
    # this stays "" (the message already IS the text). This is the field a non-text
    # sense fills so its content actually reaches the model — folded into the prompt
    # by cognitive_pipeline. INJECTION-ONLY: excluded from to_dict() so derived
    # content never leaks into telemetry/journal (ADR §13 'no raw content').
    derived_text: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("derived_text", None)    # never serialized to telemetry/journal
        return d


def hash_session(session_id: str) -> str:
    """SHA-256 the session id before it appears anywhere (PII policy §4.4)."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def build_evidence_envelope(request, *, session_id: str = "", modality: str = "text",
                            sensor_anchors: list[str] | None = None,
                            derived_text: str = "") -> EvidenceEnvelope:
    """request may be a str or an object with a `.message` attribute.

    ``derived_text`` is the LM-readable rendering of a NON-text sense (image
    caption/OCR, audio transcript, sensor summary) that a modality adapter passes
    so its content reaches cognition. Leave "" for plain text. ``modality`` is a free
    tag per ADR-0001 §7.1 ("text" | "visual" | "auditory" | "speech" | "sensor" | …).
    """
    text = request if isinstance(request, str) else getattr(request, "message", "") or ""
    entities = _extract_entities(text)
    profile = _byte_profile(text)
    anchors = list(sensor_anchors or [])
    # salience: entity density + non-ascii (richer) signal, clamped to [0,1].
    salience = min(1.0, 0.5 * min(len(entities), 8) / 8.0 + 0.5 * (1.0 - profile["ascii_printable"]))
    payload_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    _sess_hash = hash_session(session_id) if session_id else ""
    return EvidenceEnvelope(
        session_hash=_sess_hash,
        modality=modality, entities=entities, sensory_anchors=anchors,
        byte_profile=profile, salience=round(salience, 4), length=len(text),
        metadata={"entity_count": len(entities)},
        evidence_id="ev:" + payload_hash[7:23], payload_hash=payload_hash,
        risk_class="standard", privacy_class="private",
        materialization_state="envelope",
        # §6.3 completed fields
        source_kind=("user" if modality == "text" else "sensor"),
        source_id_hash=_sess_hash,
        timestamp_ns=time.time_ns(),
        retention_hint="session",
        confidence=round(salience, 4),
        derived_text=derived_text or "",
    )
