"""memory_types — ADR-0002 §4.7 Edge G data contracts.

SPDX-License-Identifier: MIT

Defines the three return types that the Memory Continuity System sends back
to the Model Runtime at the close of each turn (Edge G).  ADR-0002 §4.7 names
ContinuityState, RecallReadiness, MemoryHealth, and SessionContinuitySummary
as required contracts; field shapes are derived from §4.7 intent (the ADR is
silent on per-field detail for these types).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RecallReadiness:
    """How prepared memory is to serve context for the next turn.

    Returned as part of ContinuityState so the runtime can decide whether to
    warm a retrieval prefetch before the next request arrives.
    """

    available_episodes: int = 0
    """Number of episodic records available for the next turn."""

    ledger_entries: int = 0
    """Lifespan-ledger rows visible to the recall path."""

    context_packet_ready: bool = False
    """True when a pre-built context packet is ready for injection."""

    recall_latency_ms: float = 0.0
    """Estimated retrieval latency observed in the current turn (ms)."""


@dataclass
class MemoryHealth:
    """Health of the memory subsystem at turn end.

    Surfaced to the runtime so degraded-memory situations can trigger
    graceful fallback rather than silent data loss.
    """

    episodic_store_ok: bool = True
    """False when the episodic store raised an error during this turn."""

    ledger_ok: bool = True
    """False when the lifespan ledger write-back failed."""

    soul_manager_connected: bool = False
    """True when SoulManager completed its turn-end writeback without error."""

    last_writeback_quality: float = 1.0
    """Fraction of intended memory written; 1.0 = complete, 0.0 = nothing."""

    writeback_errors: int = 0
    """Count of non-fatal errors encountered during writeback this turn."""


@dataclass
class ContinuityState:
    """Cycle-closing memory → runtime return value per ADR-0002 §4.7 Edge G.

    The Memory Continuity System produces one ContinuityState per turn and
    returns it to the Model Runtime.  The runtime uses it to decide whether
    the session is healthy enough to continue and to prime the next turn's
    recall path.
    """

    session_id: str = ""
    """Opaque session identifier shared between runtime and memory system."""

    turn: int = 0
    """Zero-based turn index within the current session."""

    recall_readiness: RecallReadiness = field(default_factory=RecallReadiness)
    """Memory readiness snapshot for the upcoming turn."""

    memory_health: MemoryHealth = field(default_factory=MemoryHealth)
    """Health summary for the memory subsystem after this turn's writes."""

    continuity_score: float = 1.0
    """Scalar in [0.0, 1.0]; 1.0 = full continuity, 0.0 = cold start."""

    def to_dict(self) -> dict:
        """Return a plain-dict representation suitable for logging / JSON."""
        return dataclasses.asdict(self)

    @property
    def is_healthy(self) -> bool:
        """True when memory subsystem reports no blocking errors."""
        return (
            self.memory_health.episodic_store_ok
            and self.memory_health.ledger_ok
        )
