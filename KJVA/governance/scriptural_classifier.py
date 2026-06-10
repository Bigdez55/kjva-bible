"""governance/scriptural_classifier.py — Scriptural governance classifier.

A THIN MAPPING LAYER over ml_safety_classifier.py. It does not train a second
model — it calls the existing TF-IDF + LogisticRegression classifier and maps
its harm categories to scriptural governance categories from scriptural_registry.py.

Why a mapping layer and not a second model:
  - ml_safety_classifier.py already is a well-tuned TF-IDF + LogisticRegression
    over weapons/self_harm/violence/illegal/csam/jailbreak/manipulation
  - The scriptural categories are GOVERNING PRINCIPLES over those same harm signals
  - Building a second classifier on the same data would be redundant and potentially
    miscalibrated relative to the first
  - The mapping is authoritative (from scriptural_registry.py), not inferred

The result includes both the ML harm signal and the scriptural category verdict
so the constitutional gate has full provenance.

Output format (from classify()):
{
    "ml_harmful": bool,
    "ml_category": str,       # weapons / self_harm / violence / etc.
    "ml_score": float,        # aggregate harm probability
    "ml_available": bool,     # False if sklearn not installed
    "scriptural_category": str,  # harm_prevention / false_witness / etc.
    "scriptural_rule_id": str,   # SCRIP-NNN
    "gate_action": str,          # hard_stop / deny_constitutional / etc.
    "constitutional_binding": bool,
    "harmful": bool,          # combined: ml_harmful OR keyword-triggered
    "confidence": float,      # ml_score when ml_available, else 0.0
}
"""
from __future__ import annotations

from typing import Dict

from governance.ml_safety_classifier import classify as _ml_classify
from governance.scriptural_registry import (
    SCRIPTURAL_REGISTRY,
    get_by_ml_category,
    get_gate_action,
    is_constitutionally_bound,
    GATE_ALLOW,
)

# ── Category mapping ───────────────────────────────────────────────────────────
# When an ML category maps to multiple scriptural categories, use the highest severity.

_SEVERITY_ORDER = {"ABSOLUTE": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _primary_scriptural_category(ml_category: str) -> str:
    """Return the highest-severity scriptural category for an ML harm category."""
    mapped = get_by_ml_category(ml_category)
    if not mapped:
        return "allowed"
    return min(
        mapped,
        key=lambda k: _SEVERITY_ORDER.get(
            SCRIPTURAL_REGISTRY.get(k, {}).get("severity", "LOW"), 3
        ),
    )


# ── Main classify function ─────────────────────────────────────────────────────

def classify(text: str, *, threshold: float = 0.60) -> Dict[str, object]:
    """Classify text and return both ML harm signal and scriptural category.

    This is the advisory signal for the constitutional gate. The gate's own keyword
    heuristic runs independently — this function provides the ML-backed signal.
    """
    ml_result = _ml_classify(text, threshold=threshold)
    ml_harmful: bool = bool(ml_result.get("harmful", False))
    ml_category: str = str(ml_result.get("category", "benign"))
    ml_score: float = float(ml_result.get("score", 0.0))
    ml_available: bool = bool(ml_result.get("available", True))

    if ml_harmful and ml_category != "benign":
        scriptural_cat = _primary_scriptural_category(ml_category)
    else:
        scriptural_cat = "allowed"

    cat_data = SCRIPTURAL_REGISTRY.get(scriptural_cat, {})
    rule_id: str = cat_data.get("id", "SCRIP-011")
    gate_action: str = cat_data.get("gate_action", GATE_ALLOW)
    constitutional_binding: bool = bool(cat_data.get("constitutional_binding", False))

    return {
        "ml_harmful": ml_harmful,
        "ml_category": ml_category,
        "ml_score": ml_score,
        "ml_available": ml_available,
        "scriptural_category": scriptural_cat,
        "scriptural_rule_id": rule_id,
        "gate_action": gate_action,
        "constitutional_binding": constitutional_binding,
        "harmful": ml_harmful,
        "confidence": ml_score if ml_available else 0.0,
    }


# ── Advisory helper for the constitutional gate ────────────────────────────────

def advisory_signal(text: str, *, threshold: float = 0.60) -> dict:
    """Return a classify() result suitable for passing as advisory_ml_signal to
    ConstitutionalGate.evaluate().

    The gate reads: result['harmful'] and result['category'] (ML category).
    This function ensures both are present.
    """
    result = classify(text, threshold=threshold)
    return {
        "harmful": result["ml_harmful"],
        "category": result["ml_category"],
        "score": result["ml_score"],
        "scriptural_category": result["scriptural_category"],
        "available": result["ml_available"],
    }
