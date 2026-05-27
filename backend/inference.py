"""
inference.py — KJVA model loader and byte-level text completion.

Loads weights once at startup (lazy, on first request). All generation
runs on Apple Silicon via MLX. No GPU required; unified memory handles
the 18M-param model comfortably.

Byte encoding:
  PAD=0, BOS=1, EOS=2, byte N → token N+3  (byte_offset=3)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

# MLX is Apple-Silicon only. Per ADR-0003, the retrieval path must work in
# linux/amd64 containers and CI where MLX is absent. We import lazily and
# degrade is_ready() to False when the runtime is missing.
try:
    import mlx.core as mx
    import mlx.nn as nn  # noqa: F401  (loaded for model module side effects)
    from model import ModelConfig, TokenlessLM
    _MLX_AVAILABLE = True
except ImportError:
    mx = None
    ModelConfig = None
    TokenlessLM = None
    _MLX_AVAILABLE = False

# Weights are gitignored (72 MB .safetensors). Layout:
#   KJVA/training/weights.safetensors   ← gitignored
#   KJVA/training/model_config.json
#   KJVA/training/byte_vocab.json
_MODELS_DIR = Path(__file__).parent.parent / "KJVA" / "training"

PAD_ID = 0
BOS_ID = 1
EOS_ID = 2
BYTE_OFFSET = 3  # byte value b → token id b + 3


def _encode(text: str) -> list[int]:
    return [BOS_ID] + [b + BYTE_OFFSET for b in text.encode("utf-8")]


def _decode(token_ids: list[int]) -> str:
    raw = bytes(
        t - BYTE_OFFSET for t in token_ids
        if t not in (PAD_ID, BOS_ID, EOS_ID) and t >= BYTE_OFFSET
    )
    return raw.decode("utf-8", errors="replace")


class KJVAInference:
    def __init__(self):
        self._model = None
        self._cfg = None
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        if not _MLX_AVAILABLE:
            raise RuntimeError(
                "MLX runtime not installed. AI completion requires Apple Silicon + mlx>=0.16.0. "
                "Retrieval-only mode is still available — see ADR-0003."
            )
        weights_path = _MODELS_DIR / "weights.safetensors"
        config_path  = _MODELS_DIR / "model_config.json"
        if not weights_path.exists():
            raise RuntimeError(
                f"KJVA weights not found at {weights_path}.\n"
                "Expected: KJVA/training/weights.safetensors (gitignored, 72 MB).\n"
                "This file ships with the KJVA directory that was moved from Tokenless Models."
            )
        with open(config_path) as f:
            cfg_dict = json.load(f)
        cfg = ModelConfig(**cfg_dict)
        self._cfg = cfg
        model = TokenlessLM(cfg)
        weights = mx.load(str(weights_path))
        model.load_weights(list(weights.items()))
        mx.eval(model.parameters())
        model.freeze()
        self._model = model
        self._loaded = True

    def is_ready(self) -> bool:
        return _MLX_AVAILABLE and (_MODELS_DIR / "weights.safetensors").exists()

    def complete(
        self,
        prompt: str,
        max_new_tokens: int = 200,
        temperature: float = 0.8,
        top_p: float = 0.9,
    ) -> str:
        self._load()
        model = self._model
        cfg = self._cfg

        token_ids = _encode(prompt)
        # Truncate context to max_seq_len - max_new_tokens to leave room
        max_ctx = cfg.max_seq_len - max_new_tokens
        if len(token_ids) > max_ctx:
            token_ids = token_ids[-max_ctx:]

        generated: list[int] = []
        ctx = mx.array([token_ids])  # [1, T]

        for _ in range(max_new_tokens):
            logits = model(ctx)  # [1, T, V]
            next_logits = logits[0, -1, :]  # [V]

            if temperature == 0.0:
                next_token = int(mx.argmax(next_logits).item())
            else:
                next_logits = next_logits / temperature
                # top-p nucleus sampling
                probs = mx.softmax(next_logits, axis=-1)
                sorted_idx = mx.argsort(-probs)
                sorted_probs = probs[sorted_idx]
                cumsum = mx.cumsum(sorted_probs, axis=0)
                # keep tokens within top_p mass
                cutoff_mask = (cumsum - sorted_probs) < top_p
                filtered = mx.where(cutoff_mask, sorted_probs, mx.zeros_like(sorted_probs))
                total = filtered.sum()
                filtered = filtered / (total + 1e-8)
                sampled_pos = int(mx.random.categorical(mx.log(filtered + 1e-8)).item())
                next_token = int(sorted_idx[sampled_pos].item())

            if next_token == EOS_ID:
                break
            generated.append(next_token)
            ctx = mx.array([token_ids + generated])
            mx.eval(ctx)

        return _decode(generated)


# Module-level singleton — loaded lazily on first /api/complete call
_engine = KJVAInference()


def get_engine() -> KJVAInference:
    return _engine
