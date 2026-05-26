"""ai/tokenless-agent/src/heptagon/calibration.py
ParameterCalibrator — Heptagon Layer 6 (Calibration).

ADR-S49-01 §14 — L6 Mastery Redesign.

L6 is transformation-of-self, not merely sampler tuning.  The full L6 cycle
encompasses six stages that run BEFORE the sampler-tuning sub-routine:

  Stage 1: Resonance    — what reinforced during this cycle
  Stage 2: Friction     — what resisted
  Stage 3: Delta        — what changed
  Stage 4: Disposition  — what to do with the change
  Stage 5: Revisit      — when to return to this domain
  Stage 6: Promotion    — attempt mastery level advance (mastery.py)

And two stages that run AFTER sampler tuning:

  Stage 7: Lineage      — emit the delta for inheritance (lineage.py)
  Stage 8: Write-back   — persist retained learning (writeback.py)

The original 7 sampler-tuning rules remain intact and are invoked as the
dedicated ``calibrate()`` method, which is now a sub-step of ``full_l6_cycle()``.

Sampler-tuning rules (unchanged):
  High coherence + low relevance  -> reduce temperature (more focused)
  Low coherence                   -> reduce temperature AND top_p
  Low completeness                -> increase max_tokens
  High latency                    -> reduce max_tokens
  Low satisfaction + high errors  -> increase top_k (more diverse sampling)
  High satisfaction + no errors   -> gently restore defaults
  Repetition detected             -> increase repetition_penalty

All adjustments are bounded (BOUNDS dict) and applied incrementally via
LEARNING_RATE to prevent oscillation.
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .mastery import MasteryEngine, MasteryLevel
from .lineage import LineageEngine
from .writeback import WriteBackEngine, WriteBackRequest, WriteBackResult

logger = logging.getLogger("tokenless.heptagon.calibration")

# ── CalibrationProfile ───────────────────────────────────────────────────────

@dataclass
class CalibrationProfile:
    """Snapshot of all tuneable inference parameters."""

    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    repetition_penalty: float = 1.1
    max_tokens: int = 2048
    rate_limit_rpm: int = 120       # requests per minute
    rate_limit_window_s: int = 60   # window length (seconds)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "temperature": round(self.temperature, 4),
            "top_p": round(self.top_p, 4),
            "top_k": self.top_k,
            "repetition_penalty": round(self.repetition_penalty, 4),
            "max_tokens": self.max_tokens,
            "rate_limit_rpm": self.rate_limit_rpm,
            "rate_limit_window_s": self.rate_limit_window_s,
        }

    def clone(self) -> CalibrationProfile:
        return CalibrationProfile(
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            repetition_penalty=self.repetition_penalty,
            max_tokens=self.max_tokens,
            rate_limit_rpm=self.rate_limit_rpm,
            rate_limit_window_s=self.rate_limit_window_s,
        )


# ── AdjustmentRecord ────────────────────────────────────────────────────────

@dataclass
class AdjustmentRecord:
    """One logged parameter adjustment."""

    timestamp: float
    param: str
    old_value: float
    new_value: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "param": self.param,
            "old": round(self.old_value, 4),
            "new": round(self.new_value, 4),
            "reason": self.reason,
        }


# ── L6 Transformation dataclasses ────────────────────────────────────────────

@dataclass
class ResonanceSignal:
    """What reinforced during this L6 cycle.

    Resonance occurs when a pattern from a prior encounter recurs in a
    new context and contributes positively to response quality.  The
    higher the resonance_strength, the more the current input aligns with
    established pathways in the entity's domain knowledge.
    """

    domain_id: str
    resonance_strength: float           # 0.0–1.0
    contributing_dims: List[str]        # which quality dims drove resonance
    pattern_hash: str                   # opaque hash of the resonating pattern
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "resonance_strength": round(self.resonance_strength, 4),
            "contributing_dims": self.contributing_dims,
            "pattern_hash": self.pattern_hash,
            "timestamp": self.timestamp,
        }


@dataclass
class FrictionSignal:
    """What resisted during this L6 cycle.

    Friction occurs when the entity's existing pathways were insufficient
    or contradicted by the current input.  High friction is not failure —
    it is the signal that learning is possible here.
    """

    domain_id: str
    friction_strength: float            # 0.0–1.0
    blocking_dims: List[str]            # which quality dims showed resistance
    gap_description: str                # narrative of what was lacking
    recoverable: bool                   # can this friction be resolved by calibration?
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "friction_strength": round(self.friction_strength, 4),
            "blocking_dims": self.blocking_dims,
            "gap_description": self.gap_description,
            "recoverable": self.recoverable,
            "timestamp": self.timestamp,
        }


@dataclass
class DeltaExtraction:
    """What changed as a result of this L6 cycle.

    A delta exists only when resonance and friction together produce a net
    shift — either a strengthening of existing pathways (positive delta) or
    a revision of them (corrective delta).  Pure friction with no resonance
    produces a pending-delta: recorded but not yet integrated.
    """

    domain_id: str
    delta_type: str                     # "strengthening" | "corrective" | "pending"
    improvement_score: float            # net improvement: 0.0–1.0
    resonance_contribution: float       # fraction attributable to resonance
    friction_contribution: float        # fraction attributable to resolved friction
    source_hash: str                    # context hash for lineage linking
    evidence_count: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "delta_type": self.delta_type,
            "improvement_score": round(self.improvement_score, 4),
            "resonance_contribution": round(self.resonance_contribution, 4),
            "friction_contribution": round(self.friction_contribution, 4),
            "source_hash": self.source_hash,
            "evidence_count": self.evidence_count,
            "timestamp": self.timestamp,
        }


@dataclass
class DispositionDecision:
    """What to do with the extracted delta.

    The disposition resolves the delta into one of four actions:
      "integrate"    — incorporate into the entity's pathways immediately
      "schedule"     — mark for integration at a later revisit cycle
      "discard"      — the delta is noise or below threshold
      "escalate"     — delta exceeds the entity's authority bounds;
                       hand off to a higher-authority agent
    """

    domain_id: str
    action: str                         # "integrate" | "schedule" | "discard" | "escalate"
    retention_target: str               # "soul_only" | "archive_only" | "both" | "none"
    rationale: str
    improvement_score: float
    mastery_estimate: MasteryLevel
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "action": self.action,
            "retention_target": self.retention_target,
            "rationale": self.rationale,
            "improvement_score": round(self.improvement_score, 4),
            "mastery_estimate": int(self.mastery_estimate),
            "mastery_label": self.mastery_estimate.label(),
            "timestamp": self.timestamp,
        }


@dataclass
class RevisitSchedule:
    """When to return to this domain.

    Revisit scheduling ensures that domains with unresolved friction or
    pending deltas are not abandoned.  The revisit_after_cycles field is
    advisory — the Calibrator will request re-evaluation after that many
    cycles regardless of whether new queries arrive.
    """

    domain_id: str
    priority: str                           # "immediate" | "near" | "deferred" | "none"
    revisit_after_cycles: int               # 0 = no scheduled revisit
    friction_remaining: float               # how much friction was unresolved
    pending_delta_count: int                # deltas not yet integrated
    note: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "priority": self.priority,
            "revisit_after_cycles": self.revisit_after_cycles,
            "friction_remaining": round(self.friction_remaining, 4),
            "pending_delta_count": self.pending_delta_count,
            "note": self.note,
            "timestamp": self.timestamp,
        }


@dataclass
class L6CycleResult:
    """Complete result of one full_l6_cycle() execution."""

    session_id: str
    entity_id: str
    domain_id: str
    cycle_ts: float

    resonance: ResonanceSignal
    friction: FrictionSignal
    delta: DeltaExtraction
    disposition: DispositionDecision
    revisit: RevisitSchedule

    # Post-disposition results
    mastery_promoted: bool = False
    new_mastery_level: Optional[MasteryLevel] = None
    writeback_result: Optional[WriteBackResult] = None
    lineage_delta_id: Optional[str] = None

    # The sampler profile after tuning
    calibration_profile: Optional[CalibrationProfile] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "entity_id": self.entity_id,
            "domain_id": self.domain_id,
            "cycle_ts": self.cycle_ts,
            "resonance": self.resonance.to_dict(),
            "friction": self.friction.to_dict(),
            "delta": self.delta.to_dict(),
            "disposition": self.disposition.to_dict(),
            "revisit": self.revisit.to_dict(),
            "mastery_promoted": self.mastery_promoted,
            "new_mastery_level": (
                int(self.new_mastery_level) if self.new_mastery_level is not None else None
            ),
            "new_mastery_label": (
                self.new_mastery_level.label() if self.new_mastery_level is not None else None
            ),
            "writeback_result": (
                self.writeback_result.to_dict() if self.writeback_result else None
            ),
            "lineage_delta_id": self.lineage_delta_id,
            "calibration_profile": (
                self.calibration_profile.to_dict() if self.calibration_profile else None
            ),
        }


# ── ParameterCalibrator ─────────────────────────────────────────────────────

class ParameterCalibrator:
    """Adapts inference parameters AND orchestrates the L6 transformation cycle.

    The original sampler-tuning logic (Rules 1–7) is preserved exactly and
    accessible via ``calibrate(eval_metrics)`` for backward compatibility.

    The full L6 transformation cycle is accessible via ``full_l6_cycle()``,
    which runs all eight stages in order:
      1. compute_resonance()
      2. compute_friction()
      3. extract_delta()
      4. decide_disposition()
      5. schedule_revisit()
      6. promote_mastery()
      7. calibrate()           ← the original sampler tuner
      8. emit_lineage_delta()
      9. execute_writeback()
    """

    # Tuning bounds — parameter will never leave this range
    BOUNDS: Dict[str, Tuple[float, float]] = {
        "temperature": (0.1, 1.5),
        "top_p": (0.5, 1.0),
        "top_k": (10, 100),
        "repetition_penalty": (1.0, 1.5),
        "max_tokens": (256, 8192),
        "rate_limit_rpm": (30, 300),
    }

    LEARNING_RATE: float = 0.05

    # Thresholds for triggering specific sampler adjustments
    _LOW_RELEVANCE: float = 0.40
    _LOW_COHERENCE: float = 0.50
    _LOW_COMPLETENESS: float = 0.40
    _LOW_SATISFACTION: float = 0.40
    _HIGH_LATENCY_MS: float = 4000.0
    _HIGH_ERROR_RATE: float = 0.05      # 5% error threshold

    # Resonance thresholds
    _RESONANCE_STRONG: float = 0.65     # coherence + satisfaction above this = strong resonance
    _FRICTION_HIGH: float = 0.50        # when friction exceeds this, mark recoverable

    # Improvement score thresholds for disposition decisions
    _IMPROVEMENT_INTEGRATE: float = 0.20    # below this -> discard
    _IMPROVEMENT_ARCHIVE: float = 0.35      # above this -> include archive target

    def __init__(
        self,
        entity_id: str,
        profile: Optional[CalibrationProfile] = None,
    ) -> None:
        self.entity_id = entity_id
        self.profile: CalibrationProfile = profile or CalibrationProfile()
        self.adjustment_history: List[AdjustmentRecord] = []
        self._defaults: CalibrationProfile = self.profile.clone()

        # L6 sub-engines (one per entity)
        self._mastery = MasteryEngine(entity_id)
        self._lineage = LineageEngine(entity_id)
        self._writeback = WriteBackEngine(entity_id)

        # Revisit scheduler state: domain_id -> cycles remaining
        self._revisit_pending: Dict[str, int] = {}

        # Cycle counter (incremented by full_l6_cycle)
        self._cycle_count: int = 0

        logger.debug(
            "ParameterCalibrator[%s]: initialised — temp=%.2f top_p=%.2f top_k=%d",
            entity_id, self.profile.temperature, self.profile.top_p, self.profile.top_k,
        )

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 1 — Original sampler-tuning (Rules 1–7, unchanged)
    # ════════════════════════════════════════════════════════════════════════

    def calibrate(self, eval_metrics: Any) -> CalibrationProfile:
        """Adjust sampler parameters based on evaluation metrics.

        Parameters
        ----------
        eval_metrics : EvaluationMetrics (from evaluation.py)
            Must expose .relevance_score, .coherence_score,
            .completeness_score, .user_satisfaction, .latency_ms,
            .tokens_used, .errors attributes.

        Returns
        -------
        CalibrationProfile with updated values.
        """
        rel  = eval_metrics.relevance_score
        coh  = eval_metrics.coherence_score
        comp = eval_metrics.completeness_score
        sat  = eval_metrics.user_satisfaction
        lat  = eval_metrics.latency_ms
        errs = eval_metrics.errors

        # Rule 1: High coherence + low relevance -> reduce temperature (focus)
        if coh >= 0.6 and rel < self._LOW_RELEVANCE:
            self._adjust(
                "temperature", direction=-1.0, magnitude=0.5 - rel,
                reason=f"low relevance ({rel:.2f}) with good coherence ({coh:.2f})",
            )

        # Rule 2: Low coherence -> reduce temperature AND top_p
        if coh < self._LOW_COHERENCE:
            self._adjust(
                "temperature", direction=-1.0, magnitude=self._LOW_COHERENCE - coh,
                reason=f"low coherence ({coh:.2f})",
            )
            self._adjust(
                "top_p", direction=-1.0, magnitude=(self._LOW_COHERENCE - coh) * 0.5,
                reason=f"low coherence ({coh:.2f}) — tighten nucleus",
            )

        # Rule 3: Low completeness -> increase max_tokens
        if comp < self._LOW_COMPLETENESS:
            self._adjust(
                "max_tokens", direction=1.0, magnitude=(self._LOW_COMPLETENESS - comp) * 2048,
                reason=f"low completeness ({comp:.2f}) — increase token budget",
            )

        # Rule 4: High latency -> reduce max_tokens
        if lat > self._HIGH_LATENCY_MS:
            overshoot = (lat - self._HIGH_LATENCY_MS) / self._HIGH_LATENCY_MS
            self._adjust(
                "max_tokens", direction=-1.0, magnitude=overshoot * 1024,
                reason=f"high latency ({lat:.0f}ms > {self._HIGH_LATENCY_MS:.0f}ms)",
            )

        # Rule 5: Low satisfaction + errors -> increase top_k (diversity)
        if sat < self._LOW_SATISFACTION and errs > 0:
            self._adjust(
                "top_k", direction=1.0, magnitude=errs * 5.0,
                reason=f"low satisfaction ({sat:.2f}) with {errs} errors",
            )

        # Rule 6: High satisfaction + no errors -> gently restore defaults
        if sat >= 0.85 and errs == 0 and coh >= 0.7 and rel >= 0.6:
            self._drift_toward_defaults(rate=0.02)

        # Rule 7: Repetition detected (inferred from low coherence + high tokens)
        tokens = eval_metrics.tokens_used
        if coh < 0.4 and tokens > self.profile.max_tokens * 0.8:
            self._adjust(
                "repetition_penalty", direction=1.0, magnitude=0.1,
                reason=f"suspected repetition (coh={coh:.2f}, tok={tokens})",
            )

        logger.debug(
            "ParameterCalibrator[%s]: post-calibrate temp=%.3f top_p=%.3f top_k=%d "
            "max_tok=%d rep_pen=%.3f",
            self.entity_id,
            self.profile.temperature, self.profile.top_p, self.profile.top_k,
            self.profile.max_tokens, self.profile.repetition_penalty,
        )
        return self.profile

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 2 — L6 Transformation stages
    # ════════════════════════════════════════════════════════════════════════

    def compute_resonance(
        self,
        domain_id: str,
        eval_metrics: Any,
        context_hash: str,
    ) -> ResonanceSignal:
        """Measure reinforcement signals for the given domain.

        Resonance is high when the current cycle's quality scores confirm and
        extend existing mastery pathways.  It draws from:
          - coherence_score: structural continuity with known patterns
          - user_satisfaction: the pathway produced a satisfying outcome
          - mastery depth: prior mastery amplifies resonance (deeper = easier)

        The pattern_hash captures the combined fingerprint of the context and
        the quality dimensions, used for cross-cycle pattern matching.
        """
        rel  = eval_metrics.relevance_score
        coh  = eval_metrics.coherence_score
        sat  = eval_metrics.user_satisfaction
        comp = eval_metrics.completeness_score

        current_mastery = self._mastery.get_depth(domain_id)
        # Mastery amplifier: UNDERSTANDING=1.0, INNERSTANDING=1.1, OVERSTANDING=1.2
        mastery_amp = 1.0 + 0.1 * float(int(current_mastery))

        # Resonance = weighted blend of quality dims, amplified by mastery
        raw = (0.30 * coh + 0.30 * sat + 0.20 * rel + 0.20 * comp) * mastery_amp
        strength = max(0.0, min(1.0, raw))

        # Identify which dimensions contributed most
        dim_scores = {
            "coherence": coh,
            "satisfaction": sat,
            "relevance": rel,
            "completeness": comp,
        }
        contributing = [
            k for k, v in dim_scores.items() if v >= self._RESONANCE_STRONG
        ]

        # Build pattern hash from context + top contributing dims
        pattern_input = f"{context_hash}:{','.join(sorted(contributing))}:{domain_id}"
        pattern_hash = hashlib.sha256(pattern_input.encode()).hexdigest()[:16]

        signal = ResonanceSignal(
            domain_id=domain_id,
            resonance_strength=strength,
            contributing_dims=contributing,
            pattern_hash=pattern_hash,
        )
        logger.debug(
            "ParameterCalibrator[%s]: resonance domain='%s' strength=%.3f dims=%s",
            self.entity_id, domain_id, strength, contributing,
        )
        return signal

    def compute_friction(
        self,
        domain_id: str,
        eval_metrics: Any,
        resonance: ResonanceSignal,
    ) -> FrictionSignal:
        """Measure resistance signals for the given domain.

        Friction is the complement of resonance — it quantifies where existing
        pathways were insufficient or contradicted.  Friction is NOT failure;
        it is the learning signal.  High recoverable friction = high learning
        potential.

        Friction is recoverable when:
          - It is caused by quality deficits (low scores) rather than hard errors
          - The domain is within the entity's authority bounds
          - The residual gap is smaller than the total gap (partial coverage)
        """
        rel  = eval_metrics.relevance_score
        coh  = eval_metrics.coherence_score
        sat  = eval_metrics.user_satisfaction
        comp = eval_metrics.completeness_score
        errs = eval_metrics.errors

        # Friction = 1 - resonance_strength adjusted for error presence
        base_friction = 1.0 - resonance.resonance_strength
        # Hard errors increase friction non-linearly
        error_penalty = min(0.3, errs * 0.1)
        strength = min(1.0, base_friction + error_penalty)

        # Identify blocking dimensions (below threshold)
        blocking: List[str] = []
        if rel < self._LOW_RELEVANCE:
            blocking.append("relevance")
        if coh < self._LOW_COHERENCE:
            blocking.append("coherence")
        if sat < self._LOW_SATISFACTION:
            blocking.append("satisfaction")
        if comp < self._LOW_COMPLETENESS:
            blocking.append("completeness")

        # Recoverable = no hard errors and at least one dim is NOT blocking
        # (partial coverage means calibration has something to work with)
        non_blocking_count = 4 - len(blocking)
        recoverable = (errs == 0) and (non_blocking_count > 0)

        gap = (
            f"blocking dims: {blocking or ['none']}; "
            f"error count: {errs}; "
            f"resonance was {resonance.resonance_strength:.3f}"
        )

        signal = FrictionSignal(
            domain_id=domain_id,
            friction_strength=strength,
            blocking_dims=blocking,
            gap_description=gap,
            recoverable=recoverable,
        )
        logger.debug(
            "ParameterCalibrator[%s]: friction domain='%s' strength=%.3f "
            "blocking=%s recoverable=%s",
            self.entity_id, domain_id, strength, blocking, recoverable,
        )
        return signal

    def extract_delta(
        self,
        domain_id: str,
        resonance: ResonanceSignal,
        friction: FrictionSignal,
        eval_metrics: Any,
        context_hash: str,
    ) -> DeltaExtraction:
        """Extract what changed as a result of this cycle.

        A delta exists when resonance and friction together produce a net
        learning shift.  Three delta types:
          "strengthening" — resonance > friction; existing pathways confirmed
          "corrective"    — friction > resonance; pathways need revision
          "pending"       — both signals weak; record but do not integrate yet

        improvement_score = net benefit from this cycle, 0.0–1.0.
        Evidence count is pulled from the entity's current mastery record for
        the domain, reflecting accumulated prior evidence.
        """
        res_s = resonance.resonance_strength
        fri_s = friction.friction_strength
        net   = res_s - fri_s   # positive = more resonance than friction

        if res_s < 0.20 and fri_s < 0.20:
            delta_type = "pending"
            improvement = 0.0
        elif net >= 0.0:
            delta_type = "strengthening"
            # Improvement proportional to how decisively resonance won
            improvement = min(1.0, res_s * (1.0 - 0.5 * fri_s))
        else:
            delta_type = "corrective"
            # Corrective deltas still have improvement value — they correct errors
            # proportional to how recoverable the friction was
            improvement = min(1.0, abs(net) * (1.0 if friction.recoverable else 0.3))

        # Evidence count from accumulated mastery record
        dm = self._mastery.profile.get_or_create_domain(domain_id)
        evidence_count = dm.evidence_count

        delta = DeltaExtraction(
            domain_id=domain_id,
            delta_type=delta_type,
            improvement_score=improvement,
            resonance_contribution=res_s,
            friction_contribution=fri_s,
            source_hash=context_hash,
            evidence_count=evidence_count,
        )
        logger.debug(
            "ParameterCalibrator[%s]: delta domain='%s' type=%s improve=%.3f",
            self.entity_id, domain_id, delta_type, improvement,
        )
        return delta

    def decide_disposition(
        self,
        domain_id: str,
        delta: DeltaExtraction,
        friction: FrictionSignal,
    ) -> DispositionDecision:
        """Determine what to do with the extracted delta.

        Disposition actions:
          "integrate"  — score above threshold; retain in soul state immediately
          "schedule"   — score moderate; defer integration to revisit cycle
          "discard"    — score below threshold or pure noise
          "escalate"   — friction is non-recoverable and exceeds entity bounds

        Retention target:
          "none"         — discard/escalate
          "soul_only"    — integrate/schedule with low improvement
          "archive_only" — not used here (archive only on promote)
          "both"         — integrate with high improvement (above archive threshold)
        """
        imp = delta.improvement_score
        current_mastery = self._mastery.get_depth(domain_id)

        # Non-recoverable friction with high strength = escalate
        if not friction.recoverable and friction.friction_strength > self._FRICTION_HIGH:
            return DispositionDecision(
                domain_id=domain_id,
                action="escalate",
                retention_target="none",
                rationale=(
                    f"non-recoverable friction ({friction.friction_strength:.3f}) "
                    f"exceeds entity bounds"
                ),
                improvement_score=imp,
                mastery_estimate=current_mastery,
            )

        if imp < self._IMPROVEMENT_INTEGRATE:
            # Too weak to integrate
            action = "discard"
            target = "none"
            rationale = f"improvement_score {imp:.3f} below integrate threshold {self._IMPROVEMENT_INTEGRATE}"
        elif delta.delta_type == "pending":
            action = "schedule"
            target = "soul_only"
            rationale = "pending delta — both resonance and friction were weak; defer integration"
        elif imp >= self._IMPROVEMENT_ARCHIVE:
            action = "integrate"
            target = "both"
            rationale = (
                f"strong improvement ({imp:.3f} >= {self._IMPROVEMENT_ARCHIVE}); "
                f"integrate to soul and archive"
            )
        else:
            action = "integrate"
            target = "soul_only"
            rationale = (
                f"moderate improvement ({imp:.3f}); integrate to soul only"
            )

        disposition = DispositionDecision(
            domain_id=domain_id,
            action=action,
            retention_target=target,
            rationale=rationale,
            improvement_score=imp,
            mastery_estimate=current_mastery,
        )
        logger.debug(
            "ParameterCalibrator[%s]: disposition domain='%s' action=%s target=%s",
            self.entity_id, domain_id, action, target,
        )
        return disposition

    def schedule_revisit(
        self,
        domain_id: str,
        friction: FrictionSignal,
        delta: DeltaExtraction,
        disposition: DispositionDecision,
    ) -> RevisitSchedule:
        """Schedule when to return to this domain.

        Priority tiers:
          "immediate" — non-recoverable friction or escalation; return next cycle
          "near"      — recoverable friction with pending delta; return within 5 cycles
          "deferred"  — low friction, all integrated; revisit in 20 cycles
          "none"      — no friction, high resonance, nothing pending; no revisit needed

        The _revisit_pending dict is updated so the calibrator can inject
        revisit requests into future cycles.
        """
        fri_s = friction.friction_strength
        pending_count = 1 if delta.delta_type == "pending" else 0

        if disposition.action == "escalate":
            priority = "immediate"
            after_cycles = 1
            note = "escalated — non-recoverable friction requires immediate review"
        elif delta.delta_type == "pending" or (friction.recoverable and fri_s > 0.30):
            priority = "near"
            after_cycles = 5
            note = f"recoverable friction ({fri_s:.3f}) with pending integration"
        elif fri_s > 0.10:
            priority = "deferred"
            after_cycles = 20
            note = f"residual friction ({fri_s:.3f}) resolved; routine revisit"
        else:
            priority = "none"
            after_cycles = 0
            note = "no residual friction; no revisit scheduled"

        if after_cycles > 0:
            self._revisit_pending[domain_id] = after_cycles

        schedule = RevisitSchedule(
            domain_id=domain_id,
            priority=priority,
            revisit_after_cycles=after_cycles,
            friction_remaining=max(0.0, fri_s - delta.friction_contribution * 0.5),
            pending_delta_count=pending_count,
            note=note,
        )
        logger.debug(
            "ParameterCalibrator[%s]: revisit domain='%s' priority=%s after=%d",
            self.entity_id, domain_id, priority, after_cycles,
        )
        return schedule

    def promote_mastery(
        self,
        domain_id: str,
        eval_metrics: Any,
        context_hash: str,
        delta: DeltaExtraction,
    ) -> Optional[MasteryLevel]:
        """Attempt mastery promotion for the domain (delegates to mastery.py).

        First records new evidence in the MasteryEngine using the current
        evaluation metrics, then calls MasteryEngine.promote().

        Returns the new MasteryLevel if promoted, None otherwise.
        """
        # Feed evidence into the mastery engine
        self._mastery.update_evidence(
            domain_id=domain_id,
            context_hash=context_hash,
            coherence_score=eval_metrics.coherence_score,
            usefulness_score=eval_metrics.user_satisfaction,
            route_score=(1.0 / 6.0) * 3,       # 3/18 = route budget weight
            structure_score=(1.0 / 6.0) * 6,   # 6/18 = structure budget weight
            memory_score=(1.0 / 6.0) * 9,      # 9/18 = memory budget weight
            lawful=True,
        )

        # Attempt promotion
        new_level = self._mastery.promote(domain_id)
        if new_level is not None:
            # Promotion = generation advance in lineage
            self._lineage.advance_generation(domain_id)
            logger.info(
                "ParameterCalibrator[%s]: mastery promoted in '%s' -> %s",
                self.entity_id, domain_id, new_level.label(),
            )
        return new_level

    def emit_lineage_delta(
        self,
        domain_id: str,
        delta: DeltaExtraction,
        disposition: DispositionDecision,
    ) -> Optional[str]:
        """Record the learning delta for inheritance (delegates to lineage.py).

        Returns the delta_id string if recorded, None if below threshold.
        """
        current_mastery = self._mastery.get_depth(domain_id)
        recorded = self._lineage.record_delta(
            domain_id=domain_id,
            source_hash=delta.source_hash,
            improvement_score=delta.improvement_score,
            mastery_reached=current_mastery,
            retention_target=disposition.retention_target,
            evidence_count=delta.evidence_count,
            summary=(
                f"{delta.delta_type} delta: resonance={delta.resonance_contribution:.3f} "
                f"friction={delta.friction_contribution:.3f} "
                f"action={disposition.action}"
            ),
        )
        if recorded is not None:
            logger.debug(
                "ParameterCalibrator[%s]: lineage delta emitted '%s' for domain '%s'",
                self.entity_id, recorded.delta_id, domain_id,
            )
            return recorded.delta_id
        return None

    def execute_writeback(
        self,
        session_id: str,
        domain_id: str,
        delta: DeltaExtraction,
        disposition: DispositionDecision,
    ) -> WriteBackResult:
        """Persist retained learning to the appropriate targets (delegates to writeback.py).

        Returns a WriteBackResult describing what was written.
        """
        current_mastery = self._mastery.get_depth(domain_id)
        request = WriteBackRequest(
            session_id=session_id,
            entity_id=self.entity_id,
            domain_id=domain_id,
            target=disposition.retention_target,
            improvement_score=delta.improvement_score,
            mastery_reached=current_mastery,
            input_hash=delta.source_hash,
            evidence_count=delta.evidence_count,
        )
        result = self._writeback.consolidate(request)
        logger.debug(
            "ParameterCalibrator[%s]: writeback domain='%s' "
            "accepted=%s soul=%s journal=%s archive=%s",
            self.entity_id, domain_id,
            result.accepted, result.soul_written,
            result.journal_written, result.archive_written,
        )
        return result

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 3 — Full L6 cycle orchestration
    # ════════════════════════════════════════════════════════════════════════

    def full_l6_cycle(
        self,
        eval_metrics: Any,
        domain_id: str,
        context_hash: str,
        session_id: Optional[str] = None,
    ) -> L6CycleResult:
        """Execute the complete L6 transformation cycle.

        This is the authoritative L6 entry point.  It runs all 9 stages in
        order and returns a fully populated L6CycleResult.

        Parameters
        ----------
        eval_metrics : EvaluationMetrics
            Quality snapshot from L5 CycleEvaluator.
        domain_id : str
            The domain being processed in this cycle.
        context_hash : str
            Opaque hex hash of the current query context.  Used as the
            source_hash for lineage linking and cross-context detection.
        session_id : str | None
            Session identifier for write-back records.  A UUID is generated
            if not provided.
        """
        self._cycle_count += 1
        cycle_ts = time.time()
        session_id = session_id or str(uuid.uuid4())

        # Decrement revisit counters; fire debug log if a domain is due
        for d_id in list(self._revisit_pending):
            self._revisit_pending[d_id] -= 1
            if self._revisit_pending[d_id] <= 0:
                del self._revisit_pending[d_id]
                logger.debug(
                    "ParameterCalibrator[%s]: revisit cycle reached for domain '%s'",
                    self.entity_id, d_id,
                )

        # Stage 1: Resonance
        resonance = self.compute_resonance(domain_id, eval_metrics, context_hash)

        # Stage 2: Friction
        friction = self.compute_friction(domain_id, eval_metrics, resonance)

        # Stage 3: Delta extraction
        delta = self.extract_delta(
            domain_id, resonance, friction, eval_metrics, context_hash
        )

        # Stage 4: Disposition
        disposition = self.decide_disposition(domain_id, delta, friction)

        # Stage 5: Revisit scheduling
        revisit = self.schedule_revisit(domain_id, friction, delta, disposition)

        # Stage 6: Mastery promotion (MasteryEngine)
        new_mastery: Optional[MasteryLevel] = None
        promoted = False
        if disposition.action in {"integrate", "schedule"}:
            new_mastery = self.promote_mastery(
                domain_id, eval_metrics, context_hash, delta
            )
            promoted = new_mastery is not None
        else:
            # Still update evidence even when discarding/escalating
            self._mastery.update_evidence(
                domain_id=domain_id,
                context_hash=context_hash,
                coherence_score=eval_metrics.coherence_score,
                usefulness_score=eval_metrics.user_satisfaction,
                lawful=(disposition.action != "escalate"),
            )

        # Stage 7: Sampler tuning (original calibrate sub-routine)
        updated_profile = self.calibrate(eval_metrics)

        # Stage 8: Lineage delta emission (LineageEngine)
        lineage_delta_id: Optional[str] = None
        if disposition.action in {"integrate", "schedule"}:
            lineage_delta_id = self.emit_lineage_delta(domain_id, delta, disposition)

        # Stage 9: Write-back (WriteBackEngine)
        writeback_result: Optional[WriteBackResult] = None
        if disposition.action in {"integrate", "schedule"}:
            writeback_result = self.execute_writeback(
                session_id, domain_id, delta, disposition
            )

        result = L6CycleResult(
            session_id=session_id,
            entity_id=self.entity_id,
            domain_id=domain_id,
            cycle_ts=cycle_ts,
            resonance=resonance,
            friction=friction,
            delta=delta,
            disposition=disposition,
            revisit=revisit,
            mastery_promoted=promoted,
            new_mastery_level=new_mastery,
            writeback_result=writeback_result,
            lineage_delta_id=lineage_delta_id,
            calibration_profile=updated_profile.clone(),
        )

        logger.info(
            "ParameterCalibrator[%s]: L6 cycle #%d complete — "
            "domain='%s' res=%.3f fri=%.3f delta=%s imp=%.3f "
            "disposition=%s promoted=%s",
            self.entity_id, self._cycle_count,
            domain_id,
            resonance.resonance_strength,
            friction.friction_strength,
            delta.delta_type,
            delta.improvement_score,
            disposition.action,
            promoted,
        )
        return result

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 4 — Parameter adjustment engine (original, unchanged)
    # ════════════════════════════════════════════════════════════════════════

    def _adjust(
        self,
        param: str,
        direction: float,
        magnitude: float,
        reason: str,
    ) -> None:
        """Nudge a parameter within bounds by direction * magnitude * LEARNING_RATE."""
        current = getattr(self.profile, param)
        is_int = isinstance(current, int)
        delta = direction * magnitude * self.LEARNING_RATE
        new_val = current + delta

        lo, hi = self.BOUNDS[param]
        new_val = max(lo, min(hi, new_val))

        if is_int:
            new_val = int(round(new_val))

        if new_val != current:
            record = AdjustmentRecord(
                timestamp=time.time(),
                param=param,
                old_value=float(current),
                new_value=float(new_val),
                reason=reason,
            )
            self.adjustment_history.append(record)
            setattr(self.profile, param, new_val)
            logger.debug(
                "ParameterCalibrator[%s]: %s %.4f -> %.4f (%s)",
                self.entity_id, param, current, new_val, reason,
            )

    def _drift_toward_defaults(self, rate: float = 0.02) -> None:
        """Gently nudge all parameters toward their default values."""
        for param in self.BOUNDS:
            current = getattr(self.profile, param)
            default = getattr(self._defaults, param)
            if abs(current - default) < 0.001:
                continue
            direction = 1.0 if default > current else -1.0
            magnitude = abs(default - current)
            delta = direction * magnitude * rate
            is_int = isinstance(current, int)
            new_val = current + delta
            lo, hi = self.BOUNDS[param]
            new_val = max(lo, min(hi, new_val))
            if is_int:
                new_val = int(round(new_val))
            if new_val != current:
                setattr(self.profile, param, new_val)

    # ════════════════════════════════════════════════════════════════════════
    # SECTION 5 — Reset / export / import / diagnostics (original, unchanged)
    # ════════════════════════════════════════════════════════════════════════

    def reset_to_defaults(self) -> None:
        """Reset all sampler parameters to their initial default values."""
        self.profile = self._defaults.clone()
        logger.info("ParameterCalibrator[%s]: reset to defaults", self.entity_id)

    def get_profile(self) -> CalibrationProfile:
        """Return the current profile (reference, not copy)."""
        return self.profile

    def explain_adjustments(self, last_n: int = 10) -> List[str]:
        """Human-readable list of the most recent parameter adjustments."""
        records = self.adjustment_history[-last_n:]
        lines: List[str] = []
        for r in records:
            lines.append(
                f"{r.param}: {r.old_value:.4f} -> {r.new_value:.4f} — {r.reason}"
            )
        return lines

    def export_profile(self) -> Dict[str, Any]:
        """Serialise the current sampler profile to a dict."""
        return self.profile.to_dict()

    def import_profile(self, data: Dict[str, Any]) -> None:
        """Load a sampler profile from a dict, clamping to bounds."""
        for param, bounds in self.BOUNDS.items():
            if param in data:
                lo, hi = bounds
                val = data[param]
                is_int = isinstance(getattr(self.profile, param), int)
                val = max(lo, min(hi, val))
                if is_int:
                    val = int(round(val))
                setattr(self.profile, param, val)
        if "rate_limit_window_s" in data:
            self.profile.rate_limit_window_s = max(1, int(data["rate_limit_window_s"]))
        logger.info(
            "ParameterCalibrator[%s]: imported profile — %s",
            self.entity_id, self.profile.to_dict(),
        )

    def mastery_summary(self) -> Dict[str, Any]:
        """Return the full mastery profile as a serialisable dict."""
        return self._mastery.get_profile_summary()

    def lineage_summary(self) -> Dict[str, Any]:
        """Return the full lineage state as a serialisable dict."""
        return self._lineage.get_lineage_summary()

    def revisit_pending(self) -> Dict[str, int]:
        """Return the current revisit schedule (domain -> cycles remaining)."""
        return dict(self._revisit_pending)

    def summary(self) -> str:
        """One-line summary of current calibration state."""
        p = self.profile
        return (
            f"ParameterCalibrator[{self.entity_id}]["
            f"temp={p.temperature:.2f} top_p={p.top_p:.2f} "
            f"top_k={p.top_k} max_tok={p.max_tokens} "
            f"rep={p.repetition_penalty:.2f} rpm={p.rate_limit_rpm}] "
            f"(cycle={self._cycle_count} adj={len(self.adjustment_history)} "
            f"domains={len(self._mastery.profile.domains)})"
        )

    def __repr__(self) -> str:
        return self.summary()
