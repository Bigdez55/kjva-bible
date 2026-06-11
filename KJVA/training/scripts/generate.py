#!/usr/bin/env python3
"""
generate.py - Sample text from a trained byte-level Tokenless checkpoint.

Token contract: PAD=0, BOS=1, EOS=2, byte b → token_id = b + 3.

Usage:
  python generate.py \
      --ckpt "$TOKENLESS_HOME/runs/byte_clean_v2/ckpt_step_003000.safetensors" \
      --config "$TOKENLESS_HOME/runs/byte_clean_v2/model_config.json" \
      --prompt "In the beginning" --max-tokens 200 --temperature 0.8
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import mlx.core as mx
from mlx.utils import tree_unflatten

sys.path.insert(0, str(Path(__file__).parent))
from model import ModelConfig, TokenlessLM  # noqa


SCRIPT_DIR = Path(__file__).resolve().parent
TOKENLESS_HOME = Path(os.environ.get("TOKENLESS_HOME", str(SCRIPT_DIR.parent)))

BOS = 1
EOS = 2


def encode_prompt(text: str) -> list[int]:
    return [BOS] + [b + 3 for b in text.encode("utf-8")]


def decode_token(token_id: int) -> bytes | None:
    if token_id < 3:
        return None
    return bytes([token_id - 3])


def load_model(config_path: Path, ckpt_path: Path) -> TokenlessLM:
    cfg_data = json.loads(config_path.read_text())
    cfg = ModelConfig(**cfg_data)
    model = TokenlessLM(cfg)
    weights = mx.load(str(ckpt_path))
    model.update(tree_unflatten(list(weights.items())))
    return model


def sample(logits: mx.array, temperature: float, top_k: int | None) -> mx.array:
    """logits: [V]; returns scalar int token id."""
    if temperature <= 0:
        return mx.argmax(logits)
    scaled = logits / temperature
    if top_k is not None and top_k > 0:
        top_vals = mx.topk(scaled, top_k)
        threshold = mx.min(top_vals)
        scaled = mx.where(
            scaled >= threshold,
            scaled,
            mx.full(scaled.shape, -1e9, dtype=scaled.dtype),
        )
    probs = mx.softmax(scaled, axis=-1)
    return mx.random.categorical(mx.log(probs + 1e-9))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--prompt", default="In the beginning")
    parser.add_argument("--max-tokens", type=int, default=200)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    mx.random.seed(args.seed)
    model = load_model(Path(args.config), Path(args.ckpt))
    ids = encode_prompt(args.prompt)
    tokens = mx.array(ids, dtype=mx.int32)[None, :]  # [1, T]

    print(f"Prompt: {args.prompt!r}")
    print("Generating...\n")
    print(args.prompt, end="", flush=True)

    # Rolling byte buffer for incremental UTF-8 decoding
    pending_bytes = bytearray()
    n_generated = 0

    for _ in range(args.max_tokens):
        if tokens.shape[1] > model.cfg.max_seq_len:
            tokens = tokens[:, -model.cfg.max_seq_len:]
        logits = model(tokens)[0, -1, :]
        next_id = int(sample(logits, args.temperature, args.top_k).item())
        if next_id == EOS:
            break
        tokens = mx.concatenate([tokens, mx.array([[next_id]])], axis=1)
        n_generated += 1
        b = decode_token(next_id)
        if b is not None:
            pending_bytes.extend(b)
            # Flush complete UTF-8 sequences
            try:
                text = pending_bytes.decode("utf-8")
                print(text, end="", flush=True)
                pending_bytes.clear()
            except UnicodeDecodeError:
                pass  # wait for the rest of the multi-byte sequence

    if pending_bytes:
        print(pending_bytes.decode("utf-8", errors="replace"), end="", flush=True)

    print(f"\n\n(generated {n_generated} tokens)")


if __name__ == "__main__":
    main()
