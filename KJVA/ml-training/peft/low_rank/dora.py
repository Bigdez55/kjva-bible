"""
peft/low_rank/dora.py — DoRA (Weight-Decomposed Low-Rank Adaptation)

Mathematical formulation:
  DoRA decomposes a pre-trained weight W into magnitude and direction:

    W = m * (W / ‖W‖_c)     where ‖W‖_c denotes column-wise norms

  The LoRA update is applied to the directional component, and a trainable
  magnitude vector m replaces the frozen column norms:

    W' = m / ‖W + B@A * s‖_c  *  (W + B@A * s)

  This separates "how much" (magnitude m) from "which direction" (unit weight),
  allowing LoRA to more faithfully approximate full fine-tuning without the
  directional bias LoRA introduces.

  DoRA replaces the full linear layer (not just a delta) — the output IS the
  final projection output.

Reference: Liu et al. (2024) "DoRA: Weight-Decomposed Low-Rank Adaptation"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator, kaiming_uniform


class DoRALinear(DeltaOperator):
    """
    DoRA linear layer: weight-decomposed low-rank adaptation.

    This replaces the full linear projection. The output is the complete
    adapted activation (not a delta).

    Args:
        frozen_weight: pre-trained weight of shape (out_features, in_features)
        rank:          LoRA rank
        alpha:         LoRA scaling alpha
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

        # Frozen base weight — excluded from parameter tree
        self._frozen_weight = frozen_weight

        # Compute column-wise L2 norms: shape (1, in_features)
        # Using explicit sqrt-of-sum for MLX compatibility
        col_norms = mx.sqrt(mx.sum(frozen_weight * frozen_weight, axis=0, keepdims=True))

        # Trainable magnitude vector — initialized to frozen column norms
        # shape: (1, in_features)
        self.m = col_norms

        # LoRA A: (rank, in_features) — Kaiming uniform
        self.lora_A = kaiming_uniform((rank, in_features))
        # LoRA B: (out_features, rank) — zeros
        self.lora_B = mx.zeros((out_features, rank))

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
        DoRA forward pass: full adapted output (replaces frozen linear).

        x: [..., in_features]
        returns: [..., out_features]
        """
        # Compute adapted weight
        # lora_B @ lora_A: (out, in)
        W_adapted = self._frozen_weight + self.lora_B @ self.lora_A * self.scaling

        # Column-wise norm of adapted weight: (1, in_features)
        W_norm = mx.sqrt(mx.sum(W_adapted * W_adapted, axis=0, keepdims=True))

        # DoRA weight: rescale columns by learnable magnitude
        W_dora = (self.m / W_norm) * W_adapted

        return x @ W_dora.T
