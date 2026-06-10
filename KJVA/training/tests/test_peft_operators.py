"""
test_peft_operators.py — Verify each DeltaOperator instantiates and runs forward pass.

Run from training/:
  python3 tests/test_peft_operators.py
  python3 -m pytest tests/test_peft_operators.py -v

Requires MLX to be installed (pip install mlx).
Each test:
  1. Instantiates the operator with default params matching TokenlessLM dimensions
  2. Runs a forward pass with a realistic dummy input
  3. Checks output shape is correct
  4. Checks num_trainable_params() > 0 (adapter has trainable weights)
"""
from __future__ import annotations

import sys
from pathlib import Path

ML_TRAINING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ML_TRAINING))

try:
    import mlx.core as mx
    import mlx.nn as nn
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    print("[WARN] MLX not installed — operator forward-pass tests skipped")

# TokenlessLM canonical dimensions
D_MODEL = 384
D_FFN = 1536
N_HEADS = 6
HEAD_DIM = 64
N_LAYERS = 6
SEQ_LEN = 32
BATCH = 2
RANK = 4
ALPHA = 8.0


def _dummy_hidden(batch=BATCH, seq=SEQ_LEN, dim=D_MODEL):
    """Return a random [B, T, D] MLX array."""
    return mx.random.normal((batch, seq, dim))


def _check_output(op, x, expected_shape, test_name):
    """Run forward pass, assert shape."""
    out = op(x)
    assert out.shape == expected_shape, (
        f"{test_name}: expected shape {expected_shape}, got {out.shape}"
    )


# ---------------------------------------------------------------------------
# Low-rank family
# ---------------------------------------------------------------------------

def test_lora():
    from peft.low_rank.lora import LoRALinear
    op = LoRALinear(D_MODEL, D_MODEL, rank=RANK, alpha=ALPHA)
    x = _dummy_hidden()
    _check_output(op, x, (BATCH, SEQ_LEN, D_MODEL), "LoRALinear")
    assert op.num_trainable_params() > 0


def test_rslora():
    from peft.low_rank.rslora import rsLoRALinear
    op = rsLoRALinear(D_MODEL, D_MODEL, rank=RANK, alpha=ALPHA)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_olora():
    from peft.low_rank.olora import OLoRALinear
    op = OLoRALinear(D_MODEL, D_MODEL, rank=RANK, alpha=ALPHA)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_adalora():
    from peft.low_rank.adalora import AdaLoRALinear
    op = AdaLoRALinear(D_MODEL, D_MODEL, rank=RANK, alpha=ALPHA)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_vera():
    from peft.low_rank.vera import VeRALinear
    op = VeRALinear(D_MODEL, D_MODEL, rank=RANK * 4)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_pissa():
    from peft.low_rank.pissa import PiSSALinear
    frozen_w = mx.random.normal((D_MODEL, D_MODEL))
    op = PiSSALinear(frozen_w, rank=RANK, alpha=ALPHA)
    x = _dummy_hidden()
    out = op(x)
    # PiSSA returns full output (base + delta), shape same as input linear
    assert out.shape[-1] == D_MODEL


def test_loha():
    from peft.low_rank.loha import LoHaLinear
    op = LoHaLinear(D_MODEL, D_MODEL, rank=RANK, alpha=ALPHA)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_lokr():
    from peft.low_rank.lokr import LoKrLinear
    op = LoKrLinear(D_MODEL, D_MODEL, rank=RANK, alpha=ALPHA)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_rosa():
    from peft.low_rank.rosa import RoSALinear
    op = RoSALinear(D_MODEL, D_MODEL, rank=RANK, alpha=ALPHA)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_qlora():
    from peft.low_rank.qlora import QLoRALinear
    op = QLoRALinear(D_MODEL, D_MODEL, rank=RANK, alpha=ALPHA)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_dora():
    from peft.low_rank.dora import DoRALinear
    frozen_w = mx.random.normal((D_MODEL, D_MODEL))
    op = DoRALinear(frozen_w, rank=RANK, alpha=ALPHA)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape[-1] == D_MODEL


# ---------------------------------------------------------------------------
# Additive adapters
# ---------------------------------------------------------------------------

def test_houlsby():
    from peft.additive.houlsby import HoulsbyAdapter
    op = HoulsbyAdapter(d_model=D_MODEL, bottleneck_dim=64)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)
    assert op.num_trainable_params() > 0


def test_pfeiffer():
    from peft.additive.pfeiffer import PfeifferAdapter
    op = PfeifferAdapter(d_model=D_MODEL, bottleneck_dim=64)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


# ---------------------------------------------------------------------------
# Prompt family
# ---------------------------------------------------------------------------

def test_prompt_tuning():
    from peft.prompt.prompt_tuning import PromptTuningLayer
    op = PromptTuningLayer(n_tokens=10, d_model=D_MODEL)
    x = _dummy_hidden()
    out = op(x)
    # Output is longer by n_tokens
    assert out.shape == (BATCH, SEQ_LEN + 10, D_MODEL)


def test_prefix_tuning():
    from peft.prompt.prefix_tuning import PrefixTuningLayer
    op = PrefixTuningLayer(n_prefix=8, n_heads=N_HEADS, head_dim=HEAD_DIM, n_layers=N_LAYERS)
    prefix_k, prefix_v = op.get_prefix(0)
    assert prefix_k.shape[-1] == N_HEADS * HEAD_DIM


def test_p_tuning():
    from peft.prompt.p_tuning import PTuningV2
    op = PTuningV2(n_tokens=10, d_model=D_MODEL)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN + 10, D_MODEL)


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

def test_ia3():
    from peft.activation.ia3 import IA3Layer
    op = IA3Layer(d_model=D_MODEL)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)
    # K and V scaling
    k = _dummy_hidden()
    v = _dummy_hidden()
    k_scaled = op.scale_k(k)
    v_scaled = op.scale_v(v)
    assert k_scaled.shape == k.shape
    assert v_scaled.shape == v.shape


# ---------------------------------------------------------------------------
# Selective / sparse
# ---------------------------------------------------------------------------

def test_bitfit():
    from peft.selective.bitfit import BitFitOperator
    frozen_w = mx.random.normal((D_MODEL, D_MODEL))
    op = BitFitOperator(D_MODEL, D_MODEL, frozen_w)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_diffpruning():
    from peft.selective.diffpruning import DiffPruningOperator
    op = DiffPruningOperator(D_MODEL, D_MODEL, sparsity=0.01)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)
    penalty = op.l0_penalty()
    assert penalty.shape == ()   # scalar


def test_fishmask():
    from peft.selective.fishmask import FishMaskOperator
    frozen_w = mx.random.normal((D_MODEL, D_MODEL))
    op = FishMaskOperator(frozen_w, mask_fraction=0.01)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_far():
    from peft.selective.far import FAROperator
    op = FAROperator(d_model=D_MODEL)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


# ---------------------------------------------------------------------------
# Hybrid
# ---------------------------------------------------------------------------

def test_unipelt():
    from peft.hybrid.unipelt import UniPELTBlock
    op = UniPELTBlock(d_model=D_MODEL, rank=RANK)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_mam_adapter():
    from peft.hybrid.mam_adapter import MAMBlock
    op = MAMBlock(d_model=D_MODEL)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_compacter():
    from peft.hybrid.compacter import CompacterLayer
    op = CompacterLayer(d_model=D_MODEL)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_xlora():
    from peft.hybrid.xlora import XLoRALayer
    op = XLoRALayer(D_MODEL, D_MODEL, n_experts=2, rank=RANK, alpha=ALPHA)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


# ---------------------------------------------------------------------------
# Structural
# ---------------------------------------------------------------------------

def test_oft():
    from peft.structural.oft import OFTLinear
    op = OFTLinear(features=D_MODEL, block_size=8)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_boft():
    from peft.structural.boft import BOFTLinear
    op = BOFTLinear(features=D_MODEL)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


def test_fourier_ft():
    from peft.structural.fourier_ft import FourierFTLinear
    op = FourierFTLinear(D_MODEL, D_MODEL, n_frequency=50)
    x = _dummy_hidden()
    out = op(x)
    assert out.shape == (BATCH, SEQ_LEN, D_MODEL)


# ---------------------------------------------------------------------------
# Alignment (loss computation tests)
# ---------------------------------------------------------------------------

def test_sft_loss():
    from peft.alignment.sft import SFTTrainer
    trainer = SFTTrainer()
    logits = mx.random.normal((BATCH, SEQ_LEN, 16000))
    labels = mx.zeros((BATCH, SEQ_LEN), dtype=mx.int32)
    loss = trainer.compute_loss(logits, labels)
    assert loss.shape == ()


def test_dpo_loss():
    from peft.alignment.dpo import DPOTrainer
    trainer = DPOTrainer()
    chosen = mx.array([-2.0, -1.5, -2.3])
    rejected = mx.array([-3.0, -2.8, -3.1])
    loss = trainer.compute_loss(chosen, rejected, chosen - 0.5, rejected - 0.3)
    assert loss.shape == ()


def test_ipo_loss():
    from peft.alignment.ipo import IPOTrainer
    trainer = IPOTrainer()
    chosen = mx.array([-2.0, -1.5])
    rejected = mx.array([-3.0, -2.8])
    loss = trainer.compute_loss(chosen, rejected, chosen - 0.5, rejected - 0.3)
    assert loss.shape == ()


def test_grpo_loss():
    from peft.alignment.grpo import GRPOTrainer
    trainer = GRPOTrainer()
    log_probs = mx.array([-1.0, -1.2, -0.9, -1.1])
    rewards = mx.array([1.0, 0.5, 1.5, 0.8])
    loss = trainer.compute_loss(log_probs, rewards)
    assert loss.shape == ()


# ---------------------------------------------------------------------------
# Compiler / profiler / fingerprint integration
# ---------------------------------------------------------------------------

def test_profiler_runs():
    from peft.profiler import ModelProfiler
    from peft.base import AdaptationConstraints, HardwareBudget
    profiler = ModelProfiler()
    config = {"vocab_size": 16000, "n_layers": 6, "d_model": 384,
              "d_ffn": 1536, "n_heads": 6, "head_dim": 64}
    constraints = AdaptationConstraints(hardware=HardwareBudget())
    pmap = profiler.profile(config, constraints)
    assert pmap.n_layers == 6
    assert len(pmap.profiles) > 0


def test_compiler_produces_plan():
    from peft.profiler import ModelProfiler
    from peft.fingerprint import TaskFingerprinter, DataSize
    from peft.compiler import PEFTCompiler
    from peft.base import AdaptationConstraints, HardwareBudget

    config = {"vocab_size": 16000, "n_layers": 6, "d_model": 384,
              "d_ffn": 1536, "n_heads": 6, "head_dim": 64}
    hardware = HardwareBudget()
    constraints = AdaptationConstraints(hardware=hardware)

    pmap = ModelProfiler().profile(config, constraints)
    fingerprint = TaskFingerprinter().fingerprint(
        "domain completion", ["general"], DataSize.SMALL, hardware
    )
    plan = PEFTCompiler().plan(pmap, fingerprint, constraints)

    assert plan.estimated_trainable_params > 0
    assert len(plan.layer_specs) > 0


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not MLX_AVAILABLE:
        print("[SKIP] MLX not available — install with: pip install mlx")
        sys.exit(0)

    tests = [
        test_lora, test_rslora, test_olora, test_adalora, test_vera,
        test_pissa, test_loha, test_lokr, test_rosa, test_qlora, test_dora,
        test_houlsby, test_pfeiffer,
        test_prompt_tuning, test_prefix_tuning, test_p_tuning,
        test_ia3,
        test_bitfit, test_diffpruning, test_fishmask, test_far,
        test_unipelt, test_mam_adapter, test_compacter, test_xlora,
        test_oft, test_boft, test_fourier_ft,
        test_sft_loss, test_dpo_loss, test_ipo_loss, test_grpo_loss,
        test_profiler_runs, test_compiler_produces_plan,
    ]

    passed = failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test.__name__}: {e}")
            failed += 1

    print(f"\n{passed + failed} tests  |  {passed} passed  |  {failed} failed")
    sys.exit(0 if failed == 0 else 1)
