"""
peft/activation/ia3.py — IA³ (Infused Adapter by Inhibiting and Amplifying Inner Activations)

Mathematical formulation:
  IA³ learns three tiny vectors l_k, l_v, l_ff that multiplicatively scale
  the keys, values, and FFN activations respectively:

    K' = K * l_k     (scale key projections)
    V' = V * l_v     (scale value projections)
    h' = h * l_ff    (scale intermediate FFN activations)

  All vectors are initialized to ones so the initial adapter output is
  identical to the frozen model. Only ~1152 parameters total for d_model=384
  (3 vectors of 384), making IA³ one of the most parameter-efficient PEFT methods.

Reference: Liu et al. (2022) "Few-Shot Parameter-Efficient Fine-Tuning is
Better and Cheaper than In-Context Learning"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class IA3Layer(DeltaOperator):
    """
    IA³ adapter: learns element-wise scaling vectors for K, V, and FFN activations.

    This operator is inserted at the FFN activation position. The caller is
    responsible for applying scale_k() and scale_v() at the attention layer.

    __call__(x) scales the FFN hidden state: returns x * l_ff.
    scale_k(k) and scale_v(v) are called by the patched attention forward.
    """

    def __init__(self, d_model: int = 384) -> None:
        super().__init__()
        self.d_model = d_model
        # Initialize all scaling vectors to ones — no-op at initialization
        self.l_k  = mx.ones((d_model,))
        self.l_v  = mx.ones((d_model,))
        self.l_ff = mx.ones((d_model,))

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.ACTIVATION

    @property
    def genome_config(self) -> dict:
        return {"vectors": ["l_k", "l_v", "l_ff"], "dim": self.d_model}

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Scale FFN intermediate activations.

        Args:
            x: hidden state of shape [B, T, D]
        Returns:
            x * l_ff, shape [B, T, D]
        """
        return x * self.l_ff

    def scale_k(self, k: mx.array) -> mx.array:
        """Scale key projections. k: [..., D] -> [..., D]."""
        return k * self.l_k

    def scale_v(self, v: mx.array) -> mx.array:
        """Scale value projections. v: [..., D] -> [..., D]."""
        return v * self.l_v
