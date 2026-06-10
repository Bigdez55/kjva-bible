"""
peft/selective/bitfit.py — BitFit (Bias-only Fine-Tuning)

Mathematical formulation:
  BitFit freezes all weight matrices W and trains only bias terms b:

    y = x W^T + b       where W is frozen, b is trainable

  For a d_model=384 model with 6 attention layers (4 projections each) and
  6 FFN layers (3 linear ops each), BitFit trains ~30 bias vectors — roughly
  10,000 parameters total, compared to ~16M in the full model.

  Originally proposed for BERT-scale models, BitFit is surprisingly competitive
  on medium-sized fine-tuning tasks despite its extreme parameter efficiency.

Reference: Ben-Zaken et al. (2022) "BitFit: Simple Parameter-efficient
Fine-tuning for Transformer-based Masked Language-models"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class BitFitOperator(DeltaOperator):
    """
    Wraps a frozen nn.Linear weight and adds a trainable bias vector.

    The weight matrix is stored as a frozen mx.array (underscore prefix
    keeps it out of the MLX parameter tree). Only self.bias is trainable.

    Usage:
        op = BitFitOperator(384, 384, frozen_weight=layer.weight)
        output = op(x)   # equivalent to x @ W.T + bias
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        frozen_weight: mx.array,
    ) -> None:
        super().__init__()
        self.in_features  = in_features
        self.out_features = out_features
        # Underscore prefix: excluded from MLX trainable parameter tree
        self._frozen_weight = frozen_weight
        # Only trainable parameter
        self.bias = mx.zeros((out_features,))

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.SPARSE

    @property
    def genome_config(self) -> dict:
        return {
            "in_features": self.in_features,
            "out_features": self.out_features,
            "trainable_params": self.out_features,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Forward pass: frozen weight matrix multiply + trainable bias.

        Args:
            x: input of shape [..., in_features]
        Returns:
            output of shape [..., out_features]
        """
        return x @ self._frozen_weight.T + self.bias


def apply_bitfit(model) -> object:
    """
    Walk all nn.Linear layers in a TokenlessLM and replace them with
    BitFitOperator instances that freeze the weights and train only biases.

    Args:
        model: TokenlessLM instance

    Returns:
        The same model with Linear layers replaced by BitFitOperators.
        Call model.freeze() first, then apply_bitfit to set up the operators.
    """
    # Freeze all base parameters first
    model.freeze()

    # Replace attention projection linears
    for block in model.blocks:
        attn = block.attn
        for proj_name in ("q", "k", "v", "o"):
            linear = getattr(attn, proj_name)
            d = linear.weight.shape[1]   # in_features (weight is [out, in])
            out_d = linear.weight.shape[0]
            op = BitFitOperator(d, out_d, linear.weight)
            setattr(attn, proj_name, op)

        # Replace FFN linears
        mlp = block.mlp
        for proj_name in ("gate", "up"):
            linear = getattr(mlp, proj_name)
            in_d  = linear.weight.shape[1]
            out_d = linear.weight.shape[0]
            op = BitFitOperator(in_d, out_d, linear.weight)
            setattr(mlp, proj_name, op)

        down = mlp.down
        op = BitFitOperator(down.weight.shape[1], down.weight.shape[0], down.weight)
        mlp.down = op

    return model
