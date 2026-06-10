"""memory/cognitive_memory_verdict.py — the cognition-to-memory contract record.

Defines :class:`CognitiveMemoryVerdict`, the direct cognition→memory verdict
specified in ADR-0001 §8.4. After the seven-layer pass evaluates a request, this
verdict tells the Memory and Continuity layer (§6.3) what to write back, how to
consolidate, what retention/decay to apply, and whether privacy/invariant gates
passed — enforcing "Memory is earned, not accumulated" (§6.3) and the writeback
materialization rule (§11.3).

Field set is the FULL ADR-0001 §8.4 JSON block (ADR > the task's curated subset),
including ``salience_adjustments``, ``contradiction_resolutions``, and
``lineage_level`` which the task omits but a consumer may set. Frozen, every field
defaulted, collections via ``field(default_factory=...)`` per ADR-0002 §6.3 style.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class CognitiveMemoryVerdict:
    """Direct cognition→memory verdict (ADR-0001 §8.4)."""

    verdict_id: str = ""
    request_id: str = ""
    # direct|memory_mediated|salience_routed|executive_mediated|lateral_peer
    route_type: str = "direct"
    active_layers: list[int] = field(default_factory=list)
    salience_adjustments: list[Any] = field(default_factory=list)
    quality_metrics: dict[str, Any] = field(default_factory=dict)
    # pass|warning|violation|critical
    invariant_verdict: str = "pass"
    # allow|redact|block
    privacy_verdict: str = "allow"
    writeback_targets: list[str] = field(default_factory=list)
    consolidation_directives: list[Any] = field(default_factory=list)
    contradiction_resolutions: list[Any] = field(default_factory=list)
    # understanding|innerstanding|overstanding
    lineage_level: str = "understanding"
    # discard|session|episodic|semantic|archival
    retention_mode: str = "session"
    decay_adjustment: float = 0.0
    recall_reinforcement: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


if __name__ == "__main__":
    v = CognitiveMemoryVerdict(
        verdict_id="vd-1",
        request_id="req-1",
        route_type="memory_mediated",
        active_layers=[2, 3, 4],
        invariant_verdict="pass",
        privacy_verdict="allow",
        writeback_targets=["episodic"],
        retention_mode="episodic",
        recall_reinforcement=0.15,
    )
    d = v.to_dict()
    assert d["route_type"] == "memory_mediated"
    assert d["active_layers"] == [2, 3, 4]
    assert CognitiveMemoryVerdict().retention_mode == "session"
    try:
        v.retention_mode = "archival"  # type: ignore[misc]
        raise SystemExit("FAIL: record is not frozen")
    except Exception:
        pass
    print("CognitiveMemoryVerdict OK:", d)
