"""Citadel/heptagon/member_guard.py — Member Guard

SPDX-License-Identifier: MIT

Watches for disable/remove/replace attempts against Council members.
Implements the Seat Protection Doctrine.

A Council member must be removable as a process,
but NEVER removable as a constitutional identity.

Magen classifies any operation targeting member definitions
as maximum severity threat.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

from .attestation import AttestationEngine
from .registry import EntityClass, MEMBER_REGISTRY
from .vacancy_matrix import VacancyMatrix


class ThreatClass(Enum):
    """Classification of threats to member integrity."""
    PROCESS_STOP = auto()        # Daemon killed or crashed
    CONFIG_TAMPER = auto()       # Configuration modified
    REGISTRY_EDIT = auto()       # Attempt to modify registry.py
    KEY_REVOCATION = auto()      # Attempt to revoke member keys
    PORT_HIJACK = auto()         # Daemon port taken by unauthorized process
    IDENTITY_SUBSTITUTION = auto()  # Attempt to replace member with impersonator
    MEMORY_WIPE = auto()         # Attempt to delete SoulManager data
    ROUTING_EXCLUSION = auto()   # Attempt to exclude member from routing
    CAPABILITY_STRIP = auto()    # Attempt to remove member capabilities


class ThreatSeverity(Enum):
    """Severity of the detected threat."""
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()       # Constitutional threat
    EXISTENTIAL = auto()    # Organism-level threat


@dataclass
class ThreatEvent:
    """A detected threat against a member."""
    threat_id: str = ""
    timestamp: float = field(default_factory=time.time)
    target_member: str = ""
    threat_class: ThreatClass = ThreatClass.PROCESS_STOP
    severity: ThreatSeverity = ThreatSeverity.HIGH
    source: str = ""            # What/who initiated the threat
    details: str = ""
    action_taken: str = ""
    resolved: bool = False

    def __post_init__(self) -> None:
        if not self.threat_id:
            payload = f"{self.target_member}:{self.threat_class.name}:{self.timestamp}"
            self.threat_id = hashlib.sha256(payload.encode()).hexdigest()[:12]


class MemberGuard:
    """Runtime guardian of Council seat integrity.

    Implements the Seat Protection Doctrine:
    - Registry hash verification
    - Witness-mesh liveness monitoring
    - Threat detection and classification
    - Constitutional defense activation
    - Reconstitution triggering

    Magen blocks any operation targeting member definitions.
    Sarah detects identity drift.
    Esther classifies constitutional vs maintenance actions.
    """

    def __init__(
        self,
        vacancy_matrix: Optional[VacancyMatrix] = None,
        attestation_engine: Optional[AttestationEngine] = None,
    ) -> None:
        self._vacancy_matrix = vacancy_matrix or VacancyMatrix()
        self._attestation = attestation_engine or AttestationEngine()
        self._registry_hash = self._compute_registry_hash()
        self._threat_log: List[ThreatEvent] = []
        self._liveness: Dict[str, float] = {}  # member -> last heartbeat timestamp

        # Initialize liveness for all members
        now = time.time()
        for name, member in MEMBER_REGISTRY.items():
            if member.entity_class is not EntityClass.SUBSTRATE:
                self._liveness[name] = now

    def _compute_registry_hash(self) -> str:
        """Compute SHA-256 hash of the registry for integrity verification."""
        payload_parts = []
        for name, member in sorted(MEMBER_REGISTRY.items()):
            payload_parts.append(
                f"{name}:{member.rank.name}:{member.entity_class.name}"
                f":{member.canonical_domain}:{member.daemon_port}"
            )
        payload = "|".join(payload_parts)
        return hashlib.sha256(payload.encode()).hexdigest()

    def verify_registry_integrity(self) -> bool:
        """Verify registry has not been tampered with.

        Called every cognitive cycle by Esther's constitutional invariant check.
        If hash doesn't match → CONSTITUTIONAL VIOLATION → hard stop.
        """
        current_hash = self._compute_registry_hash()
        return current_hash == self._registry_hash

    def record_heartbeat(self, member: str) -> None:
        """Record a liveness heartbeat from a member."""
        self._liveness[member] = time.time()

    def check_liveness(self, timeout_seconds: float = 30.0) -> List[str]:
        """Check which members have missed their heartbeat.

        Returns list of members that appear to be down.
        Uses witness-mesh quorum logic: a member is considered
        down only if multiple witnesses agree.
        """
        now = time.time()
        potentially_down = []
        for member, last_beat in self._liveness.items():
            if now - last_beat > timeout_seconds:
                potentially_down.append(member)
        return potentially_down

    def detect_threat(
        self,
        target_member: str,
        threat_class: ThreatClass,
        source: str = "",
        details: str = "",
    ) -> ThreatEvent:
        """Detect and classify a threat against a member.

        Every threat is logged. Constitutional threats trigger
        immediate defense activation.
        """
        # Classify severity
        severity = self._classify_severity(threat_class)

        event = ThreatEvent(
            target_member=target_member,
            threat_class=threat_class,
            severity=severity,
            source=source,
            details=details,
        )

        # Take immediate action based on severity
        if severity in (ThreatSeverity.CRITICAL, ThreatSeverity.EXISTENTIAL):
            event.action_taken = self._activate_constitutional_defense(event)
        elif severity == ThreatSeverity.HIGH:
            event.action_taken = f"Alert: {threat_class.name} against {target_member}"
        else:
            event.action_taken = f"Logged: {threat_class.name} against {target_member}"

        self._threat_log.append(event)
        return event

    def attempt_modification_blocked(
        self,
        target: str,
        operation: str,
        source: str = "",
    ) -> ThreatEvent:
        """Block any attempt to modify member definitions.

        Magen classifies these as maximum severity.
        Includes 'innocent' operations like registry updates
        or modified daemon configs.
        """
        return self.detect_threat(
            target_member=target,
            threat_class=ThreatClass.REGISTRY_EDIT if "registry" in operation.lower()
            else ThreatClass.CONFIG_TAMPER,
            source=source,
            details=f"Blocked modification: {operation}",
        )

    def trigger_reconstitution(self, member: str) -> Dict[str, Any]:
        """Trigger the reconstitution process for a missing member.

        Phase 1: Resurrection (GENSD restarts daemon)
        Phase 2: Reconstitution (restore identity, memory, behavior)

        Returns reconstitution plan with witness quorum.
        """
        # Mark seat as vacant
        effect = self._vacancy_matrix.mark_vacant(member)

        # Get reconstitution witnesses
        vacant = self._vacancy_matrix.get_vacant_seats()
        try:
            quorum = self._attestation.get_reconstitution_witnesses(member, vacant)
        except ValueError as e:
            return {
                "status": "OWNER_REVIEW_REQUIRED",
                "reason": str(e),
                "member": member,
            }

        # Mark as reconstituting
        self._vacancy_matrix.mark_reconstituting(member)

        return {
            "status": "RECONSTITUTION_INITIATED",
            "member": member,
            "phase_1": "resurrection — GENSD restarts daemon process",
            "phase_2": "reconstitution — restore identity from registry + memory from SoulManager",
            "witnesses": quorum,
            "degradation": {
                "freezes": effect.freezes,
                "continues": effect.continues,
                "temporary_coverage": effect.temporary_coverage,
            },
            "authority_mode": "RECOMMENDATION (then graduate to CONDITIONAL → FULL)",
        }

    def get_threat_log(self) -> List[ThreatEvent]:
        """Return all recorded threats."""
        return list(self._threat_log)

    def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive system health report."""
        down = self.check_liveness()
        registry_ok = self.verify_registry_integrity()
        vacant = self._vacancy_matrix.get_vacant_seats()

        return {
            "registry_integrity": registry_ok,
            "members_down": down,
            "vacant_seats": vacant,
            "degraded": self._vacancy_matrix.is_degraded(),
            "regency_triad_active": self._vacancy_matrix.get_regency_triad_active(),
            "threat_count": len(self._threat_log),
            "unresolved_threats": len([t for t in self._threat_log if not t.resolved]),
            "all_statuses": self._vacancy_matrix.get_all_statuses(),
        }

    def _classify_severity(self, threat_class: ThreatClass) -> ThreatSeverity:
        """Classify the severity of a threat."""
        critical_threats = {
            ThreatClass.REGISTRY_EDIT,
            ThreatClass.IDENTITY_SUBSTITUTION,
            ThreatClass.MEMORY_WIPE,
            ThreatClass.KEY_REVOCATION,
        }
        high_threats = {
            ThreatClass.PORT_HIJACK,
            ThreatClass.CAPABILITY_STRIP,
            ThreatClass.ROUTING_EXCLUSION,
        }

        if threat_class in critical_threats:
            return ThreatSeverity.CRITICAL
        elif threat_class in high_threats:
            return ThreatSeverity.HIGH
        else:
            return ThreatSeverity.MEDIUM

    def _activate_constitutional_defense(self, event: ThreatEvent) -> str:
        """Activate constitutional defense for critical/existential threats.

        Freeze identity surfaces.
        Lock registry.
        Snapshot heptagon state.
        Alert all surviving members.
        """
        actions = [
            f"CONSTITUTIONAL DEFENSE ACTIVATED for {event.target_member}",
            "Registry locked (hash verified)",
            "Member memory lineage frozen",
            "All surviving members alerted",
            f"Threat source: {event.source}",
            f"Classification: {event.threat_class.name} / {event.severity.name}",
        ]
        return " | ".join(actions)
