"""
tests/test_conflict_resolver.py — ConflictResolver unit tests

Covers:
  - check_compatibility: explicit conflicts_with, domain_bleed via
    routing_never_activate_when, style clash via _domain_clash
  - prune() with delta_provider for weight-space conflict
  - latency budget cap at all three thresholds (40ms→1, 99ms→2, 150ms→4)
  - weight renormalization sums to 1.0 after pruning
  - ConflictReport fields populated correctly
  - zero-norm guard in compute_delta_cosine_similarity
"""
from __future__ import annotations

import sys
from pathlib import Path

import mlx.core as mx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from peft.base import ActiveExpert, AdapterGenomeRecord, HardwareBudget, RoutePlan
from peft.conflict import ConflictResolver
from peft.registry import AdapterGenomeRegistry, RegistryEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _genome(name: str, **kwargs) -> AdapterGenomeRecord:
    defaults = dict(
        version="1.0.0",
        base_model="base_v1",
        peft_method="lora",
        delta_family="WEIGHT_ADDITIVE",
    )
    defaults.update(kwargs)
    return AdapterGenomeRecord(name=name, **defaults)


def _registry(*genomes: AdapterGenomeRecord) -> AdapterGenomeRegistry:
    """Build a minimal in-memory registry without touching the filesystem."""
    reg = object.__new__(AdapterGenomeRegistry)
    reg.entries = {}
    for g in genomes:
        entry = RegistryEntry(
            genome=g,
            checkpoint_path="",
            genome_path="",
            status="gated",
            registered_at="2026-01-01T00:00:00+00:00",
        )
        reg.entries[g.name] = entry
    return reg


def _plan(*pairs: tuple[str, float]) -> RoutePlan:
    """Build a RoutePlan from (expert_id, weight) pairs."""
    experts = [ActiveExpert(eid, w) for eid, w in pairs]
    return RoutePlan(active_experts=experts)


def _budget(latency_ms: float) -> HardwareBudget:
    return HardwareBudget(latency_target_ms=latency_ms)


resolver = ConflictResolver()


# ---------------------------------------------------------------------------
# check_compatibility — explicit conflicts_with
# ---------------------------------------------------------------------------

class TestCheckCompatibilityExplicitConflict:
    def test_a_lists_b_incompatible(self):
        a = _genome("adp_a", conflicts_with=["adp_b"])
        b = _genome("adp_b")
        assert resolver.check_compatibility(a, b) is False

    def test_b_lists_a_incompatible(self):
        a = _genome("adp_a")
        b = _genome("adp_b", conflicts_with=["adp_a"])
        assert resolver.check_compatibility(a, b) is False

    def test_no_conflict_listed_compatible(self):
        a = _genome("adp_a")
        b = _genome("adp_b")
        assert resolver.check_compatibility(a, b) is True


# ---------------------------------------------------------------------------
# check_compatibility — domain_bleed via routing_never_activate_when
# ---------------------------------------------------------------------------

class TestCheckCompatibilityDomainBleed:
    def test_a_never_when_b_domain(self):
        a = _genome("adp_a", routing_never_activate_when=["clinical"])
        b = _genome("adp_b", purpose_domains=["clinical"])
        assert resolver.check_compatibility(a, b) is False

    def test_a_never_when_b_task(self):
        a = _genome("adp_a", routing_never_activate_when=["summarize"])
        b = _genome("adp_b", purpose_tasks=["summarize"])
        assert resolver.check_compatibility(a, b) is False

    def test_b_never_when_a_domain(self):
        a = _genome("adp_a", purpose_domains=["legal"])
        b = _genome("adp_b", routing_never_activate_when=["legal"])
        assert resolver.check_compatibility(a, b) is False

    def test_no_overlap_compatible(self):
        a = _genome("adp_a", routing_never_activate_when=["clinical"])
        b = _genome("adp_b", purpose_domains=["technical"])
        assert resolver.check_compatibility(a, b) is True


# ---------------------------------------------------------------------------
# check_compatibility — style clash via _domain_clash
# ---------------------------------------------------------------------------

class TestCheckCompatibilityStyleClash:
    def test_medical_fiction_clash(self):
        a = _genome("adp_a", purpose_domains=["medical"])
        b = _genome("adp_b", purpose_domains=["fiction"])
        assert resolver.check_compatibility(a, b) is False

    def test_clinical_creative_clash(self):
        a = _genome("adp_a", purpose_domains=["clinical"])
        b = _genome("adp_b", purpose_domains=["creative"])
        assert resolver.check_compatibility(a, b) is False

    def test_legal_casual_clash(self):
        a = _genome("adp_a", purpose_domains=["legal"])
        b = _genome("adp_b", purpose_domains=["casual"])
        assert resolver.check_compatibility(a, b) is False

    def test_safety_jailbreak_clash(self):
        a = _genome("adp_a", purpose_domains=["safety"])
        b = _genome("adp_b", purpose_domains=["jailbreak"])
        assert resolver.check_compatibility(a, b) is False

    def test_reversed_clash_detected(self):
        a = _genome("adp_a", purpose_domains=["fiction"])
        b = _genome("adp_b", purpose_domains=["medical"])
        assert resolver.check_compatibility(a, b) is False

    def test_technical_technical_compatible(self):
        a = _genome("adp_a", purpose_domains=["technical"])
        b = _genome("adp_b", purpose_domains=["technical"])
        assert resolver.check_compatibility(a, b) is True


# ---------------------------------------------------------------------------
# prune() — weight-space conflict via delta_provider
# ---------------------------------------------------------------------------

class TestPruneWeightSpaceConflict:
    def test_opposing_deltas_prunes_lower_weight(self):
        plan = _plan(("high_w", 0.8), ("low_w", 0.2))
        ga = _genome("high_w")
        gb = _genome("low_w")
        reg = _registry(ga, gb)

        # Opposing unit vectors → cosine = -1
        deltas = {
            "high_w": mx.array([1.0, 0.0, 0.0]),
            "low_w": mx.array([-1.0, 0.0, 0.0]),
        }

        report = resolver.prune(
            plan, reg, _budget(100.0),
            delta_provider=deltas.get,
            weight_conflict_threshold=-0.5,
        )

        assert "low_w" in report.pruned_experts
        remaining = [e.expert_id for e in report.final_plan.active_experts]
        assert "high_w" in remaining
        assert "low_w" not in remaining

    def test_aligned_deltas_not_pruned(self):
        plan = _plan(("adp_a", 0.5), ("adp_b", 0.5))
        reg = _registry(_genome("adp_a"), _genome("adp_b"))

        # Identical direction → cosine = 1.0
        deltas = {
            "adp_a": mx.array([1.0, 0.0]),
            "adp_b": mx.array([1.0, 0.0]),
        }

        report = resolver.prune(plan, reg, _budget(100.0), delta_provider=deltas.get)
        assert report.pruned_experts == []

    def test_missing_delta_skipped_no_false_positive(self):
        plan = _plan(("adp_a", 0.5), ("adp_b", 0.5))
        reg = _registry(_genome("adp_a"), _genome("adp_b"))

        # Only one delta available — pair must be skipped
        deltas = {"adp_a": mx.array([1.0, 0.0])}

        report = resolver.prune(plan, reg, _budget(100.0), delta_provider=deltas.get)
        assert report.pruned_experts == []


# ---------------------------------------------------------------------------
# prune() — latency budget cap at three thresholds
# ---------------------------------------------------------------------------

class TestPruneLatencyBudget:
    def _four_experts(self) -> RoutePlan:
        return _plan(("e1", 0.4), ("e2", 0.3), ("e3", 0.2), ("e4", 0.1))

    def _five_experts(self) -> RoutePlan:
        return _plan(("e1", 0.5), ("e2", 0.4), ("e3", 0.3), ("e4", 0.2), ("e5", 0.1))

    def _reg_n(self, n: int) -> AdapterGenomeRegistry:
        return _registry(*[_genome(f"e{i}") for i in range(1, n + 1)])

    def test_40ms_caps_at_1(self):
        plan = self._four_experts()
        report = resolver.prune(plan, self._reg_n(4), _budget(40.0))
        assert len(report.final_plan.active_experts) == 1

    def test_99ms_caps_at_2(self):
        plan = self._four_experts()
        report = resolver.prune(plan, self._reg_n(4), _budget(99.0))
        assert len(report.final_plan.active_experts) == 2

    def test_150ms_caps_at_4(self):
        plan = self._five_experts()
        report = resolver.prune(plan, self._reg_n(5), _budget(150.0))
        assert len(report.final_plan.active_experts) == 4

    def test_40ms_retains_highest_weight(self):
        plan = self._four_experts()
        report = resolver.prune(plan, self._reg_n(4), _budget(40.0))
        assert report.final_plan.active_experts[0].expert_id == "e1"

    def test_99ms_retains_two_highest_weight(self):
        plan = self._four_experts()
        report = resolver.prune(plan, self._reg_n(4), _budget(99.0))
        ids = {e.expert_id for e in report.final_plan.active_experts}
        assert ids == {"e1", "e2"}


# ---------------------------------------------------------------------------
# Weight renormalization sums to 1.0 after pruning
# ---------------------------------------------------------------------------

class TestWeightRenormalization:
    def test_weights_sum_to_one_after_budget_prune(self):
        plan = _plan(("e1", 0.4), ("e2", 0.3), ("e3", 0.2), ("e4", 0.1))
        reg = _registry(*[_genome(f"e{i}") for i in range(1, 5)])

        report = resolver.prune(plan, reg, _budget(99.0))

        total = sum(e.weight for e in report.final_plan.active_experts)
        assert abs(total - 1.0) < 1e-6

    def test_weights_sum_to_one_after_conflict_prune(self):
        plan = _plan(("adp_a", 0.8), ("adp_b", 0.2))
        ga = _genome("adp_a", conflicts_with=["adp_b"])
        gb = _genome("adp_b")
        reg = _registry(ga, gb)

        report = resolver.prune(plan, reg, _budget(200.0))

        total = sum(e.weight for e in report.final_plan.active_experts)
        assert abs(total - 1.0) < 1e-6

    def test_single_expert_weight_is_one(self):
        plan = _plan(("adp_a", 0.37))
        reg = _registry(_genome("adp_a"))

        report = resolver.prune(plan, reg, _budget(200.0))

        assert abs(report.final_plan.active_experts[0].weight - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# ConflictReport fields populated correctly
# ---------------------------------------------------------------------------

class TestConflictReportFields:
    def test_no_conflict_report(self):
        plan = _plan(("adp_a", 0.6), ("adp_b", 0.4))
        reg = _registry(_genome("adp_a"), _genome("adp_b"))

        report = resolver.prune(plan, reg, _budget(200.0))

        assert report.has_conflicts is False
        assert report.conflicts == []
        assert report.pruned_experts == []
        assert report.final_plan.conflict_free is True

    def test_conflict_detected_report_fields(self):
        plan = _plan(("adp_a", 0.8), ("adp_b", 0.2))
        ga = _genome("adp_a", conflicts_with=["adp_b"])
        gb = _genome("adp_b")
        reg = _registry(ga, gb)

        report = resolver.prune(plan, reg, _budget(200.0))

        assert report.has_conflicts is True
        assert len(report.conflicts) >= 1
        assert len(report.pruned_experts) >= 1

        conflict = report.conflicts[0]
        assert "type" in conflict
        assert "expert_ids" in conflict
        assert "resolution" in conflict

    def test_latency_conflict_type_in_report(self):
        plan = _plan(("e1", 0.4), ("e2", 0.3), ("e3", 0.2), ("e4", 0.1))
        reg = _registry(*[_genome(f"e{i}") for i in range(1, 5)])

        report = resolver.prune(plan, reg, _budget(40.0))

        types = [c["type"] for c in report.conflicts]
        assert "latency_conflict" in types

    def test_weight_space_conflict_type_in_report(self):
        plan = _plan(("adp_a", 0.8), ("adp_b", 0.2))
        reg = _registry(_genome("adp_a"), _genome("adp_b"))
        deltas = {
            "adp_a": mx.array([1.0, 0.0]),
            "adp_b": mx.array([-1.0, 0.0]),
        }

        report = resolver.prune(
            plan, reg, _budget(200.0),
            delta_provider=deltas.get,
            weight_conflict_threshold=-0.5,
        )

        types = [c["type"] for c in report.conflicts]
        assert "weight_space_conflict" in types


# ---------------------------------------------------------------------------
# compute_delta_cosine_similarity — zero-norm guard
# ---------------------------------------------------------------------------

class TestDeltaCosineSimilarity:
    def test_zero_vector_returns_zero(self):
        a = mx.zeros((4,))
        b = mx.array([1.0, 0.0, 0.0, 0.0])
        result = resolver.compute_delta_cosine_similarity(a, b)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_both_zero_returns_zero(self):
        a = mx.zeros((4,))
        b = mx.zeros((4,))
        result = resolver.compute_delta_cosine_similarity(a, b)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_identical_vectors_return_one(self):
        v = mx.array([1.0, 2.0, 3.0])
        result = resolver.compute_delta_cosine_similarity(v, v)
        assert result == pytest.approx(1.0, abs=1e-5)

    def test_opposing_vectors_return_negative_one(self):
        a = mx.array([1.0, 0.0, 0.0])
        b = mx.array([-1.0, 0.0, 0.0])
        result = resolver.compute_delta_cosine_similarity(a, b)
        assert result == pytest.approx(-1.0, abs=1e-5)

    def test_orthogonal_vectors_return_zero(self):
        a = mx.array([1.0, 0.0])
        b = mx.array([0.0, 1.0])
        result = resolver.compute_delta_cosine_similarity(a, b)
        assert result == pytest.approx(0.0, abs=1e-5)

    def test_result_is_python_float(self):
        a = mx.array([1.0, 2.0])
        b = mx.array([3.0, 4.0])
        result = resolver.compute_delta_cosine_similarity(a, b)
        assert isinstance(result, float)

    def test_2d_arrays_flattened(self):
        a = mx.array([[1.0, 0.0], [0.0, 0.0]])
        b = mx.array([[-1.0, 0.0], [0.0, 0.0]])
        result = resolver.compute_delta_cosine_similarity(a, b)
        assert result == pytest.approx(-1.0, abs=1e-5)
