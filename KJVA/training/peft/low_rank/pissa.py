"""
peft/low_rank/pissa.py — PiSSA (Principal Singular Values and Singular Vectors Adaptation)

Mathematical formulation:
  PiSSA initializes LoRA matrices using the principal singular components of
  the pre-trained weight W, rather than random initialization:

    W = U S V^T     (full SVD)
    A = V^T[:r]     (top-r right singular vectors, shape [r, d_in])
    B = U[:, :r] * S[:r]   (scaled left singular vectors, shape [d_out, r])

  The residual W_res = W - B @ A captures the low-energy components and is
  frozen. The adapter trains on the high-energy principal subspace:

    output = x @ W_res.T + (x @ A.T @ B.T) * scaling

  By initializing in the principal subspace, PiSSA converges faster than
  random LoRA init and achieves better performance at the same rank.

Reference: Meng et al. (2024) "PiSSA: Principal Singular Values and Singular
Vectors Adaptation of Large Language Models"
"""
from __future__ import annotations

import numpy as np
import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class PiSSALinear(DeltaOperator):
    """
    PiSSA: SVD-initialized LoRA for faster convergence.

    A and B are initialized to span the principal singular subspace of the
    frozen weight. W_residual captures the remaining variance (frozen).

    __call__ returns the full adapted output (W_res + LoRA delta), not just delta.

    Args:
        frozen_weight: pre-trained weight (out_features, in_features)
        rank:          number of principal components to adapt
        alpha:         LoRA scaling factor
    """

    def __init__(
        self,
        frozen_weight: mx.array,
        rank: int = 8,
        alpha: float = 16.0,
    ) -> None:
        super().__init__()
        out_features, in_features = frozen_weight.shape
        self.in_features  = in_features
        self.out_features = out_features
        self.rank    = rank
        self.alpha   = alpha
        self.scaling = alpha / rank

        # SVD via numpy (MLX doesn't expose full SVD directly)
        W_np = np.array(frozen_weight)
        U, S, Vt = np.linalg.svd(W_np, full_matrices=False)

        # Principal subspace initialization
        # A: (rank, in_features) — top-r right singular vectors
        A_init = Vt[:rank].astype(np.float32)
        # B: (out_features, rank) — left singular vectors scaled by singular values
        B_init = (U[:, :rank] * S[:rank]).astype(np.float32)

        self.A = mx.array(A_init)   # trainable
        self.B = mx.array(B_init)   # trainable

        # Residual weight: W - B @ A  (captures low-energy variance, frozen)
        W_res = (W_np - B_init @ A_init).astype(np.float32)
        self._W_residual = mx.array(W_res)

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
        Full PiSSA forward: residual frozen weight + principal-subspace LoRA delta.

        x: [..., in_features]
        returns: [..., out_features]
        """
        # Frozen residual contribution
        residual_out = x @ self._W_residual.T
        # Trainable principal subspace delta
        delta = x @ self.A.T @ self.B.T * self.scaling
        return residual_out + delta
