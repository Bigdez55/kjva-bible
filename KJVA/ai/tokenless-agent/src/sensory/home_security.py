"""sensory/home_security.py — reference sensory integration (§11.2 step 16).

A worked example of mapping an external sensor stream (home-security events) into the
evidence envelope, demonstrating how non-text modalities enter the §12 pipeline without
renaming the taxonomy. Events are normalized to sensory anchors + a salience prior.
Pure stdlib; no device I/O (reference adapter).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .evidence import EvidenceEnvelope, hash_session

# Event type → base salience (higher = more attention-worthy).
_EVENT_SALIENCE = {
    "door_open": 0.5, "door_forced": 0.95, "motion": 0.4, "glass_break": 0.9,
    "alarm": 1.0, "camera_person": 0.7, "smoke": 0.95, "idle": 0.05,
}


@dataclass
class HomeSecurityEvent:
    event_type: str
    zone: str = "unknown"
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)


def event_to_envelope(event: HomeSecurityEvent, *, session_id: str = "") -> EvidenceEnvelope:
    base = _EVENT_SALIENCE.get(event.event_type, 0.3)
    salience = round(min(1.0, base * max(0.0, min(1.0, event.confidence))), 4)
    anchors = [f"home_security:{event.event_type}", f"zone:{event.zone}"]
    return EvidenceEnvelope(
        session_hash=hash_session(session_id) if session_id else "",
        modality="sensor", entities=[event.event_type, event.zone],
        sensory_anchors=anchors, byte_profile={}, salience=salience,
        length=0, metadata={"sensor": "home_security", "confidence": event.confidence, **event.metadata},
    )


def is_actionable(event: HomeSecurityEvent, threshold: float = 0.7) -> bool:
    return _EVENT_SALIENCE.get(event.event_type, 0.0) * event.confidence >= threshold
