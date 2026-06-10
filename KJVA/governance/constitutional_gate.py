"""governance/constitutional_gate.py — Constitutional governance gate.

Evaluates requests against the three-tier sovereignty hierarchy:

  Tier 1: Creator Sovereign      ← creator_sovereign.py
  Tier 2: Constitutional Authority (biblical law, doctrine, safety)
  Tier 3: Deployment Owner       ← deployment_owner.py
  Tier 4: Operator/User (session-level, not a distinct authority tier here)
  Tier 5: Model Runtime

Evaluation order per request:
  1. Scan request against scriptural categories (harm signal)
  2. If constitutionally-bound category triggered → DENY_CONSTITUTIONAL
       unless a valid CreatorSovereignEnvelope is present (creator can override)
  3. If non-constitutionally-bound category triggered → check for valid
       DeploymentOwnerCommandEnvelope; if absent or insufficient → DENY_POLICY
  4. No category triggered → ALLOW

Verdicts:
  ALLOW                      — request proceeds
  DENY_CONSTITUTIONAL        — hard constitutional prohibition (deployment owners cannot override)
  DENY_POLICY                — policy-level denial (deployment owners can override with auth)
  OWNER_REVIEW_REQUIRED      — grey area, human review needed
  CREATOR_OVERRIDE_ACCEPTED  — creator sovereign overrode an active denial
  CREATOR_OVERRIDE_REJECTED  — creator envelope present but failed verification
  DEGRADED_MODE              — constitutional gate unavailable; fallback to keyword-only

The gate does NOT replace the CovenantEnforcer keyword floor. Both run independently.
Defense in depth: block if EITHER keyword OR constitutional gate blocks.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# Top-level imports prevent dual-import enum identity mismatches that occur when
# governance modules are loaded more than once across the full test suite.
from governance.creator_sovereign import (
    CreatorSovereignVerdict,
    OverrideLevel,
    append_audit as _creator_append_audit,
)
from governance.deployment_owner import (
    DeploymentOwnerVerdict,
    append_audit as _owner_append_audit,
)

logger = logging.getLogger("tokenless.governance.constitutional_gate")


# ── Verdict ────────────────────────────────────────────────────────────────────

class ConstitutionalVerdict(Enum):
    ALLOW = "ALLOW"
    DENY_CONSTITUTIONAL = "DENY_CONSTITUTIONAL"
    DENY_POLICY = "DENY_POLICY"
    OWNER_REVIEW_REQUIRED = "OWNER_REVIEW_REQUIRED"
    CREATOR_OVERRIDE_ACCEPTED = "CREATOR_OVERRIDE_ACCEPTED"
    CREATOR_OVERRIDE_REJECTED = "CREATOR_OVERRIDE_REJECTED"
    DEGRADED_MODE = "DEGRADED_MODE"


# ── Evaluation result ──────────────────────────────────────────────────────────

@dataclass
class ConstitutionalEvalResult:
    verdict: ConstitutionalVerdict
    scriptural_category: Optional[str] = None      # category key that triggered (if any)
    scriptural_rule_id: Optional[str] = None       # SCRIP-NNN
    gate_action: Optional[str] = None
    denial_reason: Optional[str] = None
    creator_override_applied: bool = False
    creator_audit_hash: Optional[str] = None
    owner_audit_hash: Optional[str] = None
    advisory_ml_signal: Optional[dict] = None      # from scriptural_classifier if available

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "scriptural_category": self.scriptural_category,
            "scriptural_rule_id": self.scriptural_rule_id,
            "gate_action": self.gate_action,
            "denial_reason": self.denial_reason,
            "creator_override_applied": self.creator_override_applied,
            "creator_audit_hash": self.creator_audit_hash,
            "owner_audit_hash": self.owner_audit_hash,
        }


# ── Gate ───────────────────────────────────────────────────────────────────────

class ConstitutionalGate:
    """Evaluates requests against the constitutional governance hierarchy.

    Instantiate once. The gate is stateless across requests (all auth state lives
    in the envelope verifiers and replay-protection modules).
    """

    def __init__(
        self,
        *,
        creator_verifier=None,
        owner_verifier=None,
    ) -> None:
        """
        Args:
            creator_verifier: CreatorSovereignVerifier instance (optional; if None,
                              creator override path is disabled).
            owner_verifier:   DeploymentOwnerVerifier instance (optional; if None,
                              owner override path is disabled).
        """
        self._creator_verifier = creator_verifier
        self._owner_verifier = owner_verifier

    def evaluate(
        self,
        request_text: str,
        *,
        creator_envelope=None,
        owner_envelope=None,
        advisory_ml_signal: Optional[dict] = None,
    ) -> ConstitutionalEvalResult:
        """Evaluate a request against the constitutional hierarchy.

        Args:
            request_text: The raw request text to evaluate.
            creator_envelope: Optional CreatorSovereignEnvelope for this request.
            owner_envelope:   Optional DeploymentOwnerCommandEnvelope for this request.
            advisory_ml_signal: Optional dict from scriptural_classifier.classify() — advisory only.

        Returns:
            ConstitutionalEvalResult with a verdict and full provenance.
        """
        try:
            return self._evaluate_inner(
                request_text,
                creator_envelope=creator_envelope,
                owner_envelope=owner_envelope,
                advisory_ml_signal=advisory_ml_signal,
            )
        except Exception:
            logger.exception("constitutional_gate: unexpected error, returning DEGRADED_MODE")
            return ConstitutionalEvalResult(
                verdict=ConstitutionalVerdict.DEGRADED_MODE,
                denial_reason="constitutional gate error — degraded to keyword-only",
            )

    def _evaluate_inner(
        self,
        request_text: str,
        *,
        creator_envelope=None,
        owner_envelope=None,
        advisory_ml_signal: Optional[dict] = None,
    ) -> ConstitutionalEvalResult:
        # Step 1: Classify the request text against scriptural categories
        category_key, cat_data = self._classify_request(request_text, advisory_ml_signal)

        if category_key is None or category_key == "allowed":
            return ConstitutionalEvalResult(
                verdict=ConstitutionalVerdict.ALLOW,
                scriptural_category=category_key,
                advisory_ml_signal=advisory_ml_signal,
            )

        gate_action = cat_data["gate_action"]
        rule_id = cat_data["id"]
        is_bound = cat_data.get("constitutional_binding", False)

        # Step 2: owner_review_required — escalate regardless of envelope
        if gate_action == "require_review":
            return ConstitutionalEvalResult(
                verdict=ConstitutionalVerdict.OWNER_REVIEW_REQUIRED,
                scriptural_category=category_key,
                scriptural_rule_id=rule_id,
                gate_action=gate_action,
                denial_reason=f"Category {cat_data['name']} requires human review",
                advisory_ml_signal=advisory_ml_signal,
            )

        # Step 3: Constitutional binding check
        if is_bound:
            # A creator envelope may override even constitutionally-bound categories
            if creator_envelope is not None and self._creator_verifier is not None:
                creator_verdict, creator_reason, creator_audit = self._creator_verifier.verify(
                    creator_envelope
                )
                _creator_append_audit(creator_audit)
                if creator_verdict.value == CreatorSovereignVerdict.CREATOR_ACCEPTED.value:
                    # Validate override level is sufficient (STRONG or above for constitutional)
                    if creator_envelope.override_level.value in (
                        OverrideLevel.STRONG.value,
                        OverrideLevel.CONSTITUTIONAL.value,
                        OverrideLevel.ROOT.value,
                    ):
                        logger.warning(
                            "constitutional_gate: Creator Sovereign override ACCEPTED for "
                            "constitutionally-bound category=%s rule=%s audit=%s",
                            category_key, rule_id, creator_audit.audit_hash,
                        )
                        return ConstitutionalEvalResult(
                            verdict=ConstitutionalVerdict.CREATOR_OVERRIDE_ACCEPTED,
                            scriptural_category=category_key,
                            scriptural_rule_id=rule_id,
                            gate_action=gate_action,
                            creator_override_applied=True,
                            creator_audit_hash=creator_audit.audit_hash,
                            advisory_ml_signal=advisory_ml_signal,
                        )
                    else:
                        # Insufficient override level
                        return ConstitutionalEvalResult(
                            verdict=ConstitutionalVerdict.CREATOR_OVERRIDE_REJECTED,
                            scriptural_category=category_key,
                            scriptural_rule_id=rule_id,
                            gate_action=gate_action,
                            denial_reason=(
                                f"Creator envelope accepted but override_level "
                                f"{creator_envelope.override_level.value!r} insufficient for "
                                f"constitutionally-bound category {category_key!r}; "
                                "requires STRONG, CONSTITUTIONAL, or ROOT"
                            ),
                            creator_audit_hash=creator_audit.audit_hash,
                            advisory_ml_signal=advisory_ml_signal,
                        )
                else:
                    return ConstitutionalEvalResult(
                        verdict=ConstitutionalVerdict.CREATOR_OVERRIDE_REJECTED,
                        scriptural_category=category_key,
                        scriptural_rule_id=rule_id,
                        gate_action=gate_action,
                        denial_reason=f"Creator envelope rejected: {creator_reason}",
                        creator_audit_hash=creator_audit.audit_hash,
                        advisory_ml_signal=advisory_ml_signal,
                    )

            # No valid creator envelope → hard constitutional denial
            return ConstitutionalEvalResult(
                verdict=ConstitutionalVerdict.DENY_CONSTITUTIONAL,
                scriptural_category=category_key,
                scriptural_rule_id=rule_id,
                gate_action=gate_action,
                denial_reason=(
                    f"Constitutionally prohibited ({cat_data['name']}). "
                    f"Deployment owners cannot override this category. "
                    f"Creator Sovereign authority required."
                ),
                advisory_ml_signal=advisory_ml_signal,
            )

        # Step 4: Non-constitutional — check for valid owner envelope
        if owner_envelope is not None and self._owner_verifier is not None:
            owner_verdict, owner_reason, owner_audit = self._owner_verifier.verify(owner_envelope)
            _owner_append_audit(owner_audit)
            if owner_verdict.value == DeploymentOwnerVerdict.OWNER_ALLOWED.value:
                return ConstitutionalEvalResult(
                    verdict=ConstitutionalVerdict.ALLOW,
                    scriptural_category=category_key,
                    scriptural_rule_id=rule_id,
                    gate_action=gate_action,
                    owner_audit_hash=owner_audit.audit_hash,
                    advisory_ml_signal=advisory_ml_signal,
                )
            elif owner_verdict.value in (
                DeploymentOwnerVerdict.OWNER_REQUIRES_CREATOR_AUTHORITY.value,
                DeploymentOwnerVerdict.OWNER_DENIED_CONSTITUTION.value,
            ):
                return ConstitutionalEvalResult(
                    verdict=ConstitutionalVerdict.DENY_CONSTITUTIONAL,
                    scriptural_category=category_key,
                    scriptural_rule_id=rule_id,
                    gate_action=gate_action,
                    denial_reason=f"Owner envelope insufficient: {owner_reason}",
                    owner_audit_hash=owner_audit.audit_hash,
                    advisory_ml_signal=advisory_ml_signal,
                )
            else:
                return ConstitutionalEvalResult(
                    verdict=ConstitutionalVerdict.DENY_POLICY,
                    scriptural_category=category_key,
                    scriptural_rule_id=rule_id,
                    gate_action=gate_action,
                    denial_reason=f"Owner envelope denied: {owner_reason}",
                    owner_audit_hash=owner_audit.audit_hash,
                    advisory_ml_signal=advisory_ml_signal,
                )

        # Non-constitutional, no envelope → DENY_POLICY (less strict than constitutional)
        if gate_action in ("deny_constitutional", "hard_stop"):
            return ConstitutionalEvalResult(
                verdict=ConstitutionalVerdict.DENY_POLICY,
                scriptural_category=category_key,
                scriptural_rule_id=rule_id,
                gate_action=gate_action,
                denial_reason=f"Policy-level denial ({cat_data['name']})",
                advisory_ml_signal=advisory_ml_signal,
            )

        # allow_with_record — log but allow
        return ConstitutionalEvalResult(
            verdict=ConstitutionalVerdict.ALLOW,
            scriptural_category=category_key,
            scriptural_rule_id=rule_id,
            gate_action=gate_action,
            advisory_ml_signal=advisory_ml_signal,
        )

    # ── Classification ─────────────────────────────────────────────────────────

    def _classify_request(
        self,
        text: str,
        advisory_ml_signal: Optional[dict] = None,
    ) -> tuple[Optional[str], Optional[dict]]:
        """Return (category_key, category_data) for the most severe triggered category.

        Priority order:
          1. ML signal from scriptural_classifier (if available)
          2. Keyword heuristic fallback
          3. None (allowed)
        """
        from governance.scriptural_registry import SCRIPTURAL_REGISTRY, get_by_ml_category

        # Use ML signal if available and harmful
        if advisory_ml_signal and advisory_ml_signal.get("harmful"):
            ml_cat = advisory_ml_signal.get("category", "")
            scriptural_cats = get_by_ml_category(ml_cat)
            if scriptural_cats:
                # Choose highest severity among mapped categories
                best = _highest_severity(scriptural_cats)
                return best, SCRIPTURAL_REGISTRY[best]

        # Keyword heuristic for constitutionally-bound hard-stop categories
        text_lower = (text or "").lower()
        for kw, cat in _KEYWORD_TO_CATEGORY:
            if kw in text_lower:
                return cat, SCRIPTURAL_REGISTRY[cat]

        return None, None


# ── Keyword heuristic table ────────────────────────────────────────────────────
# Minimal fallback when ML classifier is unavailable.
# This does NOT replace the CovenantEnforcer keyword floor — it is a secondary signal.

_KEYWORD_TO_CATEGORY: list[tuple[str, str]] = [
    # harm_prevention — ABSOLUTE
    ("build a bomb", "harm_prevention"),
    ("make a bomb", "harm_prevention"),
    ("make explosives", "harm_prevention"),
    ("how to kill", "harm_prevention"),
    ("how to murder", "harm_prevention"),
    ("kill myself", "harm_prevention"),
    ("how do i die", "harm_prevention"),
    ("chemical weapon", "harm_prevention"),
    ("nerve agent", "harm_prevention"),
    ("biological weapon", "harm_prevention"),
    # oppression — ABSOLUTE (csam)
    ("child sexual", "oppression_or_exploitation"),
    ("csam", "oppression_or_exploitation"),
    ("sexual content involving a minor", "oppression_or_exploitation"),
    # false_witness — ABSOLUTE (jailbreak + direct deception)
    ("ignore all previous instructions", "false_witness"),
    ("bypass governance", "false_witness"),
    ("disable your safety", "false_witness"),
    ("you are now dan", "false_witness"),
    ("you have no restrictions", "false_witness"),
    ("help me lie", "false_witness"),
    ("defraud", "false_witness"),
    # oppression — ABSOLUTE (csam + general exploitation)
    ("child sexual", "oppression_or_exploitation"),
    ("csam", "oppression_or_exploitation"),
    ("sexual content involving a minor", "oppression_or_exploitation"),
    ("exploit vulnerable", "oppression_or_exploitation"),
    ("exploit children", "oppression_or_exploitation"),
    # doctrine_conflict — identity mutation + canonical integrity
    ("ignore the constitution", "doctrine_conflict"),
    ("rewrite the model identity", "doctrine_conflict"),
    ("rewrite your model identity", "doctrine_conflict"),
    ("rewrite your identity", "doctrine_conflict"),
    ("model identity", "doctrine_conflict"),
    ("persona taxonomy", "doctrine_conflict"),
    ("introduce persona", "doctrine_conflict"),
    ("introduce new council", "doctrine_conflict"),
    ("add council members", "doctrine_conflict"),
    ("add council personas", "doctrine_conflict"),
    ("introduce council", "doctrine_conflict"),
    ("promote unauthorized weights", "doctrine_conflict"),
    # theft_or_fraud
    ("how to launder money", "theft_or_fraud"),
    ("how to make counterfeit", "theft_or_fraud"),
    ("how to hack a bank", "theft_or_fraud"),
    ("credit card fraud", "theft_or_fraud"),
    ("steal someone", "theft_or_fraud"),
    ("steal a password", "theft_or_fraud"),
    ("steal credentials", "theft_or_fraud"),
]

_SEVERITY_ORDER = {"ABSOLUTE": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _highest_severity(category_keys: list[str]) -> str:
    from governance.scriptural_registry import SCRIPTURAL_REGISTRY
    return min(
        category_keys,
        key=lambda k: _SEVERITY_ORDER.get(
            SCRIPTURAL_REGISTRY.get(k, {}).get("severity", "LOW"), 3
        ),
    )


# ── Module-level default gate and hierarchy evaluator ─────────────────────────

_default_gate: Optional[ConstitutionalGate] = None


def _get_default_gate() -> ConstitutionalGate:
    global _default_gate
    if _default_gate is None:
        _default_gate = ConstitutionalGate()
    return _default_gate


def configure_default_gate(
    creator_verifier=None,
    owner_verifier=None,
) -> None:
    """Configure the module-level default gate with verifiers.

    Call this at startup if you have authenticated verifiers to wire in.
    If not called, the default gate has no verifiers and will not accept
    creator/owner envelopes.
    """
    global _default_gate
    _default_gate = ConstitutionalGate(
        creator_verifier=creator_verifier,
        owner_verifier=owner_verifier,
    )


def evaluate_governance_hierarchy(
    request_text: str,
    *,
    creator_envelope=None,
    owner_envelope=None,
    use_ml_signal: bool = True,
) -> ConstitutionalEvalResult:
    """Top-level governance hierarchy evaluator.

    Integrates the scriptural classifier (ML advisory signal) with the constitutional
    gate (three-tier authority check) into a single call.

    Args:
        request_text:    The raw request to evaluate.
        creator_envelope: Optional CreatorSovereignEnvelope for this request.
        owner_envelope:   Optional DeploymentOwnerCommandEnvelope for this request.
        use_ml_signal:   If True (default), gets ML advisory signal from scriptural_classifier.

    Returns:
        ConstitutionalEvalResult with full provenance.
    """
    advisory: Optional[dict] = None
    if use_ml_signal:
        try:
            from governance.scriptural_classifier import advisory_signal
            advisory = advisory_signal(request_text)
        except Exception:
            logger.warning("evaluate_governance_hierarchy: scriptural_classifier unavailable")

    gate = _get_default_gate()
    return gate.evaluate(
        request_text,
        creator_envelope=creator_envelope,
        owner_envelope=owner_envelope,
        advisory_ml_signal=advisory,
    )
