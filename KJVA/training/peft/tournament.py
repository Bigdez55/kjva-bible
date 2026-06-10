"""
peft/tournament.py — Training Tournament

Trains (or simulates training of) multiple PEFT method candidates,
evaluates them on a shared benchmark, and selects the Pareto-optimal winner.

Selection criteria:
  - Domain accuracy (did it learn the specialty?)
  - Base retention (did it preserve base model quality?)
  - Parameter count (how many trainable params?)
  - Estimated latency overhead
  - Merge safety
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .fingerprint import TaskFingerprint, DataSize, DomainShift


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CandidateResult:
    method_id: str
    domain_accuracy: float        # 0.0 – 1.0
    base_retention: float         # 0.0 – 1.0
    trainable_params: int
    latency_overhead_ms: float
    merge_safe: bool
    notes: str = ""


@dataclass
class ParetoWinner:
    winner: CandidateResult
    all_results: list[CandidateResult]
    selection_reason: str


# ---------------------------------------------------------------------------
# Heuristic property table for known methods
# ---------------------------------------------------------------------------

# Format: method_id → (base_accuracy, base_retention, param_scale, latency_ms, merge_safe)
# These are qualitative baselines; the fingerprint modulates them.
_METHOD_TABLE: dict[str, tuple[float, float, int, float, bool]] = {
    "ia3":           (0.72, 0.96, 3_000,    0.5,  True),
    "bitfit":        (0.65, 0.97, 1_500,    0.2,  True),
    "prefix":        (0.70, 0.93, 10_000,   1.0,  False),
    "lora":          (0.82, 0.91, 50_000,   1.5,  True),
    "adalora":       (0.85, 0.90, 60_000,   2.0,  True),
    "dora":          (0.88, 0.89, 65_000,   2.2,  True),
    "qlora":         (0.81, 0.90, 45_000,   1.4,  True),
    "houlsby_adapter": (0.80, 0.88, 80_000, 3.0,  True),
    "rsloRA":        (0.83, 0.91, 52_000,   1.6,  True),
    "pissa":         (0.84, 0.90, 51_000,   1.5,  True),
    "vera":          (0.79, 0.92, 20_000,   1.3,  True),
}

# Score weights for Pareto selection
_WEIGHTS = {
    "domain_accuracy": 0.35,
    "base_retention":  0.25,
    "params":          0.15,   # lower is better → inverted
    "latency":         0.15,   # lower is better → inverted
    "merge_safe":      0.10,
}

_MAX_PARAMS = 500_000    # normalisation ceiling
_MAX_LATENCY = 10.0      # ms normalisation ceiling


# ---------------------------------------------------------------------------
# Tournament
# ---------------------------------------------------------------------------

class TrainingTournament:
    """
    Runs a dry (heuristic) or live tournament over candidate PEFT methods.
    """

    def __init__(self, candidates: list[str]) -> None:
        self.candidates = candidates

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_dry(
        self,
        plasticity_map: "LayerPlasticityMap",  # type: ignore[name-defined]
        fingerprint: TaskFingerprint,
        constraints: "AdaptationConstraints",  # type: ignore[name-defined]
    ) -> ParetoWinner:
        """
        Simulate tournament using heuristic scores.
        No actual training is performed.
        """
        results = [
            self._heuristic_score(method_id, fingerprint)
            for method_id in self.candidates
        ]
        return self.pareto_select(results)

    def pareto_select(self, results: list[CandidateResult]) -> ParetoWinner:
        """
        Identify the Pareto front (non-dominated candidates) then pick the
        highest weighted-score winner.

        Selection doctrine: "cheapest sufficient change."  Lightweight methods
        like IA3 frequently win because they land on the Pareto front (their
        high base-retention score means they are not dominated by heavier
        methods), and the weighted scoring rewards low parameter count and low
        latency.  To preference accuracy-first selection on hard tasks, raise
        _WEIGHTS["domain_accuracy"] above 0.50 or restrict the candidate list
        to fingerprint.recommended_peft_stack upstream.
        """
        if not results:
            raise ValueError("Cannot select from empty results list.")

        non_dominated = self._pareto_front(results)
        scored = [(r, self._weighted_score(r)) for r in non_dominated]
        scored.sort(key=lambda x: x[1], reverse=True)
        winner, win_score = scored[0]

        reason = (
            f"{winner.method_id} selected from {len(non_dominated)} Pareto-optimal "
            f"candidates with weighted score {win_score:.3f}. "
            f"accuracy={winner.domain_accuracy:.2f}, "
            f"retention={winner.base_retention:.2f}, "
            f"params={winner.trainable_params:,}"
        )
        return ParetoWinner(winner=winner, all_results=results, selection_reason=reason)

    # ------------------------------------------------------------------
    # Heuristic scoring
    # ------------------------------------------------------------------

    def _heuristic_score(
        self,
        method_id: str,
        fingerprint: TaskFingerprint,
    ) -> CandidateResult:
        """
        Return plausible heuristic scores based on known method properties
        and the task fingerprint.
        """
        base_acc, base_ret, base_params, base_lat, merge_safe = _METHOD_TABLE.get(
            method_id, (0.75, 0.88, 70_000, 2.5, True)
        )

        # Domain shift multiplier: higher shift → accuracy improves for stronger methods,
        # but retention degrades more.
        shift_val = fingerprint.domain_shift.value  # 0–4
        shift_factor = 1.0 + shift_val * 0.02       # up to +8% accuracy for high shift

        # Data size multiplier: more data → accuracy improves
        data_bonus = {
            DataSize.TINY:       -0.06,
            DataSize.SMALL:      -0.03,
            DataSize.MEDIUM:      0.00,
            DataSize.LARGE:       0.03,
            DataSize.VERY_LARGE:  0.06,
        }.get(fingerprint.data_size, 0.0)

        # Reasoning requirement: high-capacity methods benefit more
        reasoning_bonus = 0.0
        if fingerprint.reasoning_requirement == "high":
            reasoning_bonus = 0.03 if method_id in ("dora", "adalora") else 0.0

        accuracy = min(0.99, base_acc * shift_factor + data_bonus + reasoning_bonus)
        retention = max(0.70, base_ret - shift_val * 0.01)

        # Scale params by domain shift (higher shift → larger rank needed)
        param_scale = 1.0 + shift_val * 0.15
        trainable_params = int(base_params * param_scale)

        return CandidateResult(
            method_id=method_id,
            domain_accuracy=round(accuracy, 4),
            base_retention=round(retention, 4),
            trainable_params=trainable_params,
            latency_overhead_ms=round(base_lat * (1.0 + shift_val * 0.05), 3),
            merge_safe=merge_safe,
            notes=f"heuristic estimate (shift={fingerprint.domain_shift.name}, "
                  f"data={fingerprint.data_size.name})",
        )

    # ------------------------------------------------------------------
    # Pareto utilities
    # ------------------------------------------------------------------

    def _pareto_front(self, results: list[CandidateResult]) -> list[CandidateResult]:
        """Remove dominated candidates. A candidate is dominated if another
        beats it on all five objectives simultaneously."""
        non_dom: list[CandidateResult] = []
        for candidate in results:
            dominated = False
            for other in results:
                if other is candidate:
                    continue
                if self._dominates(other, candidate):
                    dominated = True
                    break
            if not dominated:
                non_dom.append(candidate)
        return non_dom if non_dom else results  # safety fallback

    def _dominates(self, a: CandidateResult, b: CandidateResult) -> bool:
        """Return True if a dominates b (better or equal on all, strictly better on one)."""
        a_better_or_equal = (
            a.domain_accuracy >= b.domain_accuracy
            and a.base_retention >= b.base_retention
            and a.trainable_params <= b.trainable_params
            and a.latency_overhead_ms <= b.latency_overhead_ms
            and (a.merge_safe or not b.merge_safe)
        )
        a_strictly_better = (
            a.domain_accuracy > b.domain_accuracy
            or a.base_retention > b.base_retention
            or a.trainable_params < b.trainable_params
            or a.latency_overhead_ms < b.latency_overhead_ms
            or (a.merge_safe and not b.merge_safe)
        )
        return a_better_or_equal and a_strictly_better

    def _weighted_score(self, r: CandidateResult) -> float:
        """Compute scalar priority score for final selection."""
        param_score = 1.0 - min(r.trainable_params / _MAX_PARAMS, 1.0)
        lat_score = 1.0 - min(r.latency_overhead_ms / _MAX_LATENCY, 1.0)
        merge_score = 1.0 if r.merge_safe else 0.0

        return (
            _WEIGHTS["domain_accuracy"] * r.domain_accuracy
            + _WEIGHTS["base_retention"] * r.base_retention
            + _WEIGHTS["params"] * param_score
            + _WEIGHTS["latency"] * lat_score
            + _WEIGHTS["merge_safe"] * merge_score
        )
