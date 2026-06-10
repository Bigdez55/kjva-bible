"""
peft/additive/houlsby.py — Houlsby Bottleneck Adapter

Mathematical formulation:
  The Houlsby adapter is a small feed-forward bottleneck module inserted after
  both the attention sub-layer and the FFN sub-layer in each transformer block:

    adapter(x) = W_up * act(W_down * x + b_down) + b_up

  Where:
    W_down ∈ ℝ^(bottleneck × d_model)   (down-projection)
    W_up   ∈ ℝ^(d_model × bottleneck)   (up-projection)

  The adapter output is added residually: x' = x + adapter(x)

  Near-identity initialization: W_up is initialized near-zero so the adapter
  starts as a no-op, allowing stable training from the frozen model's output.

  Parameters: 2 * d_model * bottleneck_dim (+ biases)
  For d=384, bottleneck=64: ~49,152 params per adapter location.

Reference: Houlsby et al. (2019) "Parameter-Efficient Transfer Learning for NLP"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class HoulsbyAdapter(DeltaOperator):
    """
    Houlsby bottleneck adapter: down-project, activate, up-project.

    Returns the adapter delta (x is NOT included). The caller adds residually:
        x_out = x + adapter(x)

    Args:
        d_model:        model hidden dimension
        bottleneck_dim: inner bottleneck dimension (default 64)
        activation:     "gelu" or "relu"
    """

    def __init__(
        self,
        d_model: int = 384,
        bottleneck_dim: int = 64,
        activation: str = "gelu",
    ) -> None:
        super().__init__()
        self.d_model        = d_model
        self.bottleneck_dim = bottleneck_dim

        self.down = nn.Linear(d_model, bottleneck_dim, bias=True)
        self.up   = nn.Linear(bottleneck_dim, d_model, bias=True)

        # Activation function
        if activation == "gelu":
            self.act = nn.GELU()
        else:
            self.act = nn.ReLU()

        # Near-identity init for up projection — start as near no-op
        # MLX nn.Linear initializes randomly; we zero out up.weight
        self.up.weight = mx.zeros_like(self.up.weight)

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.MODULE

    @property
    def genome_config(self) -> dict:
        return {
            "d_model": self.d_model,
            "bottleneck_dim": self.bottleneck_dim,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Compute adapter delta.

        x: [B, T, D]
        returns: [B, T, D] (the delta, caller adds to x)
        """
        return self.up(self.act(self.down(x)))


class HoulsbyTransformerBlock(nn.Module):
    """
    Wraps an existing TransformerBlock and inserts Houlsby adapters after
    both the attention sub-layer and the FFN sub-layer.

    The wrapped block's parameters are frozen. Only the two adapters
    (adapter_attn, adapter_ffn) are trained.

    Args:
        block:          frozen TransformerBlock instance
        bottleneck_dim: adapter bottleneck dimension
        activation:     adapter activation function
    """

    def __init__(
        self,
        block,
        bottleneck_dim: int = 64,
        activation: str = "gelu",
    ) -> None:
        super().__init__()
        self.block = block
        self.block.freeze()   # Freeze all block parameters

        d_model = block.cfg.d_model
        self.adapter_attn = HoulsbyAdapter(d_model, bottleneck_dim, activation)
        self.adapter_ffn  = HoulsbyAdapter(d_model, bottleneck_dim, activation)

    def __call__(
        self,
        x: mx.array,
        cos: mx.array,
        sin: mx.array,
        mask: mx.array | None = None,
    ) -> mx.array:
        # Attention sub-layer with adapter
        attn_out = self.block.attn(self.block.norm1(x), cos, sin, mask)
        x = x + attn_out + self.adapter_attn(attn_out)

        # FFN sub-layer with adapter
        ffn_out = self.block.mlp(self.block.norm2(x))
        x = x + ffn_out + self.adapter_ffn(ffn_out)

        return x
