"""
peft/selective/fishmask.py — FishMask (Fisher Information-weighted Binary Mask)

Mathematical formulation:
  FishMask uses Fisher information to identify which weight parameters are
  most important for a downstream task, then restricts updates to only those
  parameters:

    importance(W_ij) ≈ E[(∂L/∂W_ij)²]   (diagonal Fisher approximation)
    mask = top_K(importance, K=fraction * total_params)
    delta_W = mask * trainable_delta
    y = x @ (W_frozen + delta_W).T

  The mask is computed once during a calibration pass over a small dataset
  and frozen for the rest of training. Only the top-K most important
  parameters are updated, achieving sparse fine-tuning guided by curvature.

Reference: Sung et al. (2021) "Training Neural Networks with Fixed Sparse
Masks"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class FishMaskOperator(DeltaOperator):
    """
    Fisher Information-weighted sparse fine-tuning.

    The frozen_weight is fixed. The binary mask selects which entries of
    the trainable delta are allowed to be updated. After calibration, call
    apply_mask(importance_scores, fraction) to set the mask.

    __call__ computes: x @ (W_frozen + delta * mask).T
    """

    def __init__(
        self,
        frozen_weight: mx.array,
        mask_fraction: float = 0.01,
    ) -> None:
        super().__init__()
        shape = frozen_weight.shape  # (out_features, in_features)
        self.mask_fraction = mask_fraction

        # Frozen base weight — underscore prefix excludes from param tree
        self._frozen_weight = frozen_weight

        # Binary mask — initialized to all-ones (all positions active)
        # Caller updates this via apply_mask() after calibration
        # Use underscore prefix: mask is not a learned parameter
        self._mask = mx.ones(shape)

        # Trainable delta — initialized to zero (no change at start)
        self.delta = mx.zeros(shape)

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.SPARSE

    @property
    def genome_config(self) -> dict:
        return {
            "mask_fraction": self.mask_fraction,
            "weight_shape": list(self._frozen_weight.shape),
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Forward pass with masked sparse delta.

        Args:
            x: input of shape [..., in_features]
        Returns:
            output of shape [..., out_features]
        """
        delta_W = self.delta * self._mask
        return x @ (self._frozen_weight + delta_W).T

    def apply_mask(self, importance_scores: mx.array, fraction: float) -> None:
        """
        Set the binary mask to the top-K most important positions.

        Args:
            importance_scores: array of same shape as frozen_weight,
                               e.g., accumulated squared gradients
            fraction: fraction of parameters to keep active (e.g., 0.01 = 1%)
        """
        total = importance_scores.size
        k = max(1, int(total * fraction))

        # Flatten, find top-K threshold, rebuild binary mask
        flat_scores = importance_scores.reshape(-1)
        # Sort descending to find threshold
        sorted_scores = mx.sort(flat_scores)[::-1]
        threshold = float(sorted_scores[k - 1])

        self._mask = (importance_scores >= threshold).astype(mx.float32)
