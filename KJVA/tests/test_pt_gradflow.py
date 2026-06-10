"""test_pt_gradflow.py — Phase-1 gate: PyTorch PEFT adapters actually train.

For each operator family: attach to a tiny base, overfit a fixed synthetic batch,
and assert (a) adapter gradients flow (nonzero), (b) loss decreases, (c) ONLY adapter
params are trainable, (d) the frozen base is bit-unchanged. This is the structural
proof that the MLX-path M1 defect (adapters absent from the graph) cannot recur.

Pure PyTorch. Run:  pytest tests/test_pt_gradflow.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
import torch.nn.functional as F  # noqa: E402

PT = Path(__file__).resolve().parents[1] / "training" / "pt"
sys.path.insert(0, str(PT))
from model import ModelConfig, TokenlessLM, init_weights  # noqa: E402
import peft  # noqa: E402

HIGH_CAPACITY = {"lora", "dora", "oft", "houlsby"}
ALL_METHODS = ["lora", "dora", "ia3", "bitfit", "oft", "houlsby"]


def _tiny():
    cfg = ModelConfig(vocab_size=259, n_layers=2, n_heads=4, d_model=64,
                      d_ffn=128, max_seq_len=64)
    return init_weights(TokenlessLM(cfg), cfg, seed=0), cfg


@pytest.mark.parametrize("method", ALL_METHODS)
def test_adapter_trains_and_base_frozen(method):
    torch.manual_seed(0)
    model, _ = _tiny()
    base_snap = {n: p.detach().clone() for n, p in model.named_parameters()}

    model, info = peft.attach_adapters(model, method, rank=4, alpha=8)
    assert info["trainable_params"] > 0, f"{method}: no trainable params"

    # Learnable periodic byte sequence (next-token has real structure to learn).
    seq = torch.tensor([10, 11, 12, 13, 14, 15, 16, 17]).repeat(8)[:48].unsqueeze(0)
    x, y = seq[:, :-1], seq[:, 1:]
    opt = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=1e-2)

    # First backward: prove adapter gradients are nonzero (the gradient actually flows).
    logits = model(x); B, T, V = logits.shape
    loss0 = F.cross_entropy(logits.reshape(B * T, V), y.reshape(B * T))
    loss0.backward()
    grad_norm = sum((p.grad.detach().pow(2).sum() for p in model.parameters()
                     if p.requires_grad and p.grad is not None)).sqrt().item()
    assert grad_norm > 0, f"{method}: adapter gradient is zero (no flow)"
    opt.step(); opt.zero_grad(set_to_none=True)

    losses = [float(loss0.detach())]
    for _ in range(149):
        logits = model(x); B, T, V = logits.shape
        loss = F.cross_entropy(logits.reshape(B * T, V), y.reshape(B * T))
        opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
        losses.append(float(loss.detach()))

    # Universal: loss strictly decreases (gradient-driven training works for every family).
    assert losses[-1] < losses[0], f"{method}: loss did not decrease {losses[0]:.3f}->{losses[-1]:.3f}"
    # Capacity-honest: high-capacity operators reduce loss substantially; low-capacity
    # (IA3 scaling / BitFit bias) reduce it modestly — both prove gradient flow.
    if method in HIGH_CAPACITY:
        assert losses[-1] < 0.85 * losses[0], \
            f"{method}: high-capacity loss only {losses[0]:.3f}->{losses[-1]:.3f}"

    # only adapter params are trainable
    trainable = {n for n, p in model.named_parameters() if p.requires_grad}
    assert trainable == set(info["trainable_param_paths"])

    # frozen base bit-unchanged (operators expose the base linear at *.base.weight)
    for n, p in model.named_parameters():
        if p.requires_grad:
            continue
        key = n[:-len(".base.weight")] + ".weight" if n.endswith(".base.weight") else n
        if key in base_snap:
            assert torch.equal(p, base_snap[key]), f"{method}: frozen base changed at {n}"


def test_catalog_no_silent_gaps():
    """Every registered method resolves to a concrete operator (bespoke or documented alias)."""
    from peft import operators as ops
    methods = ops.all_methods()
    assert len(methods) >= 20, f"expected the full catalog, got {len(methods)}"
    for m in methods:
        cls, kwargs, is_alias = ops.resolve(m)   # raises if unknown → no silent gap
        assert issubclass(cls, peft.DeltaOperator)
    status = ops.catalog_status()
    assert status["total"] == len(methods)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
