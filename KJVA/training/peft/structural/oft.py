"""
peft/structural/oft.py — OFT (Orthogonal Fine-Tuning)

Mathematical formulation:
  OFT applies an orthogonal transformation to weight matrices, preserving
  the hyperspherical energy (pairwise angles between weight neurons):

    W' = R W     where R is block-diagonal orthogonal: R ∈ SO(features)

  The block-diagonal structure uses n_blocks independent rotation matrices
  of size block_size × block_size, constraining each rotation to a subspace:

    R = diag(R_1, R_2, ..., R_{n_blocks})
    R_i ∈ SO(block_size)

  Applied to activations:
    x' = x @ R.T     (reshape x into blocks, rotate each block)

  Orthogonality constraint: R^T R = I, which is enforced during training
  via retraction onto the Stiefel manifold (or Cayley map approximation).
  In this implementation, R is initialized as identity; callers should
  apply orthogonalization after each gradient step.

  This preserves cosine similarities between neurons, preventing
  "hyperspherical collapse" that standard fine-tuning can cause.

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


class OFTLinear(DeltaOperator):
    """
    OFT: block-diagonal orthogonal rotation of hidden activations.

    R is initialized as block-diagonal identity (no-op at init).
    After each gradient step, callers should project R back to SO(block_size)
    via QR decomposition or Cayley transform to maintain orthogonality.

    __call__ returns the rotated activations (full output, not delta).

    Args:
        features:   dimension of the hidden state to rotate
        block_size: size of each rotation block (features // block_size blocks)
    """

    def __init__(
        self,
        features: int,
        block_size: int = 8,
    ) -> None:
        super().__init__()
        assert features % block_size == 0, (
            f"features ({features}) must be divisible by block_size ({block_size})"
        )
        self.features   = features
        self.block_size = block_size
        self.n_blocks   = features // block_size

        # Block-diagonal rotation matrices: (n_blocks, block_size, block_size)
        # Initialize as identity: R_i = I for all i
        identity_block = np.eye(block_size, dtype=np.float32)
        R_init = np.stack([identity_block] * self.n_blocks, axis=0)
        self.R = mx.array(R_init)

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.STRUCTURAL

    @property
    def genome_config(self) -> dict:
        return {
            "features": self.features,
            "block_size": self.block_size,
            "n_blocks": self.n_blocks,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Apply block-diagonal orthogonal rotation to activations.

        Args:
            x: hidden state [B, T, features]
        Returns:
            rotated activations [B, T, features]

        NOTE: This is a structure-preserving transform, not strictly additive.
        The output replaces the input (not a delta to be added).
        """
        B, T, F = x.shape
        # Reshape into blocks: [B, T, n_blocks, block_size]
        x_blocks = x.reshape(B, T, self.n_blocks, self.block_size)

        # Apply each block's rotation matrix
        # R: (n_blocks, block_size, block_size)
        # x_blocks: (B, T, n_blocks, block_size)
        # Result: (B, T, n_blocks, block_size)
        rotated = mx.einsum("nij,btnj->btni", self.R, x_blocks)

        return rotated.reshape(B, T, F)

    def orthogonalize(self) -> None:
        """
        Project R back onto the Stiefel manifold (SO(block_size)) via QR.
        Call after each optimizer step to maintain orthogonality.
        """
        R_np = np.array(self.R)   # (n_blocks, block_size, block_size)
        R_orth = np.zeros_like(R_np)
        for i in range(self.n_blocks):
            Q, _ = np.linalg.qr(R_np[i])
            R_orth[i] = Q
        self.R = mx.array(R_orth.astype(np.float32))
