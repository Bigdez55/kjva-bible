"""
peft/prompt/p_tuning.py — P-Tuning v2

Mathematical formulation:
  P-Tuning v2 extends prompt tuning by:
  1. Using a reparameterization network (MLP encoder) to generate soft prompts
     instead of directly learning them — improves optimization landscape
  2. Applying prompts at EVERY transformer layer (like Prefix Tuning), not
     just the input embedding

  The MLP encoder:
    encoded = W_out * GELU(W_in * prompt_embeddings + b_in) + b_out
    shape: (n_tokens, d_model) → (n_tokens, d_model)

  The encoded prompts are prepended to the input sequence at each call.

  Unlike Prefix Tuning, P-Tuning v2 uses the same encoded prompts for all
  layers (though the prompts are generated through the MLP to smooth the
  optimization). This gives better performance on NLU tasks vs Prefix Tuning.

Reference: Liu et al. (2022) "P-Tuning: GPT Understands, Too" and
"P-Tuning v2: Prompt Tuning Can Be Comparable to Fine-tuning Universally
Across Scales and Tasks"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from peft.base import DeltaFamily, DeltaOperator


class PTuningV2(DeltaOperator):
    """
    P-Tuning v2: MLP-reparameterized soft prompts prepended to input.

    An MLP encoder maps raw prompt embeddings through a hidden layer,
    allowing the optimizer to work in a smoother space than directly
    learning token embeddings.

    __call__ prepends the MLP-encoded prompts to x, returning [B, n+T, D].

    Args:
        n_tokens:       number of soft prompt tokens (default 20)
        d_model:        model embedding dimension (default 384)
        encoder_hidden: MLP hidden dimension (default 512)
    """

    def __init__(
        self,
        n_tokens: int = 20,
        d_model: int = 384,
        encoder_hidden: int = 512,
    ) -> None:
        super().__init__()
        self.n_tokens = n_tokens
        self.d_model  = d_model
        self.encoder_hidden = encoder_hidden

        # MLP prompt encoder (approximates LSTM reparameterization from P-Tuning v1)
        self.lstm_in  = nn.Linear(d_model, encoder_hidden)
        self.lstm_out = nn.Linear(encoder_hidden, d_model)

        # Raw prompt embeddings — encoded through MLP before use
        self.prompt_embeddings = mx.random.normal((n_tokens, d_model)) * 0.01

    @property
    def family(self) -> DeltaFamily:
        return DeltaFamily.PROMPT

    @property
    def genome_config(self) -> dict:
        return {
            "n_tokens": self.n_tokens,
            "d_model": self.d_model,
            "encoder_hidden": self.encoder_hidden,
        }

    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """
        Encode and prepend soft prompts to input sequence.

        Args:
            x: input embeddings of shape [B, T, D]
        Returns:
            extended sequence of shape [B, n_tokens + T, D]
        """
        # Encode raw prompts through MLP: (n_tokens, D)
        encoded = self.lstm_out(nn.gelu(self.lstm_in(self.prompt_embeddings)))

        B = x.shape[0]
        # Broadcast to batch: (1, n_tokens, D) → (B, n_tokens, D)
        prompts = mx.broadcast_to(
            encoded[None],
            (B, self.n_tokens, self.d_model),
        )
        return mx.concatenate([prompts, x], axis=1)
