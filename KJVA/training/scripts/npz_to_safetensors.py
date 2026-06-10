#!/usr/bin/env python3
"""
npz_to_safetensors.py — Convert MLX-native .npz adapter outputs to safetensors.

The XMIND C engine reads safetensors (open standard, no MLX runtime dependency).
MLX training outputs .npz natively. This converter is a thin bridge — keeps
runtime portable while letting training stay MLX-native on Apple Silicon.

Member-agnostic: pass --input/--output paths explicitly.

Usage:
    python npz_to_safetensors.py \\
        --input training/adapters/<member>/adapter.npz \\
        --output training/adapters/<member>/adapter.safetensors

Expected MLX npz key naming (low_rank PEFT exports use this convention):
    layers.<n>.attn.wq.lora_A   → 2D fp32 array
    layers.<n>.attn.wq.lora_B   → 2D fp32 array
    ...

PEFT-style names also accepted:
    base_model.model.layers.<n>.self_attn.q_proj.lora_A.weight
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("npz2st")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s :: %(message)s")


def write_safetensors(tensors: dict, out_path: Path, *, alpha: float = 16.0,
                      extra_metadata: Optional[dict] = None) -> int:
    """Write a {name: 2D float array} dict as a safetensors file the XMIND C engine
    can load (8-byte LE header length + JSON header + F32 payload). Non-2D tensors are
    skipped. Returns the number of tensors written.

    This is the single safetensors writer used by both the CLI and train_peft.py's
    save_adapter — so the train→export→XMIND absorption chain has exactly one format
    of record (no divergence between the converter and the trainer)."""
    import numpy as np

    header: dict = {
        "__metadata__": {
            "format":     "safetensors",
            "source":     "mlx_npz",
            "lora_alpha": str(alpha),
            **(extra_metadata or {}),
        }
    }
    payload = bytearray()
    offset = 0
    written = 0
    for k, v in tensors.items():
        arr = np.asarray(v).astype(np.float32, copy=False)
        if arr.ndim != 2:
            logger.warning("skipping non-2D tensor %s (ndim=%d)", k, arr.ndim)
            continue
        nbytes = arr.nbytes
        header[k] = {"dtype": "F32", "shape": list(arr.shape),
                     "data_offsets": [offset, offset + nbytes]}
        payload.extend(arr.tobytes(order="C"))
        offset += nbytes
        written += 1

    header_bytes = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(struct.pack("<Q", len(header_bytes)))
        f.write(header_bytes)
        f.write(payload)
    return written


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input",  required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--alpha",  type=float, default=16.0,
                   help="LoRA alpha for the metadata block (default 16)")
    args = p.parse_args()

    if not args.input.exists():
        logger.error("input not found: %s", args.input)
        return 2

    try:
        import numpy as np
    except ImportError:
        logger.error("numpy required: pip install numpy")
        return 2

    logger.info("loading %s", args.input)
    data = np.load(args.input, allow_pickle=False)
    tensors = {k: data[k] for k in data.files}
    logger.info("found %d arrays", len(tensors))

    written = write_safetensors(tensors, args.output, alpha=args.alpha)

    size_mb = args.output.stat().st_size / 1024 / 1024
    logger.info("✓ wrote %s (%.2f MB, %d tensors)", args.output, size_mb, written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
