#!/usr/bin/env python3
"""pt/train_byte.py — train TokenlessLM directly on UTF-8 bytes, in PyTorch.

Faithful port of scripts/train_byte.py (MLX). Same token contract (PAD=0, BOS=1,
EOS=2, byte → 3..258), same hyperparameters, same checkpoint format (safetensors
with parameter-name keys), same provenance JSONL. Runs on CPU or CUDA (Docker).

Intentionally loads no tokenizer and no pretrained weights.
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
import torch
import torch.nn.functional as F
from safetensors.torch import save_file, load_file

SCRIPT_DIR = Path(__file__).resolve().parent           # training/pt
sys.path.insert(0, str(SCRIPT_DIR))
from model import ModelConfig, TokenlessLM, init_weights  # noqa: E402

BYTE_VOCAB_SIZE = 259
TRAINING_DIR = SCRIPT_DIR.parent
TOKENLESS_HOME = Path(os.environ.get("TOKENLESS_HOME", str(TRAINING_DIR)))
RUNS_ROOT = TOKENLESS_HOME / "runs"
DEFAULT_CORPUS = TOKENLESS_HOME / "corpus" / "domain_corpus_v1" / "corpus.txt"
DEFAULT_CACHE = TOKENLESS_HOME / "corpus" / "domain_corpus_v1" / "tokens_byte_uint16.npy"


def pick_device(requested: str) -> torch.device:
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


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
    arr = np.frombuffer(raw, dtype=np.uint8).astype(np.uint16) + 3   # byte → 3..258
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, arr)
    print(f"Byte-tokenized: {len(arr):,} tokens -> {cache}", file=sys.stderr)
    return arr


def make_split(tokens: np.ndarray, valid_frac: float = 0.02):
    n_valid = max(4096, int(len(tokens) * valid_frac))
    return tokens[:-n_valid], tokens[-n_valid:]


def sample_batch(tokens: np.ndarray, batch_size: int, seq_len: int,
                 rng: np.random.Generator, device: torch.device):
    max_start = len(tokens) - seq_len - 1
    starts = rng.integers(0, max_start, size=batch_size)
    x = np.stack([tokens[s:s + seq_len].astype(np.int64) for s in starts])
    y = np.stack([tokens[s + 1:s + seq_len + 1].astype(np.int64) for s in starts])
    return (torch.from_numpy(x).to(device), torch.from_numpy(y).to(device))


def loss_fn(model: TokenlessLM, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
    logits = model(inputs)                                  # [B, T, V]
    B, T, V = logits.shape
    return F.cross_entropy(logits.reshape(B * T, V), targets.reshape(B * T))


def cosine_lr(step: int, warmup: int, total: int, lr_max: float, lr_min: float) -> float:
    if step < warmup:
        return lr_max * (step + 1) / max(1, warmup)
    if step >= total:
        return lr_min
    progress = (step - warmup) / max(1, total - warmup)
    return lr_min + 0.5 * (lr_max - lr_min) * (1.0 + math.cos(math.pi * progress))


@torch.no_grad()
def evaluate(model: TokenlessLM, tokens: np.ndarray, seq_len: int, batches: int,
             rng: np.random.Generator, device: torch.device) -> float:
    model.eval()
    losses = []
    for _ in range(batches):
        x, y = sample_batch(tokens, 4, seq_len, rng, device)
        losses.append(float(loss_fn(model, x, y).item()))
    model.train()
    return float(np.mean(losses))


def _atomic_save_safetensors(state_dict, path: Path) -> None:
    """Write safetensors atomically: full file appears or nothing (crash-safe)."""
    tmp = path.with_name(path.name + ".tmp")
    save_file(state_dict, str(tmp))
    os.replace(str(tmp), str(path))


def _atomic_torch_save(obj, path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    torch.save(obj, str(tmp))
    os.replace(str(tmp), str(path))


def find_resumable(run_dir: Path):
    """Return (ckpt_safetensors, resume_pt_or_None, step). Prefers the newest checkpoint
    that has a matching resume state; falls back to weights-only if a save was interrupted."""
    cks = sorted(run_dir.glob("ckpt_step_*.safetensors"), reverse=True)
    for ck in cks:
        n = int(ck.stem.split("_")[-1])
        rp = run_dir / f"ckpt_step_{n:06d}.resume.pt"
        if rp.exists():
            return ck, rp, n
    if cks:                                  # weights exist but no resume state (rare)
        return cks[0], None, int(cks[0].stem.split("_")[-1])
    return None, None, 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="byte_v1_20m")
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
    parser.add_argument("--device", default="auto", help="auto|cpu|cuda")
    parser.add_argument("--force-retokenize", action="store_true")
    parser.add_argument("--no-bench", action="store_true")
    parser.add_argument("--resume", action="store_true",
                        help="auto-resume from the latest checkpoint in the run dir "
                             "(restores model + optimizer + RNG + step; safe after disruption)")
    args = parser.parse_args()

    device = pick_device(args.device)
    torch.manual_seed(args.seed)
    print(f"[device] {device}", file=sys.stderr)

    run_dir = RUNS_ROOT / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    cfg = ModelConfig(
        vocab_size=BYTE_VOCAB_SIZE, n_layers=args.n_layers, n_heads=args.n_heads,
        d_model=args.d_model, d_ffn=args.d_ffn, max_seq_len=args.seq_len,
    )
    (run_dir / "model_config.json").write_text(json.dumps(cfg.to_dict(), indent=2))
    (run_dir / "byte_vocab.json").write_text(json.dumps({
        "kind": "utf8_byte", "pad_id": 0, "bos_id": 1, "eos_id": 2,
        "byte_offset": 3, "vocab_size": BYTE_VOCAB_SIZE,
    }, indent=2))

    corpus_path = Path(args.corpus)
    token_cache_path = Path(args.token_cache)
    corpus_sha256 = sha256_file(corpus_path)
    tokens = tokenize_bytes(corpus_path, token_cache_path, args.force_retokenize)
    train_tokens, valid_tokens = make_split(tokens)
    print(f"Train tokens: {len(train_tokens):,}  Valid tokens: {len(valid_tokens):,}", file=sys.stderr)

    model = init_weights(TokenlessLM(cfg), cfg, seed=args.seed).to(device)
    model.train()
    n_params = model.num_params()
    print(f"Parameters: {n_params:,}", file=sys.stderr)

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.lr, betas=(0.9, 0.95), eps=1e-8,
        weight_decay=args.weight_decay,
    )

    rng = np.random.default_rng(args.seed)
    log_path = run_dir / "train_log.jsonl"
    start_time = time.time()
    tokens_seen = 0
    last_loss = None
    last_eval = None

    # --- Resume from the latest checkpoint (model + optimizer + RNG + step) ---
    start_step = 0
    log_mode = "w"
    if args.resume:
        ckpt, resume_pt, n = find_resumable(run_dir)
        if ckpt is not None:
            model.load_state_dict(load_file(str(ckpt)))
            if resume_pt is not None:
                st = torch.load(str(resume_pt), map_location=device, weights_only=False)
                optimizer.load_state_dict(st["optimizer"])
                try:
                    torch.set_rng_state(st["torch_rng"])
                except Exception:
                    pass
                if st.get("numpy_rng") is not None:
                    rng.bit_generator.state = st["numpy_rng"]
                tokens_seen = int(st.get("tokens_seen", 0))
                print(f"[resume] step {n}: model + optimizer + RNG restored ({ckpt.name})", file=sys.stderr)
            else:
                print(f"[resume] step {n}: weights restored (optimizer reset — save was interrupted)", file=sys.stderr)
            start_step = n
            log_mode = "a"
        else:
            print("[resume] no checkpoint found — starting fresh", file=sys.stderr)

    with log_path.open(log_mode, encoding="utf-8") as logf:
        logf.write(json.dumps({
            "event": "run_resume" if start_step else "run_start",
            "start_step": start_step, "framework": "pytorch", "device": str(device),
            "tokenization": "utf8_byte", "config": cfg.to_dict(), "iters": args.iters,
            "batch": args.batch, "seq_len": args.seq_len, "lr_max": args.lr,
            "lr_min": args.lr_min, "weight_decay": args.weight_decay, "n_params": n_params,
            "train_tokens": int(len(train_tokens)), "valid_tokens": int(len(valid_tokens)),
            "corpus": str(corpus_path), "corpus_sha256": corpus_sha256,
            "byte_vocab_sha256": sha256_file(run_dir / "byte_vocab.json"),
            "random_initialization": True, "pretrained_loaded": False,
        }) + "\n")
        logf.flush()

        for step in range(start_step, args.iters):
            lr = cosine_lr(step, args.warmup, args.iters, args.lr, args.lr_min)
            for grp in optimizer.param_groups:
                grp["lr"] = lr
            x, y = sample_batch(train_tokens, args.batch, args.seq_len, rng, device)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model, x, y)
            loss.backward()
            grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
            optimizer.step()
            last_loss = float(loss.item())
            tokens_seen += args.batch * args.seq_len

            if (step + 1) % args.log_every == 0 or step == 0:
                elapsed = time.time() - start_time
                row = {"event": "step", "step": step + 1, "loss": last_loss,
                       "grad_norm": float(grad_norm), "lr": lr,
                       "tok_s": round(tokens_seen / elapsed if elapsed else 0.0, 1),
                       "elapsed_s": round(elapsed, 1)}
                logf.write(json.dumps(row) + "\n"); logf.flush()
                print(f"step={row['step']:5d} loss={row['loss']:.4f} "
                      f"gn={row['grad_norm']:.3f} lr={lr:.2e}", flush=True)

            if (step + 1) % args.eval_every == 0:
                val_loss = evaluate(model, valid_tokens, args.seq_len, args.eval_batches, rng, device)
                row = {"event": "eval", "step": step + 1, "val_loss": val_loss,
                       "val_ppl": math.exp(val_loss)}
                last_eval = row
                logf.write(json.dumps(row) + "\n"); logf.flush()
                print(f"  ==> val_loss={row['val_loss']:.4f} val_ppl={row['val_ppl']:.2f}")

            if (step + 1) % args.save_every == 0 or step + 1 == args.iters:
                ckpt_path = run_dir / f"ckpt_step_{step+1:06d}.safetensors"
                _atomic_save_safetensors(
                    {k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
                    ckpt_path)
                # Resume state: optimizer + RNG + step (atomic). Keep the 2 most recent
                # so an interrupted save can still fall back to the prior step.
                resume_pt = run_dir / f"ckpt_step_{step+1:06d}.resume.pt"
                _atomic_torch_save({
                    "step": step + 1,
                    "optimizer": optimizer.state_dict(),
                    "torch_rng": torch.get_rng_state(),
                    "numpy_rng": rng.bit_generator.state,
                    "tokens_seen": tokens_seen,
                }, resume_pt)
                for _old in sorted(run_dir.glob("ckpt_step_*.resume.pt"), reverse=True)[2:]:
                    _old.unlink(missing_ok=True)
                ckpt_sha256 = sha256_file(ckpt_path)
                meta = {
                    "event": "checkpoint_metadata", "framework": "pytorch",
                    "run_id": args.run_id, "step": step + 1, "loss": last_loss,
                    "last_eval": last_eval,
                    "validation_perplexity": (last_eval or {}).get("val_ppl"),
                    "checkpoint": str(ckpt_path), "checkpoint_sha256": ckpt_sha256,
                    "model_config": cfg.to_dict(), "tokenization": "utf8_byte",
                    "vocab_size": BYTE_VOCAB_SIZE, "corpus": str(corpus_path),
                    "corpus_sha256": corpus_sha256,
                    "byte_vocab_sha256": sha256_file(run_dir / "byte_vocab.json"),
                    "random_initialization": True, "pretrained_loaded": False,
                }
                ckpt_path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n")
                logf.write(json.dumps({"event": "checkpoint", "step": step + 1,
                                       "path": str(ckpt_path), "sha256": ckpt_sha256}) + "\n")
                logf.flush()
                print(f"  SAVED {ckpt_path}", flush=True)

        logf.write(json.dumps({"event": "run_end",
                               "total_time_s": round(time.time() - start_time, 1),
                               "total_steps": args.iters,
                               "total_tokens_seen": tokens_seen}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
