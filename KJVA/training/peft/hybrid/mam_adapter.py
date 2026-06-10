"""
peft/hybrid/mam_adapter.py — MAM Adapter (Mix-And-Match)

Mathematical formulation:
  MAM Adapter identifies which PEFT method works best for which part of the
  transformer and combines them optimally:

    Attention layers  → Prefix Tuning (prepend trainable KV pairs)
    FFN layers        → Serial Bottleneck Adapter (Pfeiffer-style)

  The key insight: prefix tuning captures syntactic/attention behavior well,
  while serial adapters are more effective for semantic/FFN transformations.
  Mixing the best method per sub-layer outperforms using either alone.

  Architecture per block:
    x → [frozen attention + prefix KV] → [frozen FFN] + Pfeiffer(x) → output

  The MAMBlock exposes get_prefix(layer_idx) for the attention side and
  __call__ for the FFN adapter delta.

Reference: He et al. (2022) "Towards a Unified View of Parameter-Efficient
Transfer Learning"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator
from peft.additive.pfeiffer import PfeifferAdapter
from peft.prompt.prefix_tuning import PrefixTuningLayer


class MAMBlock(DeltaOperator):
    """
    MAM Adapter: prefix tuning for attention + Pfeiffer adapter for FFN.

    __call__ returns the FFN adapter delta (Pfeiffer side).
    get_prefix(layer_idx) returns the attention prefix KV (prefix tuning side).

    Args:
        d_model:    hidden dimension (default 384)
        n_prefix:   prefix tokens per layer (default 8)
        bottleneck: Pfeiffer adapter bottleneck dim (default 64)
        n_heads:    attention heads (default 6)
        head_dim:   per-head dimension (default 64)
        n_layers:   number of transformer layers (default 6)
    """

    def __init__(
        self,
        d_model: int = 384,
        n_prefix: int = 8,
        bottleneck: int = 64,
        n_heads: int = 6,
        head_dim: int = 64,
        n_layers: int = 6,
    ) -> None:
        super().__init__()
        self.d_model = d_model

        # Prefix tuning for attention layers
        self.prefix = PrefixTuningLayer(
            n_prefix=n_prefix,
            n_heads=n_heads,
            head_dim=head_dim,
            n_layers=n_layers,
        )

        # Pfeiffer adapter for FFN layers
        self.adapter = PfeifferAdapter(d_model, bottleneck)

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.ROUTING

    @property
    def genome_config(self) -> dict:
        return {
            "d_model": self.d_model,
            "attn_method": "prefix_tuning",
            "ffn_method": "pfeiffer_adapter",
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Compute FFN adapter delta (Pfeiffer side).

        Args:
            x: FFN input/output of shape [B, T, D]
        Returns:
            adapter delta [B, T, D]
        """
        return self.adapter(x)

    def get_prefix(self, layer_idx: int) -> tuple[mx.array, mx.array]:
        """
        Retrieve attention prefix KV for the given layer.

        Args:
            layer_idx: transformer layer index
        Returns:
            (prefix_k, prefix_v) each of shape [n_prefix, n_heads*head_dim]
        """
        return self.prefix.get_prefix(layer_idx)
