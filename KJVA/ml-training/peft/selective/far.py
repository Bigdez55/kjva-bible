"""
peft/selective/far.py — FAR (Freeze and Reconfigure)

Mathematical formulation:
  FAR freezes the majority of model layers and selectively reconfigures
  a small subset using a learned gating mechanism:

    gate = sigmoid(W_gate * x)   ∈ [0, 1]^D
    y = x * gate * scale

  The routing_gate projects x → x to produce a per-dimension gating vector,
  and scale is a trainable global scaling factor. The combination allows
  the adapter to selectively amplify, suppress, or reroute activations.

  With reconfigure_fraction=0.1, only 10% of layers are targeted, keeping
  total trainable parameters small while allowing targeted intervention.

Reference: Vucetic et al. (2022) "Efficient Fine-Tuning of BERT Models on
the Edge"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class FAROperator(DeltaOperator):
    """
    FAR adapter: learned gating for selective layer reconfiguration.

    The routing_gate and scale are the only trainable parameters.
    This operator wraps a single layer and applies a learned sigmoid gate
    followed by element-wise scaling.

    Returns the reconfigured activation: x * gate * scale.
    This is used as the full output for the targeted layer (not a delta).
    """

    def __init__(
        self,
        d_model: int = 384,
        reconfigure_fraction: float = 0.1,
    ) -> None:
        super().__init__()
        self.d_model = d_model
        self.reconfigure_fraction = reconfigure_fraction

        # Trainable routing gate: projects d_model → d_model
        self.routing_gate = nn.Linear(d_model, d_model, bias=False)

        # Trainable per-dimension scale — init ones (no scaling at start)
        self.scale = mx.ones((d_model,))

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.SPARSE

    @property
    def genome_config(self) -> dict:
        return {
            "d_model": self.d_model,
            "reconfigure_fraction": self.reconfigure_fraction,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Apply learned gating and scaling.

        Args:
            x: hidden state of shape [B, T, D]
        Returns:
            reconfigured activation of shape [B, T, D]
        """
        gate = mx.sigmoid(self.routing_gate(x))   # [B, T, D]
        return x * gate * self.scale
