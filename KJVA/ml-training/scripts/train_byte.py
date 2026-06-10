#!/usr/bin/env python3
"""Train TokenlessLM directly on UTF-8 bytes.

Token contract:
  PAD=0, BOS=1, EOS=2, byte tokens map to 3..258.

This intentionally does not load a tokenizer or pretrained model.
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

sys.path.insert(0, str(Path(__file__).parent))
from model import ModelConfig, TokenlessLM, init_weights  # noqa
from ckpt_bench import run_checkpoint_bench, run_final_bench  # noqa


BYTE_VOCAB_SIZE = 259
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
TOKENLESS_HOME = Path(os.environ.get("TOKENLESS_HOME", str(REPO_ROOT / "ml-training")))
RUNS_ROOT = TOKENLESS_HOME / "runs"
DEFAULT_CORPUS = TOKENLESS_HOME / "corpus" / "eng_kjv_apocrypha_v1" / "corpus.txt"
DEFAULT_CACHE = TOKENLESS_HOME / "corpus" / "eng_kjv_apocrypha_v1" / "tokens_byte_uint16.npy"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tokenize_bytes(corpus: Path, cache: Path, force: bool = False) -> np.ndarray:
    if cache.exists() and not force:
        arr = np.load(cache, mmap_mode="r")
        print(f"Loaded cached byte tokens: {arr.shape[0]:,} from {cache}", file=sys.stderr)
        return arr
    raw = corpus.read_bytes()
    arr = np.frombuffer(raw, dtype=np.uint8).astype(np.uint16) + 3
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, arr)
    print(f"Byte-tokenized: {len(arr):,} tokens -> {cache}", file=sys.stderr)
    return arr


def make_split(tokens: np.ndarray, valid_frac: float = 0.02) -> tuple[np.ndarray, np.ndarray]:
    n_valid = max(4096, int(len(tokens) * valid_frac))
    return tokens[:-n_valid], tokens[-n_valid:]


def sample_batch(tokens: np.ndarray, batch_size: int, seq_len: int,
                 rng: np.random.Generator) -> tuple[mx.array, mx.array]:
    max_start = len(tokens) - seq_len - 1
    starts = rng.integers(0, max_start, size=batch_size)
    x = np.stack([tokens[s:s + seq_len].astype(np.int32) for s in starts])
    y = np.stack([tokens[s + 1:s + seq_len + 1].astype(np.int32) for s in starts])
    return mx.array(x), mx.array(y)


def loss_fn(model: TokenlessLM, inputs: mx.array, targets: mx.array) -> mx.array:
    logits = model(inputs)
    log_probs = nn.log_softmax(logits, axis=-1)
    nll = -mx.take_along_axis(log_probs, targets[..., None], axis=-1).squeeze(-1)
    return nll.mean()


def cosine_lr(step: int, warmup: int, total: int, lr_max: float, lr_min: float) -> float:
    if step < warmup:
        return lr_max * (step + 1) / max(1, warmup)
    if step >= total:
        return lr_min
    progress = (step - warmup) / max(1, total - warmup)
    return lr_min + 0.5 * (lr_max - lr_min) * (1.0 + math.cos(math.pi * progress))


def clip_grads(grads, max_norm: float) -> tuple:
    flat = tree_flatten(grads)
    sq_sum = mx.array(0.0)
    for _, g in flat:
        sq_sum = sq_sum + (g * g).sum()
    total_norm = mx.sqrt(sq_sum)
    scale = mx.minimum(mx.array(1.0), max_norm / (total_norm + 1e-6))
    return tree_map(lambda g: g * scale, grads), total_norm


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="kjv_byte_v1_20m")
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--token-cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--iters", type=int, default=5000)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--seq-len", type=int, default=1024)
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
    parser.add_argument("--n-layers", type=int, default=8)
    parser.add_argument("--d-model", type=int, default=384)
    parser.add_argument("--n-heads", type=int, default=6)
    parser.add_argument("--d-ffn", type=int, default=1536)
    parser.add_argument("--force-retokenize", action="store_true")
    parser.add_argument("--no-bench", action="store_true",
                        help="Disable inline checkpoint benchmarks and final full bench")
    parser.add_argument("--resume", action="store_true",
                        help="Auto-load latest checkpoint in the run dir and continue")
    parser.add_argument("--load-checkpoint", default=None,
                        help="Explicit checkpoint .safetensors path to resume from")
    parser.add_argument("--start-step", type=int, default=None,
                        help="Override the step offset when resuming (inferred from filename if omitted)")
    args = parser.parse_args()

    run_dir = RUNS_ROOT / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    cfg = ModelConfig(
        vocab_size=BYTE_VOCAB_SIZE,
        n_layers=args.n_layers,
        n_heads=args.n_heads,
        d_model=args.d_model,
        d_ffn=args.d_ffn,
        max_seq_len=args.seq_len,
    )
    (run_dir / "model_config.json").write_text(json.dumps(cfg.to_dict(), indent=2))
    (run_dir / "byte_vocab.json").write_text(json.dumps({
        "kind": "utf8_byte",
        "pad_id": 0,
        "bos_id": 1,
        "eos_id": 2,
        "byte_offset": 3,
        "vocab_size": BYTE_VOCAB_SIZE,
    }, indent=2))

    corpus_path = Path(args.corpus)
    token_cache_path = Path(args.token_cache)
    corpus_sha256 = sha256_file(corpus_path)
    tokens = tokenize_bytes(corpus_path, token_cache_path, args.force_retokenize)
    train_tokens, valid_tokens = make_split(tokens)
    print(f"Train tokens: {len(train_tokens):,}", file=sys.stderr)
    print(f"Valid tokens: {len(valid_tokens):,}", file=sys.stderr)

    mx.random.seed(args.seed)
    model = init_weights(TokenlessLM(cfg), cfg, seed=args.seed)
    n_params = model.num_params()
    print(f"Parameters: {n_params:,}", file=sys.stderr)

    # --- Resume logic ---
    ckpt_to_load = args.load_checkpoint
    if args.resume and ckpt_to_load is None:
        candidates = sorted(run_dir.glob("ckpt_step_*.safetensors"))
        if candidates:
            ckpt_to_load = str(candidates[-1])
            print(f"[resume] Auto-detected checkpoint: {ckpt_to_load}", file=sys.stderr)
        else:
            print("[resume] No checkpoints found — starting from scratch.", file=sys.stderr)

    start_step = 0
    if ckpt_to_load:
        ckpt_path_obj = Path(ckpt_to_load)
        weights = mx.load(str(ckpt_path_obj))
        model.load_weights(list(weights.items()))
        mx.eval(model.parameters())
        if args.start_step is not None:
            start_step = args.start_step
        else:
            # Infer from filename: ckpt_step_004000.safetensors → 4000
            stem = ckpt_path_obj.stem  # "ckpt_step_004000"
            try:
                start_step = int(stem.split("_")[-1])
            except ValueError:
                pass
        print(f"[resume] Loaded weights from step {start_step}. Continuing from step {start_step + 1}.", file=sys.stderr)
    # --- End resume logic ---

    optimizer = optim.AdamW(
        learning_rate=args.lr,
        betas=[0.9, 0.95],
        eps=1e-8,
        weight_decay=args.weight_decay,
    )
    loss_and_grad = nn.value_and_grad(model, loss_fn)

    def step_fn(x: mx.array, y: mx.array, lr: float):
        loss, grads = loss_and_grad(model, x, y)
        grads, grad_norm = clip_grads(grads, args.grad_clip)
        optimizer.learning_rate = lr
        optimizer.update(model, grads)
        return loss, grad_norm

    rng = np.random.default_rng(args.seed)
    log_path = run_dir / "train_log.jsonl"
    start_time = time.time()
    tokens_seen = 0
    last_loss: float | None = None
    last_eval: dict | None = None

    log_mode = "a" if start_step > 0 else "w"
    with log_path.open(log_mode, encoding="utf-8") as logf:
        logf.write(json.dumps({
            "event": "run_resume" if start_step > 0 else "run_start",
            "tokenization": "utf8_byte",
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
            "token_cache": str(token_cache_path),
            "byte_vocab_sha256": sha256_file(run_dir / "byte_vocab.json"),
            "random_initialization": True,
            "pretrained_loaded": False,
        }) + "\n")
        logf.flush()

        for step in range(start_step, args.iters):
            lr = cosine_lr(step, args.warmup, args.iters, args.lr, args.lr_min)
            x, y = sample_batch(train_tokens, args.batch, args.seq_len, rng)
            loss, grad_norm = step_fn(x, y, lr)
            mx.eval(loss, grad_norm, model.parameters(), optimizer.state)
            last_loss = float(loss.item())
            tokens_seen += args.batch * args.seq_len

            if (step + 1) % args.log_every == 0 or step == 0:
                elapsed = time.time() - start_time
                row = {
                    "event": "step",
                    "step": step + 1,
                    "loss": last_loss,
                    "grad_norm": float(grad_norm.item()),
                    "lr": lr,
                    "tok_s": round(tokens_seen / elapsed if elapsed else 0.0, 1),
                    "elapsed_s": round(elapsed, 1),
                }
                logf.write(json.dumps(row) + "\n")
                logf.flush()
                print(f"step={row['step']:5d} loss={row['loss']:.4f} "
                      f"gn={row['grad_norm']:.3f} lr={lr:.2e}", flush=True)

            if (step + 1) % args.eval_every == 0:
                val_loss = evaluate(model, valid_tokens, args.seq_len, args.eval_batches, rng)
                row = {
                    "event": "eval",
                    "step": step + 1,
                    "val_loss": val_loss,
                    "val_ppl": math.exp(val_loss),
                }
                last_eval = row
                logf.write(json.dumps(row) + "\n")
                logf.flush()
                print(f"  ==> val_loss={row['val_loss']:.4f} val_ppl={row['val_ppl']:.2f}")

            if (step + 1) % args.save_every == 0 or step + 1 == args.iters:
                ckpt_path = run_dir / f"ckpt_step_{step+1:06d}.safetensors"
                mx.save_safetensors(str(ckpt_path), dict(tree_flatten(model.parameters())))
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
                    "tokenization": "utf8_byte",
                    "vocab_size": BYTE_VOCAB_SIZE,
                    "corpus": str(corpus_path),
                    "corpus_sha256": corpus_sha256,
                    "token_cache": str(token_cache_path),
                    "byte_vocab": str(run_dir / "byte_vocab.json"),
                    "byte_vocab_sha256": sha256_file(run_dir / "byte_vocab.json"),
                    "random_initialization": True,
                    "pretrained_loaded": False,
                }
                meta_path = ckpt_path.with_suffix(".meta.json")
                meta_path.write_text(json.dumps(ckpt_meta, indent=2) + "\n",
                                     encoding="utf-8")
                logf.write(json.dumps({
                    "event": "checkpoint",
                    "step": step + 1,
                    "path": str(ckpt_path),
                    "sha256": ckpt_sha256,
                    "metadata": str(meta_path),
                }) + "\n")
                logf.flush()
                print(f"  SAVED {ckpt_path}", flush=True)
                if not args.no_bench:
                    run_checkpoint_bench(
                        model, valid_tokens, run_dir,
                        step=step + 1, seq_len=args.seq_len, label="byte",
                    )

        logf.write(json.dumps({
            "event": "run_end",
            "total_time_s": round(time.time() - start_time, 1),
            "total_steps": args.iters,
            "total_tokens_seen": tokens_seen,
        }) + "\n")

    if not args.no_bench:
        final_ckpt = run_dir / f"ckpt_step_{args.iters:06d}.safetensors"
        run_final_bench(run_dir, ckpt_path=final_ckpt if final_ckpt.exists() else None)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
