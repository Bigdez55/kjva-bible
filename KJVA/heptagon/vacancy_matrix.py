"""models/heptagon/vacancy_matrix.py — Vacancy Matrix

SPDX-License-Identifier: MIT

Tracks seat vacancy state across the Council. When a member goes down,
the matrix records the vacancy and computes degraded-mode effects.

For Tokenless (single-entity SaaS), this is simplified: Tokenless has no seats
to go vacant. The matrix exists to satisfy the MemberGuard interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional


class SeatStatus(Enum):
    """Status of a Council seat."""
    ACTIVE = auto()
    VACANT = auto()
    DEGRADED = auto()
    RECONSTITUTING = auto()


@dataclass
class VacancyEffect:
    """Describes the effect of a vacancy on system capabilities."""
    seat_id: str
    status: SeatStatus
    affected_domains: List[str] = field(default_factory=list)
    reason: str = ""


class VacancyMatrix:
    """Runtime vacancy tracker for Council seats.

    Manages seat status transitions and computes degraded-mode effects.
    For Tokenless single-entity deployment, all methods return healthy defaults.
    """

    def __init__(self) -> None:
        self._statuses: Dict[str, SeatStatus] = {}
        self._effects: List[VacancyEffect] = []

    def mark_vacant(self, member_id: str, reason: str = "") -> VacancyEffect:
        """Mark a seat as vacant and record the effect."""
        self._statuses[member_id] = SeatStatus.VACANT
        effect = VacancyEffect(
            seat_id=member_id,
            status=SeatStatus.VACANT,
            reason=reason,
        )
        self._effects.append(effect)
        return effect

    def mark_reconstituting(self, member_id: str) -> None:
        """Mark a seat as undergoing reconstitution."""
        self._statuses[member_id] = SeatStatus.RECONSTITUTING

    def mark_active(self, member_id: str) -> None:
        """Mark a seat as active (restored)."""
        self._statuses[member_id] = SeatStatus.ACTIVE

    def get_vacant_seats(self) -> List[str]:
        """Return list of currently vacant seat IDs."""
        return [
            mid for mid, status in self._statuses.items()
            if status == SeatStatus.VACANT
        ]

    def is_degraded(self) -> bool:
        """Return True if any seat is vacant or degraded."""
        return any(
            s in (SeatStatus.VACANT, SeatStatus.DEGRADED)
            for s in self._statuses.values()
        )

    def get_regency_triad_active(self) -> bool:
        """Return True if the regency triad (Ahki, Esther, Sarah) is intact."""
        triad = {"Ahki", "Esther", "Sarah"}
        for member in triad:
            if self._statuses.get(member) in (SeatStatus.VACANT, SeatStatus.DEGRADED):
                return False
        return True

    def get_all_statuses(self) -> Dict[str, str]:
        """Return all seat statuses as a dict."""
        return {mid: status.name for mid, status in self._statuses.items()}

    def get_effects(self) -> List[VacancyEffect]:
        """Return all recorded vacancy effects."""
        return list(self._effects)
