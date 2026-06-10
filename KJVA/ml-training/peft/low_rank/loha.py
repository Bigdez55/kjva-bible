"""
peft/low_rank/loha.py — LoHa (Low-Rank Hadamard Product Adaptation)

Mathematical formulation:
  LoHa represents the weight delta as the Hadamard (element-wise) product of
  two independent low-rank factorizations:

    W1 = B1 @ A1     ∈ ℝ^(d_out × d_in)
    W2 = B2 @ A2     ∈ ℝ^(d_out × d_in)
    ΔW = W1 ⊙ W2    (element-wise product)

  This captures multiplicative interactions between rank-r subspaces.
  The effective rank of ΔW can be up to r² while using only 4r(d_in+d_out)
  parameters — offering a richer delta structure than standard LoRA at the
  same parameter count.

  The scaling is alpha / r² to compensate for the squared magnitude from
  the Hadamard product.

Reference: Yeh et al. (2023) "LoHa: Low-Rank Hadamard Product for
Efficient Fine-Tuning"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator, kaiming_uniform


class LoHaLinear(DeltaOperator):
    """
    LoHa adapter: weight delta via Hadamard product of two low-rank factors.

    ΔW = (B1 @ A1) ⊙ (B2 @ A2), output = x @ ΔW.T * scaling

    All four matrices are trainable. A matrices use Kaiming init, B matrices
    use zero init (so ΔW ≈ 0 at initialization).

    Returns the delta only — caller adds to frozen linear output.

    Args:
        in_features:  input dimension
        out_features: output dimension
        rank:         rank for each factorization (effective rank up to rank²)
        alpha:        scaling factor
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        rank: int = 4,
        alpha: float = 16.0,
    ) -> None:
        super().__init__()
        self.in_features  = in_features
        self.out_features = out_features
        self.rank    = rank
        self.alpha   = alpha
        # Scaling compensates for Hadamard product magnitude
        self.scaling = alpha / (rank ** 2)

        # First factorization
        self.A1 = kaiming_uniform((rank, in_features))
        self.B1 = mx.zeros((out_features, rank))

        # Second factorization
        self.A2 = kaiming_uniform((rank, in_features))
        self.B2 = mx.zeros((out_features, rank))

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.WEIGHT_ADDITIVE

    @property
    def genome_config(self) -> dict:
        return {
            "rank": self.rank,
            "alpha": self.alpha,
            "scaling": self.scaling,
            "in_features": self.in_features,
            "out_features": self.out_features,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Compute LoHa delta via Hadamard product of two low-rank weight matrices.

        x: [..., in_features]
        returns: [..., out_features]
        """
        W1 = self.B1 @ self.A1   # (out_features, in_features)
        W2 = self.B2 @ self.A2   # (out_features, in_features)
        # Hadamard product then project
        delta_W = W1 * W2        # (out_features, in_features)
        return x @ delta_W.T * self.scaling
