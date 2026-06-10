"""
peft/alignment/grpo.py — GRPO (Group Relative Policy Optimization)

Mathematical formulation:
  GRPO normalizes rewards within a group (multiple completions for the same
  prompt) to compute relative advantages, eliminating the need for a reference
  model or value function:

    For a group G of completions {y_1,...,y_G} for prompt x:
      advantages_i = (r_i - mean(r)) / (std(r) + ε)

  The policy is then updated using a PPO-style clipped objective with these
  group-relative advantages:

    L_GRPO = -E[min(r_t * A_t, clip(r_t, 1-ε, 1+ε) * A_t)] + β * KL

  Where r_t = π_θ / π_ref is the probability ratio.

  GRPO avoids the critic (value function) network entirely, reducing memory
  and compute by ~half vs PPO. It is particularly effective for reasoning
  tasks where multiple solutions can be sampled and compared.

  Key usage in DeepSeek-R1: group size G=8-16 completions per prompt.

Reference: Shao et al. (2024) "DeepSeekMath: Pushing the Limits of
Mathematical Reasoning in Open Language Models"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn


class GRPOTrainer:
    """
    Group Relative Policy Optimization loss computation.

    Not a DeltaOperator — this is a training objective wrapper.

    Reward normalization within a group eliminates the need for:
    - A reference model (advantages are relative within group)
    - A value function / critic network

    Args:
        clip_eps: PPO clipping epsilon (default 0.2)
        beta:     entropy/KL bonus coefficient (default 0.04)

    Usage:
        trainer = GRPOTrainer()
        # group_rewards: [B, G] rewards for B prompts × G completions each
        # log_probs:     [B, G] policy log-probs for each completion
        loss = trainer.compute_loss(log_probs, group_rewards)
    """

    def __init__(
        self,
        clip_eps: float = 0.2,
        beta: float = 0.04,
    ) -> None:
        self.clip_eps = clip_eps
        self.beta     = beta

    def compute_loss(
        self,
        log_probs: mx.array,
        group_rewards: mx.array,
        old_log_probs: mx.array | None = None,
        clip_eps: float | None = None,
        beta: float | None = None,
    ) -> mx.array:
        """
        Compute GRPO loss with group-normalized advantages.

        Args:
            log_probs:     log π_θ(y_i | x) for each group completion [B, G]
            group_rewards: raw rewards for each completion             [B, G]
            old_log_probs: log probs from rollout policy               [B, G]
                           (if None, assumes on-policy: ratio = 1)
            clip_eps:      override instance clip_eps
            beta:          override instance beta (entropy weight)
        Returns:
            scalar GRPO loss
        """
        eps  = clip_eps if clip_eps is not None else self.clip_eps
        b    = beta     if beta     is not None else self.beta

        # Group-relative advantage normalization
        # group_rewards: [B, G] — normalize within each prompt's group
        reward_mean = group_rewards.mean(axis=-1, keepdims=True)    # [B, 1]
        reward_std  = mx.sqrt(
            ((group_rewards - reward_mean) ** 2).mean(axis=-1, keepdims=True) + 1e-8
        )                                                            # [B, 1]
        advantages = (group_rewards - reward_mean) / reward_std     # [B, G]

        # Probability ratio
        if old_log_probs is not None:
            ratio = mx.exp(log_probs - old_log_probs)
        else:
            # On-policy: ratio = 1 everywhere
            ratio = mx.ones_like(log_probs)

        # PPO-style clipped surrogate
        r_clipped   = mx.clip(ratio, 1.0 - eps, 1.0 + eps)
        surr1       = ratio     * advantages
        surr2       = r_clipped * advantages
        policy_loss = -mx.mean(mx.minimum(surr1, surr2))

        # Entropy bonus (approximate): -β * log π (encourages exploration)
        entropy_bonus = -b * mx.mean(log_probs)

        return policy_loss + entropy_bonus
