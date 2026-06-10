"""
peft/hybrid/xlora.py — X-LoRA (Mixture of LoRA Experts)

Mathematical formulation:
  X-LoRA maintains n_experts independent LoRA adapters and dynamically
  routes between them using hidden state representations:

    logits = W_router * x            ∈ ℝ^(B, T, n_experts)
    weights = softmax(logits / τ)    (soft routing with temperature τ)
    delta = Σ_i weights[..., i:i+1] * LoRA_i(x)

  The router is conditioned on the hidden state x, allowing different
  specializations to be activated for different input positions/contexts.
  This enables one set of adapters to handle diverse tasks via gating,
  rather than training separate adapters per task.

  Total params: n_experts * r * (d_in + d_out) + d_in * n_experts
  For n=4, r=8, d=384: 4 * 8 * 768 + 384 * 4 = ~26K params.

Reference: Buehler (2024) "X-LoRA: Mixture of Low-Rank Adapter Experts,
a Flexible Framework for Large Language Models with Applications in Protein
Mechanics and Design"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator
from peft.low_rank.lora import LoRALinear


class XLoRALayer(DeltaOperator):
    """
    X-LoRA: mixture of LoRA experts with learned routing.

    n_experts LoRA adapters are maintained. A router network computes
    per-position softmax weights from the hidden state, and the final
    delta is a weighted sum of all expert outputs.

    Returns the weighted expert delta — caller adds to frozen linear output.

    Args:
        in_features:  input dimension
        out_features: output dimension
        n_experts:    number of LoRA expert adapters (default 4)
        rank:         rank for each LoRA expert (default 8)
        alpha:        LoRA scaling (default 16.0)
        temperature:  softmax temperature for routing (1.0 = standard)
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        n_experts: int = 4,
        rank: int = 8,
        alpha: float = 16.0,
        temperature: float = 1.0,
    ) -> None:
        super().__init__()
        self.in_features  = in_features
        self.out_features = out_features
        self.n_experts   = n_experts
        self.rank        = rank
        self.alpha       = alpha
        self.temperature = temperature

        # n_experts independent LoRA adapters
        # MLX stores lists of modules correctly via attribute assignment
        self.experts = [
            LoRALinear(in_features, out_features, rank=rank, alpha=alpha)
            for _ in range(n_experts)
        ]

        # Router: maps hidden state to expert weights
        self.router = nn.Linear(in_features, n_experts, bias=False)

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.ROUTING

    @property
    def genome_config(self) -> dict:
        return {
            "n_experts": self.n_experts,
            "rank": self.rank,
            "alpha": self.alpha,
            "temperature": self.temperature,
            "in_features": self.in_features,
            "out_features": self.out_features,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Route x through mixture of LoRA experts.

        Args:
            x: hidden state [B, T, in_features]
        Returns:
            weighted expert delta [B, T, out_features]
        """
        # Router logits: [B, T, n_experts]
        logits = self.router(x)
        # Softmax routing weights
        weights = mx.softmax(logits / self.temperature, axis=-1)  # [B, T, n_experts]

        # Weighted sum of expert deltas
        # Each expert_i(x): [B, T, out_features]
        # weights[..., i:i+1]: [B, T, 1] — broadcast over out_features
        delta = sum(
            weights[..., i : i + 1] * expert(x)
            for i, expert in enumerate(self.experts)
        )
        return delta
