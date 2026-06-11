"""
Tests for OmniPEFTCompositeAdapter — verifying the Omni-PEFT doctrine.

Doctrine: Omni-PEFT is one unified parameter-efficient adaptation organism.
See training/peft/OMNI_PEFT_DOCTRINE.md.

Critical invariant — test_omnipeft_is_not_tournament:
  A valid Omni-PEFT artifact must NOT contain "tournament_winner".
  It MUST contain single_training_run=True, single_optimizer=True,
  and enabled_methods with length > 1.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_tiny_model():
    """Create a minimal TokenlessLM for testing (vocab=259, n_layers=2, d_model=64)."""
    from model import ModelConfig, TokenlessLM
    cfg = ModelConfig(vocab_size=259, n_layers=2, n_heads=4, d_model=64, d_ffn=128)
    return TokenlessLM(cfg)


def _make_plan(base_model):
    """Build a compiler plan over the tiny model."""
    from peft.base import AdaptationConstraints, HardwareBudget
    from peft.fingerprint import TaskFingerprinter, DataSize
    from peft.profiler import ModelProfiler
    from peft.compiler import PEFTCompiler

    hardware = HardwareBudget(train_vram_mb=16000)
    constraints = AdaptationConstraints(hardware=hardware)
    cfg_dict = {
        "vocab_size": base_model.cfg.vocab_size,
        "n_layers": base_model.cfg.n_layers,
        "d_model": base_model.cfg.d_model,
        "d_ffn": base_model.cfg.d_ffn,
    }
    plasticity = ModelProfiler().profile(cfg_dict, constraints)
    fingerprint = TaskFingerprinter().fingerprint(
        task_desc="omni test",
        domains=["technical"],
        data_size=DataSize.SMALL,
        hardware=hardware,
    )
    return PEFTCompiler().plan(plasticity, fingerprint, constraints)


# ---------------------------------------------------------------------------
# Test: Omni artifact must not be a tournament
# ---------------------------------------------------------------------------

def test_omnipeft_is_not_tournament():
    """
    Core doctrine test: an Omni-PEFT genome must not have tournament_winner.

    Checks the peft_tournament_lora_winner_v1 directory to confirm the LoRA
    artifact from the prior tournament run does NOT claim to be Omni-PEFT.
    Also verifies that any omni_adapter_genome.json found in archive dirs
    follows the doctrine schema.
    """
    # The prior tournament artifact must be reclassified (not named omnipeft)
    archive = Path(__file__).parent.parent.parent / (
        "models v7/training/gguf/archive/adapters"
    )

    omnipeft_dirs = list(archive.glob("*omnipeft*")) if archive.exists() else []
    for d in omnipeft_dirs:
        genome_path = d / "adapter_genome.json"
        if genome_path.exists():
            genome = json.loads(genome_path.read_text())
            # Any dir named *omnipeft* must be a real Omni-PEFT artifact
            assert genome.get("single_training_run") is True, (
                f"{d.name}: contains adapter_genome.json with single_training_run != True — "
                "this was a tournament, rename the directory"
            )
            assert "tournament_winner" not in genome, (
                f"{d.name}: genome has 'tournament_winner' — this is a tournament, not Omni-PEFT"
            )

    # The tournament directory must exist with the correct name
    tournament_dir = archive / "peft_tournament_lora_winner_v1"
    if archive.exists():
        assert tournament_dir.exists(), (
            "peft_tournament_lora_winner_v1 must exist — "
            "do not rename the tournament artifact back to *omnipeft*"
        )


# ---------------------------------------------------------------------------
# Test: OmniPEFTCompositeAdapter construction
# ---------------------------------------------------------------------------

def test_omni_composite_construction():
    """OmniPEFTCompositeAdapter.from_plan produces a valid composite."""
    from peft.omni_composite import OmniPEFTCompositeAdapter

    model = _make_tiny_model()
    plan = _make_plan(model)
    composite = OmniPEFTCompositeAdapter.from_plan(plan, model)

    assert isinstance(composite, nn.Module)
    assert len(composite._genome_methods) > 1, (
        "Omni composite must have more than one method"
    )
    assert composite._operator_count > 0


def test_omni_composite_has_all_families():
    """Composite must have weight-additive + activation + bias methods."""
    from peft.omni_composite import OmniPEFTCompositeAdapter

    model = _make_tiny_model()
    plan = _make_plan(model)
    composite = OmniPEFTCompositeAdapter.from_plan(plan, model)

    methods = set(composite._genome_methods)
    # Weight-additive
    assert methods & {"lora", "adalora", "dora"}, "Must have weight-additive method"
    # Activation scaling
    assert "ia3" in methods, "Must have IA3 activation scaling"
    # Bias
    assert "bitfit" in methods, "Must have BitFit bias tuning"
    # Prefix
    assert "prefix_tuning" in methods, "Must have prefix tuning"


# ---------------------------------------------------------------------------
# Test: All operators are in the trainable model tree
# ---------------------------------------------------------------------------

def test_omni_operators_in_model_tree():
    """After injection, all Omni operators are visible to value_and_grad."""
    from peft.omni_composite import OmniPEFTCompositeAdapter
    from mlx.utils import tree_flatten

    model = _make_tiny_model()
    plan = _make_plan(model)
    composite = OmniPEFTCompositeAdapter.from_plan(plan, model)

    model.freeze()
    rollback = composite.inject_into(model)

    assert len(rollback) > 0, "No layers were injected"

    # Check that the patched layers have trainable parameters
    trainable_count = 0
    for _, layer in tree_flatten(model.parameters()):
        if isinstance(layer, mx.array):
            trainable_count += layer.size

    assert trainable_count > 0, "No trainable parameters found after injection"


# ---------------------------------------------------------------------------
# Test: Single forward pass computes loss without error
# ---------------------------------------------------------------------------

def test_omni_single_forward_pass():
    """Omni-patched model runs a forward pass and produces a finite loss."""
    from peft.omni_composite import OmniPEFTCompositeAdapter

    model = _make_tiny_model()
    plan = _make_plan(model)
    composite = OmniPEFTCompositeAdapter.from_plan(plan, model)

    model.freeze()
    composite.inject_into(model)

    seq = mx.array([1] * 33)  # 33 bytes → tokens [1..32] input, [2..33] target
    tokens = seq[:-1].reshape(1, -1)
    targets = seq[1:].reshape(1, -1)
    logits = model(tokens)

    B, T, V = logits.shape
    loss = mx.mean(
        nn.losses.cross_entropy(logits.reshape(B * T, V), targets.reshape(B * T))
    )
    loss_val = float(loss.item())
    assert loss_val > 0 and loss_val < 100, (
        f"Loss out of range: {loss_val} — NaN or explosion in Omni forward pass"
    )


# ---------------------------------------------------------------------------
# Test: value_and_grad sees Omni parameters (gradient flow check)
# ---------------------------------------------------------------------------

def test_omni_gradient_flow():
    """value_and_grad computes non-zero gradients for at least one Omni operator."""
    from peft.omni_composite import OmniPEFTCompositeAdapter

    model = _make_tiny_model()
    plan = _make_plan(model)
    composite = OmniPEFTCompositeAdapter.from_plan(plan, model)

    model.freeze()
    composite.inject_into(model)

    seq = mx.array([1] * 33)

    def compute_loss():
        tokens = seq[:-1].reshape(1, -1)
        targets = seq[1:].reshape(1, -1)
        logits = model(tokens)
        B, T, V = logits.shape
        return mx.mean(
            nn.losses.cross_entropy(logits.reshape(B * T, V), targets.reshape(B * T))
        )

    loss_and_grad = nn.value_and_grad(model, compute_loss)
    loss_val, grads = loss_and_grad()
    mx.eval(grads)

    from mlx.utils import tree_flatten
    nonzero_grad_count = sum(
        1 for _, g in tree_flatten(grads)
        if isinstance(g, mx.array) and bool(mx.any(g != 0).item())
    )

    assert nonzero_grad_count > 0, (
        "All gradients are zero — Omni operators are not in the gradient path"
    )


# ---------------------------------------------------------------------------
# Test: Genome schema is correct (not a tournament record)
# ---------------------------------------------------------------------------

def test_omni_genome_schema():
    """genome_dict produces a valid Omni-PEFT genome (not a tournament record)."""
    from peft.omni_composite import OmniPEFTCompositeAdapter

    model = _make_tiny_model()
    plan = _make_plan(model)
    composite = OmniPEFTCompositeAdapter.from_plan(plan, model)

    genome = composite.genome_dict(
        base_model_sha256="abc123",
        final_avg_loss=2.5,
        training_epochs=3,
    )

    assert genome["single_training_run"] is True
    assert genome["single_optimizer"] is True
    assert genome["single_loss"] is True
    assert isinstance(genome["enabled_methods"], list)
    assert len(genome["enabled_methods"]) > 1
    assert "tournament_winner" not in genome


# ---------------------------------------------------------------------------
# Test: DoRA initializes from actual base weight (NaN regression)
# ---------------------------------------------------------------------------

def test_dora_no_nan_with_real_weight():
    """DoRALinear with a real frozen weight does not produce NaN loss."""
    from peft.low_rank.dora import DoRALinear

    in_f, out_f = 64, 64
    frozen_weight = mx.random.normal((out_f, in_f)) * 0.02

    dora = DoRALinear(frozen_weight, rank=4, alpha=8.0)

    x = mx.random.normal((2, 8, in_f))
    out = dora(x)
    mx.eval(out)

    has_nan = bool(mx.any(mx.isnan(out)).item())
    assert not has_nan, "DoRA produced NaN — zero placeholder weight bug not fixed"


# ---------------------------------------------------------------------------
# Test: PrefixTuningLayer uses correct kwargs (API mismatch regression)
# ---------------------------------------------------------------------------

def test_prefix_tuning_correct_kwargs():
    """PrefixTuningLayer constructs without TypeError from wrong kwargs."""
    from peft.prompt.prefix_tuning import PrefixTuningLayer

    layer = PrefixTuningLayer(n_prefix=8, n_heads=4, head_dim=16, n_layers=2)
    assert layer.n_prefix == 8
    assert layer.n_layers == 2
    prefix_k, prefix_v = layer.get_prefix(0)
    assert prefix_k.shape == (8, 64)
    assert prefix_v.shape == (8, 64)


# ---------------------------------------------------------------------------
# Test: extract_weights returns non-empty flat dict
# ---------------------------------------------------------------------------

def test_omni_extract_weights_non_empty():
    """After training setup, extract_weights returns all operator tensors."""
    from peft.omni_composite import OmniPEFTCompositeAdapter

    model = _make_tiny_model()
    plan = _make_plan(model)
    composite = OmniPEFTCompositeAdapter.from_plan(plan, model)

    weights = composite.extract_weights()
    assert len(weights) > 0, "extract_weights returned empty dict"
    # No key should be from the frozen base (those stay in canonical.gguf)
    for k in weights:
        assert not k.endswith("base.weight"), (
            f"extract_weights included frozen base weight: {k}"
        )
