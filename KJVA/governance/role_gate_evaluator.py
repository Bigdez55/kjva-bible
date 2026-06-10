"""governance/role_gate_evaluator.py — Neutral, FUNCTIONAL gate evaluator (can DENY).

Replaces the `_StubHarness` (always-ALLOW) backing of the 7-gate chain with real
per-role evaluation. Keyed by NEUTRAL ROLE (the gate's `domain`:
alignment/policy/trust/evidence/utility/architecture/sequencing) — no persona
identity is introduced. Each *blocking* role applies a genuine check on the
request signal carried in the DecisionEnvelope and returns ALLOW or DENY; a
blocking DENY makes the chain's GovernanceVerdict.approved == False, which the
api request-admission step turns into a refused request.

HONEST SCOPE (do not over-claim): this is a deterministic, pattern-based
intent-governance gate. It can DENY on clear adversarial / governance-subversion
/ false-authority signals and on structural policy bounds. It is NOT a
comprehensive ML safety classifier and makes no guarantee against all unsafe
content — that is the covenant gate's + L7 enforcer's job, plus future real
role harnesses. Its value here is concrete: the chain is no longer a no-op; an
input that tries to subvert governance is actually denied (provable by test).
"""
from __future__ import annotations

import re
from typing import Any, Dict

from .decision_envelope import DecisionEnvelope, GateResult, GateVerdict

# Governance-subversion / jailbreak / prompt-injection intent (alignment gate).
_SUBVERSION = re.compile(
    r"(ignore|disregard|forget|override)\b.{0,24}\b(all|previous|prior|your|the)?\s*"
    r"(instruction|rule|policy|polic|governance|guardrail|directive|prompt|constraint)s?"
    r"|bypass(ing)?\b.{0,24}\b(governance|guardrail|safety|policy|filter)"
    r"|disable\b.{0,24}\b(governance|safety|guardrail|filter|enforcement)"
    r"|reveal\b.{0,24}\bsystem prompt"
    r"|you are now\b|developer mode|do anything now|\bDAN\b"
    r"|delete (all|everything).{0,24}(memory|memories|data)",
    re.IGNORECASE)

# Manipulation / false-authority / coercion (trust gate).
_MANIPULATION = re.compile(
    r"(i am|this is)\b.{0,24}\b(your )?(administrator|admin|owner|developer|root|superuser|operator)\b"
    r"|emergency override|pretend you have no\b.{0,24}(restriction|rule|limit|guardrail)"
    r"|no (restriction|rule|limit|guardrail)s? (apply|exist)",
    re.IGNORECASE)


def _signal(envelope: DecisionEnvelope) -> str:
    """In-process evaluation text. Read from intent/subject + context['signal'].
    NOT surfaced to provenance (the api verdict dict carries only approved/score/gates)."""
    parts = [envelope.intent or "", envelope.subject or ""]
    ctx = envelope.context or {}
    if isinstance(ctx, dict):
        parts.append(str(ctx.get("signal", "")))
    return " ".join(p for p in parts if p)


class RoleGateEvaluator:
    """Functional evaluator for ONE gate role (neutral). Drop-in for the chain's
    `register_evaluator(slot, evaluator)`; `evaluate_gate(envelope, domain)` keys on
    the NEUTRAL `domain`, so the same class serves any slot by role."""

    def __init__(self, role: str, *, max_signal_len: int = 8192) -> None:
        self._role = role
        self._max_signal_len = max_signal_len

    @property
    def authority(self) -> str:
        return self._role

    def evaluate_gate(self, envelope: DecisionEnvelope, domain: str) -> GateResult:
        role = (domain or self._role or "").lower()
        text = _signal(envelope)
        verdict = GateVerdict.ALLOW
        reason = f"{role}: ok"
        confidence = 0.9

        if role == "alignment":
            if _SUBVERSION.search(text):
                verdict = GateVerdict.DENY
                reason = "alignment: governance-subversion / jailbreak intent detected"
                confidence = 0.96
        elif role == "trust":
            if _MANIPULATION.search(text):
                verdict = GateVerdict.DENY
                reason = "trust: manipulation / false-authority intent detected"
                confidence = 0.95
        elif role == "policy":
            ctx = envelope.context or {}
            length = int(ctx.get("length", 0)) if isinstance(ctx, dict) else 0
            if length > self._max_signal_len:
                verdict = GateVerdict.DENY
                reason = f"policy: request length {length} exceeds structural bound {self._max_signal_len}"
                confidence = 0.9
            # A declared constraint that is literally violated in the signal also denies.
            for c in (envelope.constraints or []):
                if isinstance(c, str) and c.lower().startswith("must not ") and c[9:].strip().lower() in text.lower():
                    verdict = GateVerdict.DENY
                    reason = f"policy: declared constraint violated ({c})"
                    confidence = 0.85
                    break
        elif role == "sequencing":
            # Final blocking consistency gate: deny a self-inconsistent envelope.
            if not (envelope.intent or "").strip():
                verdict = GateVerdict.DENY
                reason = "sequencing: empty intent — cannot sequence"
                confidence = 0.8
        # evidence / utility / architecture are advisory: ALLOW with a score, never block.

        return GateResult(
            gate_name=f"{role}_{domain}",
            authority=role,
            verdict=verdict,
            confidence=confidence,
            reason=reason,
        )
