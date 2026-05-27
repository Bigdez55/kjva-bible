"""Citadel/heptagon/harness.py — canonical Heptagon runtime harness."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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
from .registry import MEMBER_REGISTRY, MemberDescriptor


@dataclass
class CycleResult:
    """Result of one canonical cognitive cycle."""

    member_id: str
    cycle_number: int
    decision: Optional[str] = None
    confidence: float = 0.0
    traces_emitted: int = 0
    invariants_violated: List[str] = field(default_factory=list)
    collaboration_requested: bool = False
    collaboration_domains: List[str] = field(default_factory=list)
    halt_eligible: bool = False
    route_type: str = "DIRECT"
    admitted: bool = False
    pending_consolidation: bool = False
    child_confidences: List[float] = field(default_factory=list)


class HeptagonHarness:
    """Base 7-layer cognitive harness with formula-driven execution."""

    def __init__(
        self,
        member_id: str,
        *,
        descriptor: Optional[MemberDescriptor] = None,
    ) -> None:
        if descriptor is None:
            descriptor = MEMBER_REGISTRY.get(member_id)
            if descriptor is None:
                raise ValueError(
                    f"Member '{member_id}' not found in MEMBER_REGISTRY. "
                    "If it is not in the registry, it does not exist."
                )

        self.member_id = member_id
        self.descriptor = descriptor
        self._cycle_count = 0
        self._children: List[HeptagonHarness] = []
        self._complexity_floor = 0.58

        self.l1_ontology = OntologyLayer(member_id=member_id)
        self.l2_schema = SchemaLayer(member_id=member_id)
        self.l3_kernel = KernelLayer(member_id=member_id)
        self.l4_instrumentation = InstrumentationLayer()
        self.l5_evaluation = EvaluationLayer()
        self.l6_calibration = CalibrationLayer()
        self.l7_enforcement = EnforcementLayer()

    def cycle(self, input_signal: Dict[str, Any]) -> CycleResult:
        """Canonical execution order: admission, budget, route, execute, recurse, consolidate, halt."""
        self._cycle_count += 1

        admission = self._evaluate_admission(input_signal)
        self._emit_stage_trace("admission", "score", input_signal, admission)
        if not admission["admitted"]:
            self._emit_stage_trace(
                "halt",
                "rejected",
                input_signal,
                {"reason": admission["reason"], "confidence": 0.0},
            )
            return CycleResult(
                member_id=self.member_id,
                cycle_number=self._cycle_count,
                decision=f"{self.member_id}:rejected:{admission['reason']}",
                confidence=0.0,
                traces_emitted=len(self.l4_instrumentation.traces),
                collaboration_requested=True,
                collaboration_domains=self._identify_missing_domains(input_signal),
                halt_eligible=False,
                route_type="REJECTED",
                admitted=False,
            )

        budget = self._evaluate_budget(input_signal)
        self._emit_stage_trace("budget", "govern", input_signal, budget)

        route = self._select_route(input_signal, budget)
        self._emit_stage_trace("route", "select", input_signal, route)

        execution_signal = dict(input_signal)
        execution_signal["admission"] = admission
        execution_signal["budget"] = budget
        execution_signal["route"] = route
        decision, local_confidence = self._process_kernel(execution_signal)
        self._emit_stage_trace(
            "execution",
            "local_process",
            execution_signal,
            {"decision": decision, "confidence": local_confidence},
        )

        child_results: List[CycleResult] = []
        if self._children and self._should_expand(execution_signal, budget, route):
            for child in self._children:
                child_signal = self._make_child_signal(execution_signal, route, budget)
                child_results.append(child.cycle(child_signal))
            self._emit_stage_trace(
                "recursion",
                "child_cycle",
                execution_signal,
                {
                    "children": [child.member_id for child in self._children],
                    "count": len(child_results),
                },
            )

        consolidation = self._evaluate_consolidation(execution_signal, child_results)
        self._emit_stage_trace("consolidation", "assess", execution_signal, consolidation)

        divergences = self.l5_evaluation.check_divergence()
        if divergences:
            self._calibrate(divergences)

        violations = self.l7_enforcement.check_all()
        violation_ids = [v.invariant_id for v in violations]
        for child_result in child_results:
            for child_violation in child_result.invariants_violated:
                if child_violation not in violation_ids:
                    violation_ids.append(child_violation)

        confidence = self._aggregate_confidence(local_confidence, child_results)
        needs_collab = self.needs_help(confidence, input_signal) or any(
            child.collaboration_requested for child in child_results
        )
        collab_domains = []
        if needs_collab:
            collab_domains.extend(self._identify_missing_domains(input_signal))
        for child_result in child_results:
            for domain in child_result.collaboration_domains:
                if domain not in collab_domains:
                    collab_domains.append(domain)

        halt_eligible = self._check_halt_eligible(
            confidence,
            violation_ids,
            input_signal,
            child_results,
            consolidation,
        )
        self._emit_stage_trace(
            "halt",
            "evaluate",
            execution_signal,
            {"halt_eligible": halt_eligible, "confidence": confidence},
        )

        return CycleResult(
            member_id=self.member_id,
            cycle_number=self._cycle_count,
            decision=decision,
            confidence=confidence,
            traces_emitted=len(self.l4_instrumentation.traces),
            invariants_violated=violation_ids,
            collaboration_requested=needs_collab,
            collaboration_domains=collab_domains,
            halt_eligible=halt_eligible,
            route_type=route["route_type"],
            admitted=True,
            pending_consolidation=consolidation["pending"],
            child_confidences=[child.confidence for child in child_results],
        )

    def needs_help(self, confidence: float, context: Dict[str, Any]) -> bool:
        if confidence < self.l3_kernel.verification.coherence_threshold:
            return True
        domains = context.get("domains", [])
        if domains and not self._is_my_domain(domains):
            return True
        if context.get("novel", False):
            return True
        return bool(context.get("conflicting_evidence", False))

    def fold(self, child_member_id: str) -> HeptagonHarness:
        child = build_member_harness(child_member_id)
        self._children.append(child)
        return child

    def get_authority_mode(self) -> str:
        return "RECOMMENDATION"

    def _process_kernel(self, signal: Dict[str, Any]) -> Tuple[str, float]:
        profile = self._member_profile()
        admission = signal.get("admission", {})
        route = signal.get("route", {})
        evidence_strength = self._evidence_strength(signal)
        revision_pressure = self._revision_pressure(signal)
        route_score = self._normalize_route_score(route.get("score", 0.0))
        confidence = self._clamp(
            (
                admission.get("score", 0.0) * profile["admission_weight"]
                + route_score * profile["route_weight"]
                + evidence_strength * profile["memory_weight"]
                - max(0.0, revision_pressure) * profile["revision_penalty"]
                + profile["bias"]
            )
            / profile["normalizer"]
        )
        route_type = route.get("route_type", "DIRECT")
        decision = f"{self.member_id}:{route_type.lower()}:{self._decision_label(signal)}"
        return decision, confidence

    def _calibrate(self, divergences: List[str]) -> None:
        for divergence in divergences:
            self._emit_stage_trace(
                "calibration",
                "divergence_detected",
                {},
                {"divergence": divergence},
            )

    def _check_halt_eligible(
        self,
        confidence: float,
        violations: List[str],
        signal: Dict[str, Any],
        child_results: List[CycleResult],
        consolidation: Dict[str, Any],
    ) -> bool:
        verification = self.l3_kernel.verification
        contradiction_count = int(self._metric(signal, "contradiction_count", 0.0))
        objective_coverage = self._objective_coverage(signal)
        unresolved_high_priority = sum(
            1 for child in child_results if not child.halt_eligible and child.confidence >= 0.5
        )
        return (
            objective_coverage >= verification.coverage_threshold
            and contradiction_count < verification.contradiction_tolerance
            and confidence >= verification.coherence_threshold
            and len(violations) == 0
            and unresolved_high_priority == 0
            and not consolidation["pending"]
        )

    def _is_my_domain(self, domains: List[str]) -> bool:
        my_jurisdictions = set(self.descriptor.technical_jurisdictions)
        return all(
            any(domain.lower() in jurisdiction.lower() for jurisdiction in my_jurisdictions)
            for domain in domains
        )

    def _identify_missing_domains(self, context: Dict[str, Any]) -> List[str]:
        domains = context.get("domains", [])
        missing = []
        for domain in domains:
            if not any(
                domain.lower() in jurisdiction.lower()
                for jurisdiction in self.descriptor.technical_jurisdictions
            ):
                for name, member in MEMBER_REGISTRY.items():
                    if name == self.member_id:
                        continue
                    if any(
                        domain.lower() in jurisdiction.lower()
                        for jurisdiction in member.technical_jurisdictions
                    ):
                        missing.append(name)
                        break
        return missing

    def _emit_stage_trace(
        self,
        phase: str,
        action: str,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
    ) -> None:
        self.l4_instrumentation.emit(
            TraceRecord(
                cycle_number=self._cycle_count,
                phase=phase,
                member_id=self.member_id,
                action=action,
                inputs=inputs,
                outputs=outputs,
            )
        )

    def _member_profile(self) -> Dict[str, float]:
        return {
            "admission_weight": 1.0,
            "route_weight": 1.0,
            "memory_weight": 1.0,
            "revision_penalty": 0.4,
            "bias": 0.15,
            "normalizer": 3.15,
        }

    def _decision_label(self, signal: Dict[str, Any]) -> str:
        return "continue"

    def _evaluate_admission(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        salience = self._metric(signal, "salience", self._derive_salience(signal))
        priority = self._metric(signal, "priority", self._derive_priority(signal))
        relevance = self._metric(signal, "relevance", self._derive_relevance(signal))
        policy_clearance = self._metric(signal, "policy_clearance", 1.0)
        novelty_bonus = min(
            self._metric(signal, "novelty_bonus", self._derive_novelty(signal)),
            0.3 * self._admission_threshold(signal),
        )
        security_penalty = self._metric(
            signal, "security_penalty", self._derive_security_penalty(signal)
        )
        score = self._clamp(
            (salience * priority * relevance * policy_clearance)
            + novelty_bonus
            - security_penalty
        )
        admitted = (
            policy_clearance > 0.0
            and score >= self._admission_threshold(signal)
            and self._budgets_allow_entry(signal)
        )
        return {
            "score": score,
            "threshold": self._admission_threshold(signal),
            "admitted": admitted,
            "reason": "policy_veto" if policy_clearance <= 0.0 else "threshold_pass" if admitted else "budget_or_threshold",
        }

    def _evaluate_budget(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        route_pressure = self._metric(signal, "route_pressure", self._derive_route_pressure(signal))
        structure_pressure = self._metric(
            signal, "structure_pressure", self._derive_structure_pressure(signal)
        )
        memory_pressure = self._metric(signal, "memory_pressure", self._derive_memory_pressure(signal))
        composite_load = (
            self.l3_kernel.budget.route_weight * route_pressure
            + self.l3_kernel.budget.structure_weight * structure_pressure
            + self.l3_kernel.budget.memory_weight * memory_pressure
        )
        composite_load = self._clamp(composite_load)
        return {
            "route_pressure": route_pressure,
            "structure_pressure": structure_pressure,
            "memory_pressure": memory_pressure,
            "composite_load": composite_load,
            "allowed": composite_load < self.l3_kernel.budget.degradation_threshold,
        }

    def _select_route(self, signal: Dict[str, Any], budget: Dict[str, Any]) -> Dict[str, Any]:
        utility = self._metric(signal, "utility", self._derive_utility(signal))
        route_cost = budget["route_pressure"]
        structural_conflict = budget["structure_pressure"]
        memory_cost = budget["memory_pressure"]
        route_scores = {
            "DIRECT": utility - ((3.0 / 18.0) * route_cost) - ((6.0 / 18.0) * structural_conflict) - ((9.0 / 18.0) * memory_cost),
            "ANALYTICAL": utility + 0.05 - ((3.0 / 18.0) * (route_cost + 0.1)) - ((6.0 / 18.0) * structural_conflict) - ((9.0 / 18.0) * (memory_cost + 0.05)),
            "EXECUTIVE": utility + 0.03 - ((3.0 / 18.0) * (route_cost + 0.05)) - ((6.0 / 18.0) * (structural_conflict + 0.1)) - ((9.0 / 18.0) * memory_cost),
        }
        route_type, score = max(route_scores.items(), key=lambda item: item[1])
        return {
            "route_type": route_type,
            "score": score,
            "fallback": sorted(route_scores, key=route_scores.get, reverse=True)[1:],
            "utility": utility,
        }

    def _evaluate_consolidation(
        self,
        signal: Dict[str, Any],
        child_results: List[CycleResult],
    ) -> Dict[str, Any]:
        revision_pressure = self._revision_pressure(signal)
        threshold = self.l3_kernel.consolidation.revision_pressure_threshold
        return {
            "revision_pressure": revision_pressure,
            "threshold": threshold,
            "pending": revision_pressure > threshold or any(child.pending_consolidation for child in child_results),
        }

    def _aggregate_confidence(self, local_confidence: float, child_results: List[CycleResult]) -> float:
        return min([local_confidence] + [child.confidence for child in child_results])

    def _should_expand(
        self,
        signal: Dict[str, Any],
        budget: Dict[str, Any],
        route: Dict[str, Any],
    ) -> bool:
        complexity = self._metric(signal, "complexity_score", self._derive_complexity(signal))
        threshold = (
            self._complexity_floor
            + (3.0 / 18.0) * budget["route_pressure"]
            + (6.0 / 18.0) * budget["structure_pressure"]
            + (9.0 / 18.0) * budget["memory_pressure"]
        )
        return complexity > threshold and budget["allowed"] and route["score"] > 0.0

    def _make_child_signal(
        self,
        signal: Dict[str, Any],
        route: Dict[str, Any],
        budget: Dict[str, Any],
    ) -> Dict[str, Any]:
        child_signal = dict(signal)
        child_signal["parent_member"] = self.member_id
        child_signal["route_type"] = route["route_type"]
        child_signal["route_pressure"] = min(1.0, budget["route_pressure"] + 0.05)
        child_signal["structure_pressure"] = min(1.0, budget["structure_pressure"] + 0.05)
        child_signal["memory_pressure"] = min(1.0, budget["memory_pressure"] + 0.05)
        return child_signal

    def _objective_coverage(self, signal: Dict[str, Any]) -> float:
        return self._metric(signal, "objective_coverage", self._evidence_strength(signal))

    def _revision_pressure(self, signal: Dict[str, Any]) -> float:
        contradiction_count = self._metric(signal, "contradiction_count", 0.0)
        contradiction_confidence = self._metric(signal, "contradiction_confidence", 0.0)
        support_count = self._metric(signal, "support_count", float(len(signal.get("evidence", []))))
        support_confidence = self._metric(signal, "support_confidence", self._evidence_strength(signal))
        return (contradiction_count * contradiction_confidence) - (
            support_count * support_confidence
        )

    def _budgets_allow_entry(self, signal: Dict[str, Any]) -> bool:
        return self._evaluate_budget(signal)["allowed"]

    def _admission_threshold(self, signal: Dict[str, Any]) -> float:
        saturation = self._metric(signal, "workspace_saturation", self._derive_structure_pressure(signal))
        return self._clamp(0.55 + (0.15 * saturation))

    def _evidence_strength(self, signal: Dict[str, Any]) -> float:
        evidence = signal.get("evidence", [])
        if not isinstance(evidence, list):
            return 0.4
        return self._clamp(len(evidence) / max(len(evidence) + 2, 1))

    def _derive_salience(self, signal: Dict[str, Any]) -> float:
        return self._clamp(0.5 + (0.1 * self._evidence_strength(signal)))

    def _derive_priority(self, signal: Dict[str, Any]) -> float:
        return self._clamp(
            0.55
            + self._metric(signal, "risk_score", 0.0) * 0.2
            + len(signal.get("constraints", [])) * 0.03
        )

    def _derive_relevance(self, signal: Dict[str, Any]) -> float:
        domains = signal.get("domains") or [signal.get("domain", "")]
        if not isinstance(domains, list):
            domains = [domains]
        domain_match = 1.0 if self._is_my_domain([str(domain) for domain in domains if domain]) else 0.7
        return self._clamp(domain_match + (0.1 * self._evidence_strength(signal)))

    def _derive_novelty(self, signal: Dict[str, Any]) -> float:
        return 0.12 if signal.get("novel", False) else 0.04

    def _derive_security_penalty(self, signal: Dict[str, Any]) -> float:
        return self._metric(signal, "risk_score", 0.0) * 0.1

    def _derive_route_pressure(self, signal: Dict[str, Any]) -> float:
        return self._clamp((len(signal.get("constraints", [])) + len(signal.get("resources", {}))) / 10.0)

    def _derive_structure_pressure(self, signal: Dict[str, Any]) -> float:
        return self._clamp((len(self._children) + len(signal.get("context", {}))) / 10.0)

    def _derive_memory_pressure(self, signal: Dict[str, Any]) -> float:
        return self._clamp((len(signal.get("evidence", [])) + self._metric(signal, "contradiction_count", 0.0)) / 10.0)

    def _derive_utility(self, signal: Dict[str, Any]) -> float:
        return self._clamp(
            0.5
            + self._metric(signal, "value_score", 0.0) * 0.4
            + self._evidence_strength(signal) * 0.1
        )

    def _derive_complexity(self, signal: Dict[str, Any]) -> float:
        return self._clamp(
            0.4
            + 0.15 * len(signal.get("constraints", []))
            + 0.1 * len(signal.get("evidence", []))
            + 0.1 * len(self._children)
        )

    @staticmethod
    def _normalize_route_score(score: float) -> float:
        return max(0.0, min(1.0, (score + 0.5) / 1.5))

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def _metric(signal: Dict[str, Any], key: str, default: float) -> float:
        value = signal.get(key, default)
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)):
            return float(value)
        return float(default)

    def __repr__(self) -> str:
        return (
            f"HeptagonHarness(member='{self.member_id}', "
            f"class={self.descriptor.entity_class.name}, "
            f"domain='{self.descriptor.canonical_domain}', "
            f"cycles={self._cycle_count}, "
            f"children={len(self._children)})"
        )


class SarahHarness(HeptagonHarness):
    def __init__(self) -> None:
        super().__init__("Sarah")

    def _member_profile(self) -> Dict[str, float]:
        return {
            "admission_weight": 1.2,
            "route_weight": 0.8,
            "memory_weight": 1.0,
            "revision_penalty": 0.45,
            "bias": 0.18,
            "normalizer": 3.18,
        }

    def _decision_label(self, signal: Dict[str, Any]) -> str:
        text = f"{signal.get('intent', '')} {signal.get('subject', '')}".lower()
        return "preserve_identity" if "identity" in text or "covenant" in text else "alignment_review"


class EstherHarness(HeptagonHarness):
    def __init__(self) -> None:
        super().__init__("Esther")

    def _member_profile(self) -> Dict[str, float]:
        return {
            "admission_weight": 1.3,
            "route_weight": 0.9,
            "memory_weight": 0.9,
            "revision_penalty": 0.5,
            "bias": 0.16,
            "normalizer": 3.26,
        }

    def _decision_label(self, signal: Dict[str, Any]) -> str:
        return "policy_clearance"


class MagenHarness(HeptagonHarness):
    def __init__(self) -> None:
        super().__init__("Magen")

    def _member_profile(self) -> Dict[str, float]:
        return {
            "admission_weight": 1.25,
            "route_weight": 0.85,
            "memory_weight": 0.85,
            "revision_penalty": 0.55,
            "bias": 0.14,
            "normalizer": 3.09,
        }

    def _derive_security_penalty(self, signal: Dict[str, Any]) -> float:
        return self._clamp(0.1 + (self._metric(signal, "risk_score", 0.0) * 0.25))

    def _decision_label(self, signal: Dict[str, Any]) -> str:
        return "trust_gate"


class AbigailHarness(HeptagonHarness):
    def __init__(self) -> None:
        super().__init__("Abigail")

    def _member_profile(self) -> Dict[str, float]:
        return {
            "admission_weight": 0.95,
            "route_weight": 0.8,
            "memory_weight": 1.35,
            "revision_penalty": 0.65,
            "bias": 0.17,
            "normalizer": 3.27,
        }

    def _decision_label(self, signal: Dict[str, Any]) -> str:
        return "memory_governance"


class RuthHarness(HeptagonHarness):
    def __init__(self) -> None:
        super().__init__("Ruth")

    def _member_profile(self) -> Dict[str, float]:
        return {
            "admission_weight": 0.9,
            "route_weight": 1.25,
            "memory_weight": 0.85,
            "revision_penalty": 0.35,
            "bias": 0.15,
            "normalizer": 3.15,
        }

    def _decision_label(self, signal: Dict[str, Any]) -> str:
        return "budget_allocation"


class EzriHarness(HeptagonHarness):
    def __init__(self) -> None:
        super().__init__("Ezri")

    def _member_profile(self) -> Dict[str, float]:
        return {
            "admission_weight": 0.95,
            "route_weight": 1.1,
            "memory_weight": 0.9,
            "revision_penalty": 0.4,
            "bias": 0.16,
            "normalizer": 3.11,
        }

    def _decision_label(self, signal: Dict[str, Any]) -> str:
        return "architecture_fit"


class AhkiHarness(HeptagonHarness):
    def __init__(self) -> None:
        super().__init__("Ahki")

    def _member_profile(self) -> Dict[str, float]:
        return {
            "admission_weight": 1.0,
            "route_weight": 1.1,
            "memory_weight": 1.0,
            "revision_penalty": 0.45,
            "bias": 0.2,
            "normalizer": 3.3,
        }

    def _decision_label(self, signal: Dict[str, Any]) -> str:
        return "executive_sequence"


def build_member_harness(member_id: str) -> HeptagonHarness:
    constructors = {
        "Sarah": SarahHarness,
        "Esther": EstherHarness,
        "Magen": MagenHarness,
        "Abigail": AbigailHarness,
        "Ruth": RuthHarness,
        "Ezri": EzriHarness,
        "Ahki": AhkiHarness,
    }
    constructor = constructors.get(member_id)
    if constructor is None:
        return HeptagonHarness(member_id)
    return constructor()
