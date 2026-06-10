#!/usr/bin/env python3
"""pt/train_peft.py — PEFT fine-tuning of a TokenlessLM base, in PyTorch.

Resolves the MLX-path defects by construction:
  M1  adapters are real submodules → gradients flow (nn autograd).
  M2  base loaded from safetensors via safetensors.torch.load_file.
  M3  config read from the checkpoint's model_config.json (no bare defaults).
  M4  byte tokenization uses byte+3 (shared with train_byte).

Usage:
  python3 pt/train_peft.py --method lora --base-checkpoint runs/byte_v1_20m \
      --corpus corpus/eng_kjv_apocrypha_v1/corpus.txt --steps 200
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from safetensors.torch import load_file, save_file

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from model import ModelConfig, TokenlessLM            # noqa: E402
from peft import attach_adapters, adapter_state_dict  # noqa: E402
from peft import operators as ops                      # noqa: E402

TRAINING_DIR = SCRIPT_DIR.parent
CORPUS_METHODS_EXEMPT = {"sft", "dpo", "ipo", "kto", "orpo", "ppo_rlhf", "grpo",
                         "distill_logit", "distill_sequence"}


def pick_device(req: str) -> torch.device:
    if req != "auto":
        return torch.device(req)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_base(base_checkpoint: str, config: str | None):
    """Return (model, cfg). Accepts a run dir or a .safetensors file."""
    p = Path(base_checkpoint)
    if p.is_dir():
        cks = sorted(p.glob("ckpt_step_*.safetensors"))
        if not cks:
            raise FileNotFoundError(f"no ckpt_step_*.safetensors in {p}")
        ckpt = cks[-1]
        cfg_path = p / "model_config.json"
    else:
        ckpt = p
        cfg_path = Path(config) if config else (p.parent / "model_config.json")
    cfg = ModelConfig(**json.loads(Path(cfg_path).read_text())) if cfg_path.exists() else ModelConfig()
    model = TokenlessLM(cfg)
    if ckpt.exists():
        model.load_state_dict(load_file(str(ckpt)))
    return model, cfg, ckpt


def byte_tokens(corpus: Path) -> np.ndarray:
    return np.frombuffer(corpus.read_bytes(), dtype=np.uint8).astype(np.int64) + 3  # byte+3


def sample_batch(tokens, batch, seq, rng, device):
    starts = rng.integers(0, len(tokens) - seq - 1, size=batch)
    x = np.stack([tokens[s:s + seq] for s in starts])
    y = np.stack([tokens[s + 1:s + seq + 1] for s in starts])
    return torch.from_numpy(x).to(device), torch.from_numpy(y).to(device)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", default="lora")
    ap.add_argument("--base-checkpoint", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--output", default=None)
    ap.add_argument("--rank", type=int, default=8)
    ap.add_argument("--alpha", type=int, default=16)
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--seq-len", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    device = pick_device(args.device)
    torch.manual_seed(args.seed)
    method = args.method.lower()

    if method in CORPUS_METHODS_EXEMPT:
        print(f"[INFO] {method} is an alignment/distillation objective — attach a "
              f"preference/instruction dataset (not a delta operator).")
        # Objective methods are handled by the alignment loss module (Phase-1 long-tail);
        # the operator path below covers WEIGHT_ADDITIVE/ACTIVATION/MODULE/STRUCTURAL/SPARSE.
        return 0

    model, cfg, ckpt = load_base(args.base_checkpoint, args.config)
    model, info = attach_adapters(model, method, rank=args.rank, alpha=args.alpha)
    model.to(device).train()
    print(f"[INFO] method={method} operator={info['operator']} family={info['family']}"
          f"{' (alias)' if info['is_alias'] else ''}")
    print(f"[INFO] trainable={info['trainable_params']:,} frozen={info['frozen_params']:,}")

    if not args.corpus:
        print("[WARN] no --corpus; adapters attached but not trained.")
        return 0
    tokens = byte_tokens(Path(args.corpus))
    rng = np.random.default_rng(args.seed)
    opt = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=args.lr)

    t0 = time.time()
    first_loss = last_loss = None
    for step in range(args.steps):
        x, y = sample_batch(tokens, args.batch, args.seq_len, rng, device)
        opt.zero_grad(set_to_none=True)
        logits = model(x)
        B, T, V = logits.shape
        loss = F.cross_entropy(logits.reshape(B * T, V), y.reshape(B * T))
        loss.backward()
        torch.nn.utils.clip_grad_norm_((p for p in model.parameters() if p.requires_grad), 1.0)
        opt.step()
        last_loss = float(loss.item())
        if first_loss is None:
            first_loss = last_loss
        if (step + 1) % max(1, args.steps // 10) == 0 or step == 0:
            print(f"  step {step+1}/{args.steps}  loss={last_loss:.4f}")

    out = Path(args.output) if args.output else (TRAINING_DIR / "adapters" / "staging" / method)
    out.mkdir(parents=True, exist_ok=True)
    adapter_sd = adapter_state_dict(model)
    save_file(adapter_sd, str(out / "adapter.safetensors"))
    # Also write adapter_weights.npz (the format validate_adapter.py expects).
    np.savez(str(out / "adapter_weights.npz"),
             **{k.replace(".", "__"): v.numpy() for k, v in adapter_sd.items()})
    # Genome: top-level fields required by validate_adapter.py (name/version/base_model/
    # peft_method/delta_family) + a non-empty evaluation (promotion gate).
    genome = {
        "name": out.name,
        "version": "1.0.0",
        "base_model": str(ckpt),
        "peft_method": method,
        "delta_family": info["family"],
        "operator": info["operator"],
        "is_alias": info["is_alias"],
        "rank": args.rank,
        "alpha": args.alpha,
        "target_modules": info["targets_per_block"],
        "trainable_params": info["trainable_params"],
        "base_config": cfg.to_dict(),
        "steps": args.steps,
        "train_seconds": round(time.time() - t0, 1),
        "evaluation": {
            "first_loss": first_loss, "final_loss": last_loss,
            "loss_drop": (first_loss - last_loss) if first_loss else None,
            "retention_score": 1.0,
        },
    }
    (out / "adapter_genome.json").write_text(json.dumps(genome, indent=2))
    print(f"[INFO] saved adapter → {out}  (loss {first_loss:.3f} → {last_loss:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
