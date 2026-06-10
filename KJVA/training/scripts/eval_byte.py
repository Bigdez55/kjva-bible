#!/usr/bin/env python3
"""Evaluate a byte-level TokenlessLM checkpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn
import numpy as np
from mlx.utils import tree_unflatten

sys.path.insert(0, str(Path(__file__).parent))
from model import ModelConfig, TokenlessLM  # noqa


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
TOKENLESS_HOME = Path(os.environ.get("TOKENLESS_HOME", str(SCRIPT_DIR.parent)))
DEFAULT_CACHE = TOKENLESS_HOME / "corpus" / "domain_corpus_v1" / "tokens_byte_uint16.npy"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def latest_ckpt(run_dir: Path) -> Path:
    ckpts = sorted(run_dir.glob("ckpt_step_*.safetensors"))
    if not ckpts:
        raise FileNotFoundError(f"no checkpoints in {run_dir}")
    return ckpts[-1]


def load_model(config_path: Path, ckpt_path: Path) -> TokenlessLM:
    cfg = ModelConfig(**json.loads(config_path.read_text(encoding="utf-8")))
    model = TokenlessLM(cfg)
    weights = mx.load(str(ckpt_path))
    model.update(tree_unflatten(list(weights.items())))
    return model


def compute_full_valid_ppl(model: TokenlessLM, valid_tokens: np.ndarray) -> tuple[float, int]:
    seq_len = model.cfg.max_seq_len
    total_nll = 0.0
    total_tokens = 0
    n_chunks = (len(valid_tokens) - 1) // seq_len
    for i in range(n_chunks):
        s = i * seq_len
        e = s + seq_len + 1
        if e > len(valid_tokens):
            break
        chunk = valid_tokens[s:e].astype(np.int32)
        x = mx.array(chunk[:-1])[None, :]
        y = mx.array(chunk[1:])[None, :]
        logits = model(x)
        log_probs = nn.log_softmax(logits, axis=-1)
        gathered = mx.take_along_axis(log_probs, y[..., None], axis=-1).squeeze(-1)
        nll_sum = -gathered.sum()
        mx.eval(nll_sum)
        total_nll += float(nll_sum.item())
        total_tokens += y.size
    return math.exp(total_nll / max(1, total_tokens)), total_tokens


def encode_bytes(text: str) -> list[int]:
    return [1] + [b + 3 for b in text.encode("utf-8")]


def decode_bytes(ids: list[int]) -> str:
    raw = bytes(max(0, min(255, i - 3)) for i in ids if 3 <= i <= 258)
    return raw.decode("utf-8", errors="replace")


def sample_token(logits: mx.array, temperature: float, top_k: int | None) -> int:
    if temperature <= 0:
        return int(mx.argmax(logits).item())
    scaled = logits / temperature
    if top_k:
        top_vals = mx.topk(scaled, top_k)
        threshold = mx.min(top_vals)
        scaled = mx.where(
            scaled >= threshold,
            scaled,
            mx.full(scaled.shape, -1e9, dtype=scaled.dtype),
        )
    probs = mx.softmax(scaled, axis=-1)
    return int(mx.random.categorical(mx.log(probs + 1e-9)).item())


def generate(model: TokenlessLM, prompt: str, max_new: int,
             temperature: float, top_k: int) -> str:
    tokens = mx.array(encode_bytes(prompt), dtype=mx.int32)[None, :]
    out_ids: list[int] = []
    for _ in range(max_new):
        if tokens.shape[1] > model.cfg.max_seq_len:
            tokens = tokens[:, -model.cfg.max_seq_len:]
        logits = model(tokens)[0, -1, :]
        mx.eval(logits)
        next_id = sample_token(logits, temperature, top_k)
        if next_id == 2:
            break
        out_ids.append(next_id)
        tokens = mx.concatenate([tokens, mx.array([[next_id]])], axis=1)
    return decode_bytes(out_ids)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--ckpt", default=None)
    parser.add_argument("--token-cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--out", default=None)
    parser.add_argument("--skip-generation", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--max-new", type=int, default=150)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    mx.random.seed(args.seed)
    run_dir = Path(args.run_dir)
    ckpt_path = Path(args.ckpt) if args.ckpt else latest_ckpt(run_dir)
    model = load_model(run_dir / "model_config.json", ckpt_path)

    print(f"Computing byte full-valid perplexity for {ckpt_path}", file=sys.stderr)
    tokens = np.load(args.token_cache, mmap_mode="r")
    n_valid = max(4096, int(len(tokens) * 0.02))
    valid_tokens = np.asarray(tokens[-n_valid:])
    t0 = time.time()
    val_ppl, val_n = compute_full_valid_ppl(model, valid_tokens)

    generations = []
    if not args.skip_generation:
        for prompt in [
            "GEN 1:1",
            "The LORD is my shepherd",
            "For God so loved the world",
        ]:
            generations.append({
                "prompt": prompt,
                "generation": generate(model, prompt, args.max_new,
                                       args.temperature, args.top_k),
            })

    report = {
        "checkpoint": str(ckpt_path),
        "checkpoint_sha256": sha256_file(ckpt_path),
        "config_path": str(run_dir / "model_config.json"),
        "tokenization": "utf8_byte",
        "token_cache": str(args.token_cache),
        "val_ppl": round(val_ppl, 4),
        "val_tokens_scored": val_n,
        "elapsed_s": round(time.time() - t0, 1),
        "generations": generations,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
