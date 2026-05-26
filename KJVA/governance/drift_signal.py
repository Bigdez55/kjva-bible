"""Citadel/governance/drift_signal.py — Drift Signal

SPDX-License-Identifier: MIT

Sarah's anti-drift machinery. Tracks identity regression over
rolling windows. If DriftIndex crosses threshold, shifts from
full autonomy to conditional mode.

Source: Sarah's Heptagon L5 metrics + Covenant Stewardship doctrine
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List


@dataclass
class DriftSignal:
    """A single drift measurement."""
    timestamp: float = field(default_factory=time.time)
    policy_override_rate: float = 0.0     # How often is policy overridden?
    exception_rate: float = 0.0           # How many exceptions to doctrine?
    goal_divergence: float = 0.0          # How far from founding goals?
    reversal_rate: float = 0.0            # How often are decisions reversed?
    mode_mismatch: float = 0.0            # Operating outside declared mode?
    artifact_inconsistency: float = 0.0   # Artifacts contradict each other?
    covenant_violation_count: int = 0     # Covenant rules violated this window


class DriftDetector:
    """Continuous drift detection for Sarah's L5 evaluation.

    Monitors identity regression over rolling windows.
    When DriftIndex exceeds threshold → alert + mode restriction.

    The system may evolve but must remain the same covenantal organism.
    """

    def __init__(
        self,
        window_size: int = 100,
        alert_threshold: float = 0.30,
        critical_threshold: float = 0.60,
    ) -> None:
        self.window_size = window_size
        self.alert_threshold = alert_threshold
        self.critical_threshold = critical_threshold
        self._signals: Deque[DriftSignal] = deque(maxlen=window_size)
        self._alerts: List[Dict[str, Any]] = []

    def record(self, signal: DriftSignal) -> None:
        """Record a new drift measurement."""
        self._signals.append(signal)

    def compute_drift_index(self) -> float:
        """Compute the current DriftIndex over the rolling window.

        DriftIndex = weighted sum of all drift dimensions.
        Higher = more drift = more danger.
        """
        if not self._signals:
            return 0.0

        n = len(self._signals)
        weights = {
            "policy_override": 0.20,
            "exception": 0.15,
            "goal_divergence": 0.25,
            "reversal": 0.10,
            "mode_mismatch": 0.15,
            "artifact_inconsistency": 0.10,
            "covenant_violation": 0.05,
        }

        totals = {
            "policy_override": sum(s.policy_override_rate for s in self._signals) / n,
            "exception": sum(s.exception_rate for s in self._signals) / n,
            "goal_divergence": sum(s.goal_divergence for s in self._signals) / n,
            "reversal": sum(s.reversal_rate for s in self._signals) / n,
            "mode_mismatch": sum(s.mode_mismatch for s in self._signals) / n,
            "artifact_inconsistency": sum(s.artifact_inconsistency for s in self._signals) / n,
            "covenant_violation": min(
                sum(s.covenant_violation_count for s in self._signals) / max(n, 1) / 5.0,
                1.0,
            ),
        }

        return sum(weights[k] * totals[k] for k in weights)

    def check(self) -> Dict[str, Any]:
        """Check current drift state and generate alerts if needed."""
        index = self.compute_drift_index()

        status = "GREEN"
        action = "none"

        if index >= self.critical_threshold:
            status = "CRITICAL"
            action = "freeze_all_identity_changes"
            self._alerts.append({
                "timestamp": time.time(),
                "drift_index": index,
                "status": status,
                "action": action,
            })
        elif index >= self.alert_threshold:
            status = "WARNING"
            action = "shift_to_conditional_mode"
            self._alerts.append({
                "timestamp": time.time(),
                "drift_index": index,
                "status": status,
                "action": action,
            })

        return {
            "drift_index": round(index, 4),
            "status": status,
            "action": action,
            "window_size": len(self._signals),
            "alert_count": len(self._alerts),
        }

    def get_alerts(self) -> List[Dict[str, Any]]:
        return list(self._alerts)
