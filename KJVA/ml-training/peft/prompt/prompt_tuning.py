"""
peft/prompt/prompt_tuning.py — Prompt Tuning

Mathematical formulation:
  Prompt Tuning prepends n_tokens trainable "soft" embedding vectors to the
  input token sequence. The model weights are frozen; only the prompt
  embeddings are trained:

    Input:  [x_1, x_2, ..., x_T]           shape [B, T, D]
    Output: [p_1, ..., p_n, x_1, ..., x_T]  shape [B, n+T, D]

  Where p_i ∈ ℝ^D are trainable prompt tokens, initialized with small random
  normal values. The model learns to condition its behavior on these soft
  tokens without modifying any weights.

  Parameters: n_tokens * d_model = 20 * 384 = 7,680 (at default settings).
  Competitive with full fine-tuning at large model scales (11B+), though
  less effective at smaller scales.

Reference: Lester et al. (2021) "The Power of Scale for Parameter-Efficient
Prompt Tuning"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class PromptTuningLayer(DeltaOperator):
    """
    Soft prompt tuning: prepends n_tokens trainable embeddings to the input.

    __call__ prepends the prompt embeddings to the input sequence.
    The output has sequence length n_tokens + T.

    Attention masks must be updated by the caller to cover the extra prompt
    tokens (typically by extending the causal mask).

    Args:
        n_tokens: number of soft prompt tokens to prepend (default 20)
        d_model:  embedding dimension (default 384)
    """

    def __init__(
        self,
        n_tokens: int = 20,
        d_model: int = 384,
    ) -> None:
        super().__init__()
        self.n_tokens = n_tokens
        self.d_model  = d_model

        # Trainable soft prompt embeddings — init small normal
        self.prompt_embeddings = mx.random.normal((n_tokens, d_model)) * 0.01

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.PROMPT

    @property
    def genome_config(self) -> dict:
        return {
            "n_tokens": self.n_tokens,
            "d_model": self.d_model,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Prepend prompt embeddings to the input sequence.

        Args:
            x: input embeddings of shape [B, T, D]
        Returns:
            concatenated tensor of shape [B, n_tokens + T, D]
        """
        B = x.shape[0]
        # Broadcast prompt embeddings to batch dimension
        # prompt_embeddings: (n_tokens, D) → (1, n_tokens, D) → (B, n_tokens, D)
        prompts = mx.broadcast_to(
            self.prompt_embeddings[None],
            (B, self.n_tokens, self.d_model),
        )
        return mx.concatenate([prompts, x], axis=1)
