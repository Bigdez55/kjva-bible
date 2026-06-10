"""heptagon/determinant_record.py — deterministic/probabilistic boundary record.

Defines :class:`DeterminantProbabilityRecord` (ADR-0001 §10.1), the audit record at
the seam between deterministic control and probabilistic cognition (§10). It pins the
deterministic input snapshot hashes alongside the probabilistic outputs and the route
the control layer **selected**, giving the replay property in
``training/peft/v2/determinism.py``: "identical inputs ⇒ identical route."

Hard rule (§10.1): "The probabilistic model may propose. The deterministic control
layer disposes."

The two nested objects mirror the ADR JSON shape and are kept as plain dicts (the
"minimal honest" choice — no nested frozen dataclasses):

  * ``deterministic_inputs`` — keys: policy_snapshot_hash, model_snapshot_hash,
    adapter_snapshot_hashes(list), memory_index_snapshot_hash, route_policy_hash,
    budget_state_hash.
  * ``probabilistic_outputs`` — keys: confidence, uncertainty, candidate_scores(list),
    retrieval_scores(list), simulation_scores(list).

Frozen, every field defaulted, nested dicts via ``field(default_factory=...)`` so the
empty-default record carries the full ADR key skeleton. ``seed``/``temperature`` are
Optional (ADR shows ``null``).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


def _default_deterministic_inputs() -> dict[str, Any]:
    return {
        "policy_snapshot_hash": "",
        "model_snapshot_hash": "",
        "adapter_snapshot_hashes": [],
        "memory_index_snapshot_hash": "",
        "route_policy_hash": "",
        "budget_state_hash": "",
    }


def _default_probabilistic_outputs() -> dict[str, Any]:
    return {
        "confidence": 0.0,
        "uncertainty": 0.0,
        "candidate_scores": [],
        "retrieval_scores": [],
        "simulation_scores": [],
    }


@dataclass(frozen=True)
class DeterminantProbabilityRecord:
    """Deterministic-input / probabilistic-output replay record (ADR-0001 §10.1)."""

    record_id: str = ""
    request_id: str = ""
    deterministic_inputs: dict[str, Any] = field(
        default_factory=_default_deterministic_inputs
    )
    probabilistic_outputs: dict[str, Any] = field(
        default_factory=_default_probabilistic_outputs
    )
    selected_route: str = ""
    selection_reason: str = ""
    replayable: bool = True
    seed: Optional[int] = None
    temperature: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    # ------------------------------------------------------------------ #
    # ADR-0002 §10.2 DeterminantProbabilityRecord field-NAME aliases.     #
    # ------------------------------------------------------------------ #
    # ADR-0002 §10.2 specifies the same record with a different field
    # vocabulary than the ADR-0001 §10.1 shape implemented above (an
    # inter-ADR naming conflict — see FULL_GAP_LEDGER_2026-06-04 row
    # "PARTIAL · heptagon/determinant_record.py"). These read-only
    # @property aliases expose the §10.2 names mapped onto the existing
    # §10.1 storage so a §10.2 consumer can read them, WITHOUT touching the
    # §10.1 fields or `to_dict()`. Backward-compatible.
    #
    # Three §10.2 names — `record_id`, `seed`, `selection_reason` — are
    # ALREADY real §10.1 fields with identical names, so they need no alias
    # (and a property colliding with a frozen-dataclass field would break
    # __init__). They appear in `to_dict_v2()` below directly.
    #
    # §10.2 fields with no §10.1 correspondent (`decision_kind`,
    # `input_hash`, `deterministic_replay_hash`) resolve to documented
    # empty-string defaults: the §10.1 record never carried those
    # semantics, and fabricating a hash inside a property would invent
    # meaning the replay model does not have. The spec-literal requirement
    # is only that the NAME resolves read-only — "" satisfies it.

    @property
    def selected_candidate(self) -> str:
        """§10.2 ← §10.1 `selected_route` (the route control selected)."""
        return self.selected_route

    @property
    def probabilistic_confidence(self) -> float:
        """§10.2 ← §10.1 `probabilistic_outputs['confidence']`."""
        return float(self.probabilistic_outputs.get("confidence", 0.0))

    @property
    def candidate_scores(self) -> dict[str, float]:
        """§10.2 dict[str, float] ← §10.1 `probabilistic_outputs['candidate_scores']`.

        §10.1 stores a bare score *list* with no candidate labels; §10.2
        types this as a labelled dict. With no label source we index by
        position (``"candidate_<i>"``) so the §10.2 dict type is honoured
        without inventing names. An already-dict value is passed through.
        """
        raw = self.probabilistic_outputs.get("candidate_scores", [])
        if isinstance(raw, dict):
            return {str(k): float(v) for k, v in raw.items()}
        return {f"candidate_{i}": float(v) for i, v in enumerate(raw)}

    @property
    def state_hash(self) -> str:
        """§10.2 ← closest §10.1 correspondent `budget_state_hash`."""
        return str(self.deterministic_inputs.get("budget_state_hash", ""))

    @property
    def decision_kind(self) -> str:
        """§10.2 only — no §10.1 correspondent; empty-string default."""
        return ""

    @property
    def input_hash(self) -> str:
        """§10.2 only — no clean 1:1 §10.1 correspondent; empty-string default."""
        return ""

    @property
    def deterministic_replay_hash(self) -> str:
        """§10.2 only — §10.1 has `replayable: bool`, not a hash; empty default."""
        return ""

    def to_dict_v2(self) -> dict:
        """Serialize using the ADR-0002 §10.2 field names (all 10).

        Companion to :meth:`to_dict` (which stays §10.1). Lets a §10.2
        consumer read the named fields without parsing the §10.1 shape.
        """
        return {
            "record_id": self.record_id,
            "decision_kind": self.decision_kind,
            "input_hash": self.input_hash,
            "state_hash": self.state_hash,
            "seed": self.seed,
            "candidate_scores": self.candidate_scores,
            "selected_candidate": self.selected_candidate,
            "selection_reason": self.selection_reason,
            "deterministic_replay_hash": self.deterministic_replay_hash,
            "probabilistic_confidence": self.probabilistic_confidence,
        }


if __name__ == "__main__":
    rec = DeterminantProbabilityRecord(
        record_id="dpr-1",
        request_id="req-1",
        selected_route="direct",
        selection_reason="low risk, high memory confidence",
        seed=1337,
        temperature=0.0,
    )
    d = rec.to_dict()
    assert d["replayable"] is True
    assert "policy_snapshot_hash" in d["deterministic_inputs"]
    assert "candidate_scores" in d["probabilistic_outputs"]
    assert DeterminantProbabilityRecord().seed is None

    # ADR-0002 §10.2 alias checks (read-only; §10.1 to_dict() unchanged above).
    rec2 = DeterminantProbabilityRecord(
        record_id="dpr-2",
        selected_route="memory_mediated",
        selection_reason="recall confidence high",
        probabilistic_outputs={
            "confidence": 0.87,
            "uncertainty": 0.1,
            "candidate_scores": [0.9, 0.6, 0.3],
            "retrieval_scores": [],
            "simulation_scores": [],
        },
        deterministic_inputs={**_default_deterministic_inputs(),
                              "budget_state_hash": "bsh-abc"},
        seed=7,
    )
    assert rec2.selected_candidate == rec2.selected_route == "memory_mediated"
    assert rec2.probabilistic_confidence == 0.87
    assert rec2.state_hash == "bsh-abc"
    assert rec2.candidate_scores == {"candidate_0": 0.9, "candidate_1": 0.6, "candidate_2": 0.3}
    assert rec2.decision_kind == "" and rec2.input_hash == "" and rec2.deterministic_replay_hash == ""
    v2 = rec2.to_dict_v2()
    _expected_v2 = {
        "record_id", "decision_kind", "input_hash", "state_hash", "seed",
        "candidate_scores", "selected_candidate", "selection_reason",
        "deterministic_replay_hash", "probabilistic_confidence",
    }
    assert _expected_v2 <= set(v2), f"to_dict_v2 missing §10.2 names: {_expected_v2 - set(v2)}"
    assert v2["seed"] == 7 and v2["selected_candidate"] == "memory_mediated"
    # Aliases must be read-only (frozen dataclass forbids attribute set anyway).
    try:
        rec2.selected_candidate = "x"  # type: ignore[misc]
        raise SystemExit("FAIL: §10.2 alias is not read-only")
    except SystemExit:
        raise
    except (AttributeError, Exception):
        pass
    try:
        rec.selected_route = "memory_mediated"  # type: ignore[misc]
        raise SystemExit("FAIL: record is not frozen")
    except SystemExit:
        raise
    except Exception:
        pass
    print("DeterminantProbabilityRecord OK:", d)
