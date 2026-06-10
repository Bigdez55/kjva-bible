"""
peft/alignment/sft.py — SFT (Supervised Fine-Tuning) Trainer

Mathematical formulation:
  SFT minimizes the standard causal language modeling loss (cross-entropy)
  over supervised (input, output) pairs:

    L_SFT = -E[log p_θ(y_t | y_{<t}, x)]

  In practice: shift labels by one position so each token predicts the next.
  Tokens at ignore_index positions (e.g., padding, prompt) are excluded
  from the loss.

    loss = mean(CE(logits[:, :-1], labels[:, 1:]) at non-ignored positions)

  SFT is the foundational alignment step before RLHF/DPO. It teaches the
  model to follow instructions by maximizing the likelihood of gold-standard
  responses.
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn


class SFTTrainer:
    """
    Supervised Fine-Tuning loss computation.

    Not a DeltaOperator — this is a training objective wrapper.

    Usage:
        trainer = SFTTrainer()
        loss = trainer.compute_loss(logits, labels)
        # loss.backward() / use with MLX value_and_grad
    """

    def compute_loss(
        self,
        logits: mx.array,
        labels: mx.array,
        ignore_index: int = -100,
    ) -> mx.array:
        """
        Compute shifted cross-entropy loss for causal language modeling.

        Args:
            logits:       model output [B, T, V]
            labels:       token ids [B, T] (positions with ignore_index are masked)
            ignore_index: label value to ignore in loss (typically padding/prompt)
        Returns:
            scalar mean loss
        """
        # Shift: predict token t+1 from position t
        # logits: [B, T-1, V], labels: [B, T-1]
        shift_logits = logits[:, :-1, :]   # [B, T-1, V]
        shift_labels = labels[:, 1:]       # [B, T-1]

        # Mask ignored positions
        mask = (shift_labels != ignore_index).astype(mx.float32)

        # Cross-entropy: -log_softmax(logit)[label]
        # MLX nn.losses.cross_entropy expects logits and targets
        # Use log-sum-exp formulation for numerical stability
        log_probs = shift_logits - mx.logsumexp(shift_logits, axis=-1, keepdims=True)  # [B, T-1, V]

        # Gather log-probs at label positions
        # Replace ignore_index labels with 0 for safe indexing
        safe_labels = mx.where(shift_labels == ignore_index, mx.zeros_like(shift_labels), shift_labels)
        B, T_minus1 = safe_labels.shape
        V = shift_logits.shape[-1]

        # Flatten for gather
        log_probs_flat   = log_probs.reshape(-1, V)      # [B*(T-1), V]
        safe_labels_flat = safe_labels.reshape(-1)       # [B*(T-1),]

        # Index: gather log_prob at the correct vocab position
        token_log_probs = log_probs_flat[mx.arange(B * T_minus1), safe_labels_flat]
        token_log_probs = token_log_probs.reshape(B, T_minus1)   # [B, T-1]

        # Apply mask and compute mean (over non-ignored tokens)
        masked_loss = -token_log_probs * mask
        n_valid = mx.maximum(mx.sum(mask), mx.ones(()))
        return mx.sum(masked_loss) / n_valid
