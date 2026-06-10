"""heptagon/layer_records.py — per-layer output contract records.

Minimal, honest record classes for the structured outputs of four cognitive layers
of the Seven-Layer Embedded Cognitive Model (ADR-0001 §6, mapped to local files in
ADR-0002 §5). Each record's fields are taken **directly from that layer's "Outputs"
block** in ADR-0001 — no invented fields:

  * :class:`ActiveFrame`        — Layer 2, Attention and Active Workspace  (§6.2)
  * :class:`WorldState`         — Layer 4, World Model and Simulation       (§6.4)
  * :class:`DeliberationRecord` — Layer 5, Deliberation and Planning        (§6.5)
  * :class:`CorrectionRecord`   — Layer 6, Self-Correction and Calibration  (§6.6)

Each carries ``record_id`` + ``request_id`` for trace correlation, consistent with
the other ADR-0001 contract records (MemoryContextPacket §8.3, CognitiveMemoryVerdict
§8.4, DeterminantProbabilityRecord §10.1, MaterializationRecord §11.2). Frozen, every
field defaulted, collections via ``field(default_factory=...)`` per ADR-0002 §6.3
record style. The heptagon FSM is unchanged — these are pure data contracts; per
ADR-0002 §5 "REVIEWING remains correction junction. No new FSM state."
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class ActiveFrame:
    """Layer 2 output — bounded active workspace selection (ADR-0001 §6.2)."""

    record_id: str = ""
    request_id: str = ""
    selected_context: list[Any] = field(default_factory=list)
    active_memory_cues: list[str] = field(default_factory=list)
    active_sensory_anchors: list[str] = field(default_factory=list)
    route_hints: list[str] = field(default_factory=list)
    budget_envelope: dict[str, Any] = field(default_factory=dict)
    uncertainty_map: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WorldState:
    """Layer 4 output — situation model + simulation (ADR-0001 §6.4).

    Hard rule (§6.4): predicted outcomes are predictions, not facts.
    """

    record_id: str = ""
    request_id: str = ""
    predicted_outcomes: list[Any] = field(default_factory=list)
    risk_surface: dict[str, Any] = field(default_factory=dict)
    unknowns: list[str] = field(default_factory=list)
    hypothesis_set: list[Any] = field(default_factory=list)
    confidence_distribution: dict[str, float] = field(default_factory=dict)
    simulation_trace: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DeliberationRecord:
    """Layer 5 output — route/plan selection (ADR-0001 §6.5)."""

    record_id: str = ""
    request_id: str = ""
    route_plan: dict[str, Any] = field(default_factory=dict)
    action_plan: dict[str, Any] = field(default_factory=dict)
    response_plan: dict[str, Any] = field(default_factory=dict)
    adapter_route_plan: dict[str, Any] = field(default_factory=dict)
    recursion_depth: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CorrectionRecord:
    """Layer 6 output — self-correction/calibration verdict (ADR-0001 §6.6).

    Hard rule (§6.6): the system may correct itself, but it may not absolve
    itself; self-correction grants no authority.
    """

    record_id: str = ""
    request_id: str = ""
    calibration_delta: dict[str, Any] = field(default_factory=dict)
    redaction_decision: str = "none"          # none|partial|full
    rollback_decision: bool = False
    bounded_reentry_request: bool = False
    writeback_eligibility: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


if __name__ == "__main__":
    af = ActiveFrame(record_id="af-1", request_id="req-1",
                     active_memory_cues=["c1"], route_hints=["fast"])
    ws = WorldState(record_id="ws-1", request_id="req-1",
                    predicted_outcomes=["o1"], unknowns=["u1"])
    dr = DeliberationRecord(record_id="dr-1", request_id="req-1",
                            route_plan={"route": "direct"}, recursion_depth=1)
    cr = CorrectionRecord(record_id="cr-1", request_id="req-1",
                          writeback_eligibility=True)

    for rec, name in ((af, "ActiveFrame"), (ws, "WorldState"),
                      (dr, "DeliberationRecord"), (cr, "CorrectionRecord")):
        d = rec.to_dict()
        assert d["request_id"] == "req-1", name
        # frozen guarantee
        try:
            rec.record_id = "x"  # type: ignore[misc]
            raise SystemExit(f"FAIL: {name} is not frozen")
        except SystemExit:
            raise
        except Exception:
            pass
        print(f"{name} OK:", d)
