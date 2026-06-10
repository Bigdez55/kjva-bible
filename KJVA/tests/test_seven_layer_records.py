"""test_seven_layer_records.py — documentation-grade structural test for the
Seven-Layer Embedded Cognitive Model record contracts.

PURPOSE
-------
Assert that each of the seven cognitive layers of ADR-0001 §6 has a concrete
*record type* in the active `models v7/` source tree, that each record maps to the
layer slot defined in **ADR-0002 §5** (Seven-Layer Embedded Model Mapping), and that
each record exposes the fields its ADR-0001 "Outputs" block requires:

    Layer 1  Perception and Embodiment        EvidenceEnvelope            (§6.1 / §7.3)
    Layer 2  Attention and Active Workspace    ActiveFrame                 (§6.2)
    Layer 3  Memory and Continuity             MemoryContextPacket         (§6.3 / §8.3)
                                               + ExperienceAtom (§8.2),
                                                 RecallTrail,
                                                 CognitiveMemoryVerdict (§8.4)
    Layer 4  World Model and Simulation        WorldState                  (§6.4)
    Layer 5  Deliberation and Planning         DeliberationRecord          (§6.5)
    Layer 6  Self-Correction and Calibration   CorrectionRecord            (§6.6)
    Layer 7  Governance and Authority          GovernanceVerdict           (§6.7)

Two cross-cutting deterministic/materialization records are also covered:

    DeterminantProbabilityRecord   ADR-0001 §10.1   (deterministic↔probabilistic seam)
    MaterializationRecord          ADR-0001 §11.2   (abstract cognition → runtime state)

This is a STRUCTURAL / documentation test, not a behavioral one. It imports the real
classes and checks field *presence* against the ADR. It does not run the FSM, the
inference engine, or any model weights — consistent with ADR-0002 §5's "No new FSM
state" rule (these are pure data contracts) and the source-of-truth priority
"code > test evidence > manifests > docs".

IMPORT NOTES (load-bearing)
---------------------------
The repository contains TWO `heptagon` packages: the agent-side cognitive-control
package `ai/tokenless-agent/src/heptagon/` (which owns `layer_records.py` /
`determinant_record.py`) and the root governance package `heptagon/` (which owns
`registry.py`). They share the bare name `heptagon` and cannot both sit on
`sys.path` at once. The agent-side records resolve when ONLY the agent `src/` dir is
on the path — the pattern used by `tests/test_memory_reflex.py`. The Layer-7
`GovernanceVerdict` lives in `governance/decision_envelope.py`, whose package
`__init__` transitively imports the ROOT `heptagon`; to avoid that collision it is
loaded directly from its file (stdlib-only module) under a synthetic module name,
which never executes `governance/__init__.py`.

Run:  python3 -m pytest tests/test_seven_layer_records.py -q
"""
from __future__ import annotations

import dataclasses
import importlib.util
import sys
from pathlib import Path

import pytest

# --- agent-side source on path (sensory/memory siblings need it) ------------------
# NOTE: we deliberately do NOT rely on `import heptagon...` resolving to the agent-
# side package: the repo also has a ROOT `heptagon/` package and, under the full
# pytest session, the root dir is on sys.path so `heptagon` resolves to ROOT (which
# has no `layer_records`). To stay collision-proof, every record module below is
# loaded directly BY FILE PATH under a synthetic module name. SRC is still added so
# `recall_trail.py` (which does `from sensory.evidence import ...`) can find sensory.
_SRC = Path(__file__).resolve().parents[1] / "ai" / "tokenless-agent" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------------
# Generic file-path module loader (sidesteps the dual-`heptagon` name collision and
# never executes any package __init__).
# ---------------------------------------------------------------------------------
def _load_module(rel_path: str, synthetic_name: str, *, presets: dict | None = None):
    """Load a single .py file under a synthetic top-level module name.

    `presets` pre-registers dependency modules in sys.modules under the names the
    target file imports (used for `recall_trail`'s relative `.experience_atom`).
    """
    path = _REPO_ROOT / rel_path
    if not path.exists():
        pytest.skip(f"required record source not found: {rel_path}")
    spec = importlib.util.spec_from_file_location(synthetic_name, str(path))
    assert spec and spec.loader, f"could not build import spec for {rel_path}"
    mod = importlib.util.module_from_spec(spec)
    # Register BEFORE exec: under `from __future__ import annotations`, @dataclass's
    # KW_ONLY type check resolves `cls.__module__` via sys.modules and crashes if the
    # module is absent (CPython dataclasses._is_type).
    sys.modules[synthetic_name] = mod
    for name, dep in (presets or {}).items():
        sys.modules.setdefault(name, dep)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------------
# Fixtures: load the record classes once, all by file path.
# ---------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def records():
    base = "ai/tokenless-agent/src"

    evidence = _load_module(f"{base}/sensory/evidence.py", "_sl_evidence")
    layer_records = _load_module(f"{base}/heptagon/layer_records.py", "_sl_layer_records")
    determinant = _load_module(f"{base}/heptagon/determinant_record.py", "_sl_determinant")
    mem_packet = _load_module(f"{base}/memory/memory_context_packet.py", "_sl_mem_packet")
    mem_verdict = _load_module(f"{base}/memory/cognitive_memory_verdict.py", "_sl_mem_verdict")
    experience = _load_module(f"{base}/memory/experience_atom.py", "_sl_experience_atom")
    # recall_trail does `from .experience_atom import ExperienceAtom` (relative) and
    # `from sensory.evidence import _extract_entities` (absolute via SRC on path).
    # Pre-bind the relative parent + sibling so the file-load resolves cleanly.
    import types as _types
    parent_pkg = _types.ModuleType("_sl_memory_pkg")
    parent_pkg.__path__ = [str(_SRC / "memory")]  # type: ignore[attr-defined]
    parent_pkg.experience_atom = experience  # type: ignore[attr-defined]
    recall = _load_module(
        f"{base}/memory/recall_trail.py",
        "_sl_memory_pkg.recall_trail",
        presets={"_sl_memory_pkg": parent_pkg,
                 "_sl_memory_pkg.experience_atom": experience},
    )
    materialization = _load_module(
        f"{base}/materialization/materialization_record.py", "_sl_materialization"
    )
    gov = _load_module("governance/decision_envelope.py", "_sl_gov_decision_envelope")

    return {
        "EvidenceEnvelope": evidence.EvidenceEnvelope,
        "ActiveFrame": layer_records.ActiveFrame,
        "MemoryContextPacket": mem_packet.MemoryContextPacket,
        "ExperienceAtom": experience.ExperienceAtom,
        "RecallTrail": recall.RecallTrail,
        "CognitiveMemoryVerdict": mem_verdict.CognitiveMemoryVerdict,
        "WorldState": layer_records.WorldState,
        "DeliberationRecord": layer_records.DeliberationRecord,
        "CorrectionRecord": layer_records.CorrectionRecord,
        "GovernanceVerdict": gov.GovernanceVerdict,
        "DeterminantProbabilityRecord": determinant.DeterminantProbabilityRecord,
        "MaterializationRecord": materialization.MaterializationRecord,
    }


def _fields(cls) -> set[str]:
    assert dataclasses.is_dataclass(cls), f"{cls.__name__} must be a dataclass record"
    return {f.name for f in dataclasses.fields(cls)}


# ---------------------------------------------------------------------------------
# ADR field maps. Each entry: implementation field -> ADR-0001 "Outputs" concept.
# We assert the IMPLEMENTATION field names exist; the comments cite the ADR concept.
# ---------------------------------------------------------------------------------

# Layer 1 — Perception and Embodiment (ADR-0001 §6.1 Outputs / §7.3 envelope).
# §6.1 lists: EvidenceEnvelope, modality tag, confidence score, source hash,
# attention hints. The byte-text impl realizes these as:
_L1_EVIDENCE = {
    "modality",        # §6.1 "modality tag"
    "entities",        # §6.1 derived entities
    "sensory_anchors", # §6.1 "attention hints" / §7.3 derived anchors
    "salience",        # §6.1 "confidence/attention" signal
    "session_hash",    # §7.3 source hash (PII-safe session hash)
}

# Layer 2 — Attention and Active Workspace (ADR-0001 §6.2 Outputs block).
_L2_ACTIVE_FRAME = {
    "selected_context",        # §6.2 "selected context"
    "active_memory_cues",      # §6.2 "active memory cues"
    "active_sensory_anchors",  # §6.2 "active sensory anchors"
    "route_hints",             # §6.2 "route hints"
    "budget_envelope",         # §6.2 "budget envelope"
    "uncertainty_map",         # §6.2 "uncertainty map"
}

# Layer 3 — Memory and Continuity. MemoryContextPacket is the §8.3 JSON block.
_L3_MEMORY_PACKET = {
    "packet_id", "request_id",          # trace correlation (§8.3)
    "cue_terms",                        # §8.3 cue_terms
    "retrieved_experience_ids",         # §8.3
    "retrieved_archival_pointers",      # §8.3 (exact-source pointers, §8.1)
    "sensory_anchors",                  # §8.3
    "temporal_span",                    # §8.3 {start,end}
    "contradiction_flags",              # §8.3 / §6.3 contradiction links
    "confidence",                       # §8.3 / §6.3 confidence score
    "privacy_class",                    # §8.3
    "recommended_recall_depth",         # §8.3 (bounded recall, §8.5)
}
# §8.2 ExperienceAtom — the persisted memory unit.
_L3_EXPERIENCE_ATOM = {
    "cue_entities",   # §8.2 entities
    "response",       # §8.2 episodic/semantic content
    "salience",       # §8.2 emotional/user salience
    "strength",       # decayable strength (§8 retention/decay)
    "lineage",        # §8.2 lineage_ref / correction_history
    "atom_id",        # §8.2 experience_id
}
# RecallTrail — the §8.5 cue-triggered recall cascade output (ADR-0002 §7.3).
_L3_RECALL_TRAIL = {
    "cue_entities",   # ADR-0002 §7.3 recovered_entities / cue
    "hits",           # ADR-0002 §7.3 visited_memory_ids (ranked recall hits)
}
# §8.4 CognitiveMemoryVerdict — the cognition→memory writeback verdict.
_L3_MEMORY_VERDICT = {
    "verdict_id", "request_id",       # §8.4
    "route_type",                     # §8.4 route_type enum
    "active_layers",                  # §8.4
    "invariant_verdict",              # §8.4 pass|warning|violation|critical
    "privacy_verdict",                # §8.4 allow|redact|block
    "writeback_targets",              # §8.4
    "retention_mode",                 # §8.4 discard|session|episodic|semantic|archival
    "recall_reinforcement",           # §8.4
}

# Layer 4 — World Model and Simulation (ADR-0001 §6.4 Outputs block).
_L4_WORLD_STATE = {
    "predicted_outcomes",        # §6.4 "predicted outcomes" (predictions, not facts)
    "risk_surface",              # §6.4 "risk surface"
    "unknowns",                  # §6.4 "unknowns"
    "hypothesis_set",            # §6.4 "hypothesis set"
    "confidence_distribution",   # §6.4 "confidence distribution"
    "simulation_trace",          # §6.4 "simulation trace"
}

# Layer 5 — Deliberation and Planning (ADR-0001 §6.5 Outputs block).
_L5_DELIBERATION = {
    "route_plan",          # §6.5 "RoutePlan"
    "action_plan",         # §6.5 "ActionPlan"
    "response_plan",       # §6.5 "ResponsePlan"
    "adapter_route_plan",  # §6.5 "adapter route plan"
    "recursion_depth",     # §6.5 "recursion depth decision"
}

# Layer 6 — Self-Correction and Calibration (ADR-0001 §6.6 Outputs block).
_L6_CORRECTION = {
    "calibration_delta",        # §6.6 "CalibrationDelta"
    "redaction_decision",       # §6.6 "redaction decision"
    "rollback_decision",        # §6.6 "rollback decision"
    "bounded_reentry_request",  # §6.6 "bounded re-entry request"
    "writeback_eligibility",    # §6.6 "writeback eligibility"
}

# Layer 7 — Governance and Authority (ADR-0001 §6.7 Outputs block).
# GovernanceVerdict (governance/decision_envelope.py) is the final gate-chain verdict.
_L7_GOVERNANCE = {
    "envelope",          # the DecisionEnvelope carrying §6.7 inputs/verdict
    "approved",          # §6.7 allow / refuse / block decision
    "governance_score",  # §6.7 verdict strength
    "blocking_gate",     # §6.7 which gate constrained/blocked
    "recommendations",   # §6.7 constrain/redact guidance
}

# §10.1 DeterminantProbabilityRecord — deterministic↔probabilistic seam.
_DETERMINANT = {
    "record_id", "request_id",
    "deterministic_inputs",    # §10.1 snapshot-hash block
    "probabilistic_outputs",   # §10.1 confidence/uncertainty/scores block
    "selected_route",          # §10.1
    "selection_reason",        # §10.1
    "replayable",              # §10.1
    "seed",                    # §10.1 (nullable)
    "temperature",             # §10.1 (nullable)
}

# §11.2 MaterializationRecord — abstract cognition → runtime state.
_MATERIALIZATION = {
    "materialization_id",
    "materialization_type",   # §11.1 type enum
    "source_refs",
    "source_hashes",          # §11.3 "no artifact loads without hash verification"
    "owning_role",            # §11.2 owning_role
    "authority_scope",        # §11.2 / §11.3 scope verification
    "privacy_class",          # §11.2
    "retention_mode",         # §11.2
    "rollback_refs",          # §11.2 rollback_refs
    "status",                 # §11.2 planned|active|committed|rolled_back|revoked|archived
}


# ---------------------------------------------------------------------------------
# Layer 1–7 existence + field tests.
# ---------------------------------------------------------------------------------
def test_layer1_perception_evidence_envelope(records):
    """ADR-0002 §5 Layer 1 → EvidenceEnvelope (ADR-0001 §6.1 / §7.3)."""
    cls = records["EvidenceEnvelope"]
    assert dataclasses.is_dataclass(cls)
    missing = _L1_EVIDENCE - _fields(cls)
    assert not missing, f"EvidenceEnvelope missing §6.1/§7.3 fields: {sorted(missing)}"


def test_layer2_attention_active_frame(records):
    """ADR-0002 §5 Layer 2 → ActiveFrame (ADR-0001 §6.2)."""
    cls = records["ActiveFrame"]
    missing = _L2_ACTIVE_FRAME - _fields(cls)
    assert not missing, f"ActiveFrame missing §6.2 Outputs fields: {sorted(missing)}"


def test_layer3_memory_context_packet(records):
    """ADR-0002 §5 Layer 3 → MemoryContextPacket (ADR-0001 §6.3 / §8.3)."""
    cls = records["MemoryContextPacket"]
    missing = _L3_MEMORY_PACKET - _fields(cls)
    assert not missing, f"MemoryContextPacket missing §8.3 fields: {sorted(missing)}"


def test_layer3_experience_atom(records):
    """ADR-0002 §5 Layer 3 support → ExperienceAtom (ADR-0001 §8.2)."""
    cls = records["ExperienceAtom"]
    missing = _L3_EXPERIENCE_ATOM - _fields(cls)
    assert not missing, f"ExperienceAtom missing §8.2 fields: {sorted(missing)}"


def test_layer3_recall_trail(records):
    """ADR-0002 §5 Layer 3 support → RecallTrail (ADR-0002 §7.3 / ADR-0001 §8.5)."""
    cls = records["RecallTrail"]
    missing = _L3_RECALL_TRAIL - _fields(cls)
    assert not missing, f"RecallTrail missing recall-cascade fields: {sorted(missing)}"


def test_layer3_cognitive_memory_verdict(records):
    """ADR-0002 §5 Layer 3 writeback → CognitiveMemoryVerdict (ADR-0001 §8.4)."""
    cls = records["CognitiveMemoryVerdict"]
    missing = _L3_MEMORY_VERDICT - _fields(cls)
    assert not missing, f"CognitiveMemoryVerdict missing §8.4 fields: {sorted(missing)}"


def test_layer4_world_state(records):
    """ADR-0002 §5 Layer 4 → WorldState (ADR-0001 §6.4)."""
    cls = records["WorldState"]
    missing = _L4_WORLD_STATE - _fields(cls)
    assert not missing, f"WorldState missing §6.4 Outputs fields: {sorted(missing)}"


def test_layer5_deliberation_record(records):
    """ADR-0002 §5 Layer 5 → DeliberationRecord (ADR-0001 §6.5)."""
    cls = records["DeliberationRecord"]
    missing = _L5_DELIBERATION - _fields(cls)
    assert not missing, f"DeliberationRecord missing §6.5 Outputs fields: {sorted(missing)}"


def test_layer6_correction_record(records):
    """ADR-0002 §5 Layer 6 → CorrectionRecord (ADR-0001 §6.6)."""
    cls = records["CorrectionRecord"]
    missing = _L6_CORRECTION - _fields(cls)
    assert not missing, f"CorrectionRecord missing §6.6 Outputs fields: {sorted(missing)}"


def test_layer7_governance_verdict(records):
    """ADR-0002 §5 Layer 7 → GovernanceVerdict (ADR-0001 §6.7)."""
    cls = records["GovernanceVerdict"]
    missing = _L7_GOVERNANCE - _fields(cls)
    assert not missing, f"GovernanceVerdict missing §6.7 verdict fields: {sorted(missing)}"


# ---------------------------------------------------------------------------------
# Cross-cutting records (§8 / §10 / §11).
# ---------------------------------------------------------------------------------
def test_determinant_probability_record(records):
    """ADR-0001 §10.1 — deterministic↔probabilistic seam record."""
    cls = records["DeterminantProbabilityRecord"]
    missing = _DETERMINANT - _fields(cls)
    assert not missing, f"DeterminantProbabilityRecord missing §10.1 fields: {sorted(missing)}"
    # §10.1 nested key skeleton must exist on a zero-arg record.
    rec = cls()
    assert "policy_snapshot_hash" in rec.deterministic_inputs
    assert "candidate_scores" in rec.probabilistic_outputs


def test_materialization_record(records):
    """ADR-0001 §11.2 — abstract cognition → runtime state record."""
    cls = records["MaterializationRecord"]
    missing = _MATERIALIZATION - _fields(cls)
    assert not missing, f"MaterializationRecord missing §11.2 fields: {sorted(missing)}"
    # §11.2 honest lifecycle default: a fresh record is "planned", not "committed".
    assert cls().status == "planned"


# ---------------------------------------------------------------------------------
# Coverage assertions: all seven layers AND the two cross-cutting records present.
# ---------------------------------------------------------------------------------
def test_all_seven_layers_have_a_record(records):
    """Every ADR-0002 §5 layer slot resolves to a concrete record class."""
    layer_to_record = {
        1: "EvidenceEnvelope",
        2: "ActiveFrame",
        3: "MemoryContextPacket",
        4: "WorldState",
        5: "DeliberationRecord",
        6: "CorrectionRecord",
        7: "GovernanceVerdict",
    }
    for layer, name in layer_to_record.items():
        cls = records.get(name)
        assert cls is not None and dataclasses.is_dataclass(cls), (
            f"Layer {layer} record {name!r} is missing or not a dataclass"
        )


def test_cross_cutting_records_present(records):
    """§10.1 and §11.2 cross-cutting records exist as dataclasses."""
    for name in ("DeterminantProbabilityRecord", "MaterializationRecord",
                 "ExperienceAtom", "RecallTrail", "CognitiveMemoryVerdict"):
        cls = records.get(name)
        assert cls is not None and dataclasses.is_dataclass(cls), (
            f"cross-cutting record {name!r} is missing or not a dataclass"
        )
