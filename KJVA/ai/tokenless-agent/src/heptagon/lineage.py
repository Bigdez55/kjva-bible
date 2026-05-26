"""ai/tokenless-agent/src/heptagon/lineage.py
LineageEngine — Heptagon Layer 6 (Calibration) generational inheritance tracking.

Implements the lineage-delta doctrine from ADR-S49-01 §14.  Each time the L6
cycle confirms retained learning, a LineageDelta is emitted into the entity's
LineageStore.  The store records the entire learning trajectory across
generations — forming the inheritable knowledge chain.

"Generation" here is a semantic concept: a generation advances when the entity
crosses a mastery level boundary.  Between promotions all deltas accumulate in
the same generation.  This means an entity that never promotes stays in
generation 0 indefinitely, while an entity that reaches OVERSTANDING in a
domain will have traversed generations 0, 1, and 2.

The LineageStore is the canonical historical record.  It can be serialised
(to_dict) and transmitted to child entities or restored from an archive.
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .mastery import MasteryLevel, MasteryProfile

logger = logging.getLogger("tokenless.heptagon.lineage")

# Maximum number of deltas retained in memory before the oldest are archived
_MAX_DELTA_MEMORY: int = 500

# Minimum improvement score for a delta to be recorded at all
_DELTA_MIN_IMPROVEMENT: float = 0.05


# ── LineageDelta ─────────────────────────────────────────────────────────────

@dataclass
class LineageDelta:
    """A single learning delta — one moment of retained, lawful change.

    Each delta records what changed, what level mastery reached, how
    confident the change was, and which generation it belongs to.
    The source_hash links back to the original input artifact.
    """

    delta_id: str               # hex SHA-256 of (entity_id:domain_id:generation:timestamp)
    source_hash: str            # SHA-256 of source artifact / query context
    domain_id: str
    improvement_score: float    # 0.0–1.0 confidence that this delta is real learning
    generation_index: int
    mastery_reached: MasteryLevel
    # "soul_only" | "archive_only" | "both" | "none"
    retention_target: str
    timestamp: float
    evidence_count: int
    # Optional narrative summary of what changed (set by caller — may be empty)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "delta_id": self.delta_id,
            "source_hash": self.source_hash,
            "domain_id": self.domain_id,
            "improvement_score": round(self.improvement_score, 4),
            "generation_index": self.generation_index,
            "mastery_reached": int(self.mastery_reached),
            "mastery_label": self.mastery_reached.label(),
            "retention_target": self.retention_target,
            "timestamp": self.timestamp,
            "evidence_count": self.evidence_count,
            "summary": self.summary,
        }


# ── LineageStore ──────────────────────────────────────────────────────────────

@dataclass
class LineageStore:
    """Complete lineage record for one entity.

    Stores all LineageDeltas across all domains and all generations.
    Provides queries over the historical record.
    """

    entity_id: str
    deltas: List[LineageDelta] = field(default_factory=list)
    current_generation: int = 0
    mastery_profile: Optional[MasteryProfile] = None
    created_ts: float = field(default_factory=time.time)
    last_delta_ts: float = 0.0

    # Generation advancement history: list of (old_gen, new_gen, domain_id, timestamp)
    generation_history: List[Dict[str, Any]] = field(default_factory=list)

    def domain_deltas(self, domain_id: str) -> List[LineageDelta]:
        """Return all deltas for a specific domain, oldest first."""
        return [d for d in self.deltas if d.domain_id == domain_id]

    def generation_deltas(self, generation: int) -> List[LineageDelta]:
        """Return all deltas from a specific generation, oldest first."""
        return [d for d in self.deltas if d.generation_index == generation]

    def highest_mastery(self, domain_id: str) -> MasteryLevel:
        """Return the highest mastery level ever recorded in a domain."""
        domain_d = self.domain_deltas(domain_id)
        if not domain_d:
            return MasteryLevel.UNDERSTANDING
        return max(d.mastery_reached for d in domain_d)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "current_generation": self.current_generation,
            "total_deltas": len(self.deltas),
            "last_delta_ts": self.last_delta_ts,
            "created_ts": self.created_ts,
            "generation_history": self.generation_history,
            "domains": list({d.domain_id for d in self.deltas}),
        }


# ── LineageEngine ─────────────────────────────────────────────────────────────

class LineageEngine:
    """Generational inheritance tracking for one Heptagon entity.

    Maintains a LineageStore and provides the canonical interface for:
      - recording new learning deltas
      - advancing generations on mastery promotion
      - querying lineage state for inheritance or serialisation

    The engine does NOT communicate with any daemon — it is a pure in-memory
    record.  Persistence is the responsibility of WriteBackEngine.
    """

    def __init__(self, entity_id: str) -> None:
        self.store = LineageStore(entity_id=entity_id)
        logger.debug("LineageEngine: initialised for entity '%s'", entity_id)

    # ── Public API ────────────────────────────────────────────────────────────

    def record_delta(
        self,
        domain_id: str,
        source_hash: str,
        improvement_score: float,
        mastery_reached: MasteryLevel,
        retention_target: str,
        evidence_count: int,
        summary: str = "",
    ) -> Optional[LineageDelta]:
        """Record a new inheritance delta.

        Returns the created LineageDelta, or None if the improvement score
        is below the minimum threshold (_DELTA_MIN_IMPROVEMENT).

        Parameters
        ----------
        domain_id:
            The domain in which learning occurred.
        source_hash:
            SHA-256 hex of the source artifact or context hash.
        improvement_score:
            How much was learned (0.0–1.0).
        mastery_reached:
            The mastery level at the time of this delta.
        retention_target:
            Where this delta will be persisted ("soul_only", "archive_only",
            "both", "none").
        evidence_count:
            How many evidence samples underpinned this delta.
        summary:
            Optional human-readable description of what changed.
        """
        improvement_score = max(0.0, min(1.0, improvement_score))

        if improvement_score < _DELTA_MIN_IMPROVEMENT:
            logger.debug(
                "LineageEngine[%s]: delta below threshold "
                "(improve=%.3f < %.3f) — not recorded",
                self.store.entity_id, improvement_score, _DELTA_MIN_IMPROVEMENT,
            )
            return None

        now = time.time()
        delta_id = hashlib.sha256(
            f"{self.store.entity_id}:{domain_id}:{self.store.current_generation}:{now}".encode()
        ).hexdigest()[:24]

        delta = LineageDelta(
            delta_id=delta_id,
            source_hash=source_hash,
            domain_id=domain_id,
            improvement_score=improvement_score,
            generation_index=self.store.current_generation,
            mastery_reached=mastery_reached,
            retention_target=retention_target,
            timestamp=now,
            evidence_count=evidence_count,
            summary=summary,
        )

        self.store.deltas.append(delta)
        self.store.last_delta_ts = now

        # Trim memory if over limit
        if len(self.store.deltas) > _MAX_DELTA_MEMORY:
            overflow = len(self.store.deltas) - _MAX_DELTA_MEMORY
            self.store.deltas = self.store.deltas[overflow:]
            logger.debug(
                "LineageEngine[%s]: trimmed %d old deltas (memory cap=%d)",
                self.store.entity_id, overflow, _MAX_DELTA_MEMORY,
            )

        logger.debug(
            "LineageEngine[%s]: delta recorded — domain='%s' gen=%d "
            "mastery=%s improve=%.3f",
            self.store.entity_id, domain_id, self.store.current_generation,
            mastery_reached.label(), improvement_score,
        )
        return delta

    def advance_generation(self, domain_id: str) -> int:
        """Increment the current generation counter.

        Should be called when MasteryEngine.promote() succeeds for a domain.
        Records the advancement in generation_history.

        Returns the new generation index.
        """
        old_gen = self.store.current_generation
        new_gen = old_gen + 1
        self.store.current_generation = new_gen
        self.store.generation_history.append({
            "old_generation": old_gen,
            "new_generation": new_gen,
            "domain_id": domain_id,
            "timestamp": time.time(),
        })
        logger.info(
            "LineageEngine[%s]: GENERATION ADVANCED — %d -> %d (domain='%s')",
            self.store.entity_id, old_gen, new_gen, domain_id,
        )
        return new_gen

    def get_lineage_summary(self) -> Dict[str, Any]:
        """Return the full lineage state as a serialisable dict."""
        summary = self.store.to_dict()
        summary["engine"] = "LineageEngine"
        summary["delta_min_improvement"] = _DELTA_MIN_IMPROVEMENT
        summary["max_delta_memory"] = _MAX_DELTA_MEMORY
        # Include the last 10 deltas for inspection
        recent = self.store.deltas[-10:]
        summary["recent_deltas"] = [d.to_dict() for d in recent]
        return summary

    def get_generation_depth(self) -> int:
        """Return the current generation index (how many promotions have occurred)."""
        return self.store.current_generation

    def get_domain_trajectory(self, domain_id: str) -> List[Dict[str, Any]]:
        """Return all deltas for a domain, serialised, oldest first."""
        return [d.to_dict() for d in self.store.domain_deltas(domain_id)]

    def inheritance_package(self, domain_id: str) -> Dict[str, Any]:
        """Prepare an inheritance package for a child entity.

        The package contains the highest-mastery delta for each generation
        of the specified domain — sufficient for a child to bootstrap
        without replaying every individual encounter.
        """
        domain_d = self.store.domain_deltas(domain_id)
        if not domain_d:
            return {
                "entity_id": self.store.entity_id,
                "domain_id": domain_id,
                "generations": [],
                "current_generation": self.store.current_generation,
            }

        # For each generation, pick the delta with the highest improvement_score
        generations: Dict[int, LineageDelta] = {}
        for delta in domain_d:
            gen = delta.generation_index
            if gen not in generations or delta.improvement_score > generations[gen].improvement_score:
                generations[gen] = delta

        return {
            "entity_id": self.store.entity_id,
            "domain_id": domain_id,
            "current_generation": self.store.current_generation,
            "generations": [
                generations[g].to_dict()
                for g in sorted(generations.keys())
            ],
            "highest_mastery": int(self.store.highest_mastery(domain_id)),
            "highest_mastery_label": self.store.highest_mastery(domain_id).label(),
        }

    def attach_mastery_profile(self, profile: MasteryProfile) -> None:
        """Attach a MasteryProfile for joint serialisation (optional)."""
        self.store.mastery_profile = profile

    def __repr__(self) -> str:
        return (
            f"LineageEngine(entity={self.store.entity_id!r}, "
            f"generation={self.store.current_generation}, "
            f"deltas={len(self.store.deltas)})"
        )
