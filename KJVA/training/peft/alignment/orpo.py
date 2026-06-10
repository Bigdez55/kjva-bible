"""
peft/alignment/orpo.py — ORPO (Odds Ratio Preference Optimization)

Mathematical formulation:
  ORPO combines supervised fine-tuning and preference alignment in a single
  objective, eliminating the need for a reference model:

    L_ORPO = L_SFT + λ * L_OR

  Where L_SFT is the standard language modeling loss on chosen responses, and
  L_OR is an odds-ratio penalty that contrasts chosen vs rejected:

    odds(y|x) = P(y|x) / (1 - P(y|x))   (in log space: log_p - log(1 - exp(log_p)))
    L_OR = -E[log σ(log(odds_chosen / odds_rejected))]

  The odds ratio is a natural measure from logistic regression theory:
  it captures how much more likely a response is compared to "not generating it".
  The ratio odds_chosen/odds_rejected measures relative preference strength.

  Key advantage: no reference model needed, saving memory and simplifying
  the training pipeline. ORPO trains from (chosen, rejected) pairs in one pass.

Reference: Hong et al. (2024) "ORPO: Monolithic Preference Optimization without
Reference Model"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn


class ORPOTrainer:
    """
    ORPO loss: combined SFT + odds-ratio preference optimization.

    No reference model required — the preference signal comes from the
    odds ratio between chosen and rejected log-probabilities.

    Args:
        lambda_orpo: weight for odds-ratio loss component (default 0.1)

    Usage:
        trainer = ORPOTrainer(lambda_orpo=0.1)
        loss = trainer.compute_loss(
            policy_chosen_logps, policy_rejected_logps, sft_logps
        )
    """

    def __init__(self, lambda_orpo: float = 0.1) -> None:
        self.lambda_orpo = lambda_orpo

    def compute_loss(
        self,
        policy_chosen_logps: mx.array,
        policy_rejected_logps: mx.array,
        sft_logps: mx.array,
        lambda_orpo: float | None = None,
    ) -> mx.array:
        """
        Compute ORPO combined loss.

        Args:
            policy_chosen_logps:   log P_policy(chosen)   [B]
            policy_rejected_logps: log P_policy(rejected)  [B]
            sft_logps:             log P_policy(chosen) for SFT objective [B]
                                   (same as policy_chosen_logps in most settings)
            lambda_orpo:           override instance lambda if provided
        Returns:
            scalar ORPO loss
        """
        lam = lambda_orpo if lambda_orpo is not None else self.lambda_orpo

        # SFT objective: maximize likelihood of chosen responses
        sft_loss = -mx.mean(sft_logps)

        # Odds ratio objective
        # Clamp log_p to avoid log(0) or log(1) instabilities
        eps = 1e-7
        log_p_chosen   = mx.clip(policy_chosen_logps,   -1e6, mx.log(mx.array(1.0 - eps)))
        log_p_rejected = mx.clip(policy_rejected_logps, -1e6, mx.log(mx.array(1.0 - eps)))

        # log odds = log(p / (1-p)) = log_p - log(1 - exp(log_p))
        # Numerically: log1mexp(log_p) = log(1 - exp(log_p)) for log_p < 0
        def log_odds(log_p: mx.array) -> mx.array:
            # log(1 - exp(log_p)) ≈ log(-expm1(log_p)) for log_p < 0
            one_minus_p = 1.0 - mx.exp(log_p)
            one_minus_p = mx.clip(one_minus_p, eps, 1.0)
            return log_p - mx.log(one_minus_p)

        log_odds_chosen   = log_odds(log_p_chosen)
        log_odds_rejected = log_odds(log_p_rejected)

        # Log odds ratio: log(odds_chosen / odds_rejected)
        log_odds_ratio = log_odds_chosen - log_odds_rejected

        # Odds-ratio loss: -log σ(log_odds_ratio)
        or_loss = -mx.mean(mx.log(mx.sigmoid(log_odds_ratio)))

        return sft_loss + lam * or_loss
