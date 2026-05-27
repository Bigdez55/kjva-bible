"""ai/tokenless-agent/src/heptagon/writeback.py
WriteBackEngine — Heptagon Layer 6 (Calibration) retained-learning persistence.

Implements the write-back doctrine from ADR-S49-01 §14.  After the L6 cycle
determines that learning was retained, this engine decides WHERE to persist
that learning and executes the write operation.

Three persistence targets:
  SoulManager  (port 18610) — live soul state; ephemeral, fast, hot path.
                               Written on every accepted cycle regardless of target.
  EventJournal (port 18612) — append-only event log; written for all non-NONE targets.
  Archives     (Tokenless)    — durable long-term store; written only when target
                               includes "archive_only" or "both".

"Lawful admissibility" is enforced here: write-back to Archives is gated on
improvement_score >= ARCHIVE_THRESHOLD AND mastery_reached >= INNERSTANDING.
Writing to SoulManager is always attempted if improvement_score > 0.

Wire format uses stdlib socket + JSON — no third-party dependencies.
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

from soul_manager.daemon_client import CouncilDaemonSyncClient

from .mastery import MasteryLevel

logger = logging.getLogger("tokenless.heptagon.writeback")

_SOUL_TIMEOUT_S: float = 0.5
_JOURNAL_TIMEOUT_S: float = 0.5

# Minimum improvement score required before we bother writing to the journal
_JOURNAL_MIN_IMPROVEMENT: float = 0.10

# Minimum conditions for archive persistence
_ARCHIVE_MIN_IMPROVEMENT: float = 0.30
_ARCHIVE_MIN_MASTERY: MasteryLevel = MasteryLevel.INNERSTANDING


# ── WriteBackRequest ──────────────────────────────────────────────────────────

@dataclass
class WriteBackRequest:
    """Describes what, where, and how to persist retained learning."""

    session_id: str
    entity_id: str
    domain_id: str
    # "soul_only" | "archive_only" | "both" | "none"
    target: str
    improvement_score: float
    mastery_reached: MasteryLevel
    input_hash: str             # hex SHA-256 of the original input/context
    evidence_count: int
    delta_data: Optional[bytes] = None   # serialised delta payload (may be None)

    def __post_init__(self) -> None:
        valid_targets = {"soul_only", "archive_only", "both", "none"}
        if self.target not in valid_targets:
            raise ValueError(
                f"WriteBackRequest.target must be one of {valid_targets}, "
                f"got {self.target!r}"
            )
        self.improvement_score = max(0.0, min(1.0, self.improvement_score))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "entity_id": self.entity_id,
            "domain_id": self.domain_id,
            "target": self.target,
            "improvement_score": round(self.improvement_score, 4),
            "mastery_reached": int(self.mastery_reached),
            "mastery_label": self.mastery_reached.label(),
            "input_hash": self.input_hash,
            "evidence_count": self.evidence_count,
            "has_delta": self.delta_data is not None,
        }


# ── WriteBackResult ───────────────────────────────────────────────────────────

@dataclass
class WriteBackResult:
    """Result of a write-back operation."""

    accepted: bool
    event_id: Optional[str] = None
    generation_index: int = 0
    soul_written: bool = False
    journal_written: bool = False
    archive_written: bool = False
    rejection_reason: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "event_id": self.event_id,
            "generation_index": self.generation_index,
            "soul_written": self.soul_written,
            "journal_written": self.journal_written,
            "archive_written": self.archive_written,
            "rejection_reason": self.rejection_reason,
            "timestamp": self.timestamp,
        }


# ── WriteBackEngine ───────────────────────────────────────────────────────────

class WriteBackEngine:
    """Persist retained learning to SoulManager, EventJournal, and Archives.

    Instantiate once per Heptagon entity.  The engine is stateless across
    calls — every ``consolidate()`` call is independent.

    Lawful write-back rules:
      - target "none"         : no write; accepted=False
      - target "soul_only"    : SoulManager + EventJournal
      - target "archive_only" : Archives + EventJournal (if lawful)
      - target "both"         : SoulManager + Archives + EventJournal (if lawful)

    Archive writes are additionally gated on:
      improvement_score >= _ARCHIVE_MIN_IMPROVEMENT AND
      mastery_reached   >= _ARCHIVE_MIN_MASTERY
    """

    def __init__(self, entity_id: str) -> None:
        self.entity_id = entity_id
        self._generation_counter: int = 0
        self._daemon = CouncilDaemonSyncClient(
            source_agent=f"{entity_id}.l6",
            namespace=entity_id,
            timeout=max(_SOUL_TIMEOUT_S, _JOURNAL_TIMEOUT_S),
        )
        logger.debug("WriteBackEngine: initialised for entity '%s'", entity_id)

    # ── Main orchestration ────────────────────────────────────────────────────

    def consolidate(self, request: WriteBackRequest) -> WriteBackResult:
        """Orchestrate write-back to appropriate targets.

        This is the single entry point for all persistence.  It evaluates
        lawful admissibility, routes to the correct sinks, and returns a
        WriteBackResult describing what was written.
        """
        if request.target == "none":
            logger.debug(
                "WriteBackEngine[%s]: target=none — skipping write for domain '%s'",
                self.entity_id, request.domain_id,
            )
            return WriteBackResult(
                accepted=False,
                rejection_reason="target_none",
            )

        if request.improvement_score <= 0.0:
            logger.debug(
                "WriteBackEngine[%s]: improvement_score=0 — no learning to persist",
                self.entity_id,
            )
            return WriteBackResult(
                accepted=False,
                rejection_reason="no_improvement",
            )

        event_id = str(uuid.uuid4())
        self._generation_counter += 1
        gen_idx = self._generation_counter

        result = WriteBackResult(
            accepted=True,
            event_id=event_id,
            generation_index=gen_idx,
        )

        needs_soul    = request.target in {"soul_only", "both"}
        needs_archive = request.target in {"archive_only", "both"}

        # SoulManager write
        if needs_soul:
            result.soul_written = self.persist_to_soul(request, event_id, gen_idx)

        # Archive write — additional lawfulness gate
        if needs_archive:
            archive_lawful = (
                request.improvement_score >= _ARCHIVE_MIN_IMPROVEMENT
                and request.mastery_reached >= _ARCHIVE_MIN_MASTERY
            )
            if archive_lawful:
                result.archive_written = self.persist_to_archive(request, event_id, gen_idx)
            else:
                logger.debug(
                    "WriteBackEngine[%s]: archive gate blocked for '%s' "
                    "(improve=%.3f min=%.3f, mastery=%s min=%s)",
                    self.entity_id, request.domain_id,
                    request.improvement_score, _ARCHIVE_MIN_IMPROVEMENT,
                    request.mastery_reached.label(), _ARCHIVE_MIN_MASTERY.label(),
                )

        # EventJournal write — always if we wrote anywhere
        if result.soul_written or result.archive_written:
            if request.improvement_score >= _JOURNAL_MIN_IMPROVEMENT:
                result.journal_written = self.record_in_journal(request, event_id, gen_idx)

        logger.info(
            "WriteBackEngine[%s]: write-back complete — domain='%s' "
            "soul=%s journal=%s archive=%s event_id=%s gen=%d",
            self.entity_id, request.domain_id,
            result.soul_written, result.journal_written, result.archive_written,
            event_id, gen_idx,
        )
        return result

    # ── Soul persistence ──────────────────────────────────────────────────────

    def persist_to_soul(
        self,
        request: WriteBackRequest,
        event_id: str,
        gen_idx: int,
    ) -> bool:
        """Write to SoulManager (port 18610).

        Wire format: {"action": "put", "key": k, "value": v}
        Returns True if accepted (connection succeeded and server responded).
        On any socket error the failure is logged and False is returned —
        the system continues without hard-failing.
        """
        return self._daemon.put(
            "persistent",
            f"mastery:{request.domain_id}",
            self._build_payload(request, event_id, gen_idx),
            namespace=request.entity_id,
        )

    # ── Archive persistence ───────────────────────────────────────────────────

    def persist_to_archive(
        self,
        request: WriteBackRequest,
        event_id: str,
        gen_idx: int,
    ) -> bool:
        """Write to Tokenless Archives.

        Archives are a local file-based store: one JSON record per write,
        named by entity_id + domain_id + generation_index.
        Falls back gracefully on filesystem errors.
        """
        payload = self._build_payload(request, event_id, gen_idx)
        payload["accepted"] = True
        return self._daemon.archive(payload, event_type="mastery_archive")

    # ── EventJournal persistence ──────────────────────────────────────────────

    def record_in_journal(
        self,
        request: WriteBackRequest,
        event_id: str,
        gen_idx: int,
    ) -> bool:
        """Record in EventJournal (port 18612).

        Wire format: {"action": "append", "event_type": ..., "payload": ...}
        Returns True if accepted, False on any socket error.
        """
        payload = self._build_payload(request, event_id, gen_idx)
        payload["target"] = request.target
        payload["accepted"] = True
        return self._daemon.journal(payload, event_type="mastery_writeback")

    def _build_payload(
        self,
        request: WriteBackRequest,
        event_id: str,
        gen_idx: int,
    ) -> Dict[str, Any]:
        return {
            "session_id": request.session_id,
            "entity_id": request.entity_id,
            "domain_id": request.domain_id,
            "mastery_reached": int(request.mastery_reached),
            "mastery_label": request.mastery_reached.label(),
            "improvement_score": round(request.improvement_score, 4),
            "evidence_count": request.evidence_count,
            "input_hash": request.input_hash,
            "event_id": event_id,
            "generation_index": gen_idx,
            "delta_data_hash": (
                hashlib.sha256(request.delta_data).hexdigest()
                if request.delta_data
                else None
            ),
            "timestamp": time.time(),
        }

    def generation_index(self) -> int:
        """Return the current (last used) generation index."""
        return self._generation_counter

    def __repr__(self) -> str:
        return (
            f"WriteBackEngine(entity={self.entity_id!r}, "
            f"generation={self._generation_counter})"
        )
