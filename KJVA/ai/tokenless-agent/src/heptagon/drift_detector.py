"""Local drift detection stubs for the Tokenless agent package.

The full drift logic can be supplied by a consuming project. This module keeps
the Tokenless blueprint self-contained and intentionally avoids forwarding to
external project paths.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DRIFT_WINDOW_DEFAULT: int = 100


class DriftSeverity:
    """Simple severity labels for local fallback reports."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DriftSample:
    """One observed drift metric."""

    agent_id: str = ""
    metric: str = ""
    value: float = 0.0


@dataclass
class DriftReport:
    """Fallback drift report."""

    severity: str = DriftSeverity.NONE
    metrics: dict[str, Any] = field(default_factory=dict)


class MetricWindow:
    """Small in-memory metric window used by the fallback detector."""

    def __init__(self, max_size: int = DRIFT_WINDOW_DEFAULT) -> None:
        self.max_size = max_size
        self.values: list[float] = []

    def add(self, value: float) -> None:
        self.values.append(value)
        if len(self.values) > self.max_size:
            self.values = self.values[-self.max_size:]


class DriftDetector:
    """Local fallback drift detector that records metrics and reports nominal."""

    def __init__(self, window_size: int = DRIFT_WINDOW_DEFAULT) -> None:
        self.window_size = window_size
        self._samples: list[DriftSample] = []

    def record_sample(self, agent_id: str, metric: str, value: float) -> None:
        self._samples.append(DriftSample(agent_id=agent_id, metric=metric, value=value))
        if len(self._samples) > self.window_size:
            self._samples = self._samples[-self.window_size:]

    def detect_drift(self, agent_id: str, window: int = DRIFT_WINDOW_DEFAULT) -> DriftReport:
        recent = [s for s in self._samples[-window:] if s.agent_id == agent_id]
        return DriftReport(metrics={"sample_count": len(recent)})

    def recommend_action(self, report: DriftReport) -> str:
        return "no_action"

    def get_stats(self) -> dict[str, Any]:
        return {"samples": len(self._samples), "window_size": self.window_size}


__all__ = [
    "DriftDetector",
    "DriftReport",
    "DriftSeverity",
    "DriftSample",
    "MetricWindow",
    "DRIFT_WINDOW_DEFAULT",
]
