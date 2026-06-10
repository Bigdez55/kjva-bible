"""
peft/additive/pfeiffer.py — Pfeiffer Adapter

Mathematical formulation:
  The Pfeiffer adapter is an ablated variant of the Houlsby adapter:

    adapter(x) = W_up * act(W_down * x + b_down) + b_up

  The structure is identical to Houlsby BUT the adapter is inserted only
  after the FFN sub-layer — NOT after attention. This halves the parameter
  count per block vs Houlsby while retaining most of the performance.

  Pfeiffer et al. found that adapter placement after FFN is more important
  than placement after attention. Their adapter also adds a LayerNorm
  before the down-projection; we follow this variant.

  Parameters: ~49K per block (half of Houlsby's ~98K).

Reference: Pfeiffer et al. (2020) "AdapterFusion: Non-Destructive Task
Composition for Transfer Learning"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class PfeifferAdapter(DeltaOperator):
    """
    Pfeiffer bottleneck adapter: LayerNorm → down-project → activate → up-project.

    Returns the adapter delta. Caller adds residually: x_out = x + adapter(x).

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

        self.norm = nn.LayerNorm(d_model)
        self.down = nn.Linear(d_model, bottleneck_dim, bias=True)
        self.up   = nn.Linear(bottleneck_dim, d_model, bias=True)

        if activation == "gelu":
            self.act = nn.GELU()
        else:
            self.act = nn.ReLU()

        # Near-identity init
        self.up.weight = mx.zeros_like(self.up.weight)

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.MODULE

    @property
    def genome_config(self) -> dict:
        return {
            "d_model": self.d_model,
            "bottleneck_dim": self.bottleneck_dim,
            "placement": "ffn_only",
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Compute Pfeiffer adapter delta.

        x: [B, T, D]
        returns: [B, T, D] (delta, caller adds to x)
        """
        return self.up(self.act(self.down(self.norm(x))))


class PfeifferTransformerBlock(nn.Module):
    """
    Wraps a TransformerBlock and inserts a Pfeiffer adapter after the FFN only
    (NOT after attention, unlike Houlsby).

    The wrapped block is frozen. Only adapter_ffn is trained.

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
        self.block.freeze()

        d_model = block.cfg.d_model
        self.adapter_ffn = PfeifferAdapter(d_model, bottleneck_dim, activation)

    def __call__(
        self,
        x: mx.array,
        cos: mx.array,
        sin: mx.array,
        mask: mx.array | None = None,
    ) -> mx.array:
        # Standard attention sub-layer (no adapter here)
        x = x + self.block.attn(self.block.norm1(x), cos, sin, mask)

        # FFN sub-layer with Pfeiffer adapter
        ffn_out = self.block.mlp(self.block.norm2(x))
        x = x + ffn_out + self.adapter_ffn(ffn_out)

        return x
