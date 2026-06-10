"""pt/export.py — export a PyTorch TokenlessLM checkpoint to safetensors → GGUF.

The torch state_dict keys are already the GGUF-mapping source keys (see pt/model.py),
so the existing `scripts/safetensors_to_gguf.py` consumes a torch-saved safetensors
file unchanged. This wrapper:
  1. writes weights.safetensors (+ model_config.json + byte_vocab.json) from a run dir
     or an explicit checkpoint, then
  2. invokes safetensors_to_gguf to emit the GGUF + sidecar consumed by XMIND.

Usage:
  python3 pt/export.py --run runs/byte_v1_20m --output gguf/model.gguf
  python3 pt/export.py --checkpoint runs/.../ckpt_step_005000.safetensors \
      --config runs/.../model_config.json --vocab runs/.../byte_vocab.json \
      --output gguf/model.gguf
"""
from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent           # training/pt
TRAINING_DIR = SCRIPT_DIR.parent                        # training
SCRIPTS_DIR = TRAINING_DIR / "scripts"


def _latest_ckpt(run_dir: Path) -> Path:
    cks = sorted(run_dir.glob("ckpt_step_*.safetensors"))
    if not cks:
        raise FileNotFoundError(f"no ckpt_step_*.safetensors in {run_dir}")
    return cks[-1]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", type=Path, default=None,
                   help="run dir containing ckpt_step_*.safetensors + model_config.json + byte_vocab.json")
    p.add_argument("--checkpoint", type=Path, default=None, help="explicit .safetensors checkpoint")
    p.add_argument("--config", type=Path, default=None, help="model_config.json (required with --checkpoint)")
    p.add_argument("--vocab", type=Path, default=None, help="byte_vocab.json (required with --checkpoint)")
    p.add_argument("--output", type=Path, required=True, help="output GGUF path")
    p.add_argument("--dtype", default="f32")
    p.add_argument("--name", default=None,
                   help="model identity for general.name (names a neutral base into a domain model)")
    p.add_argument("--domain", default=None, help="domain tag for general.domain")
    args = p.parse_args()

    if args.run:
        run = args.run
        ckpt = _latest_ckpt(run)
        config = run / "model_config.json"
        vocab = run / "byte_vocab.json"
    else:
        if not (args.checkpoint and args.config and args.vocab):
            print("[ERROR] provide --run OR (--checkpoint --config --vocab)", file=sys.stderr)
            return 2
        ckpt, config, vocab = args.checkpoint, args.config, args.vocab

    for required in (ckpt, config, vocab):
        if not required.exists():
            print(f"[ERROR] not found: {required}", file=sys.stderr)
            return 2

    print(f"[INFO] checkpoint : {ckpt}")
    print(f"[INFO] config     : {config}")
    print(f"[INFO] vocab      : {vocab}")
    print(f"[INFO] output     : {args.output}")

    # Reuse the canonical exporter unchanged (torch safetensors keys == mapping keys).
    sys.argv = [
        "safetensors_to_gguf.py",
        "--weights", str(ckpt),
        "--config", str(config),
        "--vocab", str(vocab),
        "--output", str(args.output),
        "--dtype", args.dtype,
    ]
    if args.name:
        sys.argv += ["--name", args.name]
    if args.domain:
        sys.argv += ["--domain", args.domain]
    runpy.run_path(str(SCRIPTS_DIR / "safetensors_to_gguf.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
