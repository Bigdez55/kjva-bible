"""pt/model.py — TokenlessLM decoder-only transformer in **PyTorch**.

Faithful port of the MLX reference (`training/scripts/model.py`). Same architecture,
same math, and — critically — the **same parameter names** so the exported safetensors
round-trips through `scripts/safetensors_to_gguf.py` and loads in the XMIND C runtime
unchanged (interp_tokenless.c, UNIFIED_MASTER_TECH_PACK.md Part II §25.2).

Tensor-name contract (state_dict keys → GGUF names via build_name_mapping):
    embed.weight                -> token_emb.weight
    norm_final.weight           -> output_norm.weight
    blocks.N.norm1.weight       -> blk.N.attn_norm.weight
    blocks.N.attn.{q,k,v,o}.weight -> blk.N.attn_{q,k,v,output}.weight
    blocks.N.norm2.weight       -> blk.N.ffn_norm.weight
    blocks.N.mlp.{gate,up,down}.weight -> blk.N.ffn_{gate,up,down}.weight
(tied embeddings — no lm_head in the export.)

Zero use of `transformers`. Pure torch.nn. No MLX, no Metal — runs on CPU or CUDA.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Config — field names + semantics identical to the MLX ModelConfig.
# Defaults are the canonical BYTE base (vocab 259, 8L/d384/6h/1536/seq1024) so a
# bare ModelConfig() is correct for this model (avoids the MLX-path M3 default trap).
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    vocab_size: int = 259
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
        assert self.d_model % self.n_heads == 0, (
            f"d_model {self.d_model} must be divisible by n_heads {self.n_heads}"
        )
        return self.d_model // self.n_heads

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# RoPE — identical convention to the MLX reference (rotate-half, cos/sin tables).
# ---------------------------------------------------------------------------

def precompute_rope(head_dim: int, max_seq: int, base: float = 10000.0):
    """Returns (cos, sin) float32 tensors of shape [max_seq, head_dim]."""
    assert head_dim % 2 == 0, "head_dim must be even for RoPE"
    inv_freq = 1.0 / (base ** (torch.arange(0, head_dim, 2, dtype=torch.float32) / head_dim))
    t = torch.arange(max_seq, dtype=torch.float32)
    freqs = torch.outer(t, inv_freq)                          # [max_seq, head_dim/2]
    emb = torch.cat([freqs, freqs], dim=-1)                   # [max_seq, head_dim]
    return torch.cos(emb), torch.sin(emb)


def apply_rope(x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> torch.Tensor:
    """x: [B, H, T, Dh]; cos/sin: [T, Dh] (broadcast over B,H)."""
    T = x.shape[-2]
    cos = cos[:T]
    sin = sin[:T]
    d = x.shape[-1]
    x1 = x[..., : d // 2]
    x2 = x[..., d // 2:]
    x_rot = torch.cat([-x2, x1], dim=-1)
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

    def forward(self, x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor,
                mask: torch.Tensor | None = None) -> torch.Tensor:
        B, T, D = x.shape
        H = self.cfg.n_heads
        Dh = self.cfg.head_dim

        q = self.q(x).reshape(B, T, H, Dh).transpose(1, 2)    # [B, H, T, Dh]
        k = self.k(x).reshape(B, T, H, Dh).transpose(1, 2)
        v = self.v(x).reshape(B, T, H, Dh).transpose(1, 2)

        q = apply_rope(q, cos, sin)
        k = apply_rope(k, cos, sin)

        scale = Dh ** -0.5
        scores = (q @ k.transpose(-1, -2)) * scale            # [B, H, T, T]
        if mask is not None:
            scores = scores + mask
        attn = torch.softmax(scores, dim=-1)
        out = attn @ v                                        # [B, H, T, Dh]
        out = out.transpose(1, 2).reshape(B, T, D)
        return self.o(out)


class SwiGLU(nn.Module):
    def __init__(self, d_model: int, d_ffn: int):
        super().__init__()
        self.gate = nn.Linear(d_model, d_ffn, bias=False)
        self.up = nn.Linear(d_model, d_ffn, bias=False)
        self.down = nn.Linear(d_ffn, d_model, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.down(F.silu(self.gate(x)) * self.up(x))   # silu(gate)·up → down


class TransformerBlock(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.norm1 = nn.RMSNorm(cfg.d_model, eps=cfg.rms_eps)
        self.attn = Attention(cfg)
        self.norm2 = nn.RMSNorm(cfg.d_model, eps=cfg.rms_eps)
        self.mlp = SwiGLU(cfg.d_model, cfg.d_ffn)

    def forward(self, x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor,
                mask: torch.Tensor | None = None) -> torch.Tensor:
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
        self.blocks = nn.ModuleList([TransformerBlock(cfg) for _ in range(cfg.n_layers)])
        self.norm_final = nn.RMSNorm(cfg.d_model, eps=cfg.rms_eps)
        if not cfg.tie_embeddings:
            self.lm_head = nn.Linear(cfg.d_model, cfg.vocab_size, bias=False)
        # RoPE tables: non-persistent buffers → excluded from state_dict (not weights).
        cos, sin = precompute_rope(cfg.head_dim, cfg.max_seq_len, cfg.rope_base)
        self.register_buffer("_rope_cos", cos, persistent=False)
        self.register_buffer("_rope_sin", sin, persistent=False)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        """tokens: [B, T] int64; returns logits [B, T, V]."""
        B, T = tokens.shape
        x = self.embed(tokens)                                # [B, T, D]
        mask = torch.triu(
            torch.full((T, T), -1e9, dtype=x.dtype, device=x.device), diagonal=1
        )
        for block in self.blocks:
            x = block(x, self._rope_cos, self._rope_sin, mask)
        x = self.norm_final(x)
        if self.cfg.tie_embeddings:
            logits = F.linear(x, self.embed.weight)           # x @ embed.weight.T
        else:
            logits = self.lm_head(x)
        return logits

    def num_params(self) -> int:
        return sum(p.numel() for p in self.parameters())


# ---------------------------------------------------------------------------
# Parameter initialization — same rule as the MLX reference:
#   2D weights ~ N(0, init_std); residual-projection weights (o, down, lm_head)
#   scaled by 1/sqrt(2·n_layers); RMSNorm gains left at 1.
# ---------------------------------------------------------------------------

def init_weights(model: TokenlessLM, cfg: ModelConfig, seed: int = 0) -> TokenlessLM:
    g = torch.Generator().manual_seed(seed)
    with torch.no_grad():
        for name, p in model.named_parameters():
            if p.ndim == 2:
                std = cfg.init_std
                if "lm_head" in name or name.endswith("o.weight") or name.endswith("down.weight"):
                    std = cfg.init_std / (2.0 * cfg.n_layers) ** 0.5
                p.copy_(torch.empty(p.shape).normal_(mean=0.0, std=std, generator=g))
            # 1D (RMSNorm gains): leave at the nn.RMSNorm default of 1.0
    return model


__all__ = [
    "ModelConfig", "TokenlessLM", "Attention", "SwiGLU", "TransformerBlock",
    "precompute_rope", "apply_rope", "init_weights",
]
