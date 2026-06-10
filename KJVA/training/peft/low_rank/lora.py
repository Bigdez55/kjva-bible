"""
peft/low_rank/lora.py — LoRA (Low-Rank Adaptation)

Mathematical formulation:
  LoRA decomposes the weight update ΔW into two low-rank matrices:

    ΔW = B @ A     where A ∈ ℝ^(r×d_in), B ∈ ℝ^(d_out×r)

  The adapted output is:

    y = W_frozen @ x + (B @ A) @ x * (alpha / r)

  A is initialized with Kaiming uniform, B with zeros — so at initialization
  ΔW = 0 and the adapter is a no-op. The scaling factor alpha/r controls the
  magnitude of the update.

  Parameters: r*(d_in + d_out), vs d_in*d_out for full fine-tuning.
  For d=384, r=8: 6,144 params vs 147,456 (96× compression).

Reference: Hu et al. (2022) "LoRA: Low-Rank Adaptation of Large Language Models"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator, kaiming_uniform


class LoRALinear(DeltaOperator):
    """
    LoRA adapter producing a low-rank weight delta.

    Returns the DELTA output only — the caller adds this to the frozen
    linear layer's output:

        full_output = frozen_linear(x) + lora(x)

    Args:
        in_features:  input dimension
        out_features: output dimension
        rank:         LoRA rank r (8 by default)
        alpha:        LoRA scaling alpha (16.0 by default)
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
        self.scaling = alpha / rank

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
            "in_features": self.in_features,
            "out_features": self.out_features,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Compute LoRA delta.

        x: [..., in_features]
        returns: [..., out_features]  (the delta, not full output)
        """
        h = x
        if self.dropout is not None:
            h = self.dropout(h)
        # h @ A.T: [..., rank];  @ B.T: [..., out_features]
        return h @ self.A.T @ self.B.T * self.scaling


def replace_linear_with_lora(
    model,
    target_modules: list[str],
    rank: int = 8,
    alpha: float = 16.0,
) -> object:
    """
    Replace named Linear projections in a TokenlessLM with LoRALinear adapters.

    The frozen base weight is preserved inside an nn.Linear; a LoRALinear is
    stored alongside it. The caller is responsible for combining outputs.

    Args:
        model:          TokenlessLM instance (already frozen)
        target_modules: list of projection names, e.g. ["q", "k", "v", "o"]
        rank:           LoRA rank
        alpha:          LoRA alpha

    Returns:
        dict mapping "block_{i}.{proj}" to LoRALinear instances
    """
    adapters: dict[str, LoRALinear] = {}
    for i, block in enumerate(model.blocks):
        attn = block.attn
        for proj_name in target_modules:
            if not hasattr(attn, proj_name):
                continue
            linear = getattr(attn, proj_name)
            in_f  = linear.weight.shape[1]
            out_f = linear.weight.shape[0]
            lora  = LoRALinear(in_f, out_f, rank=rank, alpha=alpha)
            key   = f"block_{i}.attn.{proj_name}"
            adapters[key] = lora
    return adapters
