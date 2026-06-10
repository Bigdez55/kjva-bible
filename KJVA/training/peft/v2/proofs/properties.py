"""properties.py — machine-checkable Omni-PEFT++ properties (§11.2 step 17).

Each predicate returns True when the property holds. They are pure (numpy/stdlib)
so they can be asserted in any environment. See SPECS.md for the English statements.
"""
from __future__ import annotations

import numpy as np

from ..adapter_ir import AdapterIR
from .. import adapter_algebra as alg
from .. import determinism as det


def prop_ir_roundtrip(ir: AdapterIR) -> bool:
    """P1: flatten→unflatten reproduces the IR exactly."""
    back = AdapterIR.unflatten(ir.meta(), ir.flatten())
    return back.content_hash() == ir.content_hash()


def prop_hash_stable(ir: AdapterIR) -> bool:
    """P2: content hash is stable across an independent copy."""
    return ir.copy().content_hash() == ir.content_hash()


def prop_compose_invertible(a: AdapterIR, b: AdapterIR, atol: float = 1e-5) -> bool:
    """P3: subtract(compose(a,b), b) ≈ a (additive algebra is invertible)."""
    recon = alg.subtract(alg.compose(a, b), b)
    return all(np.allclose(recon.tensors[k], a.tensors[k], atol=atol) for k in a.tensors)


def prop_compress_preserves_lowrank(ir: AdapterIR, rank: int, atol: float = 1e-4) -> bool:
    """P4: compressing an already-rank-r tensor to r is (near-)lossless."""
    comp = alg.compress(ir, rank)
    ok = True
    for k, arr in ir.tensors.items():
        if arr.ndim == 2 and np.linalg.matrix_rank(arr) <= rank:
            ok = ok and np.allclose(comp.tensors[k], arr, atol=atol)
    return ok


def prop_replay_deterministic(rec: det.RouteRecord) -> bool:
    """P5: replay of a route record reproduces the identical plan."""
    return det.is_deterministic(rec)


def prop_genome_v1_lossless(genome_v2) -> bool:
    """P6: AdapterGenomeV2.from_v1(g.to_v1()) preserves all v1 fields."""
    v1 = genome_v2.to_v1()
    from ..adapter_genome_v2 import AdapterGenomeV2
    return AdapterGenomeV2.from_v1(v1).to_v1() == v1


ALL_PROPERTIES = [
    "prop_ir_roundtrip", "prop_hash_stable", "prop_compose_invertible",
    "prop_compress_preserves_lowrank", "prop_replay_deterministic", "prop_genome_v1_lossless",
]
