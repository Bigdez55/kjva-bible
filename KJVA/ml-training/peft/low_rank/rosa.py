"""
peft/low_rank/rosa.py — RoSA (Robust Sparse Adaptation)

Mathematical formulation:
  RoSA combines LoRA's low-rank structured updates with a sparse correction
  for outlier directions that fall outside the low-rank subspace:

    ΔW = (B @ A) * scaling + S ⊙ M

  Where:
    B @ A    = low-rank component (captures dominant adaptation directions)
    S        = trainable sparse delta matrix (out_features, in_features)
    M        = binary sparsity mask (fixed after initialization)
    ⊙        = element-wise product

  The sparse correction captures long-tail weight updates that LoRA's subspace
  misses, improving performance on tasks requiring diverse adaptation directions.
  With sparsity=0.01, S has 99% of entries masked, making it highly efficient.

Reference: Nikdan et al. (2024) "RoSA: Accurate Parameter-Efficient Fine-Tuning
via Robust Adaptation"
"""
from __future__ import annotations

import numpy as np
import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator, kaiming_uniform


class RoSALinear(DeltaOperator):
    """
    RoSA adapter: low-rank + sparse correction.

    The low-rank component (A, B) captures the principal adaptation subspace.
    The sparse component (sparse_delta * sparse_mask) corrects outliers.
    Both components are added to produce the final delta.

    sparse_mask is a fixed random binary mask (not trained).
    sparse_delta is trained but only at masked positions during gradient application.

    Returns the delta — caller adds to frozen linear output.

    Args:
        in_features:  input dimension
        out_features: output dimension
        rank:         LoRA rank for low-rank component
        alpha:        LoRA scaling
        sparsity:     fraction of entries active in sparse component
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        rank: int = 4,
        alpha: float = 16.0,
        sparsity: float = 0.01,
    ) -> None:
        super().__init__()
        self.in_features  = in_features
        self.out_features = out_features
        self.rank     = rank
        self.alpha    = alpha
        self.sparsity = sparsity
        self.scaling  = alpha / rank

        # Low-rank component
        self.A = kaiming_uniform((rank, in_features))
        self.B = mx.zeros((out_features, rank))

        # Sparse component — trainable delta
        self.sparse_delta = mx.zeros((out_features, in_features))

        # Fixed sparse mask — random binary with `sparsity` fraction active
        # Underscore prefix: not a trainable parameter
        mask_np = (np.random.rand(out_features, in_features) < sparsity).astype(np.float32)
        self._sparse_mask = mx.array(mask_np)

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.WEIGHT_ADDITIVE

    @property
    def genome_config(self) -> dict:
        return {
            "rank": self.rank,
            "alpha": self.alpha,
            "sparsity": self.sparsity,
            "scaling": self.scaling,
            "in_features": self.in_features,
            "out_features": self.out_features,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Compute RoSA delta: low-rank + sparse correction.

        x: [..., in_features]
        returns: [..., out_features]
        """
        # Low-rank delta
        lora_delta = x @ self.A.T @ self.B.T * self.scaling

        # Sparse correction delta (only active at masked positions)
        sparse_delta = x @ (self.sparse_delta * self._sparse_mask).T

        return lora_delta + sparse_delta
