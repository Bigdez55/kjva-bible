#!/usr/bin/env python3
"""
generate.py - Sample text from a trained Tokenless checkpoint.

Usage:
  python generate.py --ckpt "$TOKENLESS_HOME/runs/bpe_v1_20m/ckpt_step_005000.safetensors" \
                     --config "$TOKENLESS_HOME/runs/bpe_v1_20m/model_config.json" \
                     --prompt "Hello, world." --max-tokens 200 --temperature 0.8
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import mlx.core as mx
from mlx.utils import tree_unflatten
import sentencepiece as spm

sys.path.insert(0, str(Path(__file__).parent))
from model import ModelConfig, TokenlessLM  # noqa


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
TOKENLESS_HOME = Path(os.environ.get("TOKENLESS_HOME", str(SCRIPT_DIR.parent)))


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
    # sample one categorical
    return mx.random.categorical(mx.log(probs + 1e-9))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--tokenizer",
                        default=str(TOKENLESS_HOME / "tokenizer/bpe_v1_20m.model"))
    parser.add_argument("--prompt", default="Hello, world.")
    parser.add_argument("--max-tokens", type=int, default=200)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    mx.random.seed(args.seed)

    sp = spm.SentencePieceProcessor(model_file=args.tokenizer)
    model = load_model(Path(args.config), Path(args.ckpt))

    # Encode prompt
    ids = [sp.bos_id()] + sp.encode(args.prompt)
    tokens = mx.array(ids, dtype=mx.int32)[None, :]  # [1, T]

    print(f"Prompt: {args.prompt!r}")
    print("Generating...", flush=True)
    print()
    print(args.prompt, end="", flush=True)

    for _ in range(args.max_tokens):
        # feed full context (simple, slow; ok for small runs)
        T = tokens.shape[1]
        if T > model.cfg.max_seq_len:
            tokens = tokens[:, -model.cfg.max_seq_len:]
        logits = model(tokens)[0, -1, :]           # [V]
        next_id = int(sample(logits, args.temperature, args.top_k).item())
        if next_id == sp.eos_id():
            break
        tokens = mx.concatenate([tokens, mx.array([[next_id]])], axis=1)
        piece = sp.id_to_piece(next_id)
        # sentencepiece uses U+2581 for leading space
        text_piece = piece.replace("\u2581", " ")
        print(text_piece, end="", flush=True)

    print()
    print()
    print(f"(generated {tokens.shape[1] - len(ids)} tokens)")


if __name__ == "__main__":
    main()
