"""
peft/alignment/ipo.py — IPO (Identity Preference Optimization)

Mathematical formulation:
  IPO addresses a theoretical limitation of DPO: when policy collapse occurs,
  DPO's log-sigmoid loss saturates and stops providing useful gradients.

  IPO uses a squared loss instead of log-sigmoid, which never saturates:

    L_IPO = E[(log(π/π_ref)(chosen) - log(π/π_ref)(rejected) - 1/(2β))²]

  The 1/(2β) target arises from the optimal policy solution: the correct
  policy achieves a log-ratio difference of 1/(2β) between chosen and rejected.
  The squared loss penalizes deviations from this value in both directions.

  Properties vs DPO:
  - Never saturates (squared loss has no flat regions)
  - Directly regresses to the optimal policy solution
  - More stable training but may need different β tuning

Reference: Azar et al. (2023) "A General Theoretical Paradigm to Understand
Learning from Human Feedback"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn


class IPOTrainer:
    """
    Identity Preference Optimization loss computation.

    Not a DeltaOperator — this is a training objective wrapper.

    Args:
        beta: KL regularization temperature (default 0.1)

    Usage:
        trainer = IPOTrainer(beta=0.1)
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
        Compute IPO loss (squared deviation from optimal log-ratio target).

        Args:
            policy_chosen_logps:   log P_policy(chosen)   [B]
            policy_rejected_logps: log P_policy(rejected)  [B]
            ref_chosen_logps:      log P_ref(chosen)       [B]
            ref_rejected_logps:    log P_ref(rejected)     [B]
            beta:                  override instance beta if provided
        Returns:
            scalar IPO loss
        """
        b = beta if beta is not None else self.beta

        # Combined log-ratio difference: (π_chosen - π_rejected) - (ref_chosen - ref_rejected)
        ratios = (
            (policy_chosen_logps - policy_rejected_logps)
            - (ref_chosen_logps - ref_rejected_logps)
        )

        # Squared deviation from optimal target 1/(2β)
        target = 1.0 / (2.0 * b)
        losses = (ratios - target) ** 2

        return mx.mean(losses)
