#!/usr/bin/env python3
"""
eval_final.py - Final evaluation of a trained Tokenless checkpoint.

1. Compute perplexity on held-out validation tokens.
2. Optionally run raw generation probes for qualitative tracking.
3. Emit a JSON result report.

Usage:
  python eval_final.py --run-dir "$TOKENLESS_HOME/runs/bpe_v1_20m"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_unflatten
import sentencepiece as spm

sys.path.insert(0, str(Path(__file__).parent))
from model import ModelConfig, TokenlessLM  # noqa


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
TOKENLESS_HOME = Path(os.environ.get("TOKENLESS_HOME", str(SCRIPT_DIR.parent)))
TOKEN_CACHE = TOKENLESS_HOME / "corpus" / "domain_corpus_v1" / "tokens_bpe_uint32.npy"
TOKENIZER_MODEL = TOKENLESS_HOME / "tokenizer" / "bpe_v1_20m.model"
GENERATION_PROMPTS = TOKENLESS_HOME / "eval" / "generation_prompts.jsonl"


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
    cfg_data = json.loads(config_path.read_text())
    cfg = ModelConfig(**cfg_data)
    model = TokenlessLM(cfg)
    weights = mx.load(str(ckpt_path))
    model.update(tree_unflatten(list(weights.items())))
    return model


def compute_full_valid_ppl(model: TokenlessLM, valid_tokens: np.ndarray,
                           seq_len: int = 512) -> tuple[float, int]:
    """Sliding-window perplexity over the held-out stream. No sampling."""
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
        gather = mx.take_along_axis(log_probs, y[..., None], axis=-1).squeeze(-1)
        nll_sum = -gather.sum()
        mx.eval(nll_sum)
        total_nll += float(nll_sum.item())
        total_tokens += y.size
    return math.exp(total_nll / max(1, total_tokens)), total_tokens


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


def generate(model: TokenlessLM, sp: spm.SentencePieceProcessor,
             prompt: str, max_new: int = 150, temperature: float = 0.8,
             top_k: int = 40) -> str:
    ids = [sp.bos_id()] + sp.encode(prompt)
    tokens = mx.array(ids, dtype=mx.int32)[None, :]
    out_ids: list[int] = []
    for _ in range(max_new):
        T = tokens.shape[1]
        if T > model.cfg.max_seq_len:
            tokens = tokens[:, -model.cfg.max_seq_len:]
        logits = model(tokens)[0, -1, :]
        mx.eval(logits)
        next_id = sample_token(logits, temperature, top_k)
        if next_id == sp.eos_id():
            break
        out_ids.append(next_id)
        tokens = mx.concatenate([tokens, mx.array([[next_id]])], axis=1)
    return sp.decode(out_ids)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True,
                        help="Run directory containing model_config.json and ckpts")
    parser.add_argument("--ckpt", default=None,
                        help="Specific checkpoint; default = latest")
    parser.add_argument("--out", default=None)
    parser.add_argument("--token-cache", default=str(TOKEN_CACHE))
    parser.add_argument("--tokenizer", default=str(TOKENIZER_MODEL))
    parser.add_argument("--skip-generation", action="store_true",
                        help="Only compute perplexity; skip raw generation probes")
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--max-new", type=int, default=150)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    mx.random.seed(args.seed)

    run_dir = Path(args.run_dir)
    config_path = run_dir / "model_config.json"
    ckpt_path = Path(args.ckpt) if args.ckpt else latest_ckpt(run_dir)

    print(f"Loading model from: {ckpt_path}", file=sys.stderr)
    t0 = time.time()
    model = load_model(config_path, ckpt_path)
    print(f"  ({time.time() - t0:.1f}s)", file=sys.stderr)

    sp = spm.SentencePieceProcessor(model_file=str(args.tokenizer))

    # --- Perplexity on full valid stream ---
    print("Computing full-valid perplexity (sliding window)...", file=sys.stderr)
    tokens = np.load(args.token_cache, mmap_mode="r")
    n_valid = max(4096, int(len(tokens) * 0.02))
    valid_tokens = np.asarray(tokens[-n_valid:])
    t0 = time.time()
    val_ppl, val_n = compute_full_valid_ppl(
        model, valid_tokens, seq_len=model.cfg.max_seq_len
    )
    ppl_time = time.time() - t0
    print(f"  val_ppl = {val_ppl:.3f} over {val_n} tokens  ({ppl_time:.1f}s)",
          file=sys.stderr)

    # --- Raw generation probes ---
    generation_probes = []
    if not args.skip_generation and GENERATION_PROMPTS.exists():
        print("Running raw generation probes...", file=sys.stderr)
        with GENERATION_PROMPTS.open("r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                gen = generate(model, sp, row["prompt"],
                               max_new=args.max_new, temperature=args.temperature,
                               top_k=args.top_k)
                generation_probes.append({
                    "id": row["id"],
                    "prompt": row["prompt"],
                    "generation": gen,
                })

    report = {
        "checkpoint": str(ckpt_path),
        "checkpoint_sha256": sha256_file(ckpt_path),
        "config_path": str(config_path),
        "tokenizer": str(args.tokenizer),
        "tokenizer_sha256": sha256_file(Path(args.tokenizer)),
        "token_cache": str(args.token_cache),
        "val_ppl": round(val_ppl, 4),
        "val_tokens_scored": val_n,
        "temperature": args.temperature,
        "top_k": args.top_k,
        "generation_probes": generation_probes,
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
