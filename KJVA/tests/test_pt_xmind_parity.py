"""Numerical parity gate: XMIND C forward == pt/model.py forward (logits).

This is the gate test_pt_parity.py never had. test_pt_parity.py only checks
tensor names/shapes/count; it CANNOT catch a forward-pass divergence. This test
loads the SAME weights into both the PyTorch reference (training/pt/model.py,
rotate-half RoPE) and the XMIND C engine (via the parity_logits harness), feeds
identical byte tokens, and asserts the last-position logits agree.

History: first introduced FAILING — it proved the XMIND C engine used interleaved
adjacent-pair RoPE while the model was trained rotate-half, with no compensating
permutation (pt argmax '.', xmind argmax 'a', MAE 1.68). docs/INFERENCE_CORRECTNESS_NOTE.md records the fix.

Run:  python3 -m pytest tests/test_pt_xmind_parity.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent          # models v7/
XMIND = ROOT / "ai" / "xmind"
HARNESS = XMIND / "build" / "parity_logits"
GGUF = ROOT / "training" / "gguf" / "clean_base_soup_v1.gguf"
SAFET = ROOT / "training" / "runs" / "byte_clean_v1" / "soup_best.safetensors"
PROMPT = "In the beginning God created the heaven and the earth"

# Q4_0 deploy vs F32 reference: the audited Python NumPy backend showed ~0.09
# logit MAE / 6-of-7 argmax agreement under Q4_0. A correct C engine must land in
# that band; the RoPE bug produced MAE 1.68 with argmax disagreement.
MAE_TOL = 0.6


def _build_harness() -> None:
    if HARNESS.exists():
        return
    subprocess.run(["make", "cli"], cwd=XMIND, check=True, capture_output=True)
    subprocess.run(
        ["clang", "-std=c11", "-Iinclude", "-Ishim",
         "tests/parity_logits.c", "build/libxmind-core.a", "-lm",
         "-o", "build/parity_logits"],
        cwd=XMIND, check=True, capture_output=True)


def _xmind_logits() -> np.ndarray:
    out = subprocess.run([str(HARNESS), str(GGUF), PROMPT],
                         capture_output=True, text=True, check=True)
    vals = []
    for ln in out.stdout.splitlines():
        try:
            vals.append(float(ln.strip()))
        except ValueError:
            pass                                        # engine load logs
    arr = np.array(vals[-259:], dtype=np.float64)
    assert arr.shape == (259,), f"expected 259 logits, got {arr.shape}"
    return arr


def _pt_logits() -> np.ndarray:
    sys.path.insert(0, str(ROOT / "training" / "pt"))
    from model import TokenlessLM, ModelConfig            # noqa: E402
    from safetensors.torch import load_file               # noqa: E402
    import torch                                          # noqa: E402
    cfg = ModelConfig(vocab_size=259, n_layers=8, n_heads=6, d_model=384,
                      d_ffn=1536, max_seq_len=1024, rope_base=10000.0,
                      tie_embeddings=True, rms_eps=1e-5, init_std=0.02)
    m = TokenlessLM(cfg)
    m.load_state_dict(load_file(str(SAFET)), strict=True)
    m.eval()
    toks = torch.tensor([[b + 3 for b in PROMPT.encode()]], dtype=torch.long)
    with torch.no_grad():
        return m(toks)[0, -1].float().numpy().astype(np.float64)


@pytest.mark.skipif(not GGUF.exists() or not SAFET.exists(),
                    reason="soup artifacts not present")
def test_pt_xmind_logit_parity():
    _build_harness()
    pt = _pt_logits()
    xm = _xmind_logits()
    mae = float(np.mean(np.abs(pt - xm)))
    same_argmax = int(np.argmax(pt)) == int(np.argmax(xm))
    msg = (f"pt argmax={int(np.argmax(pt))} xmind argmax={int(np.argmax(xm))} "
           f"MAE={mae:.4f} (tol {MAE_TOL})")
    assert same_argmax, f"argmax disagreement → forward divergence: {msg}"
    assert mae < MAE_TOL, f"logit MAE too high → forward divergence: {msg}"
