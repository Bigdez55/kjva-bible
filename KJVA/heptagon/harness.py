"""Citadel/heptagon/harness.py — The Heptagon Harness Base Class

SPDX-License-Identifier: MIT

Base 7-layer cognitive harness. Each Council member instantiates one.
Same skeleton, radically different mind.

The Heptagon IS the Citadel. Each Council member IS a complete 7-layer
cognitive entity. The folding component means sub-heptagons can recursively
nest within parent heptagons.

Name -> Nature -> Law -> Code -> Status.
The name IS the law of the branch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .layers import (
    CalibrationLayer,
    EnforcementLayer,
    EvaluationLayer,
    InstrumentationLayer,
    KernelLayer,
    OntologyLayer,
    SchemaLayer,
    TraceRecord,
)
from .registry import (
    MEMBER_REGISTRY,
    MemberDescriptor,
)


@dataclass
class CycleResult:
    """Result of one cognitive cycle through all 7 layers."""
    member_id: str
    cycle_number: int
    decision: Optional[str] = None
    confidence: float = 0.0
    traces_emitted: int = 0
    invariants_violated: List[str] = field(default_factory=list)
    collaboration_requested: bool = False
    collaboration_domains: List[str] = field(default_factory=list)
    halt_eligible: bool = False


class HeptagonHarness:
    """Base 7-layer cognitive harness.

    Each Council member instantiates one with their own specializations.
    The harness provides the skeleton; the member provides the soul.

    Fraternal reconciliation: needs_help() is not failure.
    It is "I want to make sure I'm seeing this clearly."
    Love takes whatever form the moment demands.
    """

    def __init__(self, member_id: str, *,
                 descriptor: Optional[MemberDescriptor] = None) -> None:
        if descriptor is not None:
            # Explicit descriptor provided — for entities outside MEMBER_REGISTRY
            # (Forge, Tokenless interface, Offices). The descriptor IS the constitution.
            pass
        else:
            descriptor = MEMBER_REGISTRY.get(member_id)
            if descriptor is None:
                raise ValueError(
                    f"Member '{member_id}' not found in MEMBER_REGISTRY. "
                    "If it is not in the registry, it does not exist."
                )

        self.member_id = member_id
        self.descriptor = descriptor
        self._cycle_count = 0

        # Initialize all 7 layers
        self.l1_ontology = OntologyLayer(member_id=member_id)
        self.l2_schema = SchemaLayer(member_id=member_id)
        self.l3_kernel = KernelLayer(member_id=member_id)
        self.l4_instrumentation = InstrumentationLayer()
        self.l5_evaluation = EvaluationLayer()
        self.l6_calibration = CalibrationLayer()
        self.l7_enforcement = EnforcementLayer()

        # Children (recursive fold)
        self._children: List[HeptagonHarness] = []

    # ------------------------------------------------------------------
    # CORE COGNITIVE CYCLE
    # ------------------------------------------------------------------

    def cycle(self, input_signal: Dict[str, Any]) -> CycleResult:
        """One cognitive cycle through all 7 layers.

        L3 processes the signal.
        L4 records the trace.
        L5 evaluates metrics.
        L6 calibrates if needed.
        L7 enforces invariants.

        If confidence is below threshold, collaboration is requested
        instead of guessing. Before hallucination, ask for help.
        """
        self._cycle_count += 1

        # L3: Process through kernel
        decision, confidence = self._process_kernel(input_signal)

        # L4: Record trace
        trace = TraceRecord(
            cycle_number=self._cycle_count,
            phase="cycle",
            member_id=self.member_id,
            action="process",
            inputs=input_signal,
            outputs={"decision": decision, "confidence": confidence},
        )
        self.l4_instrumentation.emit(trace)

        # L5: Check for metric divergence (anti-Goodhart)
        divergences = self.l5_evaluation.check_divergence()

        # L6: Calibrate if needed (only layer that writes back to L3)
        if divergences:
            self._calibrate(divergences)

        # L7: Enforce invariants
        violations = self.l7_enforcement.check_all()
        violation_ids = [v.invariant_id for v in violations]

        # Anti-hallucination: if confidence is low, request collaboration
        needs_collab = self.needs_help(confidence, input_signal)
        collab_domains = self._identify_missing_domains(input_signal) if needs_collab else []

        return CycleResult(
            member_id=self.member_id,
            cycle_number=self._cycle_count,
            decision=decision,
            confidence=confidence,
            traces_emitted=len(self.l4_instrumentation.traces),
            invariants_violated=violation_ids,
            collaboration_requested=needs_collab,
            collaboration_domains=collab_domains,
            halt_eligible=self._check_halt_eligible(confidence, violation_ids),
        )

    # ------------------------------------------------------------------
    # INTELLIGENT COLLABORATION (Before hallucination, ask)
    # ------------------------------------------------------------------

    def needs_help(self, confidence: float, context: Dict[str, Any]) -> bool:
        """Does this member need collaboration on this decision?

        This is NOT failure. This is:
        'I want to make sure I'm seeing this clearly —
         let me invite someone who sees what I can't.'
        """
        # Below confidence threshold
        if confidence < self.l3_kernel.verification.coherence_threshold:
            return True

        # Decision crosses into another member's domain
        domains = context.get("domains", [])
        if domains and not self._is_my_domain(domains):
            return True

        # Novel situation with no precedent
        if context.get("novel", False):
            return True

        # Conflicting evidence
        return bool(context.get("conflicting_evidence", False))

    # ------------------------------------------------------------------
    # RECURSIVE FOLDING
    # ------------------------------------------------------------------

    def fold(self, child_member_id: str) -> HeptagonHarness:
        """Recursive folding: create a sub-heptagon within this one.

        Each child inherits the parent's identity but specializes deeper.
        This is how Apex agents operate WITHIN Council member Heptagons.

        Council Member Heptagon (L1-L7)
          └── Apex Agent sub-Heptagon (L1-L7, specialized)
               └── Leaf sub-agent sub-Heptagon (L1-L7, atomic)
                    └── Skill (executable procedure)
        """
        child = HeptagonHarness(child_member_id)
        self._children.append(child)
        return child

    # ------------------------------------------------------------------
    # AUTHORITY MODES (Ruth's pattern, universal)
    # ------------------------------------------------------------------

    def get_authority_mode(self) -> str:
        """Current authority mode: RECOMMENDATION, CONDITIONAL, or FULL."""
        # Default: RECOMMENDATION until graduated
        return "RECOMMENDATION"

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------

    def _process_kernel(self, signal: Dict[str, Any]) -> tuple:
        """Process signal through L3 kernel. Override in member specializations."""
        # Base implementation: pass-through with default confidence
        return str(signal), 0.5

    def _calibrate(self, divergences: List[str]) -> None:
        """L6 writes back into L3 to correct divergence."""
        # Base implementation: log divergences
        for d in divergences:
            trace = TraceRecord(
                cycle_number=self._cycle_count,
                phase="calibration",
                member_id=self.member_id,
                action="divergence_detected",
                outputs={"divergence": d},
            )
            self.l4_instrumentation.emit(trace)

    def _check_halt_eligible(self, confidence: float, violations: List[str]) -> bool:
        """Check if this cycle can halt (Ahki's formula)."""
        v = self.l3_kernel.verification
        return (
            confidence >= v.coherence_threshold
            and len(violations) == 0
        )

    def _is_my_domain(self, domains: List[str]) -> bool:
        """Check if the given domains fall within this member's jurisdiction."""
        my_jurisdictions = set(self.descriptor.technical_jurisdictions)
        return all(any(domain.lower() in j.lower() for j in my_jurisdictions) for domain in domains)

    def _identify_missing_domains(self, context: Dict[str, Any]) -> List[str]:
        """Identify which Council members should be invited for collaboration."""
        domains = context.get("domains", [])
        missing = []
        for domain in domains:
            if not any(domain.lower() in j.lower() for j in self.descriptor.technical_jurisdictions):
                # Find which member owns this domain
                for name, member in MEMBER_REGISTRY.items():
                    if name == self.member_id:
                        continue
                    if any(domain.lower() in j.lower() for j in member.technical_jurisdictions):
                        missing.append(name)
                        break
        return missing

    # ------------------------------------------------------------------
    # REPRESENTATION
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"HeptagonHarness(member='{self.member_id}', "
            f"class={self.descriptor.entity_class.name}, "
            f"domain='{self.descriptor.canonical_domain}', "
            f"cycles={self._cycle_count}, "
            f"children={len(self._children)})"
        )
