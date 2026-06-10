"""
peft/alignment/distillation.py — Knowledge Distillation Trainers

Two distillation objectives, each a training-objective wrapper (NOT a
DeltaOperator), mirroring the SFTTrainer interface in peft/alignment/sft.py
(plain `compute_loss(...) -> mx.array` consumed by `nn.value_and_grad`).

------------------------------------------------------------------------------
TEACHER CONTRACT
------------------------------------------------------------------------------
Both trainers consume the TEACHER as a *constant* (non-differentiated) input:

  - Logit distillation:    `teacher_logits`  [B, T, V]
  - Sequence distillation: `teacher_logits`  [B, T, V]  (argmax -> tokens), OR
                           `teacher_tokens`  [B, T]      (precomputed)

The teacher tensor MUST be produced OUTSIDE the `nn.value_and_grad` closure —
either precomputed offline or via a frozen-teacher forward whose output is
`mx.stop_gradient`-ed / simply passed in as data — so the teacher is never
differentiated. Only the STUDENT logits (`logits`) carry gradient.

------------------------------------------------------------------------------
1. LOGIT DISTILLATION  (DistillationLogitTrainer / mode="logit")
------------------------------------------------------------------------------
Canonical Hinton et al. (2015) soft-target distillation — TEACHER-WEIGHTED
forward KL, i.e. cross-entropy of the student against the teacher's softened
distribution:

  p_T = softmax(z_T / T)          (teacher soft targets, temperature T)
  p_S = softmax(z_S / T)          (student soft predictions, temperature T)

  L_soft = T^2 * KL(p_T || p_S)
         = T^2 * Σ_v p_T * (log p_T - log p_S)          (per position, summed over V)

  The T^2 factor restores the gradient magnitude scaled down by 1/T^2 from
  softening, so soft- and hard-label gradients stay commensurate.

Optionally blended with the hard-label cross-entropy (shifted next-token CE,
exactly the SFT objective):

  L = alpha * L_soft + (1 - alpha) * L_hard

Direction note: this is the TEACHER-WEIGHTED (mode-covering) KL that makes the
student mimic the teacher — NOT the student-weighted reverse KL.

------------------------------------------------------------------------------
2. SEQUENCE DISTILLATION  (DistillationSequenceTrainer / mode="sequence")
------------------------------------------------------------------------------
Kim & Rush (2016) sequence-level distillation: teacher-forced cross-entropy
against the teacher's (greedy/argmax-decoded) hard token sequence. The student
is trained to reproduce the teacher's preferred next token at every position,
reusing the exact shifted-CE / masking machinery of SFT but with TEACHER tokens
as the labels instead of gold labels.

  teacher_tokens = argmax(teacher_logits, axis=-1)      (if not precomputed)
  L_seq = mean( CE(student_logits[:, :-1], teacher_tokens[:, 1:]) ) over non-ignored

Reference:
  Hinton, Vinyals, Dean (2015) "Distilling the Knowledge in a Neural Network"
  Kim & Rush (2016) "Sequence-Level Knowledge Distillation"
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn


def _shifted_hard_ce(
    logits: mx.array,
    labels: mx.array,
    ignore_index: int = -100,
) -> mx.array:
    """
    Shifted next-token cross-entropy (the SFT objective), used both for the
    hard-label term of logit distillation and as the sequence-distillation
    loss (with teacher tokens as labels). Mirrors sft.SFTTrainer.compute_loss.
    """
    shift_logits = logits[:, :-1, :]   # [B, T-1, V]
    # Cast labels to SIGNED int32 before any ignore_index (-100) comparison. Byte-LM
    # corpus tokens are naturally UNSIGNED (ids 0..258, so uint8/uint16/uint32); comparing
    # an unsigned array to the negative sentinel raises MLX "Converting -100 to uint32 would
    # overflow". int32 holds both the sentinel and every byte+3 id, and is the correct dtype
    # for the gather index below.
    shift_labels = labels[:, 1:].astype(mx.int32)   # [B, T-1]

    mask = (shift_labels != ignore_index).astype(mx.float32)

    log_probs = shift_logits - mx.logsumexp(shift_logits, axis=-1, keepdims=True)  # [B, T-1, V]

    safe_labels = mx.where(shift_labels == ignore_index, mx.zeros_like(shift_labels), shift_labels)
    B, T_minus1 = safe_labels.shape
    V = shift_logits.shape[-1]

    log_probs_flat   = log_probs.reshape(-1, V)
    safe_labels_flat = safe_labels.reshape(-1)

    token_log_probs = log_probs_flat[mx.arange(B * T_minus1), safe_labels_flat]
    token_log_probs = token_log_probs.reshape(B, T_minus1)

    masked_loss = -token_log_probs * mask
    n_valid = mx.maximum(mx.sum(mask), mx.ones(()))
    return mx.sum(masked_loss) / n_valid


class DistillationLogitTrainer:
    """
    Logit (soft-target) knowledge distillation.

    Not a DeltaOperator — a training objective wrapper.

    Args:
        temperature: softmax temperature T for soft targets (default 2.0)
        alpha:       weight on the soft KL term; (1-alpha) weights the hard CE.
                     alpha=1.0 => pure distillation (no gold labels needed).

    Usage:
        trainer = DistillationLogitTrainer(temperature=2.0, alpha=0.9)
        loss = trainer.compute_loss(student_logits, teacher_logits, labels)
    """

    def __init__(self, temperature: float = 2.0, alpha: float = 1.0) -> None:
        self.temperature = temperature
        self.alpha       = alpha

    def compute_loss(
        self,
        logits: mx.array,
        teacher_logits: mx.array,
        labels: mx.array | None = None,
        ignore_index: int = -100,
        temperature: float | None = None,
        alpha: float | None = None,
    ) -> mx.array:
        """
        Compute temperature-scaled, teacher-weighted KL distillation loss.

        Args:
            logits:         STUDENT output [B, T, V] (carries gradient)
            teacher_logits: TEACHER output [B, T, V] (constant, NOT differentiated)
            labels:         optional gold token ids [B, T] for the hard-CE blend.
                            Required iff effective alpha < 1.0.
            ignore_index:   label value masked in the hard-CE term
            temperature:    override instance temperature
            alpha:          override instance alpha
        Returns:
            scalar distillation loss
        """
        T = temperature if temperature is not None else self.temperature
        a = alpha       if alpha       is not None else self.alpha

        # Softened log-distributions (log-softmax via logsumexp, MLX idiom).
        # Teacher is data; do not let gradient flow into it.
        z_s = logits / T
        z_t = mx.stop_gradient(teacher_logits) / T

        log_p_s = z_s - mx.logsumexp(z_s, axis=-1, keepdims=True)  # log p_S  [B, T, V]
        log_p_t = z_t - mx.logsumexp(z_t, axis=-1, keepdims=True)  # log p_T  [B, T, V]
        p_t     = mx.exp(log_p_t)                                  #     p_T  [B, T, V]

        # Teacher-weighted forward KL: Σ_v p_T * (log p_T - log p_S)
        # T^2 scaling restores gradient magnitude lost to softening.
        kl_per_pos = mx.sum(p_t * (log_p_t - log_p_s), axis=-1)    # [B, T]
        l_soft = T * T * mx.mean(kl_per_pos)

        if a >= 1.0:
            return l_soft

        if labels is None:
            raise ValueError(
                "DistillationLogitTrainer.compute_loss: alpha < 1.0 requires "
                "`labels` for the hard cross-entropy term."
            )

        l_hard = _shifted_hard_ce(logits, labels, ignore_index=ignore_index)
        return a * l_soft + (1.0 - a) * l_hard


class DistillationSequenceTrainer:
    """
    Sequence-level knowledge distillation (Kim & Rush, 2016).

    Not a DeltaOperator — a training objective wrapper.

    Teacher-forced cross-entropy against the teacher's hard token sequence
    (argmax-decoded from teacher logits, or precomputed teacher tokens),
    reusing SFT's shifted-CE / masking machinery.

    Usage:
        trainer = DistillationSequenceTrainer()
        # from teacher logits:
        loss = trainer.compute_loss(student_logits, teacher_logits=teacher_logits)
        # or from precomputed teacher tokens:
        loss = trainer.compute_loss(student_logits, teacher_tokens=teacher_tokens)
    """

    def compute_loss(
        self,
        logits: mx.array,
        teacher_logits: mx.array | None = None,
        teacher_tokens: mx.array | None = None,
        ignore_index: int = -100,
    ) -> mx.array:
        """
        Compute teacher-forced sequence distillation loss.

        Args:
            logits:         STUDENT output [B, T, V] (carries gradient)
            teacher_logits: TEACHER output [B, T, V]; argmax -> hard tokens.
                            Constant (NOT differentiated). Mutually exclusive
                            with teacher_tokens.
            teacher_tokens: precomputed teacher token ids [B, T] (constant).
            ignore_index:   token value masked in the CE
        Returns:
            scalar sequence distillation loss
        """
        if teacher_tokens is None:
            if teacher_logits is None:
                raise ValueError(
                    "DistillationSequenceTrainer.compute_loss: provide either "
                    "`teacher_logits` or `teacher_tokens`."
                )
            # Greedy-decode the teacher's preferred token at every position.
            teacher_tokens = mx.argmax(mx.stop_gradient(teacher_logits), axis=-1)  # [B, T]

        # Teacher tokens are constant labels; never differentiated.
        teacher_tokens = mx.stop_gradient(teacher_tokens)
        return _shifted_hard_ce(logits, teacher_tokens, ignore_index=ignore_index)


class DistillationTrainer:
    """
    Unified distillation entry point dispatching on `mode`.

    mode="logit"    -> DistillationLogitTrainer (soft-target KL @ temperature)
    mode="sequence" -> DistillationSequenceTrainer (teacher-forced hard CE)

    The two registry entries (distill_logit / distill_sequence) point at the
    dedicated subclasses directly; this class is provided for callers that want
    a single object with a `mode` switch.

    Usage:
        trainer = DistillationTrainer(mode="logit", temperature=2.0, alpha=0.9)
        loss = trainer.compute_loss(student_logits, teacher_logits, labels)
    """

    def __init__(
        self,
        mode: str = "logit",
        temperature: float = 2.0,
        alpha: float = 1.0,
    ) -> None:
        if mode not in {"logit", "sequence"}:
            raise ValueError(f"mode must be 'logit' or 'sequence', got {mode!r}")
        self.mode = mode
        if mode == "logit":
            self._impl = DistillationLogitTrainer(temperature=temperature, alpha=alpha)
        else:
            self._impl = DistillationSequenceTrainer()

    def compute_loss(self, *args, **kwargs) -> mx.array:
        return self._impl.compute_loss(*args, **kwargs)
