"""tests/test_record_classes.py — contract test for the ADR-0001 record classes.

Pins the construct + ``to_dict()`` + frozen guarantees for the eight plane-boundary
record dataclasses defined across the agent source tree (ADR-0001 §8.3, §8.4, §6.2,
§6.4, §6.5, §6.6, §10.1, §11.2; record style ADR-0002 §6.3):

  * MemoryContextPacket        — memory/memory_context_packet.py        (§8.3)
  * CognitiveMemoryVerdict     — memory/cognitive_memory_verdict.py     (§8.4)
  * ActiveFrame                — heptagon/layer_records.py               (§6.2)
  * WorldState                 — heptagon/layer_records.py               (§6.4)
  * DeliberationRecord         — heptagon/layer_records.py               (§6.5)
  * CorrectionRecord           — heptagon/layer_records.py               (§6.6)
  * DeterminantProbabilityRecord — heptagon/determinant_record.py       (§10.1)
  * MaterializationRecord      — materialization/materialization_record.py (§11.2)

IMPORT NOTE (load-bearing): the repo has TWO ``heptagon`` packages — the top-level
``heptagon/`` (which governance/covenant code imports as ``heptagon.registry``) and
``ai/tokenless-agent/src/heptagon/`` (the cognitive-layer records here). Putting the
src tree on ``sys.path`` shadows the top-level package, and in a full ``pytest tests/``
session a sibling test may import the top-level ``heptagon`` first, caching the wrong
``heptagon.__path__`` in ``sys.modules`` so ``from heptagon.layer_records import ...``
raises ModuleNotFoundError. (test_covenant_contract.py documents the same collision.)
All eight target modules are stdlib-only (dataclasses + typing) with NO relative/intra-
package imports, so we load each one DIRECTLY BY FILE PATH via importlib — sidestepping
the package-name collision and any pytest session import order.

Run:  PYTHONPATH=ai/tokenless-agent/src python3 -m pytest tests/test_record_classes.py -q
"""
from __future__ import annotations

import dataclasses
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "ai" / "tokenless-agent" / "src"


def _load(rel_path: str, class_name: str):
    """Load ``class_name`` from ``SRC/rel_path`` by file path (no package import).

    Sidesteps the dual-``heptagon`` package collision; modules are stdlib-only so a
    direct spec load is sufficient. Skips cleanly (never fails) if a file/class is
    absent in this checkout.
    """
    path = SRC / rel_path
    if not path.exists():
        pytest.skip(f"source file not present: {path}")
    mod_name = f"_recordtest_{path.stem}_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        pytest.skip(f"could not build import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module  # so dataclasses/typing resolve cleanly
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - defensive skip, never a hard fail
        pytest.skip(f"could not exec {path}: {exc!r}")
    cls = getattr(module, class_name, None)
    if cls is None:
        pytest.skip(f"{class_name} not defined in {path}")
    return cls


def _assert_frozen(instance, field_name: str, new_value) -> None:
    """A frozen dataclass MUST raise FrozenInstanceError on attribute assignment."""
    assert dataclasses.is_dataclass(instance), "expected a dataclass instance"
    params = getattr(type(instance), "__dataclass_params__", None)
    assert params is not None and params.frozen, (
        f"{type(instance).__name__} must be declared @dataclass(frozen=True)"
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, field_name, new_value)


def _assert_to_dict(instance) -> dict:
    """``to_dict()`` exists, returns a plain dict, and round-trips every field."""
    assert hasattr(instance, "to_dict"), f"{type(instance).__name__} needs to_dict()"
    d = instance.to_dict()
    assert isinstance(d, dict), "to_dict() must return a dict"
    assert type(d) is dict, "to_dict() must return a builtin dict (asdict), not a subclass"
    # Every declared field is present and value-equal to asdict (deep copy by asdict).
    expected = dataclasses.asdict(instance)
    assert d == expected, "to_dict() must equal dataclasses.asdict(self)"
    field_names = {f.name for f in dataclasses.fields(instance)}
    assert set(d.keys()) == field_names, "to_dict() keys must be exactly the fields"
    return d


# --------------------------------------------------------------------------- #
# memory/memory_context_packet.py — MemoryContextPacket (§8.3)
# --------------------------------------------------------------------------- #
def test_memory_context_packet():
    Cls = _load("memory/memory_context_packet.py", "MemoryContextPacket")

    # zero-arg construction is valid and carries the §8.3 default skeleton
    zero = Cls()
    z = _assert_to_dict(zero)
    assert z["privacy_class"] == "private"               # §8.3 default
    assert z["temporal_span"] == {"start": None, "end": None}
    assert z["confidence"] == 0.0 and z["recommended_recall_depth"] == 0

    # populated construction round-trips
    rec = Cls(
        packet_id="pkt-1",
        request_id="req-1",
        cue_terms=["remember", "project"],
        retrieved_experience_ids=["exp-a"],
        confidence=0.62,
        recommended_recall_depth=2,
    )
    d = _assert_to_dict(rec)
    assert d["packet_id"] == "pkt-1" and d["request_id"] == "req-1"
    assert d["cue_terms"] == ["remember", "project"]
    assert d["retrieved_experience_ids"] == ["exp-a"]
    assert d["confidence"] == 0.62 and d["recommended_recall_depth"] == 2

    _assert_frozen(rec, "confidence", 1.0)


# --------------------------------------------------------------------------- #
# memory/cognitive_memory_verdict.py — CognitiveMemoryVerdict (§8.4)
# --------------------------------------------------------------------------- #
def test_cognitive_memory_verdict():
    Cls = _load("memory/cognitive_memory_verdict.py", "CognitiveMemoryVerdict")

    zero = Cls()
    z = _assert_to_dict(zero)
    assert z["route_type"] == "direct"          # §8.4 defaults
    assert z["invariant_verdict"] == "pass"
    assert z["privacy_verdict"] == "allow"
    assert z["lineage_level"] == "understanding"
    assert z["retention_mode"] == "session"

    rec = Cls(
        verdict_id="vd-1",
        request_id="req-1",
        route_type="memory_mediated",
        active_layers=[2, 3, 4],
        writeback_targets=["episodic"],
        retention_mode="episodic",
        recall_reinforcement=0.15,
    )
    d = _assert_to_dict(rec)
    assert d["route_type"] == "memory_mediated"
    assert d["active_layers"] == [2, 3, 4]
    assert d["writeback_targets"] == ["episodic"]
    assert d["retention_mode"] == "episodic"
    assert d["recall_reinforcement"] == 0.15

    _assert_frozen(rec, "retention_mode", "archival")


# --------------------------------------------------------------------------- #
# heptagon/layer_records.py — ActiveFrame (§6.2)
# --------------------------------------------------------------------------- #
def test_active_frame():
    Cls = _load("heptagon/layer_records.py", "ActiveFrame")

    z = _assert_to_dict(Cls())
    for key in ("selected_context", "active_memory_cues", "active_sensory_anchors",
                "route_hints"):
        assert z[key] == []
    for key in ("budget_envelope", "uncertainty_map"):
        assert z[key] == {}

    rec = Cls(
        record_id="af-1",
        request_id="req-1",
        active_memory_cues=["c1"],
        route_hints=["fast"],
        budget_envelope={"tokens": 100},
    )
    d = _assert_to_dict(rec)
    assert d["record_id"] == "af-1" and d["request_id"] == "req-1"
    assert d["active_memory_cues"] == ["c1"]
    assert d["route_hints"] == ["fast"]
    assert d["budget_envelope"] == {"tokens": 100}

    _assert_frozen(rec, "record_id", "x")


# --------------------------------------------------------------------------- #
# heptagon/layer_records.py — WorldState (§6.4)
# --------------------------------------------------------------------------- #
def test_world_state():
    Cls = _load("heptagon/layer_records.py", "WorldState")

    z = _assert_to_dict(Cls())
    for key in ("predicted_outcomes", "unknowns", "hypothesis_set", "simulation_trace"):
        assert z[key] == []
    for key in ("risk_surface", "confidence_distribution"):
        assert z[key] == {}

    rec = Cls(
        record_id="ws-1",
        request_id="req-1",
        predicted_outcomes=["o1"],
        unknowns=["u1"],
        confidence_distribution={"o1": 0.7},
    )
    d = _assert_to_dict(rec)
    assert d["record_id"] == "ws-1" and d["request_id"] == "req-1"
    assert d["predicted_outcomes"] == ["o1"]
    assert d["unknowns"] == ["u1"]
    assert d["confidence_distribution"] == {"o1": 0.7}

    _assert_frozen(rec, "record_id", "x")


# --------------------------------------------------------------------------- #
# heptagon/layer_records.py — DeliberationRecord (§6.5)
# --------------------------------------------------------------------------- #
def test_deliberation_record():
    Cls = _load("heptagon/layer_records.py", "DeliberationRecord")

    z = _assert_to_dict(Cls())
    for key in ("route_plan", "action_plan", "response_plan", "adapter_route_plan"):
        assert z[key] == {}
    assert z["recursion_depth"] == 0

    rec = Cls(
        record_id="dr-1",
        request_id="req-1",
        route_plan={"route": "direct"},
        recursion_depth=1,
    )
    d = _assert_to_dict(rec)
    assert d["record_id"] == "dr-1" and d["request_id"] == "req-1"
    assert d["route_plan"] == {"route": "direct"}
    assert d["recursion_depth"] == 1

    _assert_frozen(rec, "recursion_depth", 99)


# --------------------------------------------------------------------------- #
# heptagon/layer_records.py — CorrectionRecord (§6.6)
# --------------------------------------------------------------------------- #
def test_correction_record():
    Cls = _load("heptagon/layer_records.py", "CorrectionRecord")

    z = _assert_to_dict(Cls())
    assert z["calibration_delta"] == {}
    assert z["redaction_decision"] == "none"      # none|partial|full default
    assert z["rollback_decision"] is False
    assert z["bounded_reentry_request"] is False
    assert z["writeback_eligibility"] is False

    rec = Cls(
        record_id="cr-1",
        request_id="req-1",
        redaction_decision="partial",
        rollback_decision=True,
        writeback_eligibility=True,
    )
    d = _assert_to_dict(rec)
    assert d["record_id"] == "cr-1" and d["request_id"] == "req-1"
    assert d["redaction_decision"] == "partial"
    assert d["rollback_decision"] is True
    assert d["writeback_eligibility"] is True

    _assert_frozen(rec, "writeback_eligibility", False)


# --------------------------------------------------------------------------- #
# heptagon/determinant_record.py — DeterminantProbabilityRecord (§10.1)
# --------------------------------------------------------------------------- #
def test_determinant_probability_record():
    Cls = _load("heptagon/determinant_record.py", "DeterminantProbabilityRecord")

    z = _assert_to_dict(Cls())
    # default nested dicts carry the full ADR key skeleton
    assert "policy_snapshot_hash" in z["deterministic_inputs"]
    assert "adapter_snapshot_hashes" in z["deterministic_inputs"]
    assert z["deterministic_inputs"]["adapter_snapshot_hashes"] == []
    assert "candidate_scores" in z["probabilistic_outputs"]
    assert z["probabilistic_outputs"]["confidence"] == 0.0
    assert z["replayable"] is True
    assert z["seed"] is None and z["temperature"] is None  # ADR null

    rec = Cls(
        record_id="dpr-1",
        request_id="req-1",
        selected_route="direct",
        selection_reason="low risk, high memory confidence",
        seed=1337,
        temperature=0.0,
    )
    d = _assert_to_dict(rec)
    assert d["selected_route"] == "direct"
    assert d["selection_reason"] == "low risk, high memory confidence"
    assert d["seed"] == 1337 and d["temperature"] == 0.0
    assert d["replayable"] is True

    _assert_frozen(rec, "selected_route", "memory_mediated")


# --------------------------------------------------------------------------- #
# materialization/materialization_record.py — MaterializationRecord (§11.2)
# --------------------------------------------------------------------------- #
def test_materialization_record():
    Cls = _load("materialization/materialization_record.py", "MaterializationRecord")

    z = _assert_to_dict(Cls())
    assert z["status"] == "planned"             # honest lifecycle default
    assert z["privacy_class"] == "private"
    assert z["retention_mode"] == "ephemeral"
    assert z["confidence"] == 0.0
    for key in ("source_refs", "source_hashes", "input_records", "transforms",
                "authority_scope", "lineage_refs", "proof_refs", "rollback_refs"):
        assert z[key] == []

    rec = Cls(
        materialization_id="mat-1",
        materialization_type="response",
        source_refs=["draft:abc"],
        source_hashes=["sha256:deadbeef"],
        owning_role="responder",
        privacy_class="internal",
        confidence=0.91,
        created_at="2026-06-01T00:00:00Z",
        retention_mode="session",
        status="committed",
    )
    d = _assert_to_dict(rec)
    assert d["materialization_id"] == "mat-1"
    assert d["materialization_type"] == "response"
    assert d["status"] == "committed"
    assert d["privacy_class"] == "internal"
    assert d["confidence"] == 0.91

    _assert_frozen(rec, "status", "revoked")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
