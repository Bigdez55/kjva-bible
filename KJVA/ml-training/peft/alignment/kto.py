"""
peft/alignment/kto.py — KTO (Kahneman-Tversky Optimization)

Mathematical formulation:
  KTO is inspired by Kahneman-Tversky prospect theory: humans are loss-averse,
  weighting losses ~2× more than equivalent gains. KTO incorporates this
  asymmetry into the reward signal.

  For each sample, we have a (response, desirability) pair:
    desirable=1.0   → response that humans prefer (good output)
    desirable=0.0   → response that humans disprefer (bad output)

  The KTO objective:

    For desirable outputs:
      reward = β * (log π(y|x) - log π_ref(y|x))
      L_KTO = λ_d * E[1 - σ(reward - z_ref)]

    For undesirable outputs:
      L_KTO += λ_u * E[1 - σ(z_ref - reward)]

  Where z_ref is a KL reference baseline:
    z_ref = β * E[KL(π || π_ref)]  ≈ β * (log π(y|x) - log π_ref(y|x)) over all y

  KTO works with unpaired data (does not require chosen/rejected pairs),
  making it useful when only binary quality labels are available.

Reference: Ethayarajh et al. (2023) "KTO: Model Alignment as Prospect
Theoretic Optimization"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn


class KTOTrainer:
    """
    Kahneman-Tversky Optimization loss computation.

    Not a DeltaOperator — this is a training objective wrapper.
    Works with unpaired (response, desirability) data — no chosen/rejected
    pairs required.

    Args:
        beta:      KL regularization temperature (default 0.1)
        lambda_d:  weight for desirable examples (default 1.0)
        lambda_u:  weight for undesirable examples (default 1.0,
                   should be ~2× lambda_d for KT loss aversion)

    Usage:
        trainer = KTOTrainer(beta=0.1, lambda_d=1.0, lambda_u=1.0)
        loss = trainer.compute_loss(policy_logps, ref_logps, desirable)
    """

    def __init__(
        self,
        beta: float = 0.1,
        lambda_d: float = 1.0,
        lambda_u: float = 1.0,
    ) -> None:
        self.beta     = beta
        self.lambda_d = lambda_d
        self.lambda_u = lambda_u

    def compute_loss(
        self,
        policy_logps: mx.array,
        ref_logps: mx.array,
        desirable: mx.array,
        beta: float | None = None,
        lambda_d: float | None = None,
        lambda_u: float | None = None,
    ) -> mx.array:
        """
        Compute KTO loss.

        Args:
            policy_logps: log P_policy(y|x)   [B]
            ref_logps:    log P_ref(y|x)       [B]
            desirable:    binary indicator [B] (1.0 = desired, 0.0 = undesired)
            beta, lambda_d, lambda_u: override instance values if provided
        Returns:
            scalar KTO loss
        """
        b  = beta     if beta     is not None else self.beta
        ld = lambda_d if lambda_d is not None else self.lambda_d
        lu = lambda_u if lambda_u is not None else self.lambda_u

        # Per-sample log-ratio (implicit reward)
        log_ratio = policy_logps - ref_logps   # [B]

        # KL baseline: mean log-ratio over entire batch approximates z_ref
        z_ref = b * mx.mean(log_ratio)

        # Per-sample reward (scaled log-ratio)
        rewards = b * log_ratio   # [B]

        # Desirability mask
        d_mask = desirable                    # [B]
        u_mask = (1.0 - desirable)            # [B]

        # KTO loss: desirable samples want reward > z_ref; undesirable < z_ref
        # Prospect theory: loss-aversion — undesirable losses weighted by lambda_u
        desirable_loss   = ld * d_mask * (1.0 - mx.sigmoid(rewards - z_ref))
        undesirable_loss = lu * u_mask * (1.0 - mx.sigmoid(z_ref - rewards))

        total_loss = desirable_loss + undesirable_loss
        return mx.mean(total_loss)
