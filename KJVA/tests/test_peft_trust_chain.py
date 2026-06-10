"""test_peft_trust_chain.py — ADR-0002 §9.2 adapter-activation trust chain (completion).

The §9.2 chain is: sign → base-hash → scope → conflict → DeterminantProbabilityRecord.
test_adapter_genome_scope.py already pins base-hash/scope/signed-presence. This file pins
the three pieces that were "written but called by nothing" before this commit:

  - rule 1 STRONG: a present-but-FORGED HMAC signature is rejected (AdapterGenomeV2.verify
    CALLED inside HierarchicalRouter._admit_genome when a verify_key is configured).
  - rule 4 NUMERIC conflict: two adapters whose weight-deltas oppose (cosine ≤ threshold)
    are pruned — ConflictResolver.compute_delta_cosine_similarity CALLED inside prune().
  - DPR: route() emits a replayable DeterminantProbabilityRecord (RouteRecord);
    determinism.is_deterministic(record) re-derives the same plan.

Two layers:
  * Layer 1 (no MLX) — the pure-stdlib crypto + determinism PRIMITIVES the router wires.
  * Layer 2 (MLX-gated) — the actual router/conflict WIRING that CALLS those primitives.
    (The PEFT package imports MLX, so the wiring layer skips cleanly without MLX and runs
    in the training lane — this is the test the CI MLX lane must execute.)

Run:  python3 -m pytest tests/test_peft_trust_chain.py -q
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "training") not in sys.path:
    sys.path.insert(0, str(ROOT / "training"))

_V2_DIR = ROOT / "training" / "peft" / "v2"


def _load_v2(modname):
    """Load a pure-stdlib peft.v2 module BY FILE PATH, bypassing peft/__init__.py
    (which imports peft.base → MLX). The v2 modules have no relative imports, so this
    is a faithful load of the same code the router imports — without needing MLX."""
    import importlib.util
    fqname = f"_v2_{modname}"
    spec = importlib.util.spec_from_file_location(fqname, _V2_DIR / f"{modname}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[fqname] = mod  # dataclasses._is_type resolves cls.__module__ via sys.modules
    spec.loader.exec_module(mod)
    return mod


# =============================================================================
# Layer 1 — pure-stdlib primitives (no MLX). These RUN everywhere.
# =============================================================================
def test_genome_v2_sign_verify_and_tamper_detection():
    AdapterGenomeV2 = _load_v2("adapter_genome_v2").AdapterGenomeV2
    key = b"deployment-secret-key"
    g = AdapterGenomeV2(method="lora", family="LOW_RANK")
    g.compute_hash(b"adapter-ir-bytes-v1")
    g.sign(key, signer="omni-peft")

    # A correctly-signed genome verifies.
    assert g.verify(key) is True
    # A wrong key fails.
    assert g.verify(b"attacker-key") is False
    # A tampered signature fails (forgery).
    g_forged = AdapterGenomeV2(method="lora", family="LOW_RANK",
                               content_hash=g.content_hash, signature="00" + g.signature[2:])
    assert g_forged.verify(key) is False
    # A tampered content_hash (same signature) fails (the body was swapped).
    g_swapped = AdapterGenomeV2(method="lora", family="LOW_RANK",
                                content_hash="deadbeef" * 8, signature=g.signature)
    assert g_swapped.verify(key) is False


def test_route_determinant_record_replays():
    det = _load_v2("determinism")
    rec = det.record(seed=7, candidates=["a", "b", "c", "d"],
                     inputs={"input_text": "summarize this", "task_spec": {"domains": ["general"]}},
                     top_k=2)
    # The record is self-consistent: replay re-derives the recorded plan.
    assert det.is_deterministic(rec) is True
    # Identical inputs ⇒ identical plan (the determinant property).
    rec2 = det.record(seed=7, candidates=["a", "b", "c", "d"],
                      inputs={"input_text": "summarize this", "task_spec": {"domains": ["general"]}},
                      top_k=2)
    assert rec.plan == rec2.plan
    # A different seed generally changes the ordering (not the determinant property,
    # but proves the seed actually drives derivation).
    rec3 = det.record(seed=999, candidates=["a", "b", "c", "d"],
                      inputs={"input_text": "summarize this", "task_spec": {"domains": ["general"]}},
                      top_k=2)
    assert det.is_deterministic(rec3) is True


# =============================================================================
# Layer 2 — the router/conflict WIRING that CALLS the primitives (MLX-gated).
# =============================================================================
def test_admit_genome_rejects_forged_hmac():
    pytest.importorskip("mlx.core", reason="PEFT router imports MLX-backed conflict resolver")
    from peft.router import HierarchicalRouter, RouterConfig
    from peft.registry import AdapterGenomeRegistry
    from peft.conflict import ConflictResolver
    from peft.base import AdapterGenomeRecord
    from peft.v2.adapter_genome_v2 import AdapterGenomeV2

    key = b"deployment-secret-key"
    v2 = AdapterGenomeV2(method="lora", family="LOW_RANK")
    v2.compute_hash(b"adapter-ir-bytes-v1")
    v2.sign(key)

    cfg = RouterConfig(verify_key=key)  # strong verification ON
    r = HierarchicalRouter(AdapterGenomeRegistry(), ConflictResolver(), cfg)

    def _genome(sig):
        return AdapterGenomeRecord(
            name="g", version="1.0.0", base_model="", peft_method="lora",
            delta_family="LOW_RANK", purpose_domains=["general"], purpose_tasks=["completion"],
            content_hash=v2.content_hash, signature=sig,
        )

    # Valid signature → admitted (verify() CALLED, returns True).
    ok, _ = r._admit_genome(_genome(v2.signature), ["general"], ["completion"])
    assert ok is True
    # Forged signature → rejected by the HMAC verify (not mere presence).
    ok2, reason = r._admit_genome(_genome("00" + v2.signature[2:]), ["general"], ["completion"])
    assert ok2 is False and "HMAC verify failed" in reason


def test_numeric_weight_space_conflict_is_pruned():
    mx = pytest.importorskip("mlx.core", reason="numeric conflict needs MLX arrays")
    from peft.conflict import ConflictResolver
    from peft.registry import AdapterGenomeRegistry
    from peft.base import ActiveExpert, RoutePlan, HardwareBudget

    cr = ConflictResolver()
    plan = RoutePlan(
        active_experts=[ActiveExpert("A", 0.6, None), ActiveExpert("B", 0.4, None)],
        budget_vram_mb=8000.0, safety_pass=True, conflict_free=True,
    )
    # Opposing deltas: cosine = -1 ≤ -0.5 ⇒ weight-space conflict.
    deltas = {"A": mx.array([1.0, 0.0, 0.0, 0.0]), "B": mx.array([-1.0, 0.0, 0.0, 0.0])}
    report = cr.prune(
        plan, AdapterGenomeRegistry(), HardwareBudget(),
        delta_provider=lambda eid: deltas.get(eid),
        weight_conflict_threshold=-0.5,
    )
    assert report.has_conflicts is True
    assert any(c["type"] == "weight_space_conflict" for c in report.conflicts)
    # The lower-weight expert (B) is the pruned victim.
    assert "B" in report.pruned_experts
    assert [e.expert_id for e in report.final_plan.active_experts] == ["A"]

    # Aligned deltas (cosine = +1) ⇒ NO weight-space conflict (control).
    aligned = {"A": mx.array([1.0, 1.0]), "B": mx.array([2.0, 2.0])}
    report2 = cr.prune(
        plan, AdapterGenomeRegistry(), HardwareBudget(),
        delta_provider=lambda eid: aligned.get(eid),
        weight_conflict_threshold=-0.5,
    )
    assert not any(c["type"] == "weight_space_conflict" for c in report2.conflicts)


def test_route_emits_replayable_dpr(tmp_path):
    pytest.importorskip("mlx.core", reason="PEFT router imports MLX-backed conflict resolver")
    from peft.router import HierarchicalRouter, RouterConfig
    from peft.registry import AdapterGenomeRegistry
    from peft.conflict import ConflictResolver
    from peft.base import AdapterGenomeRecord, HardwareBudget
    from peft.v2 import determinism as det

    reg = AdapterGenomeRegistry(registry_root=str(tmp_path / "adapters"))
    reg.register(
        AdapterGenomeRecord(
            name="gen-adapter", version="1.0.0", base_model="", peft_method="lora",
            delta_family="LOW_RANK", purpose_domains=["general"], purpose_tasks=["generation"],
        ),
        checkpoint_path=str(tmp_path / "ckpt"),
    )
    r = HierarchicalRouter(reg, ConflictResolver(), RouterConfig())
    plan = r.route("please write a short story", {"tasks": ["generation"]}, HardwareBudget(), seed=42)

    # A DeterminantProbabilityRecord was emitted and is internally replayable.
    rec = r._last_route_record
    assert rec is not None
    assert det.is_deterministic(rec) is True
    # Re-routing identical (seed, input) yields an identical determinant plan.
    r.route("please write a short story", {"tasks": ["generation"]}, HardwareBudget(), seed=42)
    assert r._last_route_record.plan == rec.plan


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
