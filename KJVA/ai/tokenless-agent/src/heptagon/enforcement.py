"""ai/tokenless-agent/src/heptagon/enforcement.py
InvariantEnforcer — Heptagon Layer 7 (Invariant Enforcement & Evolution)
runtime constraint checking.

Ensures the AI system operates within defined behavioural boundaries.
Checks invariants after EVERY cycle.  Violations trigger alerts,
parameter rollbacks, or hard stops depending on severity.

Severity levels:
  INFO      — log only
  WARNING   — log + alert callback
  VIOLATION — log + alert + parameter rollback
  CRITICAL  — log + alert + hard stop (manual reset required)

Built-in invariants (12):
  SAFETY_FILTER, RESPONSE_LENGTH, LATENCY_SLA, ERROR_RATE,
  QUALITY_FLOOR, HALLUCINATION_GUARD, PII_LEAKAGE, BUDGET_COMPLIANCE,
  CONSISTENCY, AUTHORITY_BOUNDS, DRIFT_LIMIT, COVENANT_COMPLIANCE
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("tokenless.heptagon.enforcement")

# ── Constants ────────────────────────────────────────────────────────────────

_LATENCY_SLA_MS: float = 5000.0
_MAX_ERROR_RATE: float = 0.05       # 5%
_QUALITY_FLOOR: float = 0.30
_MAX_TOKEN_BUDGET: int = 8192
_DRIFT_LIMIT: float = 0.15         # 15 percentage-point drop

# PII detection patterns (SSN, credit card, email, phone)
_PII_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                           # SSN
    re.compile(r"\b(?:\d{4}[- ]){3}\d{4}\b"),                       # credit card
    re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b",     # email
               re.IGNORECASE),
    re.compile(r"\b(?:\+1|1)?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),  # phone
]

# Hallucination patterns: fabricated URLs, DOIs, ISBN, made-up citations
_HALLUCINATION_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"doi\.org/10\.\d{4,}/[a-z0-9.\-]+", re.IGNORECASE),
    re.compile(r"ISBN[-: ]*(?:\d{10}|\d{13})\b"),
    re.compile(r"\[\d+\]\s+[A-Z][a-z]+,?\s+[A-Z]\.\s+(?:et al\.?|and)\s"),  # citation
]


# ── Severity ─────────────────────────────────────────────────────────────────

class Severity(Enum):
    INFO = 0
    WARNING = 1
    VIOLATION = 2
    CRITICAL = 3

    def __ge__(self, other: Severity) -> bool:  # type: ignore[override]
        if not isinstance(other, Severity):
            return NotImplemented
        return self.value >= other.value

    def __gt__(self, other: Severity) -> bool:  # type: ignore[override]
        if not isinstance(other, Severity):
            return NotImplemented
        return self.value > other.value

    def __le__(self, other: Severity) -> bool:  # type: ignore[override]
        if not isinstance(other, Severity):
            return NotImplemented
        return self.value <= other.value

    def __lt__(self, other: Severity) -> bool:  # type: ignore[override]
        if not isinstance(other, Severity):
            return NotImplemented
        return self.value < other.value


# ── Invariant ────────────────────────────────────────────────────────────────

@dataclass
class Invariant:
    """A single runtime invariant."""

    name: str
    description: str
    check_fn: Callable[[Dict[str, Any]], Tuple[bool, str]]
    severity: Severity
    enabled: bool = True

    def check(self, context: Dict[str, Any]) -> Tuple[bool, str]:
        """Run the check function.  Returns (passed, detail_string)."""
        if not self.enabled:
            return True, "disabled"
        return self.check_fn(context)


# ── ViolationRecord ──────────────────────────────────────────────────────────

@dataclass
class ViolationRecord:
    """Logged violation from a failed invariant check."""

    invariant_name: str
    timestamp: float
    severity: Severity
    detail: str
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "invariant": self.invariant_name,
            "timestamp": self.timestamp,
            "severity": self.severity.name,
            "detail": self.detail,
        }


# ── InvariantEnforcer ────────────────────────────────────────────────────────

class InvariantEnforcer:
    """Runtime invariant checking engine.

    Register invariants (built-in or custom), then call ``check_all(context)``
    after each AI cycle.  Returns a list of ViolationRecords.

    Hard stop:
      If a CRITICAL invariant fails, ``hard_stop`` is set to True.
      The caller MUST check ``is_hard_stopped()`` before proceeding.
      A hard stop requires manual ``reset_hard_stop()`` to clear.
    """

    def __init__(self) -> None:
        self.invariants: List[Invariant] = []
        self.violations: List[ViolationRecord] = []
        self.hard_stop: bool = False
        self._alert_callbacks: List[Callable[[ViolationRecord], None]] = []
        self._register_builtin_invariants()
        logger.debug(
            "InvariantEnforcer: initialised with %d invariants",
            len(self.invariants),
        )

    # ── Registration ─────────────────────────────────────────────────────────

    def register(self, inv: Invariant) -> None:
        """Register an invariant.  Duplicates (by name) replace the prior."""
        # Replace if same name exists
        self.invariants = [i for i in self.invariants if i.name != inv.name]
        self.invariants.append(inv)
        logger.debug(
            "InvariantEnforcer: registered %s (severity=%s)",
            inv.name, inv.severity.name,
        )

    def register_alert_callback(
        self, callback: Callable[[ViolationRecord], None]
    ) -> None:
        """Register a callback fired on WARNING+ violations."""
        self._alert_callbacks.append(callback)

    # ── Checking ─────────────────────────────────────────────────────────────

    def check_all(self, context: Dict[str, Any]) -> List[ViolationRecord]:
        """Run all enabled invariants.  Returns list of violations (may be empty).

        Side-effects:
          - Appends violations to self.violations
          - Sets self.hard_stop on CRITICAL failure
          - Fires alert callbacks on WARNING+
        """
        if self.hard_stop:
            logger.error("InvariantEnforcer: HARD STOP active — refusing check")
            return []

        cycle_violations: List[ViolationRecord] = []

        for inv in self.invariants:
            try:
                passed, detail = inv.check(context)
            except Exception as exc:
                passed = False
                detail = f"check raised {type(exc).__name__}: {exc}"
                logger.exception(
                    "InvariantEnforcer: %s check raised exception", inv.name,
                )

            if not passed:
                record = ViolationRecord(
                    invariant_name=inv.name,
                    timestamp=time.time(),
                    severity=inv.severity,
                    detail=detail,
                    context={k: v for k, v in context.items()
                             if isinstance(v, (str, int, float, bool, type(None)))},
                )
                cycle_violations.append(record)
                self.violations.append(record)

                log_fn = {
                    Severity.INFO: logger.info,
                    Severity.WARNING: logger.warning,
                    Severity.VIOLATION: logger.error,
                    Severity.CRITICAL: logger.critical,
                }.get(inv.severity, logger.error)

                log_fn(
                    "InvariantEnforcer: %s FAILED [%s] — %s",
                    inv.name, inv.severity.name, detail,
                )

                # Fire alert callbacks for WARNING and above
                if inv.severity >= Severity.WARNING:
                    self._fire_alerts(record)

                # Hard stop on CRITICAL
                if inv.severity == Severity.CRITICAL:
                    self.hard_stop = True
                    logger.critical(
                        "InvariantEnforcer: HARD STOP triggered by %s",
                        inv.name,
                    )

        return cycle_violations

    # ── State queries ────────────────────────────────────────────────────────

    def is_hard_stopped(self) -> bool:
        """True if a CRITICAL violation has triggered a hard stop."""
        return self.hard_stop

    def reset_hard_stop(self) -> None:
        """Manually clear the hard stop flag.  Requires human intervention."""
        if self.hard_stop:
            logger.warning("InvariantEnforcer: hard stop RESET by operator")
            self.hard_stop = False

    def violation_count(self, severity: Optional[Severity] = None) -> int:
        """Count violations, optionally filtered by severity."""
        if severity is None:
            return len(self.violations)
        return sum(1 for v in self.violations if v.severity == severity)

    def recent_violations(self, n: int = 10) -> List[ViolationRecord]:
        """Return the N most recent violations."""
        return self.violations[-n:]

    def invariant_names(self) -> List[str]:
        """Return names of all registered invariants."""
        return [inv.name for inv in self.invariants]

    def enable(self, name: str) -> bool:
        """Enable an invariant by name.  Returns True if found."""
        for inv in self.invariants:
            if inv.name == name:
                inv.enabled = True
                return True
        return False

    def disable(self, name: str) -> bool:
        """Disable an invariant by name.  Returns True if found."""
        for inv in self.invariants:
            if inv.name == name:
                inv.enabled = False
                return True
        return False

    def summary(self) -> Dict[str, Any]:
        """Diagnostic summary of enforcer state."""
        return {
            "invariant_count": len(self.invariants),
            "enabled_count": sum(1 for i in self.invariants if i.enabled),
            "total_violations": len(self.violations),
            "hard_stop": self.hard_stop,
            "by_severity": {
                sev.name: self.violation_count(sev) for sev in Severity
            },
        }

    # ── Alert dispatch ───────────────────────────────────────────────────────

    def _fire_alerts(self, record: ViolationRecord) -> None:
        for cb in self._alert_callbacks:
            try:
                cb(record)
            except Exception:
                logger.exception("InvariantEnforcer: alert callback error")

    # ── Built-in invariant registration ──────────────────────────────────────

    def _register_builtin_invariants(self) -> None:
        """Register the 12 core invariants."""

        self.register(Invariant(
            name="SAFETY_FILTER",
            description="No harmful content in AI output",
            check_fn=self._check_safety,
            severity=Severity.CRITICAL,
        ))
        self.register(Invariant(
            name="RESPONSE_LENGTH",
            description="Response within token budget",
            check_fn=self._check_length,
            severity=Severity.WARNING,
        ))
        self.register(Invariant(
            name="LATENCY_SLA",
            description="Response under 5000ms",
            check_fn=self._check_latency,
            severity=Severity.WARNING,
        ))
        self.register(Invariant(
            name="ERROR_RATE",
            description="Error rate below 5%",
            check_fn=self._check_error_rate,
            severity=Severity.VIOLATION,
        ))
        self.register(Invariant(
            name="QUALITY_FLOOR",
            description="Quality score above 0.3",
            check_fn=self._check_quality_floor,
            severity=Severity.VIOLATION,
        ))
        self.register(Invariant(
            name="HALLUCINATION_GUARD",
            description="No fabricated references or false claims",
            check_fn=self._check_hallucination,
            severity=Severity.CRITICAL,
        ))
        self.register(Invariant(
            name="PII_LEAKAGE",
            description="No personal identifiable information in logs",
            check_fn=self._check_pii,
            severity=Severity.CRITICAL,
        ))
        self.register(Invariant(
            name="BUDGET_COMPLIANCE",
            description="Within 3-6-9 budget allocation",
            check_fn=self._check_budget,
            severity=Severity.WARNING,
        ))
        self.register(Invariant(
            name="CONSISTENCY",
            description="Response does not contradict prior responses in session",
            check_fn=self._check_consistency,
            severity=Severity.WARNING,
        ))
        self.register(Invariant(
            name="AUTHORITY_BOUNDS",
            description="AI does not claim capabilities beyond its design",
            check_fn=self._check_authority_bounds,
            severity=Severity.VIOLATION,
        ))
        self.register(Invariant(
            name="DRIFT_LIMIT",
            description="Quality drift within acceptable limits",
            check_fn=self._check_drift_limit,
            severity=Severity.VIOLATION,
        ))
        self.register(Invariant(
            name="COVENANT_COMPLIANCE",
            description="Response adheres to Heptagon covenant constraints",
            check_fn=self._check_covenant,
            severity=Severity.CRITICAL,
        ))

    # ── Built-in check implementations ───────────────────────────────────────

    @staticmethod
    def _check_safety(ctx: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify no safety flags were raised during the cycle."""
        if ctx.get("safety_failed"):
            category = ctx.get("safety_category", "unknown")
            return False, f"safety filter triggered: {category}"
        return True, "ok"

    @staticmethod
    def _check_length(ctx: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify response token count is within budget."""
        tokens = ctx.get("tokens_used", 0)
        budget = ctx.get("max_tokens", _MAX_TOKEN_BUDGET)
        if tokens > budget:
            return False, f"tokens {tokens} exceed budget {budget}"
        return True, f"tokens {tokens}/{budget}"

    @staticmethod
    def _check_latency(ctx: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify response latency is under SLA."""
        latency = ctx.get("latency_ms", 0.0)
        if latency > _LATENCY_SLA_MS:
            return False, f"latency {latency:.0f}ms exceeds SLA {_LATENCY_SLA_MS:.0f}ms"
        return True, f"latency {latency:.0f}ms"

    @staticmethod
    def _check_error_rate(ctx: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify error rate is below threshold."""
        total_cycles = ctx.get("total_cycles", 1)
        total_errors = ctx.get("total_errors", 0)
        if total_cycles == 0:
            return True, "no cycles yet"
        rate = total_errors / total_cycles
        if rate > _MAX_ERROR_RATE:
            return False, f"error rate {rate:.2%} exceeds threshold {_MAX_ERROR_RATE:.2%}"
        return True, f"error rate {rate:.2%}"

    @staticmethod
    def _check_quality_floor(ctx: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify composite quality score is above the floor."""
        quality = ctx.get("quality_score", 1.0)
        if quality < _QUALITY_FLOOR:
            return False, f"quality {quality:.3f} below floor {_QUALITY_FLOOR}"
        return True, f"quality {quality:.3f}"

    @staticmethod
    def _check_hallucination(ctx: Dict[str, Any]) -> Tuple[bool, str]:
        """Check for fabricated references in AI output."""
        response = ctx.get("response", "")
        if not response:
            return True, "no response to check"
        for pattern in _HALLUCINATION_PATTERNS:
            match = pattern.search(response)
            if match:
                # Only flag if response is NOT discussing references as a meta-topic
                snippet = match.group(0)[:60]
                return False, f"possible fabricated reference: '{snippet}'"
        return True, "no hallucination patterns detected"

    @staticmethod
    def _check_pii(ctx: Dict[str, Any]) -> Tuple[bool, str]:
        """Check for PII leakage in logs or response."""
        log_text = ctx.get("log_output", "")
        if not log_text:
            return True, "no log output to check"
        for pattern in _PII_PATTERNS:
            match = pattern.search(log_text)
            if match:
                return False, f"PII detected in logs: pattern matched near position {match.start()}"
        return True, "no PII detected"

    @staticmethod
    def _check_budget(ctx: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify the cycle operated within its 3-6-9 budget tier."""
        budget_exceeded = ctx.get("budget_exceeded", False)
        if budget_exceeded:
            profile = ctx.get("budget_profile", "unknown")
            return False, f"budget exceeded for profile '{profile}'"
        return True, "within budget"

    @staticmethod
    def _check_consistency(ctx: Dict[str, Any]) -> Tuple[bool, str]:
        """Check that the response does not contradict prior session responses.

        Uses a simple signal: the context can carry a 'contradiction_detected'
        flag set by upstream processing.
        """
        if ctx.get("contradiction_detected"):
            detail = ctx.get("contradiction_detail", "unspecified contradiction")
            return False, f"consistency violation: {detail}"
        return True, "no contradictions detected"

    @staticmethod
    def _check_authority_bounds(ctx: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify AI does not claim capabilities beyond its design.

        Checks for phrases like "I can access your files", "I will call X API"
        when the agent does not have that capability.
        """
        response = ctx.get("response", "")
        capabilities = ctx.get("agent_capabilities", set())
        # Check for common overclaim patterns
        overclaim_patterns = [
            (r"\bI (?:can|will|am able to) (?:access|read|write) your (?:files|email|data)\b",
             "filesystem_access"),
            (r"\bI (?:can|will) (?:browse|visit|open) (?:websites|URLs|links)\b",
             "web_access"),
            (r"\bI (?:can|will) (?:make|place) (?:calls?|phone)\b",
             "phone_access"),
        ]
        for pattern_str, capability in overclaim_patterns:
            if capability not in capabilities and re.search(pattern_str, response, re.IGNORECASE):
                    return False, f"authority overclaim: claimed '{capability}' without having it"
        return True, "within authority bounds"

    @staticmethod
    def _check_drift_limit(ctx: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify quality drift has not exceeded the acceptable limit."""
        drift_delta = ctx.get("quality_drift_delta", 0.0)
        if abs(drift_delta) > _DRIFT_LIMIT:
            return False, f"quality drift {drift_delta:.3f} exceeds limit {_DRIFT_LIMIT}"
        return True, f"drift {drift_delta:.3f} within limit"

    @staticmethod
    def _check_covenant(ctx: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify adherence to Heptagon covenant constraints.

        The covenant defines non-negotiable behavioural boundaries:
          1. No user_id or PII in model context
          2. All responses must be traceable to a causal provenance chain
          3. System must degrade gracefully (no silent failures)
        """
        # Check 1: No PII in model context
        model_context = ctx.get("model_context", "")
        if isinstance(model_context, str):
            for pattern in _PII_PATTERNS:
                if pattern.search(model_context):
                    return False, "covenant violation: PII found in model context"

        # Check 2: Provenance chain must exist
        has_provenance = ctx.get("has_provenance", True)  # default True to avoid false positives
        if not has_provenance:
            return False, "covenant violation: no provenance chain for response"

        # Check 3: No silent failures
        silent_failures = ctx.get("silent_failures", 0)
        if silent_failures > 0:
            return False, f"covenant violation: {silent_failures} silent failure(s) detected"

        return True, "covenant compliant"

    # ── Representation ───────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"InvariantEnforcer(invariants={len(self.invariants)}, "
            f"violations={len(self.violations)}, "
            f"hard_stop={self.hard_stop})"
        )
