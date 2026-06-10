"""test_distillation_wiring.py — proves knowledge distillation is REAL, not a mislabel.

Gap-ledger item: `distill_logit`/`distill_sequence` previously returned the bare base
model from build_peft_model (no operators) and never reached any training loop — they
printed "is a training objective method" and exited. The registry was repointed to the
real DistillationLogitTrainer/DistillationSequenceTrainer, but nothing CALLED them. This
test asserts the wiring end-to-end:

  1. (no MLX) registry distill_* IDs resolve to the real Distillation* classes.
  2. (no MLX) a distill_* run WITHOUT --teacher-checkpoint FAILS CLOSED (rc=2) before any
     model work — it never silently degrades to plain next-token CE under a distill label.
  3. (MLX)   the logit objective computes Hinton soft-target KL, NOT cross-entropy:
     with teacher == student the KL is ~0 while the shifted-CE on the same batch is >0.
     If the distill path were silently running CE, (3) would be impossible.

Run:  pytest tests/test_distillation_wiring.py -q
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "training" / "scripts"
PEFT = ROOT / "training"


# ----------------------------------------------------------------------------- #
# 1. Registry repoint — the IDs map to the real distillation classes (no MLX).
# ----------------------------------------------------------------------------- #
def test_registry_points_at_real_distillation_classes():
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "train_peft.py"), "--list-methods"],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert "distill_logit" in out.stdout and "DistillationLogitTrainer" in out.stdout
    assert "distill_sequence" in out.stdout and "DistillationSequenceTrainer" in out.stdout
    # and they must be tagged as the distillation family, not aliased to SFT.
    for line in out.stdout.splitlines():
        if line.startswith("distill_"):
            assert "distillation" in line, f"distill method mislabeled: {line!r}"


# ----------------------------------------------------------------------------- #
# 2. Fail-CLOSED — distill_* without a teacher refuses BEFORE any model work (no MLX).
# ----------------------------------------------------------------------------- #
@pytest.mark.parametrize("method", ["distill_logit", "distill_sequence"])
def test_distill_without_teacher_fails_closed(method):
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "train_peft.py"),
         "--method", method,
         "--base-checkpoint", "/tmp/does_not_exist.safetensors",
         "--corpus", "/tmp/does_not_exist.txt"],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 2, (
        f"{method} without --teacher-checkpoint must exit 2 (fail-closed), "
        f"got rc={out.returncode}\nstdout={out.stdout}\nstderr={out.stderr}"
    )
    msg = (out.stderr + out.stdout).lower()
    assert "teacher" in msg and "refus" in msg, (
        f"{method} fail-closed message must explain the missing teacher; got: {msg!r}"
    )
    # It must refuse FAST — before importing MLX or loading a model. A MissingModule
    # traceback would mean the guard ran too late.
    assert "modulenotfounderror" not in msg and "traceback" not in msg, (
        "fail-closed guard must run before the MLX import (fast refusal)"
    )


def test_prefix_tuning_warns_serve_inert():
    """prefix_tuning trains but is NOT applied at inference — the run must warn loudly so the
    adapter is never mistaken for deployable (ADR-0002 §11 no-silent-mislabel)."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "train_peft.py"),
         "--method", "prefix_tuning",
         "--base-checkpoint", "/tmp/does_not_exist.safetensors"],
        capture_output=True, text=True, timeout=60,
    )
    combined = (out.stderr + out.stdout).lower()
    assert "serve-inert" in combined and "not applied at inference" in combined, (
        f"prefix_tuning must warn it is serve-inert; got: {combined!r}"
    )


def test_sft_does_not_require_a_teacher():
    """sft is teacher-free; the distill guard must not trip for it."""
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "train_peft.py"),
         "--method", "sft",
         "--base-checkpoint", "/tmp/does_not_exist.safetensors"],
        capture_output=True, text=True, timeout=60,
    )
    # It will fail later (no MLX / missing base), but NOT with the distillation
    # teacher refusal — that message must be absent for sft.
    combined = (out.stderr + out.stdout).lower()
    assert "requires a frozen teacher" not in combined


# ----------------------------------------------------------------------------- #
# 3. The logit objective is KL, not CE (MLX-gated, output-differs proof).
# ----------------------------------------------------------------------------- #
def test_logit_distillation_is_kl_not_cross_entropy():
    mx = pytest.importorskip("mlx.core")
    sys.path.insert(0, str(SCRIPTS))
    sys.path.insert(0, str(PEFT))
    from model import ModelConfig, TokenlessLM  # noqa: E402
    from peft.alignment.distillation import (  # noqa: E402
        DistillationLogitTrainer,
        DistillationSequenceTrainer,
        _shifted_hard_ce,
    )

    cfg = ModelConfig(vocab_size=259, n_layers=2, n_heads=4, d_model=64, max_seq_len=64)
    student = TokenlessLM(cfg)
    teacher = TokenlessLM(cfg)
    # Make teacher == student exactly (copy params) so KL(teacher||student) == 0.
    from mlx.utils import tree_flatten, tree_unflatten
    teacher.update(tree_unflatten(list(tree_flatten(student.parameters()))))
    teacher.freeze()

    tokens = mx.array([[1, 5, 9, 13, 17, 21, 25, 29]])  # [1, T]
    s_logits = student(tokens)
    t_logits = mx.stop_gradient(teacher(tokens))

    # Soft-target KL with identical distributions must be ~0.
    kl = float(DistillationLogitTrainer(temperature=2.0, alpha=1.0)
               .compute_loss(s_logits, t_logits).item())
    # The plain shifted next-token CE on the SAME batch is clearly nonzero.
    ce = float(_shifted_hard_ce(s_logits, tokens).item())

    assert kl < 1e-3, f"KL(teacher==student) should be ~0, got {kl}"
    assert ce > 1e-1, f"shifted-CE should be clearly nonzero, got {ce}"
    # The decisive separation: if distill silently ran CE, the 'distill' number
    # could not be ~0 while the real CE is >0.1.
    assert ce - kl > 1e-1

    # Sequence distillation (teacher==student) is teacher-forced CE on argmax(teacher);
    # it must produce a finite, non-negative scalar (the path executes).
    seq = float(DistillationSequenceTrainer()
                .compute_loss(s_logits, teacher_logits=t_logits).item())
    assert seq >= 0.0 and seq == seq  # finite, not NaN


# ----------------------------------------------------------------------------- #
# 4. The LOOP itself runs (MLX-gated) — DEFINED→CALLED, not just py_compile.
#    Drives run_alignment_training + save_alignment_model end-to-end and asserts
#    the fine-tuned-model artifact + provenance are actually written. This is the
#    proof that the ~150 lines added in this commit EXECUTE, not merely compile.
# ----------------------------------------------------------------------------- #
def test_run_alignment_training_executes_and_saves(tmp_path):
    mx = pytest.importorskip("mlx.core")
    from types import SimpleNamespace
    sys.path.insert(0, str(SCRIPTS))
    sys.path.insert(0, str(PEFT))
    import train_peft  # noqa: E402  (module-level imports are MLX-free now)
    from model import ModelConfig, TokenlessLM  # noqa: E402
    from mlx.utils import tree_flatten, tree_unflatten

    cfg = ModelConfig(vocab_size=259, n_layers=2, n_heads=4, d_model=64, max_seq_len=64)
    student = TokenlessLM(cfg)
    teacher = TokenlessLM(cfg)
    teacher.update(tree_unflatten(list(tree_flatten(student.parameters()))))
    teacher.freeze()

    chunks = [mx.array([1, 5, 9, 13, 17, 21, 25, 29]),
              mx.array([2, 6, 10, 14, 18, 22, 26, 30])]
    args = SimpleNamespace(
        lr=1e-3, epochs=1, steps_per_epoch=2, no_bench=True,
        distill_temperature=2.0, distill_alpha=1.0,
        base_checkpoint=None, teacher_checkpoint="copy-of-student",
    )

    out = tmp_path / "distill_run"
    # Drives nn.value_and_grad(base_model, loss_fn), optimizer.update, the teacher
    # forward inside the grad closure, and mx.eval — the actual wiring.
    train_peft.run_alignment_training("distill_logit", student, teacher, chunks, args,
                                      output_dir=out)
    train_peft.save_alignment_model("distill_logit", student, out, args)

    assert (out / "weights.safetensors").exists(), "fine-tuned student must be saved"
    prov_path = out / "alignment_provenance.json"
    assert prov_path.exists(), "alignment provenance must be saved"
    import json
    prov = json.loads(prov_path.read_text())
    assert prov["method"] == "distill_logit"
    assert prov["objective_family"] == "distillation"
    assert prov["teacher_checkpoint"] == "copy-of-student"

    # Fail-closed re-asserted at the function layer (defense-in-depth): distill
    # without a teacher raises here too, not just at the CLI guard.
    with pytest.raises(ValueError, match="teacher"):
        train_peft.run_alignment_training("distill_sequence", student, None, chunks, args,
                                          output_dir=tmp_path / "should_not_exist")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
