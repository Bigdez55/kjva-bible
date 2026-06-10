"""
peft/low_rank/vera.py — VeRA (Vector-based Random Matrix Adaptation)

Mathematical formulation:
  VeRA uses a single pair of frozen random matrices A, B shared across all
  layers, with tiny per-layer trainable scaling vectors d and b:

    ΔW = diag(b) @ B @ diag(d) @ A

  The adapter output:

    delta = (x @ (A * d[:, None]).T) @ (B * b[:, None]).T

  Where:
    A ∈ ℝ^(r×d_in)    — frozen random, shape (rank, in_features)
    B ∈ ℝ^(d_out×r)   — frozen random, shape (out_features, rank)
    d ∈ ℝ^r            — per-layer trainable column scaling for A
    b ∈ ℝ^(d_out)      — per-layer trainable row scaling for B

  By sharing A and B across all layers and only training d and b, VeRA
  achieves extreme parameter efficiency: only r + d_out parameters per layer
  vs r*(d_in + d_out) for LoRA.

  For d=384, r=64: 448 params/layer vs 49,152 for LoRA r=8 (109× compression).

Reference: Kopiczko et al. (2024) "VeRA: Vector-based Random Matrix Adaptation"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class VeRALinear(DeltaOperator):
    """
    VeRA adapter: shared frozen random projections with per-layer scaling vectors.

    A and B are frozen random matrices (set once, never updated).
    d (rank-dim) and b (out_features-dim) are the only trainable parameters.

    Returns the delta: caller adds to frozen linear output.

    Args:
        in_features:  input dimension
        out_features: output dimension
        rank:         shared random projection rank (default 64, larger than LoRA)
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        rank: int = 64,
    ) -> None:
        super().__init__()
        self.in_features  = in_features
        self.out_features = out_features
        self.rank = rank

        # Frozen shared random matrices — underscore prefix excludes from params
        self._A_frozen = mx.random.normal(shape=(rank, in_features)) * 0.01
        self._B_frozen = mx.random.normal(shape=(out_features, rank)) * 0.01

        # Per-layer trainable scaling vectors
        self.d = mx.ones((rank,))             # scales rows (rank dim) of A
        self.b = mx.zeros((out_features,))    # scales rows of B output

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.WEIGHT_ADDITIVE

    @property
    def genome_config(self) -> dict:
        return {
            "rank": self.rank,
            "in_features": self.in_features,
            "out_features": self.out_features,
            "trainable_params_per_layer": self.rank + self.out_features,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Compute VeRA delta.

        x: [..., in_features]
        returns: [..., out_features]
        """
        # Scale rows of A by d: A_scaled[i,:] = d[i] * A[i,:]
        # d[:, None] broadcasts over columns (in_features), correct shape
        A_scaled = self._A_frozen * self.d[:, None]  # (rank, in_features)

        # x @ A_scaled.T: [..., rank]
        h = x @ A_scaled.T

        # Scale rows of B by b[:, None]: B_scaled[i,:] = b[i] * B[i,:]
        # Then h @ B_scaled.T = h @ (B_scaled): [..., out_features]
        # b[:, None]: (out_features, 1) broadcasts over rank columns
        B_scaled = self._B_frozen * self.b[:, None]  # (out_features, rank)

        return h @ B_scaled.T
