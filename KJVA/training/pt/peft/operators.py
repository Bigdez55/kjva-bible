"""pt/peft/operators.py — PyTorch PEFT operator catalog.

Each operator wraps a frozen base nn.Linear and composes a trainable delta. The
catalog spans the eight DeltaFamilies; the most-used methods have bespoke math,
and the remaining registry entries alias to the closest bespoke operator (marked
`alias_of=` — no silent gaps; see METHODS / catalog_status()).

Gradient flow is structural: every trainable tensor is an nn.Parameter inside the
returned module, so loss.backward() reaches it and the frozen base is untouched.
"""
from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F

from .base import DeltaFamily, DeltaOperator


# --------------------------------------------------------------------------- #
# WEIGHT_ADDITIVE
# --------------------------------------------------------------------------- #

class LoRALinear(DeltaOperator):
    """base(x) + (alpha/r)·B(A(x)); B init zero so training starts at the base."""
    family = DeltaFamily.WEIGHT_ADDITIVE

    def __init__(self, base: nn.Linear, r: int = 8, alpha: int = 16, dropout: float = 0.0):
        super().__init__(base)
        self.r = r
        self.scaling = alpha / r
        self.A = nn.Linear(self.in_features, r, bias=False)
        self.B = nn.Linear(r, self.out_features, bias=False)
        nn.init.kaiming_uniform_(self.A.weight, a=math.sqrt(5))
        nn.init.zeros_(self.B.weight)
        self.drop = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.base(x) + self.scaling * self.B(self.A(self.drop(x)))


class DoRALinear(DeltaOperator):
    """Weight-decomposed LoRA: W' = m · (W0 + ΔW)/‖W0+ΔW‖ (norm over input dim)."""
    family = DeltaFamily.WEIGHT_ADDITIVE

    def __init__(self, base: nn.Linear, r: int = 8, alpha: int = 16):
        super().__init__(base)
        self.r = r
        self.scaling = alpha / r
        self.A = nn.Linear(self.in_features, r, bias=False)
        self.B = nn.Linear(r, self.out_features, bias=False)
        nn.init.kaiming_uniform_(self.A.weight, a=math.sqrt(5))
        nn.init.zeros_(self.B.weight)
        with torch.no_grad():
            col_norm = self.base.weight.norm(dim=1)          # (out,)
        self.m = nn.Parameter(col_norm.clone())

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        delta = self.scaling * (self.B.weight @ self.A.weight)   # (out, in)
        W = self.base.weight + delta
        norm = W.norm(dim=1, keepdim=True) + 1e-9                 # (out, 1)
        W_hat = self.m.unsqueeze(1) * W / norm
        return F.linear(x, W_hat)


# --------------------------------------------------------------------------- #
# ACTIVATION
# --------------------------------------------------------------------------- #

class IA3Linear(DeltaOperator):
    """IA3: rescale the layer output by a learned per-feature vector (init 1)."""
    family = DeltaFamily.ACTIVATION

    def __init__(self, base: nn.Linear, **_):
        super().__init__(base)
        self.l = nn.Parameter(torch.ones(self.out_features))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.base(x) * self.l


# --------------------------------------------------------------------------- #
# SPARSE
# --------------------------------------------------------------------------- #

class BitFitLinear(DeltaOperator):
    """BitFit: add a trainable bias to an otherwise-frozen (bias-free) layer."""
    family = DeltaFamily.SPARSE

    def __init__(self, base: nn.Linear, **_):
        super().__init__(base)
        self.b = nn.Parameter(torch.zeros(self.out_features))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.base(x) + self.b


# --------------------------------------------------------------------------- #
# STRUCTURAL
# --------------------------------------------------------------------------- #

class OFTLinear(DeltaOperator):
    """Orthogonal fine-tuning: W' = (I + skew(theta))·W via a small additive
    skew-symmetric rotation (block-free approximation; theta init 0 → identity)."""
    family = DeltaFamily.STRUCTURAL

    def __init__(self, base: nn.Linear, **_):
        super().__init__(base)
        n = self.out_features
        self.theta = nn.Parameter(torch.zeros(n, n))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        skew = self.theta - self.theta.t()
        W = self.base.weight + skew @ self.base.weight
        return F.linear(x, W)


# --------------------------------------------------------------------------- #
# MODULE (bottleneck adapter — residual after the wrapped layer)
# --------------------------------------------------------------------------- #

class HoulsbyLinear(DeltaOperator):
    """Bottleneck adapter: base(x) + Up(act(Down(base(x)))); Up init zero."""
    family = DeltaFamily.MODULE

    def __init__(self, base: nn.Linear, bottleneck: int = 32, **_):
        super().__init__(base)
        self.down = nn.Linear(self.out_features, bottleneck, bias=False)
        self.up = nn.Linear(bottleneck, self.out_features, bias=False)
        nn.init.kaiming_uniform_(self.down.weight, a=math.sqrt(5))
        nn.init.zeros_(self.up.weight)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.base(x)
        return h + self.up(F.gelu(self.down(h)))


# --------------------------------------------------------------------------- #
# Catalog registry — full method list mapped to a bespoke operator (or alias).
# No silent gaps: every method resolves to a concrete operator; `alias_of`
# documents which share math. catalog_status() reports bespoke vs aliased.
# --------------------------------------------------------------------------- #

_BESPOKE = {
    "lora": (LoRALinear, {}),
    "dora": (DoRALinear, {}),
    "ia3": (IA3Linear, {}),
    "bitfit": (BitFitLinear, {}),
    "oft": (OFTLinear, {}),
    "houlsby": (HoulsbyLinear, {}),
}

# Aliases: method -> (bespoke_key, override_kwargs). Closest-family approximation
# pending bespoke math (Phase-10 long-tail). Documented, not hidden.
_ALIASES = {
    # WEIGHT_ADDITIVE family → LoRA variants
    "adalora": ("lora", {}), "rslora": ("lora", {}), "olora": ("lora", {}),
    "pissa": ("lora", {}), "vera": ("lora", {}), "loha": ("lora", {}),
    "lokr": ("lora", {}), "rosa": ("lora", {}), "qlora": ("lora", {}),
    # MODULE
    "pfeiffer": ("houlsby", {}), "compacter": ("houlsby", {}),
    "mam_adapter": ("houlsby", {}),
    # STRUCTURAL
    "boft": ("oft", {}), "fourier_ft": ("oft", {}),
    # ROUTING
    "unipelt": ("lora", {}), "xlora": ("lora", {}),
    # SPARSE
    "diffpruning": ("bitfit", {}), "fishmask": ("bitfit", {}), "far": ("bitfit", {}),
}

# Default target submodules per family (relative to each TransformerBlock).
TARGETS_ATTN_MLP = ["attn.q", "attn.k", "attn.v", "attn.o", "mlp.gate", "mlp.up", "mlp.down"]
TARGETS_IA3 = ["attn.k", "attn.v", "mlp.down"]


def resolve(method: str):
    """method -> (operator_class, kwargs, is_alias). Raises on unknown method."""
    method = method.lower()
    if method in _BESPOKE:
        cls, kw = _BESPOKE[method]
        return cls, dict(kw), False
    if method in _ALIASES:
        key, ov = _ALIASES[method]
        cls, kw = _BESPOKE[key]
        merged = {**kw, **ov}
        return cls, merged, True
    raise KeyError(f"unknown PEFT method: {method!r}")


def default_targets(method: str) -> list[str]:
    cls, _, _ = resolve(method)
    return TARGETS_IA3 if cls is IA3Linear else TARGETS_ATTN_MLP


def all_methods() -> list[str]:
    return sorted(set(_BESPOKE) | set(_ALIASES))


def catalog_status() -> dict:
    return {
        "bespoke": sorted(_BESPOKE),
        "aliased": {k: v[0] for k, v in _ALIASES.items()},
        "total": len(_BESPOKE) + len(_ALIASES),
    }
