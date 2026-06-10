"""
peft/alignment/dpo.py — DPO (Direct Preference Optimization)

Mathematical formulation:
  DPO eliminates the need for a separate reward model by directly optimizing
  a policy from preference data (chosen vs rejected response pairs):

    L_DPO = -E[log σ(β * (log(π/π_ref)(chosen) - log(π/π_ref)(rejected)))]

  Where:
    π         = current (trainable) policy
    π_ref     = frozen reference policy (base model)
    β         = temperature controlling deviation from reference (0.1 typical)
    σ         = sigmoid function

  The log-ratios are computed over complete sequences:
    log(π/π_ref)(y|x) = log π(y|x) - log π_ref(y|x)
                      = Σ_t log p(y_t|y_{<t}, x) - log p_ref(y_t|y_{<t}, x)

  Callers pass pre-computed log probabilities for chosen and rejected sequences
  under both the policy and reference model.

Reference: Rafailov et al. (2023) "Direct Preference Optimization: Your
Language Model is Secretly a Reward Model"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn


class DPOTrainer:
    """
    Direct Preference Optimization loss computation.

    Not a DeltaOperator — this is a training objective wrapper.

    Args:
        beta: temperature for KL penalty (default 0.1)

    Usage:
        trainer = DPOTrainer(beta=0.1)
        loss = trainer.compute_loss(
            policy_chosen_logps, policy_rejected_logps,
            ref_chosen_logps, ref_rejected_logps
        )
    """

    def __init__(self, beta: float = 0.1) -> None:
        self.beta = beta

    def compute_loss(
        self,
        policy_chosen_logps: mx.array,
        policy_rejected_logps: mx.array,
        ref_chosen_logps: mx.array,
        ref_rejected_logps: mx.array,
        beta: float | None = None,
    ) -> mx.array:
        """
        Compute DPO loss.

        Args:
            policy_chosen_logps:   log P_policy(chosen)   [B]
            policy_rejected_logps: log P_policy(rejected)  [B]
            ref_chosen_logps:      log P_ref(chosen)       [B]
            ref_rejected_logps:    log P_ref(rejected)     [B]
            beta:                  override instance beta if provided
        Returns:
            scalar DPO loss
        """
        b = beta if beta is not None else self.beta

        # Policy log-ratio: log π(chosen) - log π(rejected)
        pi_logratios  = policy_chosen_logps  - policy_rejected_logps
        # Reference log-ratio: log π_ref(chosen) - log π_ref(rejected)
        ref_logratios = ref_chosen_logps - ref_rejected_logps

        # DPO objective: -log σ(β * (π_ratio - ref_ratio))
        # Using mx.log(mx.sigmoid(z)) = -softplus(-z) for stability
        logits = b * (pi_logratios - ref_logratios)
        losses = -mx.log(mx.sigmoid(logits))

        return mx.mean(losses)
