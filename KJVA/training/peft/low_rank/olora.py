"""
peft/low_rank/olora.py — OLoRA (Orthonormal Low-Rank Adaptation)

Mathematical formulation:
  OLoRA modifies the LoRA initialization by using QR decomposition to ensure
  A starts as an orthonormal matrix:

    Random M ∈ ℝ^(r×d_in) → QR decomposition → Q is orthonormal (r×d_in)
    A ← Q      (orthonormal rows)
    B ← 0      (zero init, same as standard LoRA)

  The orthonormal initialization ensures:
  1. Rows of A are unit vectors with pairwise orthogonality
  2. No two LoRA components adapt redundant directions at initialization
  3. Better gradient flow through A at the start of training

  The forward pass is identical to LoRA. The improvement is purely in init.

Reference: Büyükakyüz (2024) "OLoRA: Orthonormal Low-Rank Adaptation of
Large Language Models"
"""
from __future__ import annotations

import numpy as np
import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class OLoRALinear(DeltaOperator):
    """
    OLoRA adapter: orthonormal initialization of the A matrix via QR decomposition.

    A is initialized as an orthonormal matrix (rows are orthonormal unit vectors).
    B is initialized to zero, so ΔW=0 at start (same as standard LoRA).
    Forward pass is identical to LoRA.

    Returns the delta only — caller adds to frozen linear output.

    Args:
        in_features:  input dimension
        out_features: output dimension
        rank:         LoRA rank
        alpha:        LoRA scaling alpha
        dropout:      dropout probability (0 = disabled)
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        rank: int = 8,
        alpha: float = 16.0,
        dropout: float = 0.0,
    ) -> None:
        super().__init__()
        self.in_features  = in_features
        self.out_features = out_features
        self.rank    = rank
        self.alpha   = alpha
        self.scaling = alpha / rank

        # Orthonormal init for A via QR decomposition
        # Random matrix: (rank, in_features) or (in_features, rank) depending on which is larger
        rand_mat = np.random.randn(max(rank, in_features), min(rank, in_features)).astype(np.float32)
        Q, _ = np.linalg.qr(rand_mat)
        if rank <= in_features:
            # Q is (in_features, rank) — we need (rank, in_features)
            A_init = Q[:rank, :].T  # this gives (rank, rank) — wrong if rank < in_features
            # Correct: Q from (in_features, rank) → (in_features, rank), take transpose → (rank, in_features)
            rand_mat = np.random.randn(in_features, rank).astype(np.float32)
            Q, _ = np.linalg.qr(rand_mat)
            A_init = Q.T[:rank]  # (rank, in_features) — orthonormal rows
        else:
            # rank > in_features: Q is (rank, in_features)
            A_init = Q[:rank, :in_features]

        self.A = mx.array(A_init.astype(np.float32))
        # B: (out_features, rank) — zero init
        self.B = mx.zeros((out_features, rank))

        self.dropout = nn.Dropout(p=dropout) if dropout > 0.0 else None

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.WEIGHT_ADDITIVE

    @property
    def genome_config(self) -> dict:
        return {
            "rank": self.rank,
            "alpha": self.alpha,
            "scaling": self.scaling,
            "init": "orthonormal_qr",
            "in_features": self.in_features,
            "out_features": self.out_features,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Compute OLoRA delta (identical to LoRA forward, better init).

        x: [..., in_features]
        returns: [..., out_features]
        """
        h = x
        if self.dropout is not None:
            h = self.dropout(h)
        return h @ self.A.T @ self.B.T * self.scaling
