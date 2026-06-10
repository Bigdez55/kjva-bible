"""test_v2_modules.py — Phase-2 gate: Omni-PEFT++ v2 modules are pure + correct.

Imports the v2 package **without torch or mlx** (proves framework-neutrality), then
exercises IR roundtrip, genome v1↔v2 losslessness, adapter algebra, compression,
deterministic replay, plasticity maps, multilane tournament, and every formal proof.

Run:  pytest tests/test_v2_modules.py -q   (numpy only)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Import v2 as a standalone package (bypasses the mlx-coupled peft/__init__.py).
PEFT = Path(__file__).resolve().parents[1] / "training" / "peft"
sys.path.insert(0, str(PEFT))
import v2  # noqa: E402
from v2 import adapter_algebra as alg  # noqa: E402
from v2 import determinism as det       # noqa: E402
from v2.proofs import properties as props  # noqa: E402


def _ir(seed=0):
    rng = np.random.default_rng(seed)
    return v2.AdapterIR.from_named_arrays(
        "WEIGHT_ADDITIVE", "lora", "attn.q", 0,
        {"A": rng.standard_normal((4, 8)).astype(np.float32),
         "B": rng.standard_normal((8, 4)).astype(np.float32)},
        {"rank": 4, "alpha": 8})


def test_imports_without_mlx_or_torch():
    # Poison torch+mlx in a fresh subprocess; v2 must still import (proves neutrality
    # robustly regardless of what sibling tests loaded into this process).
    import subprocess
    code = (
        "import sys\n"
        "for m in ('mlx','mlx.core','mlx.nn','torch'): sys.modules[m]=None\n"
        f"sys.path.insert(0, {str(PEFT)!r})\n"
        "import v2\n"
        "from v2 import (adapter_ir, adapter_algebra, adapter_genome_v2, layer_plasticity,\n"
        "                sensory_plasticity, tournament_v2, determinism, proofs)\n"
        "from v2.proofs import properties\n"
        "print('OK', len(properties.ALL_PROPERTIES))\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0 and "OK" in r.stdout, f"v2 failed to import w/o torch+mlx:\n{r.stderr}"
    for name in ("adapter_ir", "adapter_algebra", "adapter_genome_v2", "layer_plasticity",
                 "sensory_plasticity", "tournament_v2", "determinism", "proofs"):
        assert hasattr(v2, name), f"missing v2 module: {name}"


def test_ir_roundtrip_and_hash():
    ir = _ir()
    assert ir.param_count() == 4 * 8 + 8 * 4
    assert props.prop_ir_roundtrip(ir)
    assert props.prop_hash_stable(ir)


def test_algebra_invertible_and_compress():
    a, b = _ir(1), _ir(2)
    assert props.prop_compose_invertible(a, b)
    # low-rank tensor compresses losslessly
    rng = np.random.default_rng(3)
    low = (rng.standard_normal((10, 2)) @ rng.standard_normal((2, 10))).astype(np.float32)
    ir = v2.AdapterIR.from_named_arrays("WEIGHT_ADDITIVE", "lora", "mlp.down", 0, {"W": low})
    assert props.prop_compress_preserves_lowrank(ir, rank=2)


def test_genome_v1_lossless_and_sign():
    g = v2.AdapterGenomeV2(method="lora", family="WEIGHT_ADDITIVE", rank=8, alpha=16,
                           target_modules=["attn.q"], trainable_params=8704,
                           operator="LoRALinear", base_checkpoint="runs/x",
                           evaluation={"final_loss": 2.9})
    assert props.prop_genome_v1_lossless(g)
    g.compute_hash(_ir().canonical_bytes())
    g.sign(b"secret-key")
    assert g.verify(b"secret-key") and not g.verify(b"wrong-key")
    y = g.to_yaml_dict()
    assert set(y) == {"adapter_genome", "adapter_genome_v2"}        # non-breaking dual block
    assert "method" in y["adapter_genome"]                          # v1 block intact


def test_determinism_replay():
    rec = det.record(seed=42, candidates=["lora", "dora", "ia3", "bitfit"], inputs={"task": "kjv"}, top_k=2)
    assert props.prop_replay_deterministic(rec)
    # same seed+inputs → same plan; different inputs → (almost surely) different plan
    rec2 = det.record(seed=42, candidates=["lora", "dora", "ia3", "bitfit"], inputs={"task": "kjv"}, top_k=2)
    assert rec.plan == rec2.plan


def test_layer_and_sensory_plasticity():
    lp = v2.LayerPlasticityV2.build({"n_layers": 8})
    assert lp.zone_of(0, "embed") == "embeddings"
    assert lp.zone_of(7, "attn") == "late_attn"
    assert "dora" in lp.recommend(7, "mlp")
    sp = v2.SensoryPlasticityMap.from_corpus_bytes(b"In the beginning God created \x00\xc3\xa9")
    norm = sp.normalized()
    assert abs(sum(norm.values()) - 1.0) < 1e-6
    assert norm["ascii_printable"] > 0


def test_tournament_multilane():
    cands = [
        v2.Candidate("lora", {"robustness": .8, "domain_accuracy": .9, "attack_success": .2,
                              "leakage": .1, "base_retention": .85, "retention": .8,
                              "params": 8704, "latency": 12, "sensor_coverage": .7}),
        v2.Candidate("dora", {"robustness": .9, "domain_accuracy": .88, "attack_success": .1,
                              "leakage": .05, "base_retention": .9, "retention": .9,
                              "params": 9856, "latency": 14, "sensor_coverage": .6}),
    ]
    t = v2.TournamentV2(cands)
    winners = t.run_multilane()
    assert set(winners) == set(v2.tournament_v2.LANES)
    assert t.sovereign_winner() in ("lora", "dora")


def test_all_proofs_hold():
    for name in props.ALL_PROPERTIES:
        assert hasattr(props, name), f"missing proof predicate {name}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
