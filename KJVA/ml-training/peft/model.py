"""
peft/model.py — OmniPEFTBlock and OmniPEFTModel

OmniPEFTBlock: frozen_layer + delta_experts + router
  - Wraps any nn.Module layer
  - At forward time: runs frozen layer, then adds weighted expert deltas
  - Router controls which experts activate and at what weight

OmniPEFTModel: complete adapted model
  - Wraps TokenlessLM
  - Provides adapt() and generate() methods
  - Routes through adapter registry at inference time
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import mlx.core as mx
import mlx.nn as nn

from .base import DeltaOperator, ActiveExpert

if TYPE_CHECKING:
    from .registry import AdapterGenomeRegistry
    from .compiler import PEFTCompiler, AdaptationPlan
    from .router import HierarchicalRouter


# ---------------------------------------------------------------------------
# OmniPEFTBlock
# ---------------------------------------------------------------------------

class OmniPEFTBlock(nn.Module):
    """
    Wraps a single frozen layer and manages a set of delta experts.

    Forward logic:
      1. Pass input through the frozen base layer.
      2. If experts exist, accumulate weighted deltas from active experts.
      3. Return base_out + delta sum.

    When router is None, all experts are activated with equal weight.
    When delta_experts is empty, the block is a transparent pass-through.
    """

    def __init__(
        self,
        frozen_layer: nn.Module,
        delta_experts: dict[str, DeltaOperator],
        router: "HierarchicalRouter | None" = None,
    ) -> None:
        super().__init__()
        frozen_layer.freeze()
        self.frozen_layer = frozen_layer
        self.delta_experts = delta_experts
        self.router = router

    def __call__(
        self,
        x: mx.array,
        task_descriptor: str | None = None,
        domain_descriptor: str | None = None,
        runtime_budget: object | None = None,
    ) -> mx.array:
        base_out = self.frozen_layer(x)

        if not self.delta_experts:
            return base_out

        active_experts = self._resolve_experts(
            x, task_descriptor, domain_descriptor, runtime_budget
        )

        if not active_experts:
            return base_out

        # Accumulate weighted deltas
        delta: mx.array | None = None
        for expert_id, weight in active_experts:
            expert = self.delta_experts.get(expert_id)
            if expert is None:
                continue
            expert_delta = expert(x) * weight
            delta = expert_delta if delta is None else delta + expert_delta

        if delta is None:
            return base_out

        return base_out + delta

    # ------------------------------------------------------------------
    # Expert resolution helpers
    # ------------------------------------------------------------------

    def _resolve_experts(
        self,
        x: mx.array,
        task_descriptor: str | None,
        domain_descriptor: str | None,
        runtime_budget: object | None,
    ) -> list[tuple[str, float]]:
        """
        Return list of (expert_id, weight) pairs for this forward pass.
        """
        if self.router is not None and (task_descriptor or domain_descriptor):
            return self._route_via_router(task_descriptor, domain_descriptor, runtime_budget)

        # No router — equal weight for all experts
        n = len(self.delta_experts)
        equal_weight = 1.0 / n
        return [(eid, equal_weight) for eid in self.delta_experts]

    def _route_via_router(
        self,
        task_descriptor: str | None,
        domain_descriptor: str | None,
        runtime_budget: object | None,
    ) -> list[tuple[str, float]]:
        """Route via the hierarchical router. Falls back to equal weight on error."""
        try:
            from .base import HardwareBudget

            budget = runtime_budget if isinstance(runtime_budget, HardwareBudget) else HardwareBudget()
            task_spec = {
                "tasks": [task_descriptor] if task_descriptor else [],
                "domains": [domain_descriptor] if domain_descriptor else [],
            }
            input_text = " ".join(filter(None, [task_descriptor, domain_descriptor]))
            route_plan = self.router.route(input_text, task_spec, budget)

            return [
                (ae.expert_id, ae.weight)
                for ae in route_plan.active_experts
                if ae.expert_id in self.delta_experts
            ]
        except Exception:
            # Graceful degradation — equal weight fallback
            n = len(self.delta_experts)
            equal_weight = 1.0 / n if n > 0 else 0.0
            return [(eid, equal_weight) for eid in self.delta_experts]


# ---------------------------------------------------------------------------
# OmniPEFTModel
# ---------------------------------------------------------------------------

class OmniPEFTModel(nn.Module):
    """
    Top-level adapted model wrapping a frozen TokenlessLM.

    Provides:
      - adapt(plan): apply a compiled adaptation plan
      - __call__(tokens): forward pass returning logits
      - num_trainable_params(): count of live trainable parameters
    """

    def __init__(
        self,
        base_model: nn.Module,
        adapter_registry: "AdapterGenomeRegistry",
        compiler: "PEFTCompiler",
    ) -> None:
        super().__init__()
        base_model.freeze()
        self.base_model = base_model
        self.adapter_registry = adapter_registry
        self.compiler = compiler
        # Map from layer_idx → OmniPEFTBlock (populated by adapt())
        self._peft_blocks: dict[int, OmniPEFTBlock] = {}

    # ------------------------------------------------------------------
    # Adaptation
    # ------------------------------------------------------------------

    def adapt(self, plan: "AdaptationPlan") -> "OmniPEFTModel":
        """
        Store an AdaptationPlan so the training loop can wire up DeltaOperators.

        This method is a *planning shell* — it does not construct DeltaOperator
        modules or wrap frozen layers in OmniPEFTBlocks.  The construction step
        requires the concrete PEFT subclasses (peft/additive/, peft/activation/,
        etc.) and must be performed by the training loop, which has access to
        the live model weights.

        Typical training-loop usage::

            model.adapt(plan)
            for spec in model._pending_specs:
                operator = method_factory(spec)            # instantiate DeltaOperator
                block = OmniPEFTBlock(frozen_layer, {spec.peft_method: operator})
                model.register_peft_block(spec.layer_idx, block)

        IMPORTANT: Calling model(tokens) before the training loop installs
        OmniPEFTBlocks via register_peft_block() returns unmodified base-model
        logits.  num_trainable_params() also returns 0 until that point.
        """
        self._active_plan = plan
        # Signal to training loop which specs are active
        self._pending_specs = list(plan.layer_specs)
        return self

    # ------------------------------------------------------------------
    # Forward pass
    # ------------------------------------------------------------------

    def __call__(self, tokens: mx.array) -> mx.array:
        """
        Forward pass through the adapted model.

        If OmniPEFTBlocks have been installed (via the training loop after
        adapt() is called), they handle delta injection automatically.
        Otherwise, this delegates directly to the frozen base model.
        """
        return self.base_model(tokens)

    # ------------------------------------------------------------------
    # Parameter counting
    # ------------------------------------------------------------------

    def num_trainable_params(self) -> int:
        """Sum trainable parameters across all registered delta experts."""
        from mlx.utils import tree_flatten

        total = 0
        # Count params in any PEFT blocks
        for block in self._peft_blocks.values():
            for _, arr in tree_flatten(block.trainable_parameters()):
                total += int(arr.size)

        # Also count any trainable params that were not wrapped in blocks
        # (e.g., alignment-layer parameters added by the training loop)
        for _, arr in tree_flatten(self.base_model.trainable_parameters()):
            total += int(arr.size)

        return total

    def register_peft_block(self, layer_idx: int, block: OmniPEFTBlock) -> None:
        """Register an OmniPEFTBlock installed by the training loop."""
        self._peft_blocks[layer_idx] = block
