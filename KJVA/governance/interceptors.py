"""Citadel/governance/interceptors.py — Governance Interceptors

SPDX-License-Identifier: MIT

Every critical subsystem must expose governance hooks.
Every critical decision must produce a governance artifact.
Every critical mutation must be attributable, replayable, and challengeable.

These interceptors create ONE governance language across the platform.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .decision_envelope import DecisionEnvelope, GateChainExecutor
from .storage_envelope import StorageEnvelope


@dataclass
class InterceptResult:
    """Result of a governance intercept."""
    allowed: bool
    reason: str = ""
    envelope_id: str = ""
    timestamp: float = field(default_factory=time.time)
    authority: str = ""
    artifacts: List[Dict[str, Any]] = field(default_factory=list)


class GovernanceInterceptors:
    """Governance hook API for the entire platform.

    Every subsystem calls these before critical operations.
    The interceptors route through the appropriate Council authorities.

    citadel_before_execute()  — L7 invariant check before action
    citadel_before_persist()  — L4 instrumentation trace on storage
    citadel_before_route()    — L3.3 route engine validation
    citadel_after_event()     — L4 trace emission + EventJournal
    citadel_after_failure()   — L5 evaluation + L6 calibration
    """

    def __init__(self, gate_chain: Optional[GateChainExecutor] = None) -> None:
        self._gate_chain = gate_chain or GateChainExecutor()
        self._event_log: List[Dict[str, Any]] = []
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []

    def register_pre_hook(self, hook: Callable) -> None:
        """Register a function called before every intercept."""
        self._pre_hooks.append(hook)

    def register_post_hook(self, hook: Callable) -> None:
        """Register a function called after every intercept."""
        self._post_hooks.append(hook)

    def citadel_before_execute(
        self,
        intent: str,
        subject: str,
        context: Optional[Dict[str, Any]] = None,
        created_by: str = "",
    ) -> InterceptResult:
        """Gate check before any execution.

        Creates a DecisionEnvelope, runs it through the gate chain,
        and returns whether the action is approved.
        """
        envelope = DecisionEnvelope(
            intent=intent,
            subject=subject,
            context=context or {},
            created_by=created_by,
        )

        for hook in self._pre_hooks:
            hook(envelope)

        verdict = self._gate_chain.evaluate(envelope)

        result = InterceptResult(
            allowed=verdict.approved,
            reason=verdict.envelope.final_reason if not verdict.approved else "Approved",
            envelope_id=envelope.envelope_id,
            authority=verdict.blocking_gate or "all_passed",
        )

        self._log_event("before_execute", result, envelope)

        for hook in self._post_hooks:
            hook(result, envelope)

        return result

    def citadel_before_persist(
        self,
        storage_envelope: StorageEnvelope,
    ) -> InterceptResult:
        """Governance headers check on storage operations.

        Validates that all required governance fields are present.
        """
        missing = storage_envelope.validate()
        allowed = len(missing) == 0

        result = InterceptResult(
            allowed=allowed,
            reason=f"Missing fields: {missing}" if not allowed else "Storage envelope valid",
            envelope_id=storage_envelope.object_id,
            authority="storage_validator",
        )

        self._log_event("before_persist", result)
        return result

    def citadel_before_route(
        self,
        destination: str,
        payload: Dict[str, Any],
        sender: str = "",
    ) -> InterceptResult:
        """Route validation before message dispatch."""
        # Basic validation: destination must be a known member
        from ..heptagon.registry import MEMBER_REGISTRY, OFFICE_REGISTRY

        known = set(MEMBER_REGISTRY.keys()) | set(OFFICE_REGISTRY.keys()) | {"Forge", "TOKENLESS_INTERFACE"}
        allowed = destination in known

        result = InterceptResult(
            allowed=allowed,
            reason=f"Unknown destination: {destination}" if not allowed else "Route valid",
            authority="route_validator",
        )

        self._log_event("before_route", result)
        return result

    def citadel_after_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        source: str = "",
    ) -> None:
        """Trace emission + EventJournal after an event occurs."""
        self._log_event("after_event", InterceptResult(
            allowed=True,
            reason=event_type,
            authority=source,
            artifacts=[event_data],
        ))

    def citadel_after_failure(
        self,
        failure_type: str,
        failure_data: Dict[str, Any],
        source: str = "",
    ) -> None:
        """L5 evaluation + L6 calibration after a failure."""
        self._log_event("after_failure", InterceptResult(
            allowed=False,
            reason=failure_type,
            authority=source,
            artifacts=[failure_data],
        ))

    def get_event_log(self) -> List[Dict[str, Any]]:
        """Return the full event log for auditing."""
        return list(self._event_log)

    def _log_event(
        self,
        intercept_type: str,
        result: InterceptResult,
        envelope: Optional[DecisionEnvelope] = None,
    ) -> None:
        """Log every intercept for provenance and replay."""
        entry = {
            "intercept_type": intercept_type,
            "timestamp": result.timestamp,
            "allowed": result.allowed,
            "reason": result.reason,
            "authority": result.authority,
            "envelope_id": result.envelope_id,
        }
        if envelope:
            entry["envelope_data"] = envelope.to_dict()
        self._event_log.append(entry)
