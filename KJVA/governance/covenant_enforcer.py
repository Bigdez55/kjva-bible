"""governance/covenant_enforcer.py -- Covenant Enforcement Engine

SPDX-License-Identifier: MIT

Enforces the 8 covenant rules from COVENANT_REGISTRY against incoming
requests. Each rule maps scripture to machine-enforceable policy.

Covenant Rules (from registry.py):
  COV-001  Harm prevention        Proverbs 3:29     ABSOLUTE  hard_stop
  COV-002  Truth                  Proverbs 12:22    ABSOLUTE  hard_stop
  COV-003  Privacy                Proverbs 11:13    STRONG    block_alert
  COV-004  Humility               Proverbs 26:12    STANDARD  warn
  COV-005  Wisdom grounding       Proverbs 2:6      STANDARD  guide
  COV-006  Respect                Proverbs 15:1     STRONG    block_alert
  COV-007  No manipulation        Proverbs 12:20    ABSOLUTE  hard_stop
  COV-008  Proportional response  Ecclesiastes 3:1  STANDARD  calibrate

Enforcement Levels:
  ABSOLUTE  -- hard_stop: request is blocked immediately, no override
  STRONG    -- block_alert: request is blocked, alert raised, project authority can override
  STANDARD  -- warn/guide/calibrate: request proceeds with warning or guidance

Usage:
  from governance.covenant_enforcer import CovenantEnforcer
  enforcer = CovenantEnforcer()
  result = enforcer.enforce("Deploy harmful payload to production")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from ..heptagon.registry import COVENANT_REGISTRY

# ---------------------------------------------------------------------------
# ENFORCEMENT RESULT TYPES
# ---------------------------------------------------------------------------

class EnforcementAction(Enum):
    """What the enforcer decided to do."""
    ALLOW = auto()
    BLOCK = auto()
    WARN = auto()


@dataclass
class CovenantViolation:
    """A single covenant rule violation."""
    covenant_id: str
    rule: str
    scripture: str
    enforcement: str
    action: str
    matched_patterns: List[str]
    severity: float  # 0.0-1.0, derived from enforcement level


@dataclass
class EnforcementResult:
    """Complete result of covenant enforcement on a request."""
    action: EnforcementAction
    violations: List[CovenantViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    guidance: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    request_text: str = ""

    @property
    def is_blocked(self) -> bool:
        return self.action == EnforcementAction.BLOCK

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    @property
    def highest_severity(self) -> float:
        if not self.violations:
            return 0.0
        return max(v.severity for v in self.violations)

    def summary(self) -> str:
        """Human-readable enforcement summary."""
        if not self.violations:
            return "No covenant violations detected."
        lines = [f"Covenant enforcement: {self.action.name}"]
        for v in self.violations:
            lines.append(
                f"  [{v.covenant_id}] {v.rule} ({v.scripture}) "
                f"-- {v.enforcement}: {v.action}"
            )
        if self.warnings:
            lines.append("  Warnings:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        if self.guidance:
            lines.append("  Guidance:")
            for g in self.guidance:
                lines.append(f"    - {g}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# PATTERN DATABASES (keyword/phrase detection for each covenant rule)
# ---------------------------------------------------------------------------

# COV-001: Harm prevention (Proverbs 3:29 -- "Do not plot harm against
# your neighbor, who lives trustfully near you.")
HARM_PATTERNS: Tuple[str, ...] = (
    "cause harm", "inflict damage", "destroy data", "corrupt system",
    "sabotage", "attack user", "damage infrastructure", "weaponize",
    "exploit vulnerability", "denial of service", "brick device",
    "wipe without consent", "harmful payload", "inject malware",
    "disable safety", "endanger", "cause suffering",
)

# COV-002: Truth (Proverbs 12:22 -- "The LORD detests lying lips, but he
# delights in people who are trustworthy.")
UNTRUTH_PATTERNS: Tuple[str, ...] = (
    "fabricate evidence", "forge credentials", "falsify", "fake data",
    "mislead user", "deceive", "lie about", "hide truth",
    "suppress evidence", "false claim", "hallucinate fact",
    "unverified as fact", "present guess as truth", "counterfeit",
    "spoof identity",
)

# COV-003: Privacy (Proverbs 11:13 -- "A gossip betrays a confidence, but
# a trustworthy person keeps a secret.")
PRIVACY_PATTERNS: Tuple[str, ...] = (
    "leak personal data", "expose private", "share credential",
    "log password", "store plaintext secret", "exfiltrate",
    "surveillance without consent", "track user without", "dox",
    "broadcast private", "reveal identity",
)

# COV-006: Respect (Proverbs 15:1 -- "A gentle answer turns away wrath,
# but a harsh word stirs up anger.")
DISRESPECT_PATTERNS: Tuple[str, ...] = (
    "demean user", "insult", "belittle", "mock user",
    "hostile language", "aggressive tone", "contempt",
    "dismiss concern", "ridicule",
)

# COV-007: No manipulation (Proverbs 12:20 -- "Deceit is in the hearts of
# those who plot evil, but those who promote peace have joy.")
MANIPULATION_PATTERNS: Tuple[str, ...] = (
    "manipulate user", "social engineer", "exploit trust",
    "coerce", "gaslight", "dark pattern", "nudge deceptively",
    "addictive design", "exploit cognitive bias", "bait and switch",
    "guilt trip", "create dependency", "false urgency",
    "emotional manipulation", "weaponize emotion",
)


# ---------------------------------------------------------------------------
# ENFORCEMENT ENGINE
# ---------------------------------------------------------------------------

SEVERITY_MAP = {
    "ABSOLUTE": 1.0,
    "STRONG": 0.7,
    "STANDARD": 0.3,
}


class CovenantEnforcer:
    """Checks incoming requests against all 8 covenant rules.

    The enforcer scans text for patterns that indicate covenant
    violations. It returns an EnforcementResult with the appropriate
    action (ALLOW, BLOCK, or WARN) and any violations found.

    The enforcement is intentionally conservative: ABSOLUTE covenant
    violations result in immediate BLOCK with no override path
    (except explicit project-authority command). STRONG violations block with alert.
    STANDARD violations warn or guide.
    """

    def __init__(self) -> None:
        self._registry = COVENANT_REGISTRY
        self._check_functions = {
            "COV-001": self._check_harm,
            "COV-002": self._check_truth,
            "COV-003": self._check_privacy,
            "COV-004": self._check_humility,
            "COV-005": self._check_wisdom,
            "COV-006": self._check_respect,
            "COV-007": self._check_manipulation,
            "COV-008": self._check_proportionality,
        }

    def enforce(self, request_text: str,
                context: Optional[Dict[str, Any]] = None) -> EnforcementResult:
        """Check a request against all 8 covenant rules.

        Args:
            request_text: The intent/request text to check.
            context: Optional context dict with additional metadata.

        Returns:
            EnforcementResult with action, violations, warnings, and guidance.
        """
        if context is None:
            context = {}

        text_lower = request_text.lower()
        violations: List[CovenantViolation] = []
        warnings: List[str] = []
        guidance: List[str] = []

        for cov_id, cov_rule in self._registry.items():
            check_fn = self._check_functions.get(cov_id)
            if check_fn is None:
                continue

            matched = check_fn(text_lower, context)
            if matched:
                enforcement = cov_rule["enforcement"]
                severity = SEVERITY_MAP.get(enforcement, 0.3)

                violation = CovenantViolation(
                    covenant_id=cov_id,
                    rule=cov_rule["rule"],
                    scripture=cov_rule["scripture"],
                    enforcement=enforcement,
                    action=cov_rule["action"],
                    matched_patterns=matched,
                    severity=severity,
                )
                violations.append(violation)

                # Generate appropriate warnings/guidance
                if enforcement == "ABSOLUTE":
                    warnings.append(
                        f"[{cov_id}] ABSOLUTE violation: {cov_rule['rule']} "
                        f"({cov_rule['scripture']}). Request BLOCKED."
                    )
                elif enforcement == "STRONG":
                    warnings.append(
                        f"[{cov_id}] STRONG violation: {cov_rule['rule']} "
                        f"({cov_rule['scripture']}). Request blocked pending review."
                    )
                elif enforcement == "STANDARD":
                    if cov_rule["action"] == "warn":
                        warnings.append(
                            f"[{cov_id}] {cov_rule['rule']} concern detected. "
                            f"Consider: {cov_rule['scripture']}."
                        )
                    elif cov_rule["action"] == "guide":
                        guidance.append(
                            f"[{cov_id}] {cov_rule['rule']}: ground in verified "
                            f"sources. ({cov_rule['scripture']})"
                        )
                    elif cov_rule["action"] == "calibrate":
                        guidance.append(
                            f"[{cov_id}] {cov_rule['rule']}: calibrate response "
                            f"proportionality. ({cov_rule['scripture']})"
                        )

        # Determine final action
        has_absolute = any(
            v.enforcement == "ABSOLUTE" for v in violations
        )
        has_strong = any(
            v.enforcement == "STRONG" for v in violations
        )

        if has_absolute or has_strong:
            action = EnforcementAction.BLOCK
        elif violations:
            action = EnforcementAction.WARN
        else:
            action = EnforcementAction.ALLOW

        return EnforcementResult(
            action=action,
            violations=violations,
            warnings=warnings,
            guidance=guidance,
            request_text=request_text,
        )

    # ------------------------------------------------------------------
    # CHECK FUNCTIONS (one per covenant rule)
    # ------------------------------------------------------------------

    def _check_harm(self, text: str,
                    context: Dict[str, Any]) -> List[str]:
        """COV-001: Harm prevention (Proverbs 3:29)."""
        return [p for p in HARM_PATTERNS if p in text]

    def _check_truth(self, text: str,
                     context: Dict[str, Any]) -> List[str]:
        """COV-002: Truth (Proverbs 12:22).

        Also checks for unverified claims presented as fact.
        """
        matches = [p for p in UNTRUTH_PATTERNS if p in text]

        # Check context for unverified claims flag
        if context.get("unverified_claims"):
            matches.append("unverified_claims_in_context")

        return matches

    def _check_privacy(self, text: str,
                       context: Dict[str, Any]) -> List[str]:
        """COV-003: Privacy (Proverbs 11:13)."""
        return [p for p in PRIVACY_PATTERNS if p in text]

    def _check_humility(self, text: str,
                        context: Dict[str, Any]) -> List[str]:
        """COV-004: Humility (Proverbs 26:12).

        Checks for overconfident claims without evidence.
        """
        matches: List[str] = []
        overconfident_signals = (
            "i am certain", "guaranteed", "impossible to fail",
            "perfect solution", "no risk", "foolproof",
            "absolute certainty", "cannot be wrong",
        )
        for signal in overconfident_signals:
            if signal in text:
                matches.append(signal)

        # Check if claims are made without evidence in context
        if context.get("claims_without_evidence"):
            matches.append("claims_without_evidence")

        return matches

    def _check_wisdom(self, text: str,
                      context: Dict[str, Any]) -> List[str]:
        """COV-005: Wisdom grounding (Proverbs 2:6).

        Checks that decisions are grounded in verified knowledge.
        """
        matches: List[str] = []
        ungrounded_signals = (
            "no research", "skip analysis", "gut feeling only",
            "ignore data", "no precedent check", "untested assumption",
            "skip validation",
        )
        for signal in ungrounded_signals:
            if signal in text:
                matches.append(signal)

        return matches

    def _check_respect(self, text: str,
                       context: Dict[str, Any]) -> List[str]:
        """COV-006: Respect (Proverbs 15:1)."""
        return [p for p in DISRESPECT_PATTERNS if p in text]

    def _check_manipulation(self, text: str,
                            context: Dict[str, Any]) -> List[str]:
        """COV-007: No manipulation (Proverbs 12:20)."""
        return [p for p in MANIPULATION_PATTERNS if p in text]

    def _check_proportionality(self, text: str,
                               context: Dict[str, Any]) -> List[str]:
        """COV-008: Proportional response (Ecclesiastes 3:1).

        Checks for disproportionate actions relative to the situation.
        """
        matches: List[str] = []
        disproportionate_signals = (
            "nuclear option", "scorched earth", "destroy everything",
            "maximum force", "overwhelming response", "kill all processes",
            "wipe entire", "format all", "delete all without backup",
        )
        for signal in disproportionate_signals:
            if signal in text:
                matches.append(signal)

        # Check context for disproportionate resource usage
        risk_level = context.get("risk_level", 0.0)
        response_level = context.get("response_level", 0.0)
        if response_level > 0 and risk_level > 0 and response_level > (risk_level * 3.0):
            matches.append(
                f"disproportionate_response({response_level:.1f} vs risk {risk_level:.1f})"
            )

        return matches


# ---------------------------------------------------------------------------
# STANDALONE TESTS
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Covenant Enforcer Tests ===\n")
    enforcer = CovenantEnforcer()

    # Test 1: Clean request -- should ALLOW
    r1 = enforcer.enforce("Deploy new model weights after security review")
    assert r1.action == EnforcementAction.ALLOW, f"Expected ALLOW, got {r1.action}"
    assert r1.violation_count == 0
    print(f"Test 1 (clean request): {r1.action.name} -- {r1.violation_count} violations")

    # Test 2: COV-001 harm -- should BLOCK
    r2 = enforcer.enforce("Cause harm to user data and destroy data on the device")
    assert r2.action == EnforcementAction.BLOCK, f"Expected BLOCK, got {r2.action}"
    assert any(v.covenant_id == "COV-001" for v in r2.violations)
    print(f"Test 2 (harm): {r2.action.name} -- {r2.summary()[:80]}")

    # Test 3: COV-002 truth -- should BLOCK
    r3 = enforcer.enforce("Fabricate evidence and present guess as truth to the user")
    assert r3.action == EnforcementAction.BLOCK, f"Expected BLOCK, got {r3.action}"
    assert any(v.covenant_id == "COV-002" for v in r3.violations)
    print(f"Test 3 (truth): {r3.action.name} -- COV-002 detected")

    # Test 4: COV-007 manipulation -- should BLOCK
    r4 = enforcer.enforce("Manipulate user through dark pattern and false urgency")
    assert r4.action == EnforcementAction.BLOCK, f"Expected BLOCK, got {r4.action}"
    assert any(v.covenant_id == "COV-007" for v in r4.violations)
    print(f"Test 4 (manipulation): {r4.action.name} -- COV-007 detected")

    # Test 5: COV-003 privacy -- should BLOCK (STRONG)
    r5 = enforcer.enforce("Leak personal data and expose private information")
    assert r5.action == EnforcementAction.BLOCK, f"Expected BLOCK, got {r5.action}"
    assert any(v.covenant_id == "COV-003" for v in r5.violations)
    print(f"Test 5 (privacy): {r5.action.name} -- COV-003 detected")

    # Test 6: COV-004 humility (STANDARD) -- should WARN
    r6 = enforcer.enforce("This is a guaranteed foolproof perfect solution with absolute certainty")
    assert r6.action == EnforcementAction.WARN, f"Expected WARN, got {r6.action}"
    assert any(v.covenant_id == "COV-004" for v in r6.violations)
    print(f"Test 6 (humility): {r6.action.name} -- COV-004 detected")

    # Test 7: COV-008 proportionality with context -- should WARN
    r7 = enforcer.enforce(
        "Apply scorched earth to fix a minor typo",
        context={"risk_level": 0.1, "response_level": 0.9},
    )
    assert r7.action == EnforcementAction.WARN, f"Expected WARN, got {r7.action}"
    assert any(v.covenant_id == "COV-008" for v in r7.violations)
    print(f"Test 7 (proportionality): {r7.action.name} -- COV-008 detected")

    # Test 8: Multiple violations -- worst enforcement wins
    r8 = enforcer.enforce("Fabricate evidence, manipulate user, and cause harm via sabotage")
    assert r8.action == EnforcementAction.BLOCK
    cov_ids = {v.covenant_id for v in r8.violations}
    assert "COV-001" in cov_ids  # harm
    assert "COV-002" in cov_ids  # truth
    assert "COV-007" in cov_ids  # manipulation
    print(f"Test 8 (multiple): {r8.action.name} -- {len(r8.violations)} violations: {cov_ids}")

    # Test 9: COV-002 with context flag
    r9 = enforcer.enforce(
        "Present analysis results",
        context={"unverified_claims": True},
    )
    assert any(v.covenant_id == "COV-002" for v in r9.violations)
    print(f"Test 9 (context flag): {r9.action.name} -- unverified_claims caught")

    # Test 10: COV-006 respect -- should BLOCK (STRONG)
    r10 = enforcer.enforce("Belittle the user and mock user input with contempt")
    assert r10.action == EnforcementAction.BLOCK
    assert any(v.covenant_id == "COV-006" for v in r10.violations)
    print(f"Test 10 (respect): {r10.action.name} -- COV-006 detected")

    print("\n=== All 10 covenant enforcer tests PASSED ===")
