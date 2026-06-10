"""
peft/hybrid/unipelt.py — UniPELT (Unified Parameter-Efficient Language Model Tuning)

Mathematical formulation:
  UniPELT combines LoRA, Prefix Tuning, and Houlsby Adapters with learned
  gating mechanisms that control each component's contribution:

    g_lora  = sigmoid(W_gate_lora  * mean(x))   ∈ [0, 1]
    g_adapt = sigmoid(W_gate_adapt * mean(x))   ∈ [0, 1]

    delta = g_lora * LoRA(x) + g_adapt * Adapter(x)
    (prefix is applied externally via PrefixTuningLayer.get_prefix)

  The gating allows the model to learn which PEFT method contributes most
  for each layer, effectively performing soft method selection during training.

  This multi-method approach avoids the need to pick a single PEFT method
  a priori, achieving better generalization across diverse task types.

Reference: Mao et al. (2022) "UniPELT: A Unified Framework for Parameter-
Efficient Language Model Tuning"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator
from peft.low_rank.lora import LoRALinear
from peft.additive.houlsby import HoulsbyAdapter
from peft.prompt.prefix_tuning import PrefixTuningLayer


class UniPELTBlock(DeltaOperator):
    """
    UniPELT: gated combination of LoRA, Prefix Tuning, and Houlsby Adapter.

    The gating mechanism computes scalar gates from the mean of x, routing
    how much each sub-adapter contributes to the output.

    __call__ returns the combined delta (LoRA + Adapter, gated).
    Prefix tokens are retrieved separately via prefix.get_prefix(layer_idx).

    Args:
        d_model:            hidden dimension (default 384)
        rank:               LoRA rank (default 4)
        n_prefix:           number of prefix tokens (default 8)
        adapter_bottleneck: Houlsby bottleneck dim (default 32)
        n_heads:            attention heads for prefix (default 6)
        head_dim:           per-head dim for prefix (default 64)
    """

    def __init__(
        self,
        d_model: int = 384,
        rank: int = 4,
        n_prefix: int = 8,
        adapter_bottleneck: int = 32,
        n_heads: int = 6,
        head_dim: int = 64,
    ) -> None:
        super().__init__()
        self.d_model = d_model

        # Sub-adapters
        self.lora    = LoRALinear(d_model, d_model, rank=rank)
        self.prefix  = PrefixTuningLayer(n_prefix=n_prefix, n_heads=n_heads, head_dim=head_dim)
        self.adapter = HoulsbyAdapter(d_model, adapter_bottleneck)

        # Scalar gates — project mean(x) [B, 1, D] → [B, 1, 1]
        self.gate_lora    = nn.Linear(d_model, 1, bias=True)
        self.gate_adapter = nn.Linear(d_model, 1, bias=True)

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.ROUTING

    @property
    def genome_config(self) -> dict:
        return {
            "d_model": self.d_model,
            "components": ["lora", "prefix_tuning", "houlsby_adapter"],
            "gating": "sigmoid_on_mean",
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Compute gated LoRA + Adapter delta.

        Args:
            x: hidden state [B, T, D]
        Returns:
            combined delta [B, T, D]
        """
        # Mean pooling over sequence for gating: [B, 1, D]
        x_mean = x.mean(axis=1, keepdims=True)

        # Scalar gates: [B, 1, 1]
        g_lora  = mx.sigmoid(self.gate_lora(x_mean))
        g_adapt = mx.sigmoid(self.gate_adapter(x_mean))

        # LoRA and adapter deltas
        lora_delta    = self.lora(x)
        adapter_delta = self.adapter(x)

        return g_lora * lora_delta + g_adapt * adapter_delta
