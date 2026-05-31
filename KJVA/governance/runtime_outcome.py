"""Unified policy outcome shape shared by runtime adapters."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class DecisionKind(str, Enum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    DENY = "DENY"


@dataclass(frozen=True)
class DecisionOutcome:
    decision: DecisionKind
    reason_code: str
    severity: str
    authority: str
    trace_id: str
    detail: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision in (DecisionKind.ALLOW, DecisionKind.WARN)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason_code": self.reason_code,
            "severity": self.severity,
            "authority": self.authority,
            "trace_id": self.trace_id,
            "detail": self.detail,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def allow(
        cls,
        trace_id: str,
        authority: str,
        reason_code: str = "ALLOW",
        detail: str = "Allowed",
        metadata: Dict[str, Any] | None = None,
    ) -> "DecisionOutcome":
        return cls(
            decision=DecisionKind.ALLOW,
            reason_code=reason_code,
            severity="INFO",
            authority=authority,
            trace_id=trace_id,
            detail=detail,
            metadata=metadata or {},
        )

    @classmethod
    def warn(
        cls,
        trace_id: str,
        authority: str,
        reason_code: str,
        detail: str,
        metadata: Dict[str, Any] | None = None,
    ) -> "DecisionOutcome":
        return cls(
            decision=DecisionKind.WARN,
            reason_code=reason_code,
            severity="WARN",
            authority=authority,
            trace_id=trace_id,
            detail=detail,
            metadata=metadata or {},
        )

    @classmethod
    def deny(
        cls,
        trace_id: str,
        authority: str,
        reason_code: str,
        detail: str,
        severity: str = "ERROR",
        metadata: Dict[str, Any] | None = None,
    ) -> "DecisionOutcome":
        return cls(
            decision=DecisionKind.DENY,
            reason_code=reason_code,
            severity=severity,
            authority=authority,
            trace_id=trace_id,
            detail=detail,
            metadata=metadata or {},
        )

