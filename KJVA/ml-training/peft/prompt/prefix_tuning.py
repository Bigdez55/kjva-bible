"""
peft/prompt/prefix_tuning.py — Prefix Tuning

Mathematical formulation:
  Prefix Tuning prepends trainable key-value pairs to every attention layer.
  Unlike Prompt Tuning which operates on the input embedding, Prefix Tuning
  injects trainable context at each transformer layer's KV cache:

    K' = concat([P_k^l, K])    ∈ ℝ^(n_prefix+T, D)
    V' = concat([P_v^l, V])    ∈ ℝ^(n_prefix+T, D)

  Where P_k^l, P_v^l are the trainable prefix K and V vectors for layer l.

  Each layer gets its own prefix (not shared), so total parameters:
    n_layers * 2 * n_prefix * (n_heads * head_dim)
    = 6 * 2 * 32 * 384 = 147,456

  The __call__ is identity — prefix is injected by patching attention's KV
  using get_prefix(layer_idx) at the attention forward step.

Reference: Li & Liang (2021) "Prefix-Tuning: Optimizing Continuous Prompts
for Generation"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class PrefixTuningLayer(DeltaOperator):
    """
    Prefix tuning: per-layer trainable K and V prefix vectors.

    This operator stores all prefix vectors. The caller retrieves per-layer
    prefixes via get_prefix(layer_idx) and prepends them to K and V in the
    attention mechanism.

    __call__ is an identity pass — prefix injection is handled externally.

    Args:
        n_prefix:  number of prefix tokens per layer (default 32)
        n_heads:   number of attention heads (default 6)
        head_dim:  per-head dimension (default 64)
        n_layers:  number of transformer layers (default 6)
    """

    def __init__(
        self,
        n_prefix: int = 32,
        n_heads: int = 6,
        head_dim: int = 64,
        n_layers: int = 6,
    ) -> None:
        super().__init__()
        self.n_prefix = n_prefix
        self.n_heads  = n_heads
        self.head_dim = head_dim
        self.n_layers = n_layers
        self.d_kv = n_heads * head_dim   # = 384

        # Per-layer prefix K and V — init small normal
        # Shape: (n_layers, n_prefix, d_kv)
        self.prefix_key = mx.random.normal((n_layers, n_prefix, self.d_kv)) * 0.01
        self.prefix_val = mx.random.normal((n_layers, n_prefix, self.d_kv)) * 0.01

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.PROMPT

    @property
    def genome_config(self) -> dict:
        return {
            "n_prefix": self.n_prefix,
            "n_heads": self.n_heads,
            "head_dim": self.head_dim,
            "n_layers": self.n_layers,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Identity pass — prefix injection is applied via get_prefix() at attention.

        Args:
            x: any input array
        Returns:
            x unchanged
        """
        return x

    def get_prefix(self, layer_idx: int) -> tuple[mx.array, mx.array]:
        """
        Retrieve prefix K and V for a specific transformer layer.

        Args:
            layer_idx: layer index in [0, n_layers)
        Returns:
            (prefix_k, prefix_v) each of shape [n_prefix, d_kv]
        """
        return self.prefix_key[layer_idx], self.prefix_val[layer_idx]


def apply_prefix_to_attention(
    attn_output: mx.array,
    prefix_layer: PrefixTuningLayer,
    layer_idx: int,
    k: mx.array,
    v: mx.array,
) -> tuple[mx.array, mx.array]:
    """
    Prepend prefix KV vectors to attention K and V matrices.

    This is called inside the patched attention forward before computing
    attention scores. The prefix tokens attend to each other and to the
    input sequence.

    Args:
        attn_output: unused placeholder for API symmetry
        prefix_layer: the PrefixTuningLayer instance
        layer_idx:    current transformer layer index
        k: current key of shape [B, H, T, Dh] (before prefix)
        v: current val of shape [B, H, T, Dh]

    Returns:
        (k_extended, v_extended) each of shape [B, H, n_prefix+T, Dh]

    NOTE: This function shows how prefix injection works. Wire it into
    the attention forward by replacing the k, v variables after projection.
    """
    prefix_k, prefix_v = prefix_layer.get_prefix(layer_idx)
    B, H, T, Dh = k.shape
    n_prefix = prefix_layer.n_prefix

    # Reshape prefix: (n_prefix, H*Dh) → (1, H, n_prefix, Dh) → (B, H, n_prefix, Dh)
    pk = prefix_k.reshape(n_prefix, H, Dh).transpose(1, 0, 2)[None]
    pv = prefix_v.reshape(n_prefix, H, Dh).transpose(1, 0, 2)[None]
    pk = mx.broadcast_to(pk, (B, H, n_prefix, Dh))
    pv = mx.broadcast_to(pv, (B, H, n_prefix, Dh))

    k_ext = mx.concatenate([pk, k], axis=2)
    v_ext = mx.concatenate([pv, v], axis=2)
    return k_ext, v_ext
