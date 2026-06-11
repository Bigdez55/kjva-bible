"""
peft/omni_composite.py — OmniPEFTCompositeAdapter

The unified PEFT genome. All enabled PEFT operators train simultaneously
in one forward pass, one loss, one backward pass, producing one artifact.

This is NOT a tournament. This is NOT a LoRA winner. This is a fused
adaptation surface where each mechanism contributes its gradient signal
to the same optimization.

Architecture:
  For each model layer slot (attn.q, attn.k, attn.v, attn.o, mlp.gate, ...):
    - One weight-additive operator (lora / adalora / dora) per compiler plan
    - One IA3 activation scaling vector (l_k or l_v for attn, l_ff for ffn)
    - One BitFit bias vector
  Global:
    - One PrefixTuningLayer (per-layer prefix K/V vectors)

All operators are non-underscore attributes of _OmniPatched → visible to
nn.value_and_grad when the patched layers are injected into base_model.

Artifact schema: see OMNI_PEFT_DOCTRINE.md
"""
from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from peft.base import DeltaFamily


# ---------------------------------------------------------------------------
# Per-layer patched module — holds all Omni operators for one linear slot
# ---------------------------------------------------------------------------

class _OmniPatched(nn.Module):
    """
    Replaces a single nn.Linear with a unified Omni-PEFT surface.

    Composition order:
      1. weight-additive delta (LoRA/AdaLoRA: additive; DoRA: replaces weight)
      2. activation scaling (IA3 l_k or l_v or l_ff — multiplicative)
      3. bias term (BitFit — additive)

    All non-underscore attributes are in the MLX parameter tree and receive
    gradients through nn.value_and_grad(base_model, ...) after injection.
    """

    def __init__(
        self,
        base_linear: nn.Module,
        weight_op,          # LoRALinear / AdaLoRALinear / DoRALinear or None
        ia3_scale: mx.array | None,   # shape (out_features,), ones-init
        bitfit_bias: mx.array | None, # shape (out_features,), zeros-init
    ) -> None:
        super().__init__()
        self.base = base_linear
        self.base.freeze()
        self.weight_op = weight_op          # trainable delta operator
        self.ia3_scale = ia3_scale          # trainable scaling vector
        self.bitfit_bias = bitfit_bias      # trainable bias vector
        # Flag: operator returns full adapted output — base must NOT be added again.
        # DoRA carries _frozen_weight; PiSSA carries _W_residual; both return
        # the complete W*x contribution internally.
        self._is_full_output_op = (
            weight_op is not None and
            hasattr(weight_op, "family") and
            weight_op.family == DeltaFamily.WEIGHT_ADDITIVE and
            (hasattr(weight_op, "_frozen_weight") or hasattr(weight_op, "_W_residual"))
        )
        # Keep backward-compat alias used in __call__
        self._is_dora = self._is_full_output_op

    def __call__(self, x: mx.array) -> mx.array:
        if self.weight_op is not None and self._is_dora:
            # DoRA computes the full adapted output (includes frozen weight)
            out = self.weight_op(x)
        elif self.weight_op is not None:
            # LoRA / AdaLoRA: additive delta over frozen base
            out = self.base(x) + self.weight_op(x)
        else:
            out = self.base(x)

        if self.ia3_scale is not None:
            out = out * self.ia3_scale

        if self.bitfit_bias is not None:
            out = out + self.bitfit_bias

        return out


# ---------------------------------------------------------------------------
# Composite adapter — the full Omni-PEFT genome container
# ---------------------------------------------------------------------------

class OmniPEFTCompositeAdapter(nn.Module):
    """
    Unified Omni-PEFT genome: all operators in one trainable module tree.

    Build with from_plan(plan, base_model) to get a composite wired to the
    compiler's layer-wise method assignment.

    After construction, call inject_into(base_model) to replace attention
    projections with _OmniPatched modules. The patched model is then passed
    to nn.value_and_grad for training.

    On save, call extract_weights() to get all trainable params as a flat dict.
    """

    # The adapter stores a list of _OmniPatched modules as attributes
    # (using setattr with flat names so MLX traverses them).
    # A separate _key_to_attr dict (underscore = excluded from param tree)
    # maps canonical "layer{N}.{module}" keys to attribute names.

    def __init__(self) -> None:
        super().__init__()
        self._key_to_attr: dict[str, str] = {}
        self._genome_methods: list[str] = []
        self._operator_count: int = 0
        # Prefix tuning: global across all layers (set during from_plan)
        self.prefix_tuning = None

    @classmethod
    def from_plan(
        cls,
        plan,             # AdaptationPlan from peft.compiler
        base_model,
        enable_ia3: bool = True,
        enable_bitfit: bool = True,
        enable_prefix: bool = True,
        prefix_n: int = 8,
    ) -> "OmniPEFTCompositeAdapter":
        """
        Build the composite adapter from a compiler AdaptationPlan.

        For each layer_spec in the plan:
          - Instantiate the assigned weight-additive operator (lora/adalora/dora)
          - Add IA3 activation scaling (if enable_ia3)
          - Add BitFit bias (if enable_bitfit)
          - Wrap everything in _OmniPatched

        Also adds a global PrefixTuningLayer (if enable_prefix).
        """
        from peft.low_rank.lora import LoRALinear
        from peft.low_rank.adalora import AdaLoRALinear
        from peft.low_rank.dora import DoRALinear
        from peft.prompt.prefix_tuning import PrefixTuningLayer

        cfg = base_model.cfg
        d_model = cfg.d_model
        n_layers = cfg.n_layers
        n_heads = cfg.n_heads
        head_dim = d_model // n_heads

        composite = cls()
        enabled_methods_set: set[str] = set()
        operator_count = 0

        for spec in plan.layer_specs:  # noqa: F841 (cfg/n_layers used above)
            block_idx = spec.layer_idx
            module_name = spec.module_name  # e.g., "attn.q", "mlp.gate"
            method = spec.peft_method
            rank = spec.rank or 8
            alpha = spec.alpha or 16.0

            # Resolve base linear from model
            base_linear, in_f, out_f = _get_base_linear(base_model, block_idx, module_name)
            if base_linear is None:
                continue

            # Build weight-additive operator
            if method == "dora":
                weight_op = DoRALinear(base_linear.weight, rank=rank, alpha=alpha)
            elif method in ("adalora",):
                weight_op = AdaLoRALinear(in_f, out_f, rank=rank, alpha=alpha)
            else:
                # lora, rslora, olora, pissa → use LoRALinear
                weight_op = LoRALinear(in_f, out_f, rank=rank, alpha=alpha)

            # Record the weight-additive family actually used, not the compiler's
            # domain hint (which may be "ia3" or "bitfit" for cheap escalations).
            if isinstance(weight_op, DoRALinear):
                enabled_methods_set.add("dora")
            elif isinstance(weight_op, AdaLoRALinear):
                enabled_methods_set.add("adalora")
            else:
                enabled_methods_set.add("lora")

            # IA3 activation scaling vector (per output dimension)
            ia3_scale = mx.ones((out_f,)) if enable_ia3 else None
            if enable_ia3:
                enabled_methods_set.add("ia3")

            # BitFit bias vector
            bitfit_bias = mx.zeros((out_f,)) if enable_bitfit else None
            if enable_bitfit:
                enabled_methods_set.add("bitfit")

            patched = _OmniPatched(base_linear, weight_op, ia3_scale, bitfit_bias)

            # Register as attribute with flat name (no dots — MLX uses dots as path sep)
            key = f"layer{block_idx}_{module_name.replace('.', '_')}"
            attr_name = f"op_{key}"
            setattr(composite, attr_name, patched)
            composite._key_to_attr[f"layer{block_idx}.{module_name}"] = attr_name
            operator_count += 1

        # Global prefix tuning
        if enable_prefix and n_layers > 0:
            composite.prefix_tuning = PrefixTuningLayer(
                n_prefix=prefix_n,
                n_heads=n_heads,
                head_dim=head_dim,
                n_layers=n_layers,
            )
            enabled_methods_set.add("prefix_tuning")

        composite._genome_methods = sorted(enabled_methods_set)
        composite._operator_count = operator_count
        return composite

    def inject_into(self, base_model) -> dict:
        """
        Replace attention/MLP projections in base_model with _OmniPatched modules.
        Also wires PrefixTuningLayer into each TransformerBlock via _prefix_layer /
        _prefix_layer_idx so Attention.__call__ can prepend learned K/V context.

        Returns a rollback dict: {key: (block_idx, module_path, original_linear)}
        for restoring the model after training if needed.
        """
        rollback: dict = {}
        for canon_key, attr_name in self._key_to_attr.items():
            patched = getattr(self, attr_name)
            block_idx, module_path = _parse_canon_key(canon_key)
            if block_idx is None:
                continue
            orig = _set_model_module(base_model, block_idx, module_path, patched)
            if orig is not None:
                rollback[canon_key] = (block_idx, module_path, orig)

        # Wire PrefixTuningLayer into every TransformerBlock.
        # _prefix_layer uses underscore convention → excluded from MLX param tree on
        # the block, but the same PrefixTuningLayer object is reachable via
        # composite.prefix_tuning, so gradient flow through prefix_key/prefix_val
        # is preserved during nn.value_and_grad training.
        if self.prefix_tuning is not None:
            for i, block in enumerate(base_model.blocks):
                block._prefix_layer = self.prefix_tuning
                block._prefix_layer_idx = i

        return rollback

    def extract_weights(self) -> dict[str, mx.array]:
        """
        Return all trainable operator weights as a flat dict suitable for npz save.

        Keys: "{attr_name}.{param_path}" e.g. "op_layer0_attn_q.weight_op.A"
        """
        from mlx.utils import tree_flatten
        weights: dict[str, mx.array] = {}
        for attr_name in self._key_to_attr.values():
            module = getattr(self, attr_name, None)
            if module is None:
                continue
            for pname, pval in tree_flatten(module.parameters()):
                # Skip the frozen base weight (it's in base_model, not the adapter)
                if pname.startswith("base."):
                    continue
                weights[f"{attr_name}.{pname}"] = pval
        # Prefix tuning params
        if self.prefix_tuning is not None:
            for pname, pval in tree_flatten(self.prefix_tuning.parameters()):
                weights[f"prefix_tuning.{pname}"] = pval
        return weights

    def genome_dict(
        self,
        base_model_sha256: str = "",
        final_avg_loss: float = 0.0,
        training_epochs: int = 0,
        deployment_mode: str = "semi-merged",
    ) -> dict:
        """Return the Omni-PEFT genome record as a dict for JSON serialisation.

        Schema version 1.1 — includes deployment_mode, retention target,
        evaluation gates, and rollback manifest per OMNI_PEFT_DOCTRINE.md.
        """
        return {
            "omni_peft_version": "1.1.0",
            "single_training_run": True,
            "single_optimizer": True,
            "single_loss": True,
            "enabled_methods": self._genome_methods,
            "operator_count": self._operator_count,
            "total_trainable_params": _count_params(self),
            "base_model_sha256": base_model_sha256,
            "training_epochs": training_epochs,
            "final_avg_loss": final_avg_loss,
            "deployment_mode": deployment_mode,
            "base_retention_target": 0.93,
            "evaluation_gates": [
                "domain_accuracy",
                "base_retention",
                "hallucination_delta",
                "latency_ms",
                "merge_safety",
            ],
            "rollback": {
                "previous_stable": None,
                "quarantine_conditions": [
                    "base_retention_below_0.93",
                    "domain_bleed_detected",
                    "latency_above_budget",
                ],
            },
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_base_linear(base_model, block_idx: int, module_name: str):
    """
    Retrieve the nn.Linear at (block_idx, module_name) from a TokenlessLM.

    Returns (linear, in_features, out_features) or (None, 0, 0) if not found.
    """
    try:
        block = base_model.blocks[block_idx]
    except (IndexError, AttributeError):
        return None, 0, 0

    parts = module_name.split(".")  # e.g., ["attn", "q"] or ["mlp", "gate"]
    obj = block
    for p in parts:
        obj = getattr(obj, p, None)
        if obj is None:
            return None, 0, 0

    if not hasattr(obj, "weight"):
        return None, 0, 0

    out_f, in_f = obj.weight.shape
    return obj, in_f, out_f


def _parse_canon_key(key: str):
    """
    Parse "layer{N}.attn.q" → (block_idx=N, module_path="attn.q").
    Returns (None, None) on parse failure.
    """
    parts = key.split(".", 1)  # ["layer0", "attn.q"]
    if len(parts) != 2 or not parts[0].startswith("layer"):
        return None, None
    try:
        block_idx = int(parts[0][len("layer"):])
    except ValueError:
        return None, None
    return block_idx, parts[1]


def _set_model_module(base_model, block_idx: int, module_path: str, replacement):
    """
    Set base_model.blocks[block_idx].<module_path> = replacement.
    Returns the original object, or None on failure.
    """
    try:
        block = base_model.blocks[block_idx]
    except (IndexError, AttributeError):
        return None

    parts = module_path.split(".")
    obj = block
    for p in parts[:-1]:
        obj = getattr(obj, p, None)
        if obj is None:
            return None

    attr = parts[-1]
    original = getattr(obj, attr, None)
    if original is None:
        return None
    setattr(obj, attr, replacement)
    return original


def _count_params(module: nn.Module) -> int:
    """Count trainable (non-frozen) parameter elements in a module."""
    from mlx.utils import tree_flatten
    return sum(
        v.size for _, v in tree_flatten(module.trainable_parameters())
        if isinstance(v, mx.array)
    )
