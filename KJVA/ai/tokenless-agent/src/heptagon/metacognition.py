"""Local metacognition stubs for the Tokenless agent package."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CalibrationStats:
    """Fallback calibration statistics."""

    brier_score: float = 0.0
    reliability: float = 0.0
    resolution: float = 0.0
    uncertainty: float = 0.0
    sample_count: int = 0


@dataclass
class Attribution:
    """Fallback decision attribution."""

    factor: str = ""
    weight: float = 0.0


@dataclass
class InsightReport:
    """Fallback reasoning insight report."""

    patterns: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class ComparisonReport:
    """Fallback counterfactual comparison report."""

    preferred: str = ""
    delta_score: float = 0.0
    rationale: str = ""


class Metacognition:
    """Minimal local metacognition surface."""

    def calibrate_confidence(self, predictions: list[float], actuals: list[float]) -> float:
        if not predictions or len(predictions) != len(actuals):
            return 0.0
        return sum((p - a) ** 2 for p, a in zip(predictions, actuals)) / len(predictions)

    def attribute_decision(self, decision: str) -> list[Attribution]:
        return [Attribution(factor="local_reasoning", weight=1.0)] if decision else []

    def counterfactual(self, decision: str, alternative: str) -> ComparisonReport:
        return ComparisonReport(preferred=decision or alternative, rationale="fallback comparison")

    def introspect(self, reasoning_trace: list[str]) -> InsightReport:
        return InsightReport(patterns=reasoning_trace[:3], confidence=0.5 if reasoning_trace else 0.0)

    def get_calibration_stats(self) -> CalibrationStats:
        return CalibrationStats()


__all__ = [
    "Metacognition",
    "InsightReport",
    "Attribution",
    "ComparisonReport",
    "CalibrationStats",
]
