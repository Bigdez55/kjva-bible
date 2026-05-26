"""Local invariant engine stubs for the Tokenless agent package."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class InvariantSeverity:
    """Simple severity labels for local fallback invariants."""

    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    FATAL = "fatal"


@dataclass
class InvariantViolation:
    """A local invariant violation record."""

    invariant_name: str = ""
    agent_id: str = ""
    severity: str = InvariantSeverity.WARNING
    details: str = ""


class InvariantEngine:
    """Minimal local invariant engine with pluggable checkers."""

    def __init__(self) -> None:
        self._checkers: dict[str, Callable[[], bool]] = {}

    def register_invariant(self, name: str, checker: Callable[[], bool]) -> None:
        self._checkers[name] = checker

    def check_all(self) -> list[InvariantViolation]:
        violations: list[InvariantViolation] = []
        for name, checker in self._checkers.items():
            try:
                ok = bool(checker())
            except Exception as exc:  # noqa: BLE001
                violations.append(
                    InvariantViolation(name, severity=InvariantSeverity.ERROR, details=str(exc))
                )
                continue
            if not ok:
                violations.append(InvariantViolation(name, severity=InvariantSeverity.ERROR))
        return violations

    def enforce(self) -> None:
        violations = self.check_all()
        fatal = [v for v in violations if v.severity in {InvariantSeverity.CRITICAL, InvariantSeverity.FATAL}]
        if fatal:
            raise RuntimeError(f"fatal invariant violation: {fatal[0].invariant_name}")


def build_heptagon_engine() -> InvariantEngine:
    """Return the local fallback invariant engine."""

    return InvariantEngine()


__all__ = [
    "InvariantEngine",
    "InvariantViolation",
    "InvariantSeverity",
    "build_heptagon_engine",
]
