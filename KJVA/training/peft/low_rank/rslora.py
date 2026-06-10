"""
peft/low_rank/rslora.py — rsLoRA (Rank-Stabilized LoRA)

Mathematical formulation:
  rsLoRA is identical to LoRA except for the scaling factor:

    LoRA scaling:   alpha / r
    rsLoRA scaling: alpha / sqrt(r)

  Standard LoRA's alpha/r scaling causes the effective learning rate to
  decrease linearly as rank increases, destabilizing training at larger ranks.
  The sqrt(r) denominator stabilizes the gradient norms across ranks, enabling
  effective training at r=64, 128, or higher.

  Empirically: at fixed alpha, rsLoRA with r=64 outperforms LoRA r=8 on most
  benchmarks because the higher-rank subspace better approximates full fine-tuning
  without gradient instability.

Reference: Kalajdzievski (2023) "A Rank Stabilization Scaling Factor for
Fine-Tuning with LoRA"
"""
from __future__ import annotations

import math
import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator, kaiming_uniform


class rsLoRALinear(DeltaOperator):
    """
    rsLoRA adapter: rank-stabilized LoRA using alpha / sqrt(rank) scaling.

    The sqrt denominator allows stable training at larger ranks.
    Structure is identical to LoRALinear — only the scaling formula differs.

    Returns the delta only — caller adds to frozen linear output.

    Args:
        in_features:  input dimension
        out_features: output dimension
        rank:         LoRA rank (supports larger values stably, e.g., 32, 64)
        alpha:        LoRA scaling alpha
        dropout:      dropout probability applied to input (0 = disabled)
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
        # Key difference from LoRA: sqrt(rank) stabilizes gradients at high rank
        self.scaling = alpha / math.sqrt(rank)

        # A: (rank, in_features) — Kaiming uniform init
        self.A = kaiming_uniform((rank, in_features))
        # B: (out_features, rank) — zero init so ΔW=0 at start
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
            "scaling_type": "alpha/sqrt(rank)",
            "in_features": self.in_features,
            "out_features": self.out_features,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Compute rsLoRA delta.

        x: [..., in_features]
        returns: [..., out_features]  (the delta, not full output)
        """
        h = x
        if self.dropout is not None:
            h = self.dropout(h)
        return h @ self.A.T @ self.B.T * self.scaling
