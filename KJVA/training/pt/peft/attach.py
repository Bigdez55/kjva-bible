"""pt/peft/attach.py — attach PEFT operators into a TokenlessLM forward graph.

Replaces target submodules (per-block attn.{q,k,v,o} / mlp.{gate,up,down}) with
adapter-wrapped versions, freezes the base, and returns the in-place-modified model
plus the set of trainable adapter param paths. Because adapters become real
submodules, nn autograd reaches them naturally (the MLX-path M1 defect cannot recur).
"""
from __future__ import annotations

import torch.nn as nn

from .base import DeltaOperator, get_submodule, set_submodule
from . import operators as ops


def attach_adapters(model: nn.Module, method: str, *, rank: int = 8, alpha: int = 16):
    """Attach `method` adapters to every TransformerBlock. Returns (model, info)."""
    cls, kwargs, is_alias = ops.resolve(method)
    targets = ops.default_targets(method)
    if cls in (ops.LoRALinear, ops.DoRALinear):
        kwargs = {**kwargs, "r": rank, "alpha": alpha}

    # Freeze the entire base first; adapter params (created below) stay trainable.
    for p in model.parameters():
        p.requires_grad_(False)

    n_blocks = len(model.blocks)
    attached: list[str] = []
    for i in range(n_blocks):
        for rel in targets:
            dotted = f"blocks.{i}.{rel}"
            base_lin = get_submodule(model, dotted)
            if not isinstance(base_lin, nn.Linear):
                continue
            op = cls(base_lin, **kwargs)
            set_submodule(model, dotted, op)
            attached.append(dotted)

    trainable_paths = {
        name for name, p in model.named_parameters() if p.requires_grad
    }
    info = {
        "method": method,
        "operator": cls.__name__,
        "family": cls.family.name,
        "is_alias": is_alias,
        "targets_per_block": targets,
        "attached_modules": attached,
        "trainable_param_paths": sorted(trainable_paths),
        "trainable_params": sum(
            p.numel() for p in model.parameters() if p.requires_grad
        ),
        "frozen_params": sum(
            p.numel() for p in model.parameters() if not p.requires_grad
        ),
    }
    return model, info


def adapter_state_dict(model: nn.Module) -> dict:
    """Only the trainable (adapter) tensors — what gets saved as the adapter."""
    return {
        name: p.detach().cpu().contiguous()
        for name, p in model.named_parameters()
        if p.requires_grad
    }


def is_adapter_operator(mod: nn.Module) -> bool:
    return isinstance(mod, DeltaOperator)
