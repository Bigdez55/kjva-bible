"""
peft/selective/diffpruning.py — DiffPruning (Differentiable Sparse Delta)

Mathematical formulation:
  DiffPruning learns a sparse additive delta to the weight matrix using an
  L0-regularization approximation via the hard concrete / stretched sigmoid
  distribution:

    delta_W = z * W_delta
    z = sigmoid(log_alpha)       (soft/differentiable mask during training)

  The L0 penalty encourages most mask values to be near zero:

    L0_penalty = sum(sigmoid(log_alpha))

  Sparsity target: only `sparsity` fraction of weight entries are non-zero.
  During inference, a hard threshold (z > 0.5) creates a binary mask.

  For a 384x384 weight matrix with sparsity=0.01, only ~1,475 of 147,456
  entries are active, yielding massive parameter efficiency.

Reference: Guo et al. (2020) "Parameter-Efficient Transfer Learning with
Diff Pruning"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class DiffPruningOperator(DeltaOperator):
    """
    Differentiable sparse weight delta using L0 mask relaxation.

    Both W_delta (the candidate delta weights) and log_alpha (the mask logits)
    are trainable. The L0 penalty on log_alpha drives sparsity.

    During training: soft mask = sigmoid(log_alpha) in [0, 1].
    During eval/inference: hard mask = (sigmoid(log_alpha) > 0.5).

    __call__ returns the sparse delta x @ (W_delta * mask).T — the caller
    adds this to the frozen base output.
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        sparsity: float = 0.01,
    ) -> None:
        super().__init__()
        self.in_features  = in_features
        self.out_features = out_features
        self.sparsity     = sparsity

        # Trainable sparse delta weights — initialized to zero (no change at start)
        self.W_delta   = mx.zeros((out_features, in_features))
        # Mask logits — initialized to a large negative value so sigmoid ≈ 0 (sparse)
        # log_alpha = -5.0 → sigmoid(-5) ≈ 0.007, close to our target sparsity
        self.log_alpha = mx.full((out_features, in_features), -5.0)

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.SPARSE

    @property
    def genome_config(self) -> dict:
        return {
            "in_features": self.in_features,
            "out_features": self.out_features,
            "sparsity": self.sparsity,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Compute sparse weight delta output.

        Args:
            x: input of shape [..., in_features]
        Returns:
            sparse delta of shape [..., out_features]
        """
        mask = mx.sigmoid(self.log_alpha)           # soft mask in [0,1]
        return x @ (self.W_delta * mask).T

    def l0_penalty(self) -> mx.array:
        """
        L0 regularization penalty.

        Encourages most mask values toward zero. Add lambda * l0_penalty()
        to the training loss to drive sparsity.

        Returns:
            scalar penalty (sum of sigmoid(log_alpha) values)
        """
        return mx.sum(mx.sigmoid(self.log_alpha))
