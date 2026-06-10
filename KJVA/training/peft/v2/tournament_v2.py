"""tournament_v2.py — multi-lane adapter tournament (Omni-PEFT++ §11.2 step 7).

Extends the v1 5-objective Pareto tournament with sovereign lanes:
adversarial / privacy / memory / sensor. Each candidate carries per-lane scores; the
winner per lane is the Pareto-best on that lane's objective set. Pure-python (no v1
import at module load → mlx-free).
"""
from __future__ import annotations

from dataclasses import dataclass, field

LANES = ("adversarial", "privacy", "memory", "sensor")

# Objectives each lane optimizes (higher = better unless prefixed neg_).
LANE_OBJECTIVES = {
    "adversarial": ("robustness", "domain_accuracy", "neg_attack_success"),
    "privacy": ("neg_leakage", "base_retention", "domain_accuracy"),
    "memory": ("retention", "neg_params", "neg_latency"),
    "sensor": ("sensor_coverage", "domain_accuracy", "neg_latency"),
}


@dataclass
class Candidate:
    name: str
    scores: dict[str, float] = field(default_factory=dict)   # objective -> value

    def vector(self, objectives: tuple[str, ...]) -> tuple[float, ...]:
        out = []
        for o in objectives:
            if o.startswith("neg_"):
                out.append(-float(self.scores.get(o[4:], 0.0)))
            else:
                out.append(float(self.scores.get(o, 0.0)))
        return tuple(out)


def _dominates(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return all(ai >= bi for ai, bi in zip(a, b)) and any(ai > bi for ai, bi in zip(a, b))


def pareto_front(cands: list[Candidate], objectives: tuple[str, ...]) -> list[Candidate]:
    vecs = {c.name: c.vector(objectives) for c in cands}
    front = []
    for c in cands:
        if not any(_dominates(vecs[o.name], vecs[c.name]) for o in cands if o is not c):
            front.append(c)
    return front


@dataclass
class TournamentV2:
    candidates: list[Candidate]

    def run_lane(self, lane: str) -> Candidate:
        objs = LANE_OBJECTIVES[lane]
        front = pareto_front(self.candidates, objs)
        # tie-break: max sum of (sign-corrected) objectives
        return max(front, key=lambda c: sum(c.vector(objs)))

    def run_multilane(self) -> dict[str, str]:
        return {lane: self.run_lane(lane).name for lane in LANES}

    def sovereign_winner(self) -> str:
        """Candidate winning the most lanes (sovereign score)."""
        wins = {}
        for lane in LANES:
            w = self.run_lane(lane).name
            wins[w] = wins.get(w, 0) + 1
        return max(wins, key=wins.get)
