"""ai/tokenless-agent/src/heptagon/mastery.py
MasteryEngine — Heptagon Layer 6 (Calibration) domain-specific mastery tracking.

Implements the transformation-of-self doctrine from ADR-S49-01 §14.
Mastery is per-entity, per-domain — NOT one global depth.

Three mastery levels (ADR §5):
  UNDERSTANDING = 0  — foundation; knowing the paths, base procedure
  INNERSTANDING = 1  — interior structure; why things connect, how rooms relate
  OVERSTANDING  = 2  — roof; closure, whole-system consequence awareness

Promotion is governed by multi-criterion accumulation, NOT single-score thresholds:
  - repeated_recurrence       : domain visited across multiple independent cycles
  - cross_context_stability   : pattern holds across different query contexts
  - structural_coherence      : internal consistency of the entity's responses in domain
  - lawful_admissibility      : domain is within entity's authority bounds
  - retained_usefulness       : prior mastery state still helps in new encounters
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("tokenless.heptagon.mastery")

# ── Promotion thresholds (governed accumulation) ─────────────────────────────
# All five criteria must EACH surpass their respective threshold before
# promotion is evaluated.  No single criterion is sufficient alone.

_PROMO_RECURRENCE_MIN: int = 5          # minimum distinct visits to domain
_PROMO_CROSS_CTX_MIN: float = 0.65     # stability across contexts
_PROMO_STRUCTURAL_MIN: float = 0.70    # internal coherence
_PROMO_RETAINED_MIN: float = 0.60      # usefulness of prior mastery
_PROMO_EVIDENCE_MIN: int = 3           # minimum evidence samples per level

# How much evidence degrades per elapsed time (per 86400 s window).
# Keeps mastery from being awarded on stale or infrequent engagement.
_EVIDENCE_DECAY_RATE: float = 0.005    # per-second decay multiplier

# Maximum number of historical evidence snapshots kept per domain
_MAX_EVIDENCE_SNAPSHOTS: int = 50


# ── MasteryLevel ─────────────────────────────────────────────────────────────

class MasteryLevel(IntEnum):
    """Ordered mastery levels from ADR-S49-01 §5."""
    UNDERSTANDING = 0
    INNERSTANDING = 1
    OVERSTANDING  = 2

    def label(self) -> str:
        return self.name.capitalize()

    def description(self) -> str:
        _desc = {
            MasteryLevel.UNDERSTANDING: (
                "Foundation — knows the paths and base procedures; "
                "can traverse but does not yet see structure."
            ),
            MasteryLevel.INNERSTANDING: (
                "Interior structure — understands why things connect "
                "and how rooms relate; sees the load-bearing walls."
            ),
            MasteryLevel.OVERSTANDING: (
                "Roof — whole-system consequence awareness; "
                "knows what breaks when anything moves."
            ),
        }
        return _desc[self]


# ── EvidenceSnapshot ─────────────────────────────────────────────────────────

@dataclass
class EvidenceSnapshot:
    """A single piece of evidence supporting mastery in a domain."""

    snapshot_id: str            # hex hash of (entity_id + domain_id + timestamp)
    timestamp: float
    context_hash: str           # opaque hash of the query context — used for cross-ctx check
    coherence_score: float      # structural coherence of this encounter (0.0–1.0)
    usefulness_score: float     # did prior mastery help here? (0.0–1.0)
    cross_context: bool         # was this a context distinct from prior encounters?

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "context_hash": self.context_hash,
            "coherence_score": round(self.coherence_score, 4),
            "usefulness_score": round(self.usefulness_score, 4),
            "cross_context": self.cross_context,
        }


# ── DomainMastery ─────────────────────────────────────────────────────────────

@dataclass
class DomainMastery:
    """Per-entity, per-domain mastery state."""

    domain_id: str
    level: MasteryLevel = MasteryLevel.UNDERSTANDING

    # 3-6-9 budget scores (from L3.7 BudgetGovernor)
    route_score: float = 0.0        # how fluently the entity routes in this domain
    structure_score: float = 0.0    # structural coherence across encounters
    memory_score: float = 0.0       # retention effectiveness

    evidence_count: int = 0
    last_update_ts: float = 0.0

    # Promotion criteria tracking (governed accumulation)
    recurrence_count: int = 0           # distinct cycle visits
    cross_context_stability: float = 0.0
    structural_coherence: float = 0.0
    retained_usefulness: float = 0.0
    lawful_admissible: bool = True      # within entity's authority bounds

    # Evidence log (bounded to _MAX_EVIDENCE_SNAPSHOTS)
    evidence_snapshots: List[EvidenceSnapshot] = field(default_factory=list)

    # Promotion history: list of (from_level, to_level, timestamp)
    promotion_history: List[Tuple[int, int, float]] = field(default_factory=list)

    def effective_evidence_count(self) -> int:
        """Evidence count after time-decay correction.

        Recent snapshots count fully; old snapshots are down-weighted by
        elapsed time.  Returns the integer floor of the decayed total.
        """
        now = time.time()
        total = 0.0
        for snap in self.evidence_snapshots:
            elapsed = max(0.0, now - snap.timestamp)
            weight = max(0.0, 1.0 - (_EVIDENCE_DECAY_RATE * elapsed))
            total += weight
        return int(total)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "level": self.level.label(),
            "level_int": int(self.level),
            "route_score": round(self.route_score, 4),
            "structure_score": round(self.structure_score, 4),
            "memory_score": round(self.memory_score, 4),
            "evidence_count": self.evidence_count,
            "effective_evidence_count": self.effective_evidence_count(),
            "last_update_ts": self.last_update_ts,
            "recurrence_count": self.recurrence_count,
            "cross_context_stability": round(self.cross_context_stability, 4),
            "structural_coherence": round(self.structural_coherence, 4),
            "retained_usefulness": round(self.retained_usefulness, 4),
            "lawful_admissible": self.lawful_admissible,
            "promotion_count": len(self.promotion_history),
        }


# ── MasteryProfile ────────────────────────────────────────────────────────────

@dataclass
class MasteryProfile:
    """Per-entity domain mastery profile.

    Each entity (e.g., Ruth, Magen, Abigail) has a distinct profile.
    Domains are indexed by domain_id string (e.g., "security", "economics").
    There is NO global depth — every domain is tracked independently.
    """

    entity_id: str
    domains: Dict[str, DomainMastery] = field(default_factory=dict)
    created_ts: float = field(default_factory=time.time)
    last_activity_ts: float = field(default_factory=time.time)

    def get_or_create_domain(self, domain_id: str) -> DomainMastery:
        """Return existing DomainMastery or create a new UNDERSTANDING-level one."""
        if domain_id not in self.domains:
            self.domains[domain_id] = DomainMastery(
                domain_id=domain_id,
                last_update_ts=time.time(),
            )
            logger.debug(
                "MasteryProfile[%s]: created domain '%s' at UNDERSTANDING",
                self.entity_id, domain_id,
            )
        return self.domains[domain_id]

    def domain_level(self, domain_id: str) -> MasteryLevel:
        """Return current mastery level for domain, defaulting to UNDERSTANDING."""
        if domain_id not in self.domains:
            return MasteryLevel.UNDERSTANDING
        return self.domains[domain_id].level

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "domain_count": len(self.domains),
            "domains": {k: v.to_dict() for k, v in self.domains.items()},
            "created_ts": self.created_ts,
            "last_activity_ts": self.last_activity_ts,
        }


# ── MasteryEngine ─────────────────────────────────────────────────────────────

class MasteryEngine:
    """Domain-specific mastery tracking and governed promotion.

    One engine instance is used per Heptagon entity.  It owns the entity's
    MasteryProfile and provides the canonical interface for all mastery
    state mutations.

    Promotion rules (all must hold — governed accumulation):
      1. recurrence_count  >= _PROMO_RECURRENCE_MIN
      2. cross_context_stability >= _PROMO_CROSS_CTX_MIN
      3. structural_coherence >= _PROMO_STRUCTURAL_MIN
      4. retained_usefulness >= _PROMO_RETAINED_MIN
      5. effective_evidence_count >= _PROMO_EVIDENCE_MIN
      6. lawful_admissible == True
      7. level has not already reached OVERSTANDING
    """

    def __init__(self, entity_id: str) -> None:
        self.profile = MasteryProfile(entity_id=entity_id)
        logger.debug("MasteryEngine: initialised for entity '%s'", entity_id)

    # ── Public API ────────────────────────────────────────────────────────────

    def update_evidence(
        self,
        domain_id: str,
        context_hash: str,
        coherence_score: float,
        usefulness_score: float,
        route_score: float = 0.0,
        structure_score: float = 0.0,
        memory_score: float = 0.0,
        lawful: bool = True,
    ) -> DomainMastery:
        """Record a new evidence encounter for the given domain.

        Parameters
        ----------
        domain_id:
            The domain being updated (e.g., "security", "finance").
        context_hash:
            Opaque hash of the query context — used to detect cross-context stability.
        coherence_score:
            Structural coherence of this encounter, 0.0–1.0.
        usefulness_score:
            How much did prior mastery help? 0.0–1.0.
        route_score / structure_score / memory_score:
            3-6-9 budget dimension scores for this encounter.
        lawful:
            Whether this encounter is within the entity's authority bounds.

        Returns the updated DomainMastery.
        """
        dm = self.profile.get_or_create_domain(domain_id)
        now = time.time()

        # Determine if this context hash is novel (cross-context)
        seen_contexts = {s.context_hash for s in dm.evidence_snapshots}
        is_cross_context = context_hash not in seen_contexts

        # Build evidence snapshot
        snap_id = hashlib.sha256(
            f"{self.profile.entity_id}:{domain_id}:{now}".encode()
        ).hexdigest()[:16]
        snap = EvidenceSnapshot(
            snapshot_id=snap_id,
            timestamp=now,
            context_hash=context_hash,
            coherence_score=max(0.0, min(1.0, coherence_score)),
            usefulness_score=max(0.0, min(1.0, usefulness_score)),
            cross_context=is_cross_context,
        )
        dm.evidence_snapshots.append(snap)

        # Trim to bounded size (keep most recent)
        if len(dm.evidence_snapshots) > _MAX_EVIDENCE_SNAPSHOTS:
            dm.evidence_snapshots = dm.evidence_snapshots[-_MAX_EVIDENCE_SNAPSHOTS:]

        # Update counters and scores
        dm.evidence_count += 1
        dm.recurrence_count += 1
        dm.last_update_ts = now
        dm.lawful_admissible = lawful

        # Update 3-6-9 budget scores via EWM (alpha = 0.15)
        alpha = 0.15
        dm.route_score    = alpha * route_score    + (1 - alpha) * dm.route_score
        dm.structure_score = alpha * structure_score + (1 - alpha) * dm.structure_score
        dm.memory_score   = alpha * memory_score   + (1 - alpha) * dm.memory_score

        # Recompute aggregated promotion criteria
        dm.structural_coherence = self._compute_structural_coherence(dm)
        dm.retained_usefulness  = self._compute_retained_usefulness(dm)
        dm.cross_context_stability = self._compute_cross_context_stability(dm)

        self.profile.last_activity_ts = now

        logger.debug(
            "MasteryEngine[%s]: evidence for '%s' — recur=%d coh=%.3f use=%.3f xctx=%.3f",
            self.profile.entity_id, domain_id,
            dm.recurrence_count, dm.structural_coherence,
            dm.retained_usefulness, dm.cross_context_stability,
        )
        return dm

    def evaluate_promotion(self, domain_id: str) -> Tuple[bool, str]:
        """Check whether domain mastery should advance.

        Returns (eligible, reason_string).
        reason_string names the blocking criterion if not eligible.
        """
        dm = self.profile.get_or_create_domain(domain_id)

        if dm.level == MasteryLevel.OVERSTANDING:
            return False, "already_at_ceiling"

        if not dm.lawful_admissible:
            return False, "not_lawfully_admissible"

        if dm.recurrence_count < _PROMO_RECURRENCE_MIN:
            return False, (
                f"recurrence_count {dm.recurrence_count} < {_PROMO_RECURRENCE_MIN}"
            )

        eff_count = dm.effective_evidence_count()
        if eff_count < _PROMO_EVIDENCE_MIN:
            return False, (
                f"effective_evidence {eff_count} < {_PROMO_EVIDENCE_MIN}"
            )

        if dm.cross_context_stability < _PROMO_CROSS_CTX_MIN:
            return False, (
                f"cross_context_stability {dm.cross_context_stability:.3f}"
                f" < {_PROMO_CROSS_CTX_MIN}"
            )

        if dm.structural_coherence < _PROMO_STRUCTURAL_MIN:
            return False, (
                f"structural_coherence {dm.structural_coherence:.3f}"
                f" < {_PROMO_STRUCTURAL_MIN}"
            )

        if dm.retained_usefulness < _PROMO_RETAINED_MIN:
            return False, (
                f"retained_usefulness {dm.retained_usefulness:.3f}"
                f" < {_PROMO_RETAINED_MIN}"
            )

        return True, "all_criteria_met"

    def promote(self, domain_id: str) -> Optional[MasteryLevel]:
        """Attempt to advance mastery level for a domain.

        Runs evaluate_promotion() first.  Returns the new level if
        promoted, None if not eligible.
        """
        dm = self.profile.get_or_create_domain(domain_id)
        eligible, reason = self.evaluate_promotion(domain_id)

        if not eligible:
            logger.debug(
                "MasteryEngine[%s]: promotion blocked for '%s' — %s",
                self.profile.entity_id, domain_id, reason,
            )
            return None

        old_level = dm.level
        new_level = MasteryLevel(int(dm.level) + 1)
        dm.level = new_level
        dm.promotion_history.append((int(old_level), int(new_level), time.time()))

        # Reset accumulation counters after promotion — must re-earn at new level
        dm.recurrence_count = 0
        dm.cross_context_stability = 0.0
        dm.structural_coherence    = 0.0
        dm.retained_usefulness     = 0.0

        logger.info(
            "MasteryEngine[%s]: PROMOTED '%s' — %s -> %s",
            self.profile.entity_id, domain_id,
            old_level.label(), new_level.label(),
        )
        return new_level

    def get_depth(self, domain_id: str) -> MasteryLevel:
        """Query current mastery depth for a domain."""
        return self.profile.domain_level(domain_id)

    def get_profile_summary(self) -> Dict[str, Any]:
        """Return full mastery profile as a serialisable dict."""
        summary = self.profile.to_dict()
        summary["engine"] = "MasteryEngine"
        summary["promo_thresholds"] = {
            "recurrence_min": _PROMO_RECURRENCE_MIN,
            "cross_context_min": _PROMO_CROSS_CTX_MIN,
            "structural_min": _PROMO_STRUCTURAL_MIN,
            "retained_usefulness_min": _PROMO_RETAINED_MIN,
            "evidence_min": _PROMO_EVIDENCE_MIN,
        }
        return summary

    # ── Internal score computations ───────────────────────────────────────────

    @staticmethod
    def _compute_structural_coherence(dm: DomainMastery) -> float:
        """Rolling mean of coherence_score over all evidence snapshots."""
        snaps = dm.evidence_snapshots
        if not snaps:
            return 0.0
        total = sum(s.coherence_score for s in snaps)
        return total / len(snaps)

    @staticmethod
    def _compute_retained_usefulness(dm: DomainMastery) -> float:
        """Rolling mean of usefulness_score over all evidence snapshots."""
        snaps = dm.evidence_snapshots
        if not snaps:
            return 0.0
        total = sum(s.usefulness_score for s in snaps)
        return total / len(snaps)

    @staticmethod
    def _compute_cross_context_stability(dm: DomainMastery) -> float:
        """Fraction of evidence snapshots that represent novel contexts.

        A domain mastered in only one context has cross_context_stability = 0.
        A domain seen in N distinct contexts scores proportionally higher,
        capped at 1.0.
        """
        snaps = dm.evidence_snapshots
        if not snaps:
            return 0.0
        cross_count = sum(1 for s in snaps if s.cross_context)
        # Normalise: want at least 4 cross-context encounters to score 1.0
        return min(1.0, cross_count / 4.0)

    # ── Representation ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        domain_count = len(self.profile.domains)
        return (
            f"MasteryEngine(entity={self.profile.entity_id!r}, "
            f"domains={domain_count})"
        )
