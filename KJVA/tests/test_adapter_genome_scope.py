"""test_adapter_genome_scope.py — ADR-0002 §9.2 adapter-activation admission gate.

§12 required test name. Pins the §9.2 trust-chain rules that were previously "written but called
by nothing" on the activation path (HierarchicalRouter._admit_genome):
  rule 2 base-hash:  an adapter for the WRONG base model is rejected
  rule 3 scope:      an adapter whose routing_never_activate_when matches the request is rejected
  rule 1 unsigned:   when require_signed, an unsigned adapter is rejected

MLX-gated (the PEFT router imports the MLX-backed conflict resolver). Skips cleanly without MLX;
runs fully in the training lane.

Run:  python3 -m pytest tests/test_adapter_genome_scope.py -q
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "training") not in sys.path:
    sys.path.insert(0, str(ROOT / "training"))

pytest.importorskip("mlx.core", reason="MLX not installed — PEFT router admission test skipped")


def _router(active_base="base_tokenless_v1", require_signed=False):
    from peft.router import HierarchicalRouter, RouterConfig
    from peft.registry import AdapterGenomeRegistry
    from peft.conflict import ConflictResolver
    reg = AdapterGenomeRegistry()
    cfg = RouterConfig(active_base=active_base, require_signed=require_signed)
    return HierarchicalRouter(reg, ConflictResolver(), cfg)


def _genome(name, base="base_tokenless_v1", never=None, signature=""):
    from peft.base import AdapterGenomeRecord
    return AdapterGenomeRecord(
        name=name, version="1.0.0", base_model=base, peft_method="lora", delta_family="LOW_RANK",
        purpose_domains=["general"], purpose_tasks=["completion"],
        routing_never_activate_when=list(never or []), signature=signature,
    )


def test_rule2_base_mismatch_rejected():
    r = _router(active_base="base_tokenless_v1")
    ok, reason = r._admit_genome(_genome("wrong", base="some_other_base"), ["general"], ["completion"])
    assert ok is False and "base mismatch" in reason
    ok2, _ = r._admit_genome(_genome("right", base="base_tokenless_v1"), ["general"], ["completion"])
    assert ok2 is True


def test_rule3_scope_never_activate_rejected():
    r = _router()
    ok, reason = r._admit_genome(_genome("scoped", never=["medical"]), ["medical"], ["completion"])
    assert ok is False and "scope" in reason


def test_rule1_unsigned_rejected_when_required():
    r = _router(require_signed=True)
    ok, reason = r._admit_genome(_genome("unsigned", signature=""), ["general"], ["completion"])
    assert ok is False and "unsigned" in reason
    ok2, _ = r._admit_genome(_genome("signed", signature="deadbeef"), ["general"], ["completion"])
    assert ok2 is True


def test_genome_carries_signature_field():
    # the v1 genome now carries the §9.2 rule-1 signature field
    assert hasattr(_genome("x"), "signature")
