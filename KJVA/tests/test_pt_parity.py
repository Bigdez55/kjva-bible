"""test_pt_parity.py — Phase-1 gate: the PyTorch trainer produces an XMIND-consumable GGUF.

Exercises the real CLIs end-to-end (subprocess) so it also catches import/path issues:
  1. pt/model.py: byte base = exactly 18,980,352 params, 74-tensor name contract.
  2. pt/train_byte.py: trains a few steps on a tiny corpus, loss decreases, checkpoint saved.
  3. pt/export.py → GGUF: valid GGUF v3, 74 tensors, 18,980,352 params (Q4_0 attn/ffn + F32 norms/embed).

Pure-PyTorch — no MLX. Run:  pytest tests/test_pt_parity.py -q
"""
from __future__ import annotations

import importlib.util
import json
import struct
import subprocess
import sys
from pathlib import Path

import pytest

TRAINING = Path(__file__).resolve().parents[1] / "training"
PT = TRAINING / "pt"

torch = pytest.importorskip("torch")  # skip cleanly if torch absent (MLX-less != torch-less)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_param_count_and_tensor_contract():
    m = _load("pt_model_test", PT / "model.py")
    sg = _load("s2g_test", TRAINING / "scripts" / "safetensors_to_gguf.py")
    cfg = m.ModelConfig()                       # byte base defaults
    model = m.init_weights(m.TokenlessLM(cfg), cfg, seed=42)
    assert model.num_params() == 18_980_352, "byte base must be exactly 18.98M params"
    sd = set(model.state_dict().keys())
    mapped = set(sg.build_name_mapping(cfg.n_layers).keys())
    assert sd == mapped, f"tensor-name contract mismatch: {sd ^ mapped}"
    assert len(sd) == 74
    out = model(torch.randint(3, 259, (2, 16)))
    assert tuple(out.shape) == (2, 16, 259)
    assert not any("rope" in k for k in sd), "RoPE buffers must be excluded from state_dict"


def test_train_then_export_gguf(tmp_path):
    # Tiny corpus (full 8-layer arch so the 74-tensor contract is exercised).
    corpus = tmp_path / "corpus.txt"
    corpus.write_text(("In the beginning God created the heaven and the earth. " * 400), encoding="utf-8")
    home = tmp_path / "home"
    (home / "runs").mkdir(parents=True)
    env = {**__import__("os").environ, "TOKENLESS_HOME": str(home)}

    r = subprocess.run(
        [sys.executable, str(PT / "train_byte.py"),
         "--run-id", "ptt", "--corpus", str(corpus), "--token-cache", str(tmp_path / "tok.npy"),
         "--iters", "6", "--batch", "2", "--seq-len", "64", "--warmup", "2",
         "--eval-every", "3", "--save-every", "6", "--log-every", "1", "--no-bench", "--device", "cpu"],
        cwd=str(TRAINING), env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"train failed:\n{r.stdout}\n{r.stderr}"

    run_dir = home / "runs" / "ptt"
    ckpt = run_dir / "ckpt_step_000006.safetensors"
    assert ckpt.exists(), "checkpoint not written"

    # Loss should fall from first to last logged step.
    steps = [json.loads(l) for l in (run_dir / "train_log.jsonl").read_text().splitlines()
             if '"event": "step"' in l]
    assert steps[-1]["loss"] < steps[0]["loss"], "loss did not decrease"

    gguf = tmp_path / "out.gguf"
    r2 = subprocess.run(
        [sys.executable, str(PT / "export.py"), "--run", str(run_dir), "--output", str(gguf)],
        cwd=str(TRAINING), env=env, capture_output=True, text=True, timeout=300)
    assert r2.returncode == 0, f"export failed:\n{r2.stdout}\n{r2.stderr}"

    with gguf.open("rb") as f:
        magic = f.read(4); ver = struct.unpack("<I", f.read(4))[0]
        n_tensors = struct.unpack("<Q", f.read(8))[0]
    assert magic == b"GGUF" and ver == 3
    assert n_tensors == 74, f"expected 74 tensors, got {n_tensors}"
    sidecar = json.loads((gguf.with_suffix(".gguf.json")).read_text())
    assert sidecar["total_params"] == 18_980_352
    assert sidecar["interpreter_family"] == "tokenless_lm"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
