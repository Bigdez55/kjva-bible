"""Regression test: LoRA adapter weights must change after one gradient step.

Guards against re-introduction of the zero-gradient bug where
nn.value_and_grad(base_model, fn) targeted frozen base_model instead of adapters.
"""
import sys
import os
import pytest

ML_TRAINING = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ML_TRAINING)
sys.path.insert(0, os.path.join(ML_TRAINING, "scripts"))

mlx_core = pytest.importorskip("mlx.core", reason="MLX required")


def test_lora_adapter_weights_change_after_one_step():
    import mlx.core as mx
    from scripts.train_peft import build_peft_model, run_peft_training
    from scripts.model import ModelConfig, TokenlessLM
    import argparse

    cfg = ModelConfig()
    model = TokenlessLM(cfg)

    args = argparse.Namespace(
        rank=4, alpha=8.0, train_vram_mb=1000, prompt_tokens=4,
        n_frequency=4, mask_fraction=0.01, bottleneck_dim=16,
        epochs=1, steps_per_epoch=2, lr=1e-2, no_bench=True,
        base_checkpoint=None, corpus=None, domains=None, tasks=None,
    )

    operators, method = build_peft_model("lora", model, args)
    assert isinstance(operators, dict)
    assert len(operators) > 0

    first_key = next(iter(operators))
    first_op = operators[first_key]
    # NOTE: LoRALinear stores weights as .A (rank×in) and .B (out×rank).
    # The task spec erroneously used 'lora_A' — the real attribute is 'A'.
    assert hasattr(first_op, "A"), f"Expected A on {type(first_op)}"
    before = mx.array(first_op.A).tolist()

    raw = b"In the beginning God created the heavens and the earth"
    toks = [b + 1 for b in raw]
    needed = cfg.max_seq_len + 1
    toks = (toks * ((needed // len(toks)) + 1))[:needed]
    # NOTE: steps_per_epoch=2 is intentional. LoRA inits B=0, so the gradient
    # w.r.t. A is zero on step 1 (A is gated by B in the output path).
    # A first receives a non-zero gradient on step 2, once B has moved.
    # Reducing steps_per_epoch below 2 would produce a false failure here.
    corpus = [mx.array(toks), mx.array(toks)]

    run_peft_training(method, operators, model, corpus, args, output_dir=None)

    after = mx.array(first_op.A).tolist()
    assert before != after, (
        "LoRA A matrix unchanged after gradient step — gradient target is wrong. "
        "nn.value_and_grad must target the model that CONTAINS the adapter (not frozen base)."
    )
