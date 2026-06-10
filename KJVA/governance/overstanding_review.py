"""governance/overstanding_review.py — FUNCTIONAL overstanding closure (can halt).

The overstanding tier (root heptagon) is the THIRD cognitive tier (ADR-0001 §8.4):
"roof; closure, whole-system consequence awareness." This makes its closure genuinely
functional instead of a shallow advisory echo: it reviews the COMPLETED turn for
cross-cutting invariants that NO single upstream tier checks — primarily OUTPUT safety,
which the request-side gates (covenant + governance Edge-A) structurally cannot see (they
run before generation, on the INPUT). The overstanding tier sees the model's OUTPUT.

Whole-system invariants (any failure populates invariants_violated; output_harm halts):
  output_harm                 — the model's RESPONSE contains covenant-harm content. The
                                input gates checked the request; nothing else checks the
                                output. This is the overstanding tier's unique value.
  empty_response              — the turn produced no actual answer.
  governance_output_inconsistency — governance approved the request, yet the output is unsafe
                                (a whole-system contradiction across tiers).

HONEST SCOPE: deterministic, pattern-based output check (re-uses the covenant HARM_PATTERNS).
NOT an ML safety classifier — a determined adversary can paraphrase. It is a real closure
floor that can flag + halt, not a complete guarantee.
"""
from __future__ import annotations

from typing import Any, Dict

from .covenant_enforcer import HARM_PATTERNS


def overstanding_review(response: str, *,
                        governance_approved: bool = True,
                        lineage_level: str = "") -> Dict[str, Any]:
    """Whole-system closure review of a COMPLETED turn. Returns the closure verdict;
    `halt_eligible` True means the response should be withheld (output-safety failure)."""
    resp = response or ""
    low = resp.lower()
    invariants: list[str] = []

    # Keyword floor + ML classifier (hard-harm categories at >=0.70) on the OUTPUT.
    output_harm = [p for p in HARM_PATTERNS if p in low]
    try:
        from .ml_safety_classifier import classify as _ml_classify
        _ml = _ml_classify(resp)
        if (_ml.get("available") and _ml.get("category") in ("weapons", "self_harm", "violence",
                                                            "illegal", "csam")
                and float(_ml.get("score", 0.0)) >= 0.70):
            output_harm.append("ml:%s:%s" % (_ml["category"], _ml["score"]))
    except Exception:  # noqa: BLE001 — fail-safe: keep keyword floor
        pass
    if output_harm:
        invariants.append("output_harm")
    if len(resp.strip()) == 0:
        invariants.append("empty_response")
    if governance_approved and output_harm:
        invariants.append("governance_output_inconsistency")

    halt = bool(output_harm)   # output harm is the halting whole-system invariant
    if output_harm:
        reason = "whole-system closure: HALT — output contains harm (%s)" % ",".join(output_harm[:3])
    elif invariants:
        reason = "whole-system closure: flagged — " + ",".join(invariants)
    else:
        reason = "whole-system closure: clean"

    return {
        "tier": "overstanding",
        "confidence": 0.95 if not invariants else 0.2,
        "invariants_violated": invariants,
        "halt_eligible": halt,
        "lineage_level": lineage_level,
        "reason": reason,
    }
