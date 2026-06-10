"""
peft/low_rank/adalora.py — AdaLoRA (Adaptive Budget Allocation via Singular Value Decomposition)

Mathematical formulation:
  AdaLoRA parameterizes the weight delta using truncated SVD:

    ΔW = P Λ Q     where P ∈ ℝ^(d_out×r), Q ∈ ℝ^(r×d_in), Λ = diag(λ_1,...,λ_r)

  P and Q are initialized as orthogonal matrices. Λ holds learnable singular
  values that act as importance weights. During training, singular values with
  low magnitude are pruned by zeroing them out, adaptively reducing rank for
  less important layers and increasing it (up to budget) for important ones.

  Budget allocation: total_rank budget is distributed across layers by pruning
  low-importance singular values identified by a running average of |Λ|.

  The output delta is: x @ Q.T * Λ @ P.T * (alpha / r)

Reference: Zhang et al. (2022) "AdaLoRA: Adaptive Budget Allocation for
Parameter-Efficient Fine-Tuning"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator, orthogonal_init


class AdaLoRALinear(DeltaOperator):
    """
    AdaLoRA: SVD-parameterized low-rank delta with importance-guided rank pruning.

    The weight delta is ΔW = P diag(Λ) Q, with P, Q orthogonal and Λ trainable.
    Calling prune_to_rank(new_rank) zeros out the least important singular values.

    Args:
        in_features:  input dimension
        out_features: output dimension
        rank:         initial rank r
        alpha:        scaling factor
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        rank: int = 8,
        alpha: float = 16.0,
    ) -> None:
        super().__init__()
        self.in_features  = in_features
        self.out_features = out_features
        self.rank    = rank
        self.alpha   = alpha
        self.scaling = alpha / rank

        # P: (out_features, rank) — orthogonal init
        self.P = orthogonal_init(out_features, rank)
        # Q: (rank, in_features) — orthogonal init
        self.Q = orthogonal_init(rank, in_features)
        # Lambda: (rank,) — small uniform init for singular values
        import numpy as np
        self.Lambda = mx.array(
            np.random.uniform(0.0, 0.1, (rank,)).astype(np.float32)
        )

        # Running importance score (not a learned param — underscore prefix)
        self._importance = mx.zeros((rank,))

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
        Compute SVD-parameterized weight delta.

        x: [..., in_features]
        returns: [..., out_features] (the delta, add to frozen output)
        """
        # x @ Q.T: [..., rank]
        # * Lambda: [..., rank]  (broadcast singular values)
        # @ P.T:    [..., out_features]
        h = x @ self.Q.T              # [..., rank]
        h = h * self.Lambda           # [..., rank] element-wise scale
        return h @ self.P.T * self.scaling

    def update_importance(self) -> None:
        """Update running importance scores as exponential moving average of |Lambda|."""
        self._importance = 0.9 * self._importance + 0.1 * mx.abs(self.Lambda)

    def prune_to_rank(self, new_rank: int) -> None:
        """
        Zero out the (rank - new_rank) least important singular values,
        effectively reducing the active rank for this layer.

        Args:
            new_rank: target rank (must be <= self.rank)
        """
        if new_rank >= self.rank:
            return
        # Find indices of lowest-importance singular values
        # Sort ascending; keep top new_rank by zeroing the rest
        sorted_idx = mx.argsort(self._importance)  # ascending
        n_prune = self.rank - new_rank
        # Build a mask: 1 for kept, 0 for pruned
        mask = mx.ones((self.rank,))
        prune_indices = sorted_idx[:n_prune]
        # Set pruned positions to 0 via scatter — use numpy for index ops
        import numpy as np
        mask_np = np.ones((self.rank,), dtype=np.float32)
        prune_np = np.array(prune_indices.tolist(), dtype=np.int32)
        mask_np[prune_np] = 0.0
        pruned_lambda = self.Lambda * mx.array(mask_np)
        self.Lambda = pruned_lambda
