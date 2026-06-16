"""Backend-local governance decision outcome.

``DecisionOutcome`` is the value object kjva_runtime.py threads through the
constitution -> governance -> heptagon -> soul_manager pipeline. The original
``KJVA.governance.runtime_outcome`` module was removed in the 2026-06 KJVA migration;
the HTTP adapter (``backend``) owns its own outcome type here. Reconstructed from
kjva_runtime.py's usage contract (the .allow/.warn/.deny classmethods and the
.allowed/.trace_id/.authority/.reason_code/.detail/.to_dict() surface it reads).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class DecisionOutcome:
    trace_id: str
    authority: str
    reason_code: str
    allowed: bool
    detail: str = ""
    severity: str = "INFO"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def allow(
        cls,
        trace_id: str,
        authority: str,
        reason_code: str,
        detail: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "DecisionOutcome":
        return cls(trace_id, authority, reason_code, True, detail or "", "INFO", dict(metadata or {}))

    @classmethod
    def warn(
        cls,
        trace_id: str,
        authority: str,
        reason_code: str,
        detail: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "DecisionOutcome":
        # A warning still permits the action (allowed=True) but flags disclosure.
        return cls(trace_id, authority, reason_code, True, detail or "", "WARN", dict(metadata or {}))

    @classmethod
    def deny(
        cls,
        trace_id: str,
        authority: str,
        reason_code: str,
        detail: str = "",
        severity: str = "ERROR",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "DecisionOutcome":
        return cls(trace_id, authority, reason_code, False, detail or "", severity, dict(metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "authority": self.authority,
            "reason_code": self.reason_code,
            "allowed": self.allowed,
            "detail": self.detail,
            "severity": self.severity,
            "metadata": self.metadata,
        }
