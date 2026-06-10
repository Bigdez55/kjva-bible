"""adapter_algebra.py — algebra over AdapterIR (Omni-PEFT++ §11.1, §11.2 step 6).

Pure numpy. Operations compose/diff/intersect/subtract/compress/distill adapter
deltas. Compatibility (same target/family/shapes) is enforced; mismatches raise.
"""
from __future__ import annotations

import numpy as np

from .adapter_ir import AdapterIR, compatible


def _require(a: AdapterIR, b: AdapterIR) -> None:
    if not compatible(a, b):
        raise ValueError(f"incompatible IRs: {a.target_module}/{a.family} vs {b.target_module}/{b.family}")


def _binary(a: AdapterIR, b: AdapterIR, fn, method_suffix: str) -> AdapterIR:
    _require(a, b)
    out = {k: fn(a.tensors[k], b.tensors[k]) for k in a.tensors}
    return AdapterIR.from_named_arrays(a.family, f"{a.method}{method_suffix}",
                                       a.target_module, a.layer_idx, out, a.hparams)


def compose(a: AdapterIR, b: AdapterIR, w_a: float = 1.0, w_b: float = 1.0) -> AdapterIR:
    """Weighted sum of two deltas (adapter merge)."""
    return _binary(a, b, lambda x, y: w_a * x + w_b * y, "+compose")


def subtract(a: AdapterIR, b: AdapterIR) -> AdapterIR:
    return _binary(a, b, lambda x, y: x - y, "-sub")


def diff(a: AdapterIR, b: AdapterIR) -> dict[str, float]:
    """Per-tensor L2 distance between two deltas."""
    _require(a, b)
    return {k: float(np.linalg.norm(a.tensors[k] - b.tensors[k])) for k in a.tensors}


def intersect(a: AdapterIR, b: AdapterIR, eps: float = 1e-6) -> AdapterIR:
    """Element-wise shared component (same-sign min magnitude) — the common subspace."""
    def _isect(x, y):
        same = np.sign(x) == np.sign(y)
        return np.where(same, np.sign(x) * np.minimum(np.abs(x), np.abs(y)), 0.0)
    return _binary(a, b, _isect, "&isect")


def compress(a: AdapterIR, rank: int, method: str = "svd") -> AdapterIR:
    """Low-rank-compress each 2D tensor to `rank` via truncated SVD (1D left as-is)."""
    out = {}
    for k, arr in a.tensors.items():
        if arr.ndim == 2 and rank < min(arr.shape):
            U, S, Vt = np.linalg.svd(arr, full_matrices=False)
            out[k] = (U[:, :rank] * S[:rank]) @ Vt[:rank, :]
        else:
            out[k] = arr.copy()
    ir = AdapterIR.from_named_arrays(a.family, f"{a.method}+compress{rank}",
                                     a.target_module, a.layer_idx, out, {**a.hparams, "compress_rank": rank})
    return ir


def distill(teachers: list[AdapterIR], weights: list[float] | None = None) -> AdapterIR:
    """Average several teacher deltas into a single student delta (weighted)."""
    if not teachers:
        raise ValueError("distill needs at least one teacher")
    base = teachers[0]
    for t in teachers[1:]:
        _require(base, t)
    w = weights or [1.0 / len(teachers)] * len(teachers)
    out = {k: sum(wi * t.tensors[k] for wi, t in zip(w, teachers)) for k in base.tensors}
    return AdapterIR.from_named_arrays(base.family, f"{base.method}+distill",
                                       base.target_module, base.layer_idx, out, base.hparams)
