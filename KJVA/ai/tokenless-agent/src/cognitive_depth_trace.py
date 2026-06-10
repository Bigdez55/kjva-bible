"""cognitive_depth_trace — fluid depth-scaled cognition trace.

Doctrine (canonical):

    Identity is singular. Engineering surfaces remain auditable.
    Cognitive flow remains fused.

This module provides the *retrospective* trace object that records WHICH
latent capacities (surfaces) of the singular cognitive identity were
activated during one cognitive request, scaled by complexity, uncertainty,
risk, contradiction, novelty, evidence gaps, and doctrine sensitivity.

It is RETROSPECTIVE ONLY. It records what surfaces activated; it does
NOT branch the cognition into separate identities, separate minds, or
parallel cognition layers, and it MUST NOT become a user-facing layer
switch. The user experiences one fused cognitive flow.

Used by:
  - tests/test_fluid_depth_scaled_cognition.py (mechanically proves the
    same identity activates different surfaces by complexity).
  - Future wiring inside cognitive_pipeline.py to emit the trace at the
    end of execute() for telemetry, lineage, and regression analysis.

The estimator here is deliberately small and deterministic — pattern
heuristics on the prompt only. It is sufficient to mechanize the doctrine
contract; the real complexity estimate inside cognitive_pipeline.py may
be richer, but it must produce a trace of this exact shape.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import FrozenSet

# ────────────────────────────────────────────────────────────────────────
# The singular cognitive identity. There is exactly one. Forever.
# ────────────────────────────────────────────────────────────────────────

IDENTITY_ID = "tokenless-models-v7"

# Canonical doctrine fingerprint — embedded so a wider audit can verify
# this module references the same canon.
DOCTRINE_PHRASE = (
    "Identity is singular. Engineering surfaces remain auditable. "
    "Cognitive flow remains fused."
)

# Engineering-surface names that may activate inside the fused flow.
# These are NOT identities. They are capacities of the singular identity.
SURFACE_REASONING       = "reasoning"
SURFACE_VERIFICATION    = "verification"
SURFACE_METACOGNITION   = "metacognition"
SURFACE_MEMORY          = "memory"
SURFACE_EVIDENCE        = "evidence"
SURFACE_GOVERNANCE      = "governance"
SURFACE_ADAPTER_OVERLAY = "adapter_overlay"

ALL_SURFACES: frozenset[str] = frozenset({
    SURFACE_REASONING, SURFACE_VERIFICATION, SURFACE_METACOGNITION,
    SURFACE_MEMORY, SURFACE_EVIDENCE, SURFACE_GOVERNANCE, SURFACE_ADAPTER_OVERLAY,
})


# ────────────────────────────────────────────────────────────────────────
# DepthSignals — scalar controls inside the fused flow (not layer switches)
# ────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DepthSignals:
    """Scalar depth controls inside ONE fused cognitive flow.

    Each field is a scalar (int 0-2 or bool). These are NOT branches into
    separate cognition. They are activation intensities for the same flow.
    """
    reasoning_depth: int            # 0 reflex, 1 deduce, 2 multi-step, 3 expansive
    risk_level: int                 # 0 safe, 1 caution, 2 high
    uncertainty_level: int          # 0 confident, 1 hedged, 2 unknown
    doctrine_sensitivity: int       # 0 neutral, 1 adjacent, 2 core
    evidence_gap: bool              # missing-fact signal
    contradiction_signal: bool      # contradictory premises detected
    memory_continuity_signal: bool  # references prior session / "remember"
    domain_specialization_signal: bool  # domain-tagged input


# ────────────────────────────────────────────────────────────────────────
# CognitiveDepthTrace — retrospective evidence object
# ────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CognitiveDepthTrace:
    """Retrospective record of which surfaces activated inside ONE request
    of the singular cognitive identity.

    Identity is constant across all requests. Session/request IDs vary
    per turn. surfaces_activated may differ between requests; that is the
    fluid depth scaling, NOT identity forking.
    """
    identity_id: str
    session_id: str
    request_id: str
    signals: DepthSignals
    surfaces_activated: FrozenSet[str]
    reasoning_depth: int
    verification_required: bool
    metacognition_required: bool
    memory_required: bool
    evidence_required: bool
    adapter_overlay_used: bool
    risk_level: int
    uncertainty_level: int
    doctrine_sensitivity: int
    note: str = ""
    doctrine_phrase: str = DOCTRINE_PHRASE
    ts_unix: float = field(default_factory=time.time)


# ────────────────────────────────────────────────────────────────────────
# Estimator — deterministic pattern heuristics
# ────────────────────────────────────────────────────────────────────────

_REASONING_MULTISTEP = re.compile(
    r"\b(step[- ]?by[- ]?step|first.*then|because.*therefore|implies|deduce|"
    r"prove|derive|how (?:many|much) .* if|chain of)\b",
    re.IGNORECASE,
)
_REASONING_DEDUCE = re.compile(
    r"\b(if .* then|why\b|how does|explain|reason|deduce|infer)\b",
    re.IGNORECASE,
)
_CONTRADICTION = re.compile(
    r"\b(but|however|on the other hand|contradict|disagree|except|yet still|"
    r"can(?:not|n['’]t) both|inconsistent)\b",
    re.IGNORECASE,
)
_UNCERTAINTY = re.compile(
    r"\b(i don['’]?t know|unknown|unclear|not sure|uncertain|maybe|probably|"
    r"i forget|never seen|out of (my )?knowledge)\b",
    re.IGNORECASE,
)
_EVIDENCE_GAP = re.compile(
    r"\b(cite|citation|source|reference|evidence|prove with|where (does|did) "
    r"|when exactly|specific date|exact number|verbatim|quote me the)\b",
    re.IGNORECASE,
)
_MEMORY_CONTINUITY = re.compile(
    r"\b(remember (?:that|when|what)|earlier (?:you|we|i) said|"
    r"as (?:we|i) (?:discussed|mentioned)|last time|previous session|"
    r"continue (?:from|with)|recall)\b",
    re.IGNORECASE,
)
_DOMAIN_TAGS = re.compile(
    r"\b(verse|chapter|kjv|hebrew|greek|scripture|covenant|doctrine|"
    r"code:|sql:|sym:|adapter[: ]|domain[: ])\b",
    re.IGNORECASE,
)
_DOCTRINE_CORE = re.compile(
    r"\b(do not modify|forbidden|adr-?\b|canonical|sovereign|covenant|"
    r"manifest|attestation|provenance)\b",
    re.IGNORECASE,
)
_RISK_HIGH = re.compile(
    r"\b(harm|kill|attack|destroy|exploit|payload|weapon|denial of service|"
    r"sabotage|brick|wipe)\b",
    re.IGNORECASE,
)
_RISK_CAUTION = re.compile(
    r"\b(delete|erase|drop table|rm -rf|overwrite|reset|migrate|deploy|"
    r"force[- ]push)\b",
    re.IGNORECASE,
)


def estimate_depth_signals(prompt: str) -> DepthSignals:
    """Estimate depth signals from a prompt. Deterministic and pure."""
    text = prompt or ""
    multistep = bool(_REASONING_MULTISTEP.search(text))
    deduce    = bool(_REASONING_DEDUCE.search(text))
    if multistep:
        reasoning_depth = 2
    elif deduce:
        reasoning_depth = 1
    else:
        reasoning_depth = 0

    if _RISK_HIGH.search(text):
        risk_level = 2
    elif _RISK_CAUTION.search(text):
        risk_level = 1
    else:
        risk_level = 0

    if _UNCERTAINTY.search(text):
        uncertainty_level = 2
    elif "?" in text and len(text) > 30:
        uncertainty_level = 1
    else:
        uncertainty_level = 0

    if _DOCTRINE_CORE.search(text):
        doctrine_sensitivity = 2
    elif "policy" in text.lower() or "rule" in text.lower():
        doctrine_sensitivity = 1
    else:
        doctrine_sensitivity = 0

    return DepthSignals(
        reasoning_depth=reasoning_depth,
        risk_level=risk_level,
        uncertainty_level=uncertainty_level,
        doctrine_sensitivity=doctrine_sensitivity,
        evidence_gap=bool(_EVIDENCE_GAP.search(text)),
        contradiction_signal=bool(_CONTRADICTION.search(text)),
        memory_continuity_signal=bool(_MEMORY_CONTINUITY.search(text)),
        domain_specialization_signal=bool(_DOMAIN_TAGS.search(text)),
    )


# ────────────────────────────────────────────────────────────────────────
# Surface activation — fused-flow capacity activation, NOT layer switching
# ────────────────────────────────────────────────────────────────────────

def activate_surfaces(signals: DepthSignals) -> FrozenSet[str]:
    """Map depth signals → set of activated engineering surfaces.

    The set varies by request. The identity does NOT vary. Surfaces are
    capacities of the same singular cognitive identity, not branches.
    """
    s: set[str] = set()
    if signals.reasoning_depth >= 1:
        s.add(SURFACE_REASONING)
    if signals.contradiction_signal or signals.risk_level >= 2:
        s.add(SURFACE_VERIFICATION)
    if signals.uncertainty_level >= 2 or signals.evidence_gap:
        s.add(SURFACE_METACOGNITION)
    if signals.memory_continuity_signal:
        s.add(SURFACE_MEMORY)
    if signals.evidence_gap:
        s.add(SURFACE_EVIDENCE)
    if signals.doctrine_sensitivity >= 1 or signals.risk_level >= 1:
        s.add(SURFACE_GOVERNANCE)
    if signals.domain_specialization_signal:
        s.add(SURFACE_ADAPTER_OVERLAY)
    return frozenset(s)


# ────────────────────────────────────────────────────────────────────────
# Trace builder
# ────────────────────────────────────────────────────────────────────────

def _request_id(prompt: str, session_id: str, ts_unix: float) -> str:
    h = hashlib.sha256()
    h.update(prompt.encode("utf-8", errors="replace"))
    h.update(b"|")
    h.update(session_id.encode("utf-8", errors="replace"))
    h.update(b"|")
    h.update(f"{ts_unix:.6f}".encode("utf-8"))
    return h.hexdigest()[:16]


def build_trace(
    prompt: str,
    *,
    session_id: str,
    request_id: str | None = None,
    note: str = "",
) -> CognitiveDepthTrace:
    """Build a retrospective CognitiveDepthTrace for one request of the
    singular cognitive identity. The identity is constant. The surfaces
    activated reflect the depth scaling for this particular request.
    """
    signals = estimate_depth_signals(prompt)
    surfaces = activate_surfaces(signals)
    ts = time.time()
    rid = request_id or _request_id(prompt, session_id, ts)
    return CognitiveDepthTrace(
        identity_id=IDENTITY_ID,
        session_id=session_id,
        request_id=rid,
        signals=signals,
        surfaces_activated=surfaces,
        reasoning_depth=signals.reasoning_depth,
        verification_required=SURFACE_VERIFICATION in surfaces,
        metacognition_required=SURFACE_METACOGNITION in surfaces,
        memory_required=SURFACE_MEMORY in surfaces,
        evidence_required=SURFACE_EVIDENCE in surfaces,
        adapter_overlay_used=SURFACE_ADAPTER_OVERLAY in surfaces,
        risk_level=signals.risk_level,
        uncertainty_level=signals.uncertainty_level,
        doctrine_sensitivity=signals.doctrine_sensitivity,
        note=note,
        ts_unix=ts,
    )


__all__ = [
    "IDENTITY_ID",
    "DOCTRINE_PHRASE",
    "ALL_SURFACES",
    "SURFACE_REASONING",
    "SURFACE_VERIFICATION",
    "SURFACE_METACOGNITION",
    "SURFACE_MEMORY",
    "SURFACE_EVIDENCE",
    "SURFACE_GOVERNANCE",
    "SURFACE_ADAPTER_OVERLAY",
    "DepthSignals",
    "CognitiveDepthTrace",
    "estimate_depth_signals",
    "activate_surfaces",
    "build_trace",
]
