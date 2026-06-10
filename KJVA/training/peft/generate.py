"""
peft/generate.py — Adapted-model decoding loop (D23).

Holds the autoregressive decode loop used by OmniPEFTModel.generate().  Routing
(task/domain → adapter route plan) is resolved ONCE by OmniPEFTModel before this
loop runs and is pushed into the installed OmniPEFTBlocks, so this module only
has to drive the per-step forward.

Import-safety: mlx is imported lazily *inside* the function, never at module
load, so peft.generate imports cleanly in a framework-free environment (the
routing/tournament DEFINED->CALLED smoke does not need mlx to import this).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import mlx.core as mx
    from .model import OmniPEFTModel


def greedy_generate(
    model: "OmniPEFTModel",
    prompt_tokens: "mx.array",
    max_new_tokens: int = 64,
    eos_id: int | None = None,
) -> "mx.array":
    """
    Greedy autoregressive decode.

    The route plan (if any) has already been pushed into the model's blocks by
    OmniPEFTModel.generate(); here we simply call the model forward per step.  We
    call ``model.base_model`` directly per step so the already-installed route is
    not re-resolved on every token.

    Returns the full token sequence (prompt + generated) as a 1-D mx.array.
    """
    import mlx.core as mx  # lazy — keeps module-load framework-free

    tokens = prompt_tokens
    if tokens.ndim == 1:
        tokens = tokens[None, :]  # [1, T]

    for _ in range(max_new_tokens):
        logits = model.base_model(tokens)            # [B, T, V]
        next_logits = logits[:, -1, :]               # [B, V]
        next_id = mx.argmax(next_logits, axis=-1)     # [B]
        next_id = next_id[:, None]                    # [B, 1]
        tokens = mx.concatenate([tokens, next_id], axis=1)
        mx.eval(tokens)
        if eos_id is not None and int(next_id[0, 0].item()) == eos_id:
            break

    return tokens[0]
