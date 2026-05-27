"""
model.py — TokenlessLM architecture (byte-level decoder-only transformer, MLX).

Copied from Tokenless Models / ml-training/scripts/model.py.
Do not train here — this is the inference copy. Training lives in the
Tokenless Models workspace at KJVA/training/weights.safetensors.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import mlx.core as mx
import mlx.nn as nn


@dataclass
class ModelConfig:
    vocab_size: int = 259   # byte-level: 256 bytes + PAD/BOS/EOS
    n_layers: int = 8
    n_heads: int = 6
    d_model: int = 384
    d_ffn: int = 1536
    max_seq_len: int = 1024
    rope_base: float = 10000.0
    tie_embeddings: bool = True
    rms_eps: float = 1e-5
    init_std: float = 0.02

    @property
    def head_dim(self) -> int:
        assert self.d_model % self.n_heads == 0
        return self.d_model // self.n_heads

    def to_dict(self) -> dict:
        return asdict(self)


def precompute_rope(head_dim: int, max_seq: int, base: float = 10000.0):
    assert head_dim % 2 == 0
    inv_freq = 1.0 / (base ** (mx.arange(0, head_dim, 2, dtype=mx.float32) / head_dim))
    t = mx.arange(max_seq, dtype=mx.float32)
    freqs = mx.outer(t, inv_freq)
    emb = mx.concatenate([freqs, freqs], axis=-1)
    return mx.cos(emb), mx.sin(emb)


def apply_rope(x: mx.array, cos: mx.array, sin: mx.array) -> mx.array:
    T = x.shape[-2]
    cos = cos[:T]
    sin = sin[:T]
    d = x.shape[-1]
    x1 = x[..., : d // 2]
    x2 = x[..., d // 2 :]
    x_rot = mx.concatenate([-x2, x1], axis=-1)
    return x * cos + x_rot * sin


class Attention(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.q = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        self.k = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        self.v = nn.Linear(cfg.d_model, cfg.d_model, bias=False)
        self.o = nn.Linear(cfg.d_model, cfg.d_model, bias=False)

    def __call__(self, x, cos, sin, mask=None):
        B, T, D = x.shape
        H = self.cfg.n_heads
        Dh = self.cfg.head_dim

        q = self.q(x).reshape(B, T, H, Dh).transpose(0, 2, 1, 3)
        k = self.k(x).reshape(B, T, H, Dh).transpose(0, 2, 1, 3)
        v = self.v(x).reshape(B, T, H, Dh).transpose(0, 2, 1, 3)

        q = apply_rope(q, cos, sin)
        k = apply_rope(k, cos, sin)

        scale = mx.rsqrt(mx.array(Dh, dtype=q.dtype))
        scores = (q @ k.transpose(0, 1, 3, 2)) * scale
        if mask is not None:
            scores = scores + mask
        attn = mx.softmax(scores, axis=-1)
        out = attn @ v
        out = out.transpose(0, 2, 1, 3).reshape(B, T, D)
        return self.o(out)


class SwiGLU(nn.Module):
    def __init__(self, d_model: int, d_ffn: int):
        super().__init__()
        self.gate = nn.Linear(d_model, d_ffn, bias=False)
        self.up   = nn.Linear(d_model, d_ffn, bias=False)
        self.down = nn.Linear(d_ffn, d_model, bias=False)

    def __call__(self, x):
        g = self.gate(x)
        return self.down(g * mx.sigmoid(g) * self.up(x))


class TransformerBlock(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.norm1 = nn.RMSNorm(cfg.d_model, eps=cfg.rms_eps)
        self.attn  = Attention(cfg)
        self.norm2 = nn.RMSNorm(cfg.d_model, eps=cfg.rms_eps)
        self.mlp   = SwiGLU(cfg.d_model, cfg.d_ffn)

    def __call__(self, x, cos, sin, mask=None):
        x = x + self.attn(self.norm1(x), cos, sin, mask)
        x = x + self.mlp(self.norm2(x))
        return x


class TokenlessLM(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.embed = nn.Embedding(cfg.vocab_size, cfg.d_model)
        self.blocks = [TransformerBlock(cfg) for _ in range(cfg.n_layers)]
        self.norm_final = nn.RMSNorm(cfg.d_model, eps=cfg.rms_eps)
        if not cfg.tie_embeddings:
            self.lm_head = nn.Linear(cfg.d_model, cfg.vocab_size, bias=False)
        cos, sin = precompute_rope(cfg.head_dim, cfg.max_seq_len, cfg.rope_base)
        self._rope_cos = cos
        self._rope_sin = sin

    def __call__(self, tokens: mx.array) -> mx.array:
        B, T = tokens.shape
        x = self.embed(tokens)
        mask = mx.triu(mx.full((T, T), -1e9, dtype=x.dtype), k=1)
        for block in self.blocks:
            x = block(x, self._rope_cos, self._rope_sin, mask)
        x = self.norm_final(x)
        if self.cfg.tie_embeddings:
            return x @ self.embed.weight.T
        return self.lm_head(x)
