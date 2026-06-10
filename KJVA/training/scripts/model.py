"""
model.py — Custom decoder-only transformer in MLX. From scratch.

Zero use of `transformers`. Zero pretrained weights. Pure mlx.nn primitives.

Architecture (configurable via ModelConfig):
  - Token embedding (tied with output projection)
  - N decoder blocks, each:
      RMSNorm -> Multi-head self-attention (RoPE, causal mask)
      RMSNorm -> SwiGLU MLP
  - Final RMSNorm
  - Output projection = tied embedding transpose

Target size defaults: ~16M parameters (6 layers, d=384, 6 heads, ffn=1536)
— trains in hours on M2 with 16GB unified memory.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import mlx.core as mx
import mlx.nn as nn


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    vocab_size: int = 16000
    n_layers: int = 6
    n_heads: int = 6
    d_model: int = 384
    d_ffn: int = 1536
    max_seq_len: int = 512
    rope_base: float = 10000.0
    tie_embeddings: bool = True
    rms_eps: float = 1e-5
    init_std: float = 0.02

    @property
    def head_dim(self) -> int:
        assert self.d_model % self.n_heads == 0, (
            f"d_model {self.d_model} must be divisible by n_heads {self.n_heads}"
        )
        return self.d_model // self.n_heads

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# RoPE (Rotary Position Embedding)
# ---------------------------------------------------------------------------

def precompute_rope(head_dim: int, max_seq: int, base: float = 10000.0):
    """Returns (cos, sin) arrays of shape [max_seq, head_dim]."""
    assert head_dim % 2 == 0, "head_dim must be even for RoPE"
    inv_freq = 1.0 / (base ** (mx.arange(0, head_dim, 2, dtype=mx.float32) / head_dim))
    t = mx.arange(max_seq, dtype=mx.float32)
    freqs = mx.outer(t, inv_freq)                           # [max_seq, head_dim/2]
    emb = mx.concatenate([freqs, freqs], axis=-1)           # [max_seq, head_dim]
    return mx.cos(emb), mx.sin(emb)


def apply_rope(x: mx.array, cos: mx.array, sin: mx.array) -> mx.array:
    """
    x:   [B, H, T, D_h]
    cos: [T, D_h]; sin: [T, D_h]
    """
    T = x.shape[-2]
    cos = cos[:T]
    sin = sin[:T]
    # rotate half
    d = x.shape[-1]
    x1 = x[..., : d // 2]
    x2 = x[..., d // 2 :]
    x_rot = mx.concatenate([-x2, x1], axis=-1)
    return x * cos + x_rot * sin


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------

class Attention(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.q = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        self.k = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        self.v = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        self.o = nn.Linear(cfg.d_model, cfg.d_model, bias=False)

    def __call__(self, x: mx.array, cos: mx.array, sin: mx.array,
                 mask: mx.array | None = None) -> mx.array:
        B, T, D = x.shape
        H = self.cfg.n_heads
        Dh = self.cfg.head_dim

        q = self.q(x).reshape(B, T, H, Dh).transpose(0, 2, 1, 3)   # [B, H, T, Dh]
        k = self.k(x).reshape(B, T, H, Dh).transpose(0, 2, 1, 3)
        v = self.v(x).reshape(B, T, H, Dh).transpose(0, 2, 1, 3)

        q = apply_rope(q, cos, sin)
        k = apply_rope(k, cos, sin)

        scale = mx.rsqrt(mx.array(Dh, dtype=q.dtype))
        scores = (q @ k.transpose(0, 1, 3, 2)) * scale             # [B, H, T, T]
        if mask is not None:
            scores = scores + mask
        attn = mx.softmax(scores, axis=-1)
        out = attn @ v                                             # [B, H, T, Dh]
        out = out.transpose(0, 2, 1, 3).reshape(B, T, D)
        return self.o(out)


class SwiGLU(nn.Module):
    def __init__(self, d_model: int, d_ffn: int):
        super().__init__()
        self.gate = nn.Linear(d_model, d_ffn, bias=False)
        self.up   = nn.Linear(d_model, d_ffn, bias=False)
        self.down = nn.Linear(d_ffn, d_model, bias=False)

    def __call__(self, x: mx.array) -> mx.array:
        # silu(gate(x)) * up(x) -> down
        g = self.gate(x)
        silu_g = g * mx.sigmoid(g)
        return self.down(silu_g * self.up(x))


class TransformerBlock(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.norm1 = nn.RMSNorm(cfg.d_model, eps=cfg.rms_eps)
        self.attn  = Attention(cfg)
        self.norm2 = nn.RMSNorm(cfg.d_model, eps=cfg.rms_eps)
        self.mlp   = SwiGLU(cfg.d_model, cfg.d_ffn)

    def __call__(self, x: mx.array, cos: mx.array, sin: mx.array,
                 mask: mx.array | None = None) -> mx.array:
        x = x + self.attn(self.norm1(x), cos, sin, mask)
        x = x + self.mlp(self.norm2(x))
        return x


# ---------------------------------------------------------------------------
# Full model
# ---------------------------------------------------------------------------

class TokenlessLM(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.embed = nn.Embedding(cfg.vocab_size, cfg.d_model)
        self.blocks = [TransformerBlock(cfg) for _ in range(cfg.n_layers)]
        self.norm_final = nn.RMSNorm(cfg.d_model, eps=cfg.rms_eps)
        if not cfg.tie_embeddings:
            self.lm_head = nn.Linear(cfg.d_model, cfg.vocab_size, bias=False)
        # RoPE tables (not parameters — computed once, stored as buffers)
        cos, sin = precompute_rope(cfg.head_dim, cfg.max_seq_len, cfg.rope_base)
        self._rope_cos = cos
        self._rope_sin = sin

    def __call__(self, tokens: mx.array) -> mx.array:
        """tokens: [B, T]; returns logits [B, T, V]."""
        B, T = tokens.shape
        x = self.embed(tokens)                                      # [B, T, D]

        # causal mask: [T, T], additive (0 on allowed, -inf on masked future)
        mask = mx.triu(mx.full((T, T), -1e9, dtype=x.dtype), k=1)

        for block in self.blocks:
            x = block(x, self._rope_cos, self._rope_sin, mask)

        x = self.norm_final(x)

        if self.cfg.tie_embeddings:
            # weight-tied lm head
            logits = x @ self.embed.weight.T
        else:
            logits = self.lm_head(x)
        return logits

    def num_params(self) -> int:
        total = 0
        for _, v in self.parameters().items() if hasattr(self, "parameters") else []:
            pass
        # Walk tree explicitly:
        from mlx.utils import tree_flatten
        flat = tree_flatten(self.parameters())
        for _, arr in flat:
            total += int(arr.size)
        return total

# ---------------------------------------------------------------------------
# Parameter initialization
# ---------------------------------------------------------------------------

def init_weights(model: TokenlessLM, cfg: ModelConfig, seed: int = 0):
    """Apply Xavier-ish / scaled-normal init to all weights."""
    rng_key = mx.random.key(seed)

    def _init(key_name: str, arr: mx.array) -> mx.array:
        nonlocal rng_key
        rng_key, sub = mx.random.split(rng_key)
        if arr.ndim == 2:
            std = cfg.init_std
            if "lm_head" in key_name or "o.weight" in key_name or "down.weight" in key_name:
                std = cfg.init_std / (2.0 * cfg.n_layers) ** 0.5
            return mx.random.normal(shape=arr.shape, key=sub) * std
        # biases / RMSNorm gains: leave alone (nn.RMSNorm inits weight=1)
        return arr

    from mlx.utils import tree_flatten, tree_unflatten
    flat = tree_flatten(model.parameters())
    new_flat = [(name, _init(name, v)) for name, v in flat]
    model.update(tree_unflatten(new_flat))
    return model
