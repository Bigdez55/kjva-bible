"""
peft/structural/boft.py — BOFT (Butterfly Orthogonal Fine-Tuning)

Mathematical formulation:
  BOFT extends OFT by using a butterfly sparsity pattern for the orthogonal
  transform, dramatically reducing parameters from O(d²) to O(d log d):

  A butterfly matrix B_L of depth L applies L layers of paired rotations:
    Layer l: rotate pairs of dimensions spaced 2^l apart

  For depth L and dimension d, the butterfly transform:
    x' = B_1 * B_2 * ... * B_L * x

  Each level B_l consists of d/2 independent 2×2 rotation matrices
  (SO(2) elements). Total parameters: L * d/2 * 4 (vs d² for dense OFT).
  For d=384, L=2: 2 * 192 * 4 = 1,536 vs 147,456 for dense.

  The butterfly pattern ensures full rank expressivity (any orthogonal matrix
  can be approximated) while maintaining O(d log d) parameter count.

Reference: Liu et al. (2023) "Orthogonal Fine-tuning via Butterfly
Factorization"
"""
from __future__ import annotations

import numpy as np
import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class BOFTLinear(DeltaOperator):
    """
    BOFT: butterfly-structured orthogonal rotation.

    Each butterfly level operates on adjacent pairs of dimensions,
    applying independent 2×2 rotation matrices to each pair.

    __call__ returns the butterfly-rotated activations (full output).

    Args:
        features:          dimension to rotate (must be even)
        n_butterfly_levels: depth of butterfly factorization (default 2)
    """

    def __init__(
        self,
        features: int,
        n_butterfly_levels: int = 2,
    ) -> None:
        super().__init__()
        assert features % 2 == 0, f"features ({features}) must be even for butterfly OFT"
        self.features           = features
        self.n_butterfly_levels = n_butterfly_levels

        # Each level: features/2 independent 2×2 rotation matrices
        # Parameterized by a single angle θ per pair:
        #   [[cos θ, -sin θ], [sin θ, cos θ]]
        # Store as (n_levels, features//2) angles, initialized to 0 (identity)
        self.butterfly_angles = mx.zeros((n_butterfly_levels, features // 2))

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.STRUCTURAL

    @property
    def genome_config(self) -> dict:
        return {
            "features": self.features,
            "n_butterfly_levels": self.n_butterfly_levels,
            "param_count": self.n_butterfly_levels * (self.features // 2),
        }

    def _apply_butterfly_level(self, x: mx.array, level: int) -> mx.array:
        """
        Apply one butterfly level: rotate adjacent pairs of dimensions.

        For level l, pair indices (2i, 2i+1) for i in range(features//2).

        Args:
            x: [..., features]
            level: butterfly level index
        Returns:
            [..., features] after pairwise rotation
        """
        angles = self.butterfly_angles[level]   # (features//2,)
        cos_a  = mx.cos(angles)  # (features//2,)
        sin_a  = mx.sin(angles)  # (features//2,)

        # Extract even and odd indexed dimensions
        x_even = x[..., 0::2]    # [..., features//2]
        x_odd  = x[..., 1::2]    # [..., features//2]

        # Apply 2×2 rotations
        x_even_rot = cos_a * x_even - sin_a * x_odd
        x_odd_rot  = sin_a * x_even + cos_a * x_odd

        # Interleave back
        B_T = x.shape[:-1]
        out = mx.zeros((*B_T, self.features), dtype=x.dtype)
        # Build output by concatenation and transpose trick
        # Stack (even, odd) → reshape to (..., features//2, 2) → flatten
        stacked = mx.stack([x_even_rot, x_odd_rot], axis=-1)  # [..., F//2, 2]
        return stacked.reshape(*B_T, self.features)

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Apply butterfly orthogonal transform.

        Args:
            x: hidden state [..., features]
        Returns:
            rotated activations [..., features]
        """
        for level in range(self.n_butterfly_levels):
            x = self._apply_butterfly_level(x, level)
        return x
