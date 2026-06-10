"""pt/peft/base.py — PyTorch PEFT operator base.

Mirrors the MLX `peft/base.py` contract (DeltaFamily taxonomy, DeltaOperator,
num_trainable_params) but in torch. Operators are real nn.Modules that wrap a
frozen base nn.Linear and compose a trainable delta into the forward pass — so a
single loss.backward() flows gradients to adapter params only. This is the
structural resolution of the MLX-path M1 defect (adapters were never in the graph).
"""
from __future__ import annotations

from enum import Enum, auto

import torch
import torch.nn as nn


class DeltaFamily(Enum):
    WEIGHT_ADDITIVE = auto()   # LoRA / DoRA / AdaLoRA / VeRA / PiSSA / rsLoRA ...
    ACTIVATION = auto()        # IA3 (learned activation rescaling)
    PROMPT = auto()            # prompt / prefix / p-tuning
    MODULE = auto()            # Houlsby / Pfeiffer bottleneck adapters
    STRUCTURAL = auto()        # OFT / BOFT / FourierFT
    SPARSE = auto()            # BitFit / DiffPruning / FishMask / FAR
    ROUTING = auto()           # xLoRA / UniPELT / MAM
    ALIGNMENT = auto()         # SFT / DPO / IPO / KTO / ORPO / PPO / GRPO (objectives)


class DeltaOperator(nn.Module):
    """Wraps a frozen base nn.Linear; forward() returns base(x) composed with a delta.

    Subclasses set `family` and implement `forward`. The base weight is frozen here
    (requires_grad_(False)); trainable params are the operator's own submodules.
    """
    family: DeltaFamily = DeltaFamily.WEIGHT_ADDITIVE

    def __init__(self, base: nn.Linear):
        super().__init__()
        assert isinstance(base, nn.Linear), "DeltaOperator wraps an nn.Linear"
        self.base = base
        for p in self.base.parameters():
            p.requires_grad_(False)
        self.in_features = base.in_features
        self.out_features = base.out_features

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # pragma: no cover - abstract
        raise NotImplementedError

    def num_trainable_params(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


def get_submodule(root: nn.Module, dotted: str) -> nn.Module:
    mod = root
    for part in dotted.split("."):
        mod = mod[int(part)] if part.isdigit() else getattr(mod, part)
    return mod


def set_submodule(root: nn.Module, dotted: str, new: nn.Module) -> None:
    parts = dotted.split(".")
    parent = root
    for part in parts[:-1]:
        parent = parent[int(part)] if part.isdigit() else getattr(parent, part)
    last = parts[-1]
    if last.isdigit():
        parent[int(last)] = new
    else:
        setattr(parent, last, new)
