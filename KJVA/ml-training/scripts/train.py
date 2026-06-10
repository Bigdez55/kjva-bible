#!/usr/bin/env python3
"""
train.py - From-scratch training for the KJV Tokenless BPE baseline.
Pure MLX. No pretrained weights. No transformers library.

Data flow:
  corpus.txt -> tokenize once -> token stream cached to .npy
  random window [T+1] samples -> batches of shape [B, T]
  forward -> cross-entropy -> backward -> AdamW update
  cosine LR with warmup, gradient clipping, RMSNorm, SwiGLU, RoPE.

Checkpoints:
  $TOKENLESS_HOME/runs/<run_id>/ckpt_step_<step>.safetensors
  $TOKENLESS_HOME/runs/<run_id>/model_config.json
  $TOKENLESS_HOME/runs/<run_id>/train_log.jsonl

Usage:
  python train.py --run-id=kjv_bpe_v1_20m --iters=10000 --batch=8 --seq-len=512
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
import mlx.optimizers as optim
from mlx.utils import tree_flatten, tree_map

import sentencepiece as spm

sys.path.insert(0, str(Path(__file__).parent))
from model import ModelConfig, TokenlessLM, init_weights  # noqa


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
TOKENLESS_HOME = Path(os.environ.get("TOKENLESS_HOME", str(REPO_ROOT / "ml-training")))
CORPUS_FILE = TOKENLESS_HOME / "corpus" / "eng_kjv_apocrypha_v1" / "corpus.txt"
TOKENIZER_MODEL = TOKENLESS_HOME / "tokenizer" / "kjv_bpe_v1_20m.model"
TOKEN_CACHE = TOKENLESS_HOME / "corpus" / "eng_kjv_apocrypha_v1" / "tokens_bpe_uint32.npy"
RUNS_ROOT = TOKENLESS_HOME / "runs"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def tokenize_corpus(corpus: Path, tokenizer_model: Path,
                    cache: Path, force: bool = False) -> np.ndarray:
    """Tokenize the corpus once and cache to .npy for fast reload."""
    if cache.exists() and not force:
        data = np.load(cache, mmap_mode="r")
        print(f"Loaded cached tokens: {data.shape[0]:,} tokens from {cache}",
              file=sys.stderr)
        return data

    print(f"Tokenizing corpus: {corpus}", file=sys.stderr)
    sp = spm.SentencePieceProcessor(model_file=str(tokenizer_model))
    raw = corpus.read_text(encoding="utf-8")
    ids = sp.encode(raw)
    arr = np.array(ids, dtype=np.uint32)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, arr)
    print(f"Tokenized: {len(arr):,} tokens -> {cache}", file=sys.stderr)
    return arr


def make_split(tokens: np.ndarray, valid_frac: float = 0.02
               ) -> tuple[np.ndarray, np.ndarray]:
    n_valid = max(4096, int(len(tokens) * valid_frac))
    train = tokens[:-n_valid]
    valid = tokens[-n_valid:]
    return train, valid


def sample_batch(tokens: np.ndarray, batch_size: int, seq_len: int,
                 rng: np.random.Generator) -> tuple[mx.array, mx.array]:
    """Returns (input, target) mx.arrays of shape [B, T]."""
    # pick B random start offsets
    max_start = len(tokens) - seq_len - 1
    starts = rng.integers(0, max_start, size=batch_size)
    x = np.stack([tokens[s:s + seq_len].astype(np.int32) for s in starts])
    y = np.stack([tokens[s + 1:s + seq_len + 1].astype(np.int32) for s in starts])
    return mx.array(x), mx.array(y)


# ---------------------------------------------------------------------------
# Loss
# ---------------------------------------------------------------------------

def loss_fn(model: TokenlessLM, inputs: mx.array, targets: mx.array) -> mx.array:
    logits = model(inputs)                              # [B, T, V]
    # cross-entropy
    log_probs = nn.log_softmax(logits, axis=-1)
    # gather target log-probs
    T_ = targets[..., None]                             # [B, T, 1]
    nll = -mx.take_along_axis(log_probs, T_, axis=-1).squeeze(-1)   # [B, T]
    return nll.mean()


# ---------------------------------------------------------------------------
# LR schedule
# ---------------------------------------------------------------------------

def cosine_lr(step: int, warmup: int, total: int, lr_max: float, lr_min: float
              ) -> float:
    if step < warmup:
        return lr_max * (step + 1) / max(1, warmup)
    if step >= total:
        return lr_min
    progress = (step - warmup) / max(1, total - warmup)
    return lr_min + 0.5 * (lr_max - lr_min) * (1.0 + math.cos(math.pi * progress))


# ---------------------------------------------------------------------------
# Gradient clipping
# ---------------------------------------------------------------------------

def clip_grads(grads, max_norm: float) -> tuple:
    flat = tree_flatten(grads)
    sq_sum = mx.array(0.0)
    for _, g in flat:
        sq_sum = sq_sum + (g * g).sum()
    total_norm = mx.sqrt(sq_sum)
    scale = mx.minimum(mx.array(1.0), max_norm / (total_norm + 1e-6))
    return tree_map(lambda g: g * scale, grads), total_norm


# ---------------------------------------------------------------------------
# Eval
# ---------------------------------------------------------------------------

def evaluate(model: TokenlessLM, tokens: np.ndarray, seq_len: int,
             batches: int, rng: np.random.Generator) -> float:
    losses = []
    model.eval() if hasattr(model, "eval") else None
    for _ in range(batches):
        x, y = sample_batch(tokens, 4, seq_len, rng)
        loss = loss_fn(model, x, y)
        mx.eval(loss)
        losses.append(float(loss.item()))
    model.train() if hasattr(model, "train") else None
    return float(np.mean(losses))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="kjv_bpe_v1_20m")
    parser.add_argument("--corpus", default=str(CORPUS_FILE))
    parser.add_argument("--tokenizer", default=str(TOKENIZER_MODEL))
    parser.add_argument("--token-cache", default=str(TOKEN_CACHE))
    parser.add_argument("--iters", type=int, default=5000)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--seq-len", type=int, default=512)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--lr-min", type=float, default=3e-5)
    parser.add_argument("--warmup", type=int, default=200)
    parser.add_argument("--weight-decay", type=float, default=0.1)
    parser.add_argument("--grad-clip", type=float, default=1.0)
    parser.add_argument("--log-every", type=int, default=10)
    parser.add_argument("--eval-every", type=int, default=200)
    parser.add_argument("--eval-batches", type=int, default=10)
    parser.add_argument("--save-every", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    # Architecture (override defaults in ModelConfig)
    parser.add_argument("--n-layers", type=int, default=6)
    parser.add_argument("--d-model", type=int, default=384)
    parser.add_argument("--n-heads", type=int, default=6)
    parser.add_argument("--d-ffn", type=int, default=1536)
    parser.add_argument("--force-retokenize", action="store_true")
    args = parser.parse_args()

    run_dir = RUNS_ROOT / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Tokenizer
    sp = spm.SentencePieceProcessor(model_file=args.tokenizer)
    vocab_size = sp.vocab_size()
    print(f"Tokenizer vocab: {vocab_size}", file=sys.stderr)

    # Config
    cfg = ModelConfig(
        vocab_size=vocab_size,
        n_layers=args.n_layers,
        n_heads=args.n_heads,
        d_model=args.d_model,
        d_ffn=args.d_ffn,
        max_seq_len=args.seq_len,
    )
    (run_dir / "model_config.json").write_text(json.dumps(cfg.to_dict(), indent=2))

    # Tokens
    corpus_path = Path(args.corpus)
    tokenizer_path = Path(args.tokenizer)
    token_cache_path = Path(args.token_cache)
    corpus_sha256 = sha256_file(corpus_path)
    tokenizer_sha256 = sha256_file(tokenizer_path)
    tokens = tokenize_corpus(corpus_path, tokenizer_path, token_cache_path,
                             force=args.force_retokenize)
    train_tokens, valid_tokens = make_split(tokens, valid_frac=0.02)
    print(f"Train tokens: {len(train_tokens):,}", file=sys.stderr)
    print(f"Valid tokens: {len(valid_tokens):,}", file=sys.stderr)

    # Model
    mx.random.seed(args.seed)
    model = TokenlessLM(cfg)
    model = init_weights(model, cfg, seed=args.seed)
    n_params = model.num_params()
    print(f"Parameters: {n_params:,}  (~{n_params / 1e6:.1f} M)", file=sys.stderr)

    # Optimizer (AdamW)
    optimizer = optim.AdamW(
        learning_rate=args.lr,
        betas=[0.9, 0.95],
        eps=1e-8,
        weight_decay=args.weight_decay,
    )

    # Training step (compiled for speed)
    loss_and_grad = nn.value_and_grad(model, loss_fn)

    def step_fn(x: mx.array, y: mx.array, lr: float):
        loss, grads = loss_and_grad(model, x, y)
        grads, grad_norm = clip_grads(grads, args.grad_clip)
        optimizer.learning_rate = lr
        optimizer.update(model, grads)
        return loss, grad_norm

    # Data sampler RNG
    rng = np.random.default_rng(args.seed)

    log_path = run_dir / "train_log.jsonl"
    print(f"Log:    {log_path}", file=sys.stderr)
    print(f"Run:    {run_dir}", file=sys.stderr)
    print("-" * 80, file=sys.stderr)

    start_time = time.time()
    tokens_seen = 0
    last_loss: float | None = None
    last_eval: dict | None = None

    with log_path.open("w", encoding="utf-8") as logf:
        # Record run-header
        logf.write(json.dumps({
            "event": "run_start",
            "tokenization": "sentencepiece_bpe",
            "config": cfg.to_dict(),
            "iters": args.iters,
            "batch": args.batch,
            "seq_len": args.seq_len,
            "lr_max": args.lr,
            "lr_min": args.lr_min,
            "weight_decay": args.weight_decay,
            "n_params": n_params,
            "train_tokens": int(len(train_tokens)),
            "valid_tokens": int(len(valid_tokens)),
            "corpus": str(corpus_path),
            "corpus_sha256": corpus_sha256,
            "tokenizer": str(tokenizer_path),
            "tokenizer_sha256": tokenizer_sha256,
            "token_cache": str(token_cache_path),
            "random_initialization": True,
            "pretrained_loaded": False,
        }) + "\n")
        logf.flush()

        for step in range(args.iters):
            lr = cosine_lr(step, args.warmup, args.iters, args.lr, args.lr_min)
            x, y = sample_batch(train_tokens, args.batch, args.seq_len, rng)
            loss, grad_norm = step_fn(x, y, lr)
            mx.eval(loss, grad_norm, model.parameters(), optimizer.state)
            last_loss = float(loss.item())
            tokens_seen += args.batch * args.seq_len

            if (step + 1) % args.log_every == 0 or step == 0:
                elapsed = time.time() - start_time
                tok_s = tokens_seen / elapsed if elapsed > 0 else 0.0
                row = {
                    "event": "step",
                    "step": step + 1,
                    "loss": last_loss,
                    "grad_norm": float(grad_norm.item()),
                    "lr": lr,
                    "tok_s": round(tok_s, 1),
                    "elapsed_s": round(elapsed, 1),
                }
                logf.write(json.dumps(row) + "\n")
                logf.flush()
                print(f"step={step+1:5d}  loss={row['loss']:.4f}  "
                      f"gn={row['grad_norm']:.3f}  lr={lr:.2e}  "
                      f"tok/s={row['tok_s']:.0f}", flush=True)

            if (step + 1) % args.eval_every == 0:
                val_loss = evaluate(model, valid_tokens, args.seq_len,
                                    args.eval_batches, rng)
                val_ppl = math.exp(val_loss)
                row = {
                    "event": "eval",
                    "step": step + 1,
                    "val_loss": val_loss,
                    "val_ppl": val_ppl,
                }
                last_eval = row
                logf.write(json.dumps(row) + "\n")
                logf.flush()
                print(f"  ==> val_loss={val_loss:.4f}  val_ppl={val_ppl:.2f}",
                      flush=True)

            if (step + 1) % args.save_every == 0 or step + 1 == args.iters:
                ckpt_path = run_dir / f"ckpt_step_{step+1:06d}.safetensors"
                flat = tree_flatten(model.parameters())
                mx.save_safetensors(str(ckpt_path), dict(flat))
                ckpt_sha256 = sha256_file(ckpt_path)
                ckpt_meta = {
                    "event": "checkpoint_metadata",
                    "run_id": args.run_id,
                    "step": step + 1,
                    "loss": last_loss,
                    "last_eval": last_eval,
                    "validation_perplexity": (
                        last_eval.get("val_ppl") if last_eval else None
                    ),
                    "checkpoint": str(ckpt_path),
                    "checkpoint_sha256": ckpt_sha256,
                    "model_config": cfg.to_dict(),
                    "tokenization": "sentencepiece_bpe",
                    "vocab_size": vocab_size,
                    "corpus": str(corpus_path),
                    "corpus_sha256": corpus_sha256,
                    "tokenizer": str(tokenizer_path),
                    "tokenizer_sha256": tokenizer_sha256,
                    "token_cache": str(token_cache_path),
                    "random_initialization": True,
                    "pretrained_loaded": False,
                }
                meta_path = ckpt_path.with_suffix(".meta.json")
                meta_path.write_text(json.dumps(ckpt_meta, indent=2) + "\n",
                                     encoding="utf-8")
                print(f"  SAVED {ckpt_path}", flush=True)
                logf.write(json.dumps({
                    "event": "checkpoint",
                    "step": step + 1,
                    "path": str(ckpt_path),
                    "sha256": ckpt_sha256,
                    "metadata": str(meta_path),
                }) + "\n")
                logf.flush()

        logf.write(json.dumps({
            "event": "run_end",
            "total_time_s": round(time.time() - start_time, 1),
            "total_steps": args.iters,
            "total_tokens_seen": tokens_seen,
        }) + "\n")

    print("DONE.")


if __name__ == "__main__":
    main()
