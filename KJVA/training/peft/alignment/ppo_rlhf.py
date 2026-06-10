"""
peft/alignment/ppo_rlhf.py — PPO-RLHF (Proximal Policy Optimization for RLHF)

Mathematical formulation:
  PPO-RLHF uses the InstructGPT training recipe:
  1. Pre-train a reward model R(x, y) on human preference data
  2. Fine-tune the policy π_θ via PPO to maximize R while staying close to π_ref

  The PPO policy loss (clipped surrogate objective):

    r_t(θ) = π_θ(a_t|s_t) / π_θ_old(a_t|s_t)   (probability ratio)
    L_CLIP  = -E[min(r_t * A_t, clip(r_t, 1-ε, 1+ε) * A_t)]

  Where A_t is the advantage estimate (reward - value baseline).

  The KL penalty from the reference model is added:
    L_KL = β * KL(π_θ || π_ref)

  Value loss (critic network):
    L_V = E[(V(s_t) - R_t)²]   (MSE between value prediction and actual return)

  Total loss: L_CLIP + c1 * L_V - c2 * entropy_bonus

Reference: Schulman et al. (2017) "Proximal Policy Optimization Algorithms";
           Ouyang et al. (2022) "Training language models to follow instructions
           with human feedback" (InstructGPT)
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn


class PPORLHFTrainer:
    """
    PPO-RLHF training objective computation.

    Not a DeltaOperator — this is a training objective wrapper.

    Provides separate policy and value loss computations to be combined
    by the caller's training loop.

    Args:
        clip_eps:    PPO clipping epsilon (default 0.2)
        value_coeff: coefficient for value loss (default 0.5)
        entropy_coeff: entropy bonus coefficient (default 0.01)
        beta:        KL penalty coefficient vs reference model (default 0.1)

    Usage:
        trainer = PPORLHFTrainer()
        pol_loss = trainer.compute_policy_loss(log_probs, old_log_probs, advantages)
        val_loss = trainer.compute_value_loss(values, returns)
        loss = pol_loss + trainer.value_coeff * val_loss
    """

    def __init__(
        self,
        clip_eps: float = 0.2,
        value_coeff: float = 0.5,
        entropy_coeff: float = 0.01,
        beta: float = 0.1,
    ) -> None:
        self.clip_eps      = clip_eps
        self.value_coeff   = value_coeff
        self.entropy_coeff = entropy_coeff
        self.beta          = beta

    def compute_policy_loss(
        self,
        log_probs: mx.array,
        old_log_probs: mx.array,
        rewards: mx.array,
        clip_eps: float | None = None,
    ) -> mx.array:
        """
        Compute PPO clipped policy loss.

        Args:
            log_probs:     log π_θ(a|s) under current policy  [B, T] or [B]
            old_log_probs: log π_θ_old(a|s) from rollout      [B, T] or [B]
            rewards:       advantage estimates A_t             [B, T] or [B]
            clip_eps:      override instance clip_eps if provided
        Returns:
            scalar policy loss (negative — we maximize, so loss is negated)
        """
        eps = clip_eps if clip_eps is not None else self.clip_eps

        # Probability ratio: r = exp(log π - log π_old)
        ratio = mx.exp(log_probs - old_log_probs)   # [B, ...]

        # Clipped surrogate loss
        r_clipped  = mx.clip(ratio, 1.0 - eps, 1.0 + eps)
        surr1      = ratio     * rewards
        surr2      = r_clipped * rewards

        # Take the minimum (pessimistic bound) and negate (we maximize)
        policy_loss = -mx.mean(mx.minimum(surr1, surr2))
        return policy_loss

    def compute_value_loss(
        self,
        values: mx.array,
        returns: mx.array,
    ) -> mx.array:
        """
        Compute critic (value) MSE loss.

        Args:
            values:  value function predictions V(s_t)  [B, T] or [B]
            returns: Monte Carlo or GAE returns R_t     [B, T] or [B]
        Returns:
            scalar value loss
        """
        return mx.mean((values - returns) ** 2)

    def compute_kl_penalty(
        self,
        policy_logps: mx.array,
        ref_logps: mx.array,
    ) -> mx.array:
        """
        Compute KL divergence penalty from reference model.

        Approximation: KL ≈ log π_θ - log π_ref (per token, summed)

        Args:
            policy_logps: log probabilities under current policy  [B]
            ref_logps:    log probabilities under reference model [B]
        Returns:
            scalar KL penalty
        """
        return self.beta * mx.mean(policy_logps - ref_logps)
