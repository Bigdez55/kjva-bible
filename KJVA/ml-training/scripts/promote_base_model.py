#!/usr/bin/env python3
"""
promote_base_model.py — Promote a completed training run into models/<NAME>/.

This is the canonical step that graduates a trained run into a reusable base
model. Every new project copies models/ and fine-tunes from models/<NAME>/weights.safetensors.

Usage:
  python promote_base_model.py --run-dir runs/kjv_byte_v1_20m --name KJVA
  python promote_base_model.py --run-dir runs/kjv_byte_v1_20m --name KJVA --ckpt runs/kjv_byte_v1_20m/ckpt_step_005000.safetensors

What it does:
  1. Copies the best/final checkpoint as models/<NAME>/weights.safetensors
  2. Copies model_config.json and byte_vocab.json
  3. Writes/updates models/<NAME>/model_card.json with eval scores + provenance
  4. Writes models/<NAME>/training_provenance.json with full run metadata
  5. Prints a READY banner
"""
from __future__ import annotations

import argparse
import json
import hashlib
import shutil
import sys
import time
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent
ML_TRAINING  = SCRIPT_DIR.parent
REPO_ROOT    = ML_TRAINING.parent
MODELS_DIR   = REPO_ROOT / "models"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def latest_ckpt(run_dir: Path) -> Path:
    ckpts = sorted(run_dir.glob("ckpt_step_*.safetensors"))
    if not ckpts:
        raise FileNotFoundError(f"No checkpoints found in {run_dir}")
    return ckpts[-1]


def infer_step(ckpt_path: Path) -> int:
    try:
        return int(ckpt_path.stem.split("_")[-1])
    except ValueError:
        return -1


def load_best_eval(run_dir: Path, step: int) -> dict:
    """Read the last eval entry at or before this step from train_log.jsonl."""
    log = run_dir / "train_log.jsonl"
    if not log.exists():
        return {}
    best = {}
    with log.open() as f:
        for line in f:
            try:
                row = json.loads(line)
                if row.get("event") == "eval" and row.get("step", 9999999) <= step:
                    best = row
            except Exception:
                pass
    return best


def load_bench(run_dir: Path, step: int) -> dict:
    """Load bench_step_XXXXXX.json for this checkpoint if it exists."""
    bench_file = run_dir / f"bench_step_{step:06d}.json"
    if bench_file.exists():
        try:
            return json.loads(bench_file.read_text())
        except Exception:
            pass
    # Fall back to benchmark_final.json in eval/
    eval_dir = ML_TRAINING / "eval" / run_dir.name
    final = eval_dir / "benchmark_final.json"
    if final.exists():
        try:
            return json.loads(final.read_text())
        except Exception:
            pass
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a training run to models/<NAME>")
    parser.add_argument("--run-dir", required=True,
                        help="Path to the training run directory")
    parser.add_argument("--name", required=True,
                        help="Model name (e.g. KJVA). Creates models/<NAME>/")
    parser.add_argument("--ckpt", default=None,
                        help="Specific checkpoint to promote (default: latest)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite weights if model already exists in models/")
    args = parser.parse_args()

    run_dir  = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = ML_TRAINING / run_dir
    if not run_dir.exists():
        print(f"[ERROR] Run dir not found: {run_dir}", file=sys.stderr)
        return 2

    ckpt_path = Path(args.ckpt) if args.ckpt else latest_ckpt(run_dir)
    if not ckpt_path.is_absolute():
        ckpt_path = ML_TRAINING / ckpt_path
    if not ckpt_path.exists():
        print(f"[ERROR] Checkpoint not found: {ckpt_path}", file=sys.stderr)
        return 2

    step      = infer_step(ckpt_path)
    model_dir = MODELS_DIR / args.name
    weights_dst = model_dir / "weights.safetensors"

    if weights_dst.exists() and not args.force:
        print(f"[ERROR] {weights_dst} already exists. Use --force to overwrite.", file=sys.stderr)
        return 2

    model_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Copy weights ───────────────────────────────────────────────────────
    print(f"Copying weights ({ckpt_path.stat().st_size / 1024**2:.1f} MB)...", file=sys.stderr)
    shutil.copy2(str(ckpt_path), str(weights_dst))
    weights_sha = sha256(weights_dst)
    print(f"  → {weights_dst}  sha256={weights_sha[:16]}…", file=sys.stderr)

    # ── 2. Copy config + vocab ────────────────────────────────────────────────
    for fname in ("model_config.json", "byte_vocab.json"):
        src = run_dir / fname
        if src.exists():
            shutil.copy2(str(src), str(model_dir / fname))
    print(f"  → model_config.json, byte_vocab.json", file=sys.stderr)

    # ── 3. Load eval + bench data ─────────────────────────────────────────────
    eval_data  = load_best_eval(run_dir, step)
    bench_data = load_bench(run_dir, step)

    bench_ppl = None
    if bench_data:
        bench_ppl = (bench_data.get("results", {}).get("full_perplexity", {}).get("ppl")
                     or bench_data.get("perplexity", {}).get("ppl"))

    # ── 4. Write / update model_card.json ────────────────────────────────────
    card_path = model_dir / "model_card.json"
    card: dict = {}
    if card_path.exists():
        try:
            card = json.loads(card_path.read_text())
        except Exception:
            pass

    cfg_path = run_dir / "model_config.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}

    card.update({
        "model_id":   args.name,
        "full_name":  card.get("full_name", f"{args.name} Base Model"),
        "version":    "1.0.0",
        "status":     "ready",
        "architecture": {
            "family":        "TokenlessLM",
            "tokenization":  "utf8_byte",
            **cfg,
        },
        "weights_file": "weights.safetensors",
        "weights_sha256": weights_sha,
        "weights_step": step,
        "eval": {
            "val_loss":        eval_data.get("val_loss"),
            "val_ppl":         eval_data.get("val_ppl"),
            "bench_ppl":       bench_ppl,
            "benchmarked_at":  bench_data.get("benchmarked_at"),
        },
        "usage": {
            "base_checkpoint":  f"models/{args.name}/weights.safetensors",
            "config":           f"models/{args.name}/model_config.json",
            "vocab":            f"models/{args.name}/byte_vocab.json",
            "peft_entry":       f"ml-training/scripts/train_peft.py --base-checkpoint models/{args.name}/weights.safetensors",
        },
        "promoted_at":       time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "promoted_from_run": str(run_dir),
        "provenance_file":   "training_provenance.json",
    })
    card_path.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
    print(f"  → model_card.json  (val_ppl={eval_data.get('val_ppl')}, bench_ppl={bench_ppl})",
          file=sys.stderr)

    # ── 5. Write training_provenance.json ─────────────────────────────────────
    # Collect all eval rows from training log
    eval_history = []
    log = run_dir / "train_log.jsonl"
    if log.exists():
        with log.open() as f:
            for line in f:
                try:
                    row = json.loads(line)
                    if row.get("event") in ("eval", "run_start", "run_end", "run_resume"):
                        eval_history.append(row)
                except Exception:
                    pass

    provenance = {
        "run_dir":         str(run_dir),
        "run_id":          run_dir.name,
        "checkpoint":      str(ckpt_path),
        "checkpoint_step": step,
        "weights_sha256":  weights_sha,
        "promoted_at":     card["promoted_at"],
        "eval_history":    eval_history[-20:],  # last 20 events
        "bench_summary":   {k: v for k, v in bench_data.items()
                            if k in ("summary", "benchmarked_at", "checkpoint_name")}
                            if bench_data else {},
    }
    prov_path = model_dir / "training_provenance.json"
    prov_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(f"  → training_provenance.json", file=sys.stderr)

    # ── Banner ────────────────────────────────────────────────────────────────
    print(f"""
{'='*60}
  READY  models/{args.name}/
  step   {step}
  params {cfg.get('n_layers','-')}L × d{cfg.get('d_model','-')}
  val_ppl {eval_data.get('val_ppl', 'n/a')}   bench_ppl {bench_ppl or 'n/a'}

  To fine-tune with PEFT:
    python ml-training/scripts/train_peft.py \\
      --method lora \\
      --base-checkpoint models/{args.name}/weights.safetensors \\
      --corpus ml-training/corpus/eng_kjv_apocrypha_v1/corpus.txt
{'='*60}
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
