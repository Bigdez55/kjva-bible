"""memory/memory_context_packet.py — the memory-to-cognition contract record.

Defines :class:`MemoryContextPacket`, the direct memory→cognition packet specified
in ADR-0001 §8.3. It is the bounded output of the cue-triggered recall cascade
(§8.5): a small, ranked, source-grounded selection that Layer 2 (Attention/Active
Workspace, §6.2) and Layer 4 (World Model, §6.4) consume — **not** the whole memory
horizon (§8.1: "Perfect custody does not mean everything is always active.").

Field set is the FULL ADR-0001 §8.3 JSON block (source-of-truth priority: ADR over
the task's curated subset), so any future producer/consumer can construct the record
without a missing-field break. Frozen + default-everything per ADR-0002 §6.3 record
style: every collection uses ``field(default_factory=...)`` (no shared mutable state),
so zero-arg construction is valid and field order is moot.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass(frozen=True)
class MemoryContextPacket:
    """Direct memory→cognition packet (ADR-0001 §8.3)."""

    packet_id: str = ""
    request_id: str = ""
    # cue cascade inputs/results
    cue_terms: list[str] = field(default_factory=list)
    retrieved_experience_ids: list[str] = field(default_factory=list)
    retrieved_semantic_nodes: list[str] = field(default_factory=list)
    retrieved_archival_pointers: list[str] = field(default_factory=list)
    sensory_anchors: list[str] = field(default_factory=list)
    # {"start": <iso|null>, "end": <iso|null>} per §8.3
    temporal_span: dict[str, Optional[str]] = field(
        default_factory=lambda: {"start": None, "end": None}
    )
    entity_graph_refs: list[str] = field(default_factory=list)
    relationship_graph_refs: list[str] = field(default_factory=list)
    contradiction_flags: list[Any] = field(default_factory=list)
    confidence: float = 0.0
    # privacy_class default per ADR ExperienceAtom/§8.3: "private"
    privacy_class: str = "private"
    recommended_recall_depth: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


if __name__ == "__main__":
    pkt = MemoryContextPacket(
        packet_id="pkt-1",
        request_id="req-1",
        cue_terms=["remember", "the project"],
        retrieved_experience_ids=["exp-a"],
        confidence=0.62,
        recommended_recall_depth=2,
    )
    d = pkt.to_dict()
    assert d["packet_id"] == "pkt-1"
    assert d["temporal_span"] == {"start": None, "end": None}
    assert MemoryContextPacket().privacy_class == "private"
    # frozen guarantee
    try:
        pkt.confidence = 1.0  # type: ignore[misc]
        raise SystemExit("FAIL: record is not frozen")
    except Exception:
        pass
    print("MemoryContextPacket OK:", d)
