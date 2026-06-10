"""
ckpt_bench.py — Inline checkpoint benchmark, shared by train_byte.py and train_peft.py.

Called automatically at every checkpoint save during training.
Writes bench_step_XXXXXX.json (or bench_epoch_XX.json for PEFT) alongside each checkpoint.

Quick bench (runs inline, ~5-15s):
  - Perplexity on up to 8 192 validation tokens
  - A few generic generation probes (consuming project can override QUICK_PROMPTS)
  - NaN / Inf sanity check at max context length

Full bench at end of training:
  Delegates to benchmark_byte.py (the comprehensive stress-test runner).
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import mlx.core as mx
import mlx.nn as nn

SCRIPT_DIR = Path(__file__).resolve().parent
ML_TRAINING = SCRIPT_DIR.parent
DEFAULT_CACHE = ML_TRAINING / "corpus" / "domain_corpus_v1" / "tokens_byte_uint16.npy"

# Generic prompts. Consuming projects can override by reassigning QUICK_PROMPTS
# before importing ckpt_bench, or by editing this list directly.
QUICK_PROMPTS = [
    {"id": "short",   "prompt": "The model emits"},
    {"id": "mid",     "prompt": "Once upon a time,"},
    {"id": "longish", "prompt": "It was the best of times, it was"},
]


# ─────────────────────────────────────────────────────────────────────────────
# Encoding / decoding helpers
# ─────────────────────────────────────────────────────────────────────────────

def _encode(text: str) -> list[int]:
    return [1] + [b + 3 for b in text.encode("utf-8")]


def _decode(ids: list[int]) -> str:
    raw = bytes(max(0, min(255, i - 3)) for i in ids if 3 <= i <= 258)
    return raw.decode("utf-8", errors="replace")


def _sample(logits: mx.array, temperature: float = 0.8, top_k: int = 40) -> int:
    if temperature <= 0.0:
        return int(mx.argmax(logits).item())
    scaled = logits / temperature
    if top_k > 0:
        top_vals = mx.topk(scaled, min(top_k, logits.shape[-1]))
        threshold = mx.min(top_vals)
        scaled = mx.where(scaled >= threshold, scaled,
                          mx.full(scaled.shape, -1e9, dtype=scaled.dtype))
    probs = mx.softmax(scaled, axis=-1)
    return int(mx.random.categorical(mx.log(probs + 1e-9)).item())


# ─────────────────────────────────────────────────────────────────────────────
# Inline sub-tests
# ─────────────────────────────────────────────────────────────────────────────

def _quick_ppl(model, tokens: np.ndarray, seq_len: int,
               max_chunks: int = 16) -> dict[str, Any]:
    """Perplexity on up to max_chunks × seq_len validation tokens."""
    n_chunks = min(max_chunks, (len(tokens) - 1) // seq_len)
    if n_chunks == 0:
        return {"ppl": None, "tokens_scored": 0}
    total_nll, total_toks = 0.0, 0
    t0 = time.perf_counter()
    for i in range(n_chunks):
        s = i * seq_len
        chunk = tokens[s: s + seq_len + 1].astype(np.int32)
        if len(chunk) < seq_len + 1:
            break
        x = mx.array(chunk[:-1])[None, :]
        y = mx.array(chunk[1:])[None, :]
        logits = model(x)
        log_probs = logits - mx.logsumexp(logits, axis=-1, keepdims=True)
        nll = -mx.take_along_axis(log_probs, y[..., None], axis=-1).squeeze(-1).sum()
        mx.eval(nll)
        total_nll += float(nll.item())
        total_toks += y.size
    ppl = math.exp(total_nll / max(1, total_toks))
    return {
        "ppl": round(ppl, 4),
        "tokens_scored": total_toks,
        "elapsed_s": round(time.perf_counter() - t0, 2),
    }


def _quick_generation(model, max_seq_len: int) -> list[dict[str, Any]]:
    """Generation probes over QUICK_PROMPTS, 60 new tokens each."""
    results = []
    for p in QUICK_PROMPTS:
        ids = _encode(p["prompt"])
        tokens = mx.array(ids, dtype=mx.int32)[None, :]
        out_ids: list[int] = []
        t0 = time.perf_counter()
        for _ in range(60):
            if tokens.shape[1] > max_seq_len:
                tokens = tokens[:, -max_seq_len:]
            logits = model(tokens)[0, -1, :]
            mx.eval(logits)
            next_id = _sample(logits, temperature=0.8, top_k=40)
            if next_id == 2:
                break
            out_ids.append(next_id)
            tokens = mx.concatenate([tokens, mx.array([[next_id]])], axis=1)
        elapsed = time.perf_counter() - t0
        results.append({
            "id": p["id"],
            "prompt": p["prompt"],
            "generation": _decode(out_ids),
            "new_tokens": len(out_ids),
            "tok_per_s": round(len(out_ids) / elapsed, 1) if elapsed > 0 else 0,
        })
    return results


def _nan_check(model, seq_len: int) -> dict[str, Any]:
    """Single forward pass at full context length — verify no NaN/Inf."""
    x = mx.zeros((1, min(seq_len, 512)), dtype=mx.int32)
    logits = model(x)
    mx.eval(logits)
    has_nan = bool(mx.any(mx.isnan(logits)).item())
    has_inf = bool(mx.any(mx.isinf(logits)).item())
    return {"has_nan": has_nan, "has_inf": has_inf, "pass": not has_nan and not has_inf}


# ─────────────────────────────────────────────────────────────────────────────
# Public entry points
# ─────────────────────────────────────────────────────────────────────────────

def run_checkpoint_bench(
    model,
    valid_tokens: np.ndarray,
    run_dir: Path,
    step: int,
    seq_len: int = 512,
    label: str = "byte",
    token_cache: Path | None = None,
) -> dict[str, Any]:
    """
    Quick inline benchmark called at every checkpoint save in train_byte.py.
    Writes bench_step_XXXXXX.json to run_dir.
    Returns the report dict.
    """
    t0 = time.perf_counter()
    print(f"  [bench] step={step} quick eval...", file=sys.stderr)

    # Use last 8192 tokens of valid stream
    tail = np.asarray(valid_tokens[-8192:]) if len(valid_tokens) >= 8192 else np.asarray(valid_tokens)

    ppl_info   = _quick_ppl(model, tail, min(seq_len, 512))
    gen_probes = _quick_generation(model, seq_len)
    nan_info   = _nan_check(model, seq_len)

    report: dict[str, Any] = {
        "label": label,
        "step": step,
        "benchmarked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "perplexity": ppl_info,
        "nan_check": nan_info,
        "generation_probes": gen_probes,
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "pass": nan_info["pass"],
    }

    out = run_dir / f"bench_step_{step:06d}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    status = "PASS" if nan_info["pass"] else "FAIL (NaN/Inf detected)"
    print(f"  [bench] step={step}  ppl={ppl_info.get('ppl')}  {status}  → {out.name}",
          file=sys.stderr)
    return report


def run_peft_epoch_bench(
    base_model,
    run_dir: Path,
    epoch: int,
    method: str,
    seq_len: int = 128,
    token_cache: Path | None = None,
) -> dict[str, Any]:
    """
    Quick inline benchmark called at every epoch end in train_peft.py.
    Writes bench_epoch_XX.json to run_dir.
    Loads validation tokens from cache if needed.
    """
    cache = Path(token_cache) if token_cache else DEFAULT_CACHE
    if not cache.exists():
        print(f"  [bench] token cache not found — skipping bench for epoch {epoch}",
              file=sys.stderr)
        return {}

    tokens = np.load(str(cache), mmap_mode="r")
    n_valid = max(4096, int(len(tokens) * 0.02))
    valid_tokens = np.asarray(tokens[-n_valid:])

    t0 = time.perf_counter()
    print(f"  [bench] epoch={epoch} method={method} quick eval...", file=sys.stderr)

    ppl_info   = _quick_ppl(base_model, valid_tokens, seq_len, max_chunks=8)
    gen_probes = _quick_generation(base_model, seq_len)
    nan_info   = _nan_check(base_model, seq_len)

    report: dict[str, Any] = {
        "label": f"peft_{method}",
        "epoch": epoch,
        "method": method,
        "benchmarked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "perplexity": ppl_info,
        "nan_check": nan_info,
        "generation_probes": gen_probes,
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "pass": nan_info["pass"],
    }

    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / f"bench_epoch_{epoch:03d}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    status = "PASS" if nan_info["pass"] else "FAIL (NaN/Inf detected)"
    print(f"  [bench] epoch={epoch}  ppl={ppl_info.get('ppl')}  {status}  → {out.name}",
          file=sys.stderr)
    return report


def run_final_bench(run_dir: Path, ckpt_path: Path | None = None) -> None:
    """
    Spawn the full benchmark_byte.py at end of training.
    Non-blocking if the model is large; writes to eval/<run_id>/benchmark_final.json.
    """
    bench_script = SCRIPT_DIR / "benchmark_byte.py"
    if not bench_script.exists():
        print(f"  [bench] benchmark_byte.py not found — skipping final bench",
              file=sys.stderr)
        return

    out_dir = ML_TRAINING / "eval" / run_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "benchmark_final.json"

    cmd = [
        sys.executable, str(bench_script),
        "--run-dir", str(run_dir),
        "--out", str(out_file),
    ]
    if ckpt_path:
        cmd += ["--ckpt", str(ckpt_path)]

    print(f"\n  [bench] Launching full benchmark → {out_file}", file=sys.stderr)
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        print(f"  [bench] Full benchmark running in background (PID launched).",
              file=sys.stderr)
    except Exception as e:
        print(f"  [bench] Could not launch full benchmark: {e}", file=sys.stderr)
