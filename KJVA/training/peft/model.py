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

from .base import DeltaOperator, ActiveExpert, DeltaFamily

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
        # D23: a route plan pushed down once-per-forward by OmniPEFTModel so the
        # block does not re-run routing per layer.  When set, it overrides the
        # per-block router/equal-weight resolution.
        self._pushed_route: list[tuple[str, float]] | None = None

    def set_route(self, active: list[tuple[str, float]] | None) -> None:
        """Install a pre-computed (expert_id, weight) route for the next forward.

        Called by OmniPEFTModel after it runs the HierarchicalRouter ONCE.  Only
        the (expert_id, weight) pairs whose expert_id is present in this block's
        delta_experts will actually contribute.
        """
        self._pushed_route = active

    def __call__(
        self,
        x: mx.array,
        *frozen_args,
        task_descriptor: str | None = None,
        domain_descriptor: str | None = None,
        runtime_budget: object | None = None,
        **frozen_kwargs,
    ) -> mx.array:
        """Run the frozen layer, then add the routed adapter delta.

        ``*frozen_args`` / ``**frozen_kwargs`` are forwarded *verbatim* to the
        wrapped frozen layer.  This is what lets an OmniPEFTBlock be spliced into
        the base TokenlessLM block loop, where each block is called as
        ``block(x, cos, sin, mask)`` — the extra positional RoPE/mask args flow
        straight through to ``self.frozen_layer`` so the splice is transparent
        when no expert is active, and EFFECTIVE (output moves) when one is.

        The delta is computed on the *block output* ``base_out`` (shape
        ``[B, T, D]``), so a delta expert operating in hidden-state space
        (the OmniPEFTBlock contract — see base.py: ``full = frozen + delta``)
        returns a ``[B, T, D]`` correction that is added to the block result.

        PROMPT-family experts (prompt_tuning / p_tuning) are the exception: they
        do NOT return a same-shape hidden-state delta — they *prepend* ``n``
        soft-prompt rows to the input (``[B, T, D] -> [B, n+T, D]``).  Such an
        expert cannot be summed onto ``base_out``; it must instead run the frozen
        layer over the *extended* sequence so the real tokens attend to the soft
        prompt, then drop the prompt rows so the block still returns ``[B, T, D]``
        and sequence length never escapes into the next block (the base
        scripts/model.py reuses a fixed ``[T,T]`` mask + RoPE table for every
        block, so a leaked ``n+T`` length would break the downstream attention).
        See ``_apply_prompt_experts``.  This is what makes a routed prompt/p-tuning
        operator genuinely change the forward output instead of being inert.
        """
        if not self.delta_experts:
            return self.frozen_layer(x, *frozen_args, **frozen_kwargs)

        active_experts = self._resolve_experts(
            x, task_descriptor, domain_descriptor, runtime_budget
        )

        if not active_experts:
            return self.frozen_layer(x, *frozen_args, **frozen_kwargs)

        # Split the active route into PROMPT-family experts (which extend the
        # input sequence and run THROUGH the frozen layer) and same-shape
        # hidden-state experts (ACTIVATION / WEIGHT_ADDITIVE, applied to the
        # block output).  Only a non-zero weight contributes — this preserves the
        # "zero-weight route -> no effect" invariant for BOTH paths.
        prompt_route: list[tuple[DeltaOperator, float]] = []
        hidden_route: list[tuple[str, float]] = []
        for expert_id, weight in active_experts:
            expert = self.delta_experts.get(expert_id)
            if expert is None or weight <= 0.0:
                continue
            if self._is_prompt_family(expert):
                # PROMPT family splits two ways: sequence-extending operators
                # (prompt_tuning / p_tuning) go through the soft-prompt path;
                # a PROMPT operator that does NOT extend the sequence is the
                # not-yet-wired prefix-KV case (its __call__ is identity), so we
                # SKIP it rather than route it through the same-shape path —
                # adding an identity output as a hidden-state delta would double
                # the block output. Prefix-KV stays the documented ceiling (see
                # prefix_tuning.py WIRING STATUS).
                if self._prompt_extends_sequence(expert):
                    prompt_route.append((expert, weight))
                # else: inert until base-attention prefix-KV hook exists.
            else:
                hidden_route.append((expert_id, weight))

        # Run the frozen layer once — over the soft-prompt-extended input if any
        # prompt expert is active, else over the bare input.  base_out is always
        # back to [B, T, D] (prompt rows dropped inside _apply_prompt_experts).
        if prompt_route:
            base_out = self._apply_prompt_experts(
                x, prompt_route, frozen_args, frozen_kwargs
            )
        else:
            base_out = self.frozen_layer(x, *frozen_args, **frozen_kwargs)

        if not hidden_route:
            return base_out

        # Accumulate weighted same-shape deltas on the block output.  The expert
        # consumes the block output (hidden-state space) and returns a same-shape
        # correction — the original OmniPEFTBlock contract, byte-identical.
        delta: mx.array | None = None
        for expert_id, weight in hidden_route:
            expert = self.delta_experts.get(expert_id)
            if expert is None:
                continue
            expert_delta = expert(base_out) * weight
            delta = expert_delta if delta is None else delta + expert_delta

        if delta is None:
            return base_out

        return base_out + delta

    # ------------------------------------------------------------------
    # PROMPT-family soft-prompt path (prompt_tuning / p_tuning)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_prompt_family(expert: DeltaOperator) -> bool:
        """True iff this expert belongs to the PROMPT delta family.

        Compared by enum *name*, not by ``is DeltaFamily.PROMPT`` identity, on
        purpose.  The prompt operators (peft/prompt/*.py) insert ``scripts`` on
        sys.path and ``from peft.base import DeltaFamily`` — depending on how the
        package was first imported, that can resolve to a DIFFERENT module object
        than this file's ``from .base import DeltaFamily``, giving two distinct
        enum instances for which ``is`` is False.  A False here would misroute a
        sequence-extending prompt operator into the same-shape hidden path, where
        ``base_out + expert(base_out)`` is a ``[B,T,D] + [B,n+T,D]`` SHAPE CRASH.
        Name comparison is identity-independent, so the routing is robust to the
        dual-import seam (CLAUDE.md MLX-rules note) — a potential crash becomes
        safe, correct routing.
        """
        fam = getattr(expert, "family", None)
        return getattr(fam, "name", None) == DeltaFamily.PROMPT.name

    @staticmethod
    def _prompt_extends_sequence(expert: DeltaOperator) -> bool:
        """True iff this PROMPT expert actually prepends rows to the sequence.

        prompt_tuning / p_tuning return ``[B, n+T, D]`` (n>0) — those are wired
        through the soft-prompt path.  prefix_tuning's ``__call__`` is identity
        (its real injection is post-projection KV inside the frozen Attention,
        which this block cannot reach — see module note), so it does NOT extend
        the sequence and is left out of the soft-prompt path to avoid a no-op /
        double-apply.  We detect "extends" structurally from ``n_tokens`` rather
        than running the operator, so a zero-token prompt is also excluded.
        """
        n = getattr(expert, "n_tokens", None)
        return isinstance(n, int) and n > 0

    def _apply_prompt_experts(
        self,
        x: mx.array,
        prompt_route: list[tuple[DeltaOperator, float]],
        frozen_args: tuple,
        frozen_kwargs: dict,
    ) -> mx.array:
        """Run the frozen layer over a soft-prompt-extended sequence, then drop
        the prompt rows so the block output stays ``[B, T, D]``.

        Backward-compatibility / parity:
          * This path is only reached when a routed expert's ``family`` is
            ``DeltaFamily.PROMPT`` AND it extends the sequence — the same-shape
            (ACTIVATION / WEIGHT_ADDITIVE) experts never enter here, so their
            behaviour is unchanged.
          * The prompt rows are appended in front, the frozen layer runs over the
            longer sequence with a freshly-built ``[n+T, n+T]`` causal mask
            (the base reuses RoPE tables that auto-slice to ``n+T``), and the
            first ``n`` output rows are discarded — so sequence length NEVER
            escapes this block and downstream blocks/logits see the original
            ``T``.  A model with no prompt expert never calls this.

        Multiple prompt experts: their prompt rows are concatenated front-to-back
        (weighted), which is the standard soft-prompt-stacking semantics.  In the
        common single-prompt case this is just that operator's prompt.
        """
        # cos, sin, mask are the base block's positional call signature
        # (block(x, cos, sin, mask) — see scripts/model.py TransformerBlock).
        cos = frozen_args[0] if len(frozen_args) >= 1 else frozen_kwargs.get("cos")
        sin = frozen_args[1] if len(frozen_args) >= 2 else frozen_kwargs.get("sin")

        T = x.shape[1]

        # Build the extended input: [weighted soft prompts ... , x].
        prompt_blocks: list[mx.array] = []
        for expert, weight in prompt_route:
            # expert(x) -> [B, n+T, D]; the prepended rows are the first n.
            extended = expert(x)
            n = extended.shape[1] - T
            if n <= 0:
                continue
            prompt_blocks.append(extended[:, :n, :] * weight)

        if not prompt_blocks:
            # No prompt rows materialised — degrade to the plain frozen forward.
            return self.frozen_layer(x, *frozen_args, **frozen_kwargs)

        x_ext = mx.concatenate(prompt_blocks + [x], axis=1)
        n_total = x_ext.shape[1] - T

        # RoPE table bound: the base precomputes cos/sin up to max_seq_len.  If
        # the extended length would exceed it, skip the soft-prompt entirely and
        # run the unmodified frozen forward (never crash on an out-of-range slice).
        if cos is not None:
            max_seq = cos.shape[0]
            if n_total + T > max_seq:
                return self.frozen_layer(x, *frozen_args, **frozen_kwargs)

        # Fresh causal mask covering the extended sequence; matches the base's
        # additive [-1e9 above diagonal] convention (scripts/model.py).
        ext_len = n_total + T
        ext_mask = mx.triu(
            mx.full((ext_len, ext_len), -1e9, dtype=x_ext.dtype), k=1
        )

        if len(frozen_args) >= 1:
            out_ext = self.frozen_layer(x_ext, cos, sin, ext_mask)
        else:
            # Frozen layer takes cos/sin/mask by keyword only (defensive).
            kw = dict(frozen_kwargs)
            kw["mask"] = ext_mask
            out_ext = self.frozen_layer(x_ext, **kw)

        # Drop the prompt rows so the block returns [B, T, D] — length contained.
        return out_ext[:, n_total:, :]

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
        # D23: a route pushed down by OmniPEFTModel (router ran once at the top)
        # takes precedence over any per-block routing.
        if self._pushed_route is not None:
            return [
                (eid, w) for eid, w in self._pushed_route
                if eid in self.delta_experts
            ]

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
        # D23: lazily-built HierarchicalRouter (registry + ConflictResolver).
        self._router: "HierarchicalRouter | None" = None
        # D25: layer_idx → the ORIGINAL base block, captured the first time we
        # splice an OmniPEFTBlock into base_model.blocks[idx].  Lets us restore
        # the byte-identical base forward (remove_block_adapters) so the parity
        # suite can prove the spliced path degrades cleanly to base logits.
        self._original_blocks: dict[int, object] = {}

    # ------------------------------------------------------------------
    # D23 — runtime routing
    # ------------------------------------------------------------------

    def _ensure_router(self) -> "HierarchicalRouter | None":
        """Build (once) and return the HierarchicalRouter over this model's
        adapter_registry.  Returns None if construction fails (e.g. registry
        unavailable) so the forward path degrades to base logits."""
        if self._router is not None:
            return self._router
        try:
            from .router import HierarchicalRouter
            from .conflict import ConflictResolver
            self._router = HierarchicalRouter(
                registry=self.adapter_registry,
                conflict_resolver=ConflictResolver(),
            )
        except Exception:
            self._router = None
        return self._router

    def route_for(
        self,
        task_descriptor: str | None,
        domain_descriptor: str | None,
        runtime_budget: object | None = None,
    ):
        """Run the HierarchicalRouter ONCE for the given task/domain and return
        its RoutePlan (or None).  This is the single call site that flips
        HierarchicalRouter.route() from DEFINED to CALLED."""
        router = self._ensure_router()
        if router is None:
            return None
        from .base import HardwareBudget
        budget = runtime_budget if isinstance(runtime_budget, HardwareBudget) else HardwareBudget()
        task_spec = {
            "tasks": [task_descriptor] if task_descriptor else [],
            "domains": [domain_descriptor] if domain_descriptor else [],
        }
        input_text = " ".join(filter(None, [task_descriptor, domain_descriptor]))
        try:
            return router.route(input_text, task_spec, budget)
        except Exception:
            return None

    def _apply_route_to_blocks(self, route_plan) -> None:
        """Push a single RoutePlan's (expert_id, weight) pairs into every
        registered OmniPEFTBlock so routing runs once, not per layer."""
        active = None
        if route_plan is not None:
            active = [(ae.expert_id, ae.weight) for ae in route_plan.active_experts]
        for block in self._peft_blocks.values():
            block.set_route(active)

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

    def __call__(
        self,
        tokens: mx.array,
        task_descriptor: str | None = None,
        domain_descriptor: str | None = None,
        runtime_budget: object | None = None,
    ) -> mx.array:
        """
        Forward pass through the adapted model.

        D23: when a task/domain descriptor is supplied AND OmniPEFTBlocks are
        installed, the HierarchicalRouter is invoked ONCE at the top of the
        forward and its RoutePlan is pushed into every block (replacing the old
        equal-weight fallback).

        D25 (EFFECTIVE): the installed OmniPEFTBlocks are now spliced into
        ``base_model.blocks`` by register_peft_block(), so ``self.base_model(...)``
        below runs the routed adapter deltas *as part of the base forward graph*.
        The route resolved here is therefore not just CALLED — it changes the
        logits this method returns (proven by tests/test_peft_route_effective.py).

        With no descriptors, behaviour is unchanged: spliced blocks self-resolve
        (equal weight over their own experts), and a model with no spliced blocks
        returns byte-identical base logits — so ``model(tokens)`` stays fully
        backward-compatible and the parity gate holds.
        """
        if (task_descriptor or domain_descriptor) and self._peft_blocks:
            route_plan = self.route_for(task_descriptor, domain_descriptor, runtime_budget)
            self._apply_route_to_blocks(route_plan)
        return self.base_model(tokens)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt_tokens: "mx.array",
        max_new_tokens: int = 64,
        task_descriptor: str | None = None,
        domain_descriptor: str | None = None,
        runtime_budget: object | None = None,
        **kwargs,
    ):
        """
        Autoregressive generation that threads task/domain through the router the
        same way ``__call__`` does (D23).  Routing is resolved ONCE up front and
        pushed into the installed blocks, then the per-step decode loop lives in
        peft.generate (kept separate so model.py stays focused on wiring).
        """
        if (task_descriptor or domain_descriptor) and self._peft_blocks:
            route_plan = self.route_for(task_descriptor, domain_descriptor, runtime_budget)
            self._apply_route_to_blocks(route_plan)
        from .generate import greedy_generate
        return greedy_generate(self, prompt_tokens, max_new_tokens=max_new_tokens, **kwargs)

    # ------------------------------------------------------------------
    # Parameter counting
    # ------------------------------------------------------------------

    def num_trainable_params(self) -> int:
        """Count trainable parameters from a SINGLE source of truth.

        D25 note on double-counting: once an OmniPEFTBlock is spliced into
        ``base_model.blocks[idx]`` (register_peft_block), its delta-expert tensors
        are reachable from ``base_model.trainable_parameters()`` AND from
        ``self._peft_blocks[idx]``.  Summing both (the pre-D25 behaviour) would
        count every spliced delta twice.  We therefore count ONLY the base model's
        trainable tree, which — because the blocks are spliced in — already
        includes every active delta expert plus any non-block trainable params
        (e.g. alignment-layer weights the training loop adds).  Any block recorded
        in ``_peft_blocks`` but NOT spliced (no swappable ``blocks`` list on this
        base) is added separately so it is not silently dropped.
        """
        from mlx.utils import tree_flatten

        total = 0
        for _, arr in tree_flatten(self.base_model.trainable_parameters()):
            total += int(arr.size)

        # Blocks recorded but not spliced into base_model.blocks (the base had no
        # swappable block list) are NOT reachable from base_model — count them
        # once here so the report stays truthful for that fallback base.
        spliced_idxs = set(self._original_blocks.keys())
        for layer_idx, block in self._peft_blocks.items():
            if layer_idx in spliced_idxs:
                continue  # already counted via base_model (no double count)
            for _, arr in tree_flatten(block.trainable_parameters()):
                total += int(arr.size)

        return total

    def register_peft_block(self, layer_idx: int, block: OmniPEFTBlock) -> None:
        """Register an OmniPEFTBlock AND splice it into the base model's forward.

        D25 — this is the line that flips routing from CALLED to EFFECTIVE.

        Before D25, register_peft_block() only recorded the block in
        ``self._peft_blocks`` and the forward called ``self.base_model(tokens)``
        directly, so the installed block never ran — the adapter delta was
        computed nowhere on the actual call path.  Now we additionally **splice**
        the block into ``base_model.blocks[layer_idx]`` (a plain Python list in
        the MLX TokenlessLM, see scripts/model.py), replacing the original
        TransformerBlock.  Because the base forward iterates
        ``for block in self.blocks: x = block(x, cos, sin, mask)``, the spliced
        OmniPEFTBlock is now invoked *by the base forward itself* — its frozen
        layer runs (the original block) and the routed delta is added on top.

        Crucially this requires **no edit to the base model**: the base block loop
        is a list iteration over swappable elements, so the OmniPEFTBlock (made
        call-signature-compatible via ``__call__(x, *frozen_args, **kwargs)``)
        drops in transparently.  The wrapped frozen_layer should therefore be the
        ORIGINAL base block at ``layer_idx`` (the caller passes it in); we record
        that original so remove_block_adapters() can restore byte-identical
        behaviour for the parity gate.

        If the base model has no swappable ``blocks`` list (e.g. a different base
        whose forward inlines its layers), the splice is skipped and the block is
        only recorded — the route is then CALLED-but-not-EFFECTIVE for that base,
        and the precise remaining hook is documented in install_block_adapters().
        """
        self._peft_blocks[layer_idx] = block
        blocks = getattr(self.base_model, "blocks", None)
        if blocks is not None and 0 <= layer_idx < len(blocks):
            if layer_idx not in self._original_blocks:
                self._original_blocks[layer_idx] = blocks[layer_idx]
            blocks[layer_idx] = block

    def install_block_adapters(
        self,
        delta_factory,
        layer_indices: "list[int] | None" = None,
        expert_id: "str | None" = None,
    ) -> "OmniPEFTModel":
        """Wrap selected base blocks in routed OmniPEFTBlocks and splice them in.

        This is the in-process (no-training-loop) realization of the adapt() plan:
        for each requested ``layer_idx`` it builds a delta expert via
        ``delta_factory(layer_idx, base_block)`` (a callable returning either a
        single DeltaOperator or a ``{expert_id: DeltaOperator}`` dict), wraps the
        ORIGINAL base block as the frozen layer, and registers+splices the result
        so the base forward runs the delta.

        Args:
            delta_factory: ``(layer_idx, base_block) -> DeltaOperator | dict``.
                The expert(s) must consume and return hidden states of shape
                ``[B, T, D]`` (they are applied to the *block output*).
            layer_indices: which base blocks to adapt; defaults to ALL blocks.
            expert_id: the key under which a SINGLE-operator factory result is
                registered.  THE ROUTING-KEY SEAM: the HierarchicalRouter emits
                ``ActiveExpert.expert_id == genome.name`` (see router.py /
                route_for), and a pushed route only contributes if that id is a
                key in the block's ``delta_experts`` (``_resolve_experts`` filter).
                So to make the **router** (not the equal-weight fallback) drive
                the forward, pass ``expert_id`` equal to the adapter's genome name.
                If a factory returns a ``{id: op}`` dict, those keys are used
                verbatim and must likewise match the genome name(s).  Defaults to
                ``f"layer{idx}"`` — fine for presence-only application, but that
                key will NOT match any router-selected genome, so descriptor-driven
                routing would fall through to the no-route equal-weight path.

        Returns ``self`` so calls can chain.

        NOTE FOR THE TRAINING LOOP (the one remaining seam, fully wired here for
        inference): training/pt/* and training/scripts/* own the optimizer step.
        After calling ``install_block_adapters`` (or ``register_peft_block`` per
        layer), the trainable adapter params are exactly
        ``model.trainable_parameters()`` restricted to the spliced blocks
        (``num_trainable_params()`` counts them).  The training loop must:
          1. call install_block_adapters() / register_peft_block() to splice,
          2. take grads w.r.t. model.trainable_parameters() via nn.value_and_grad,
          3. NOT call base_model.blocks mutation itself — splicing is owned here.
        The exact call site the loop must invoke is this method (peft/model.py);
        no base-model (scripts/model.py / pt/model.py) edit is required.
        """
        blocks = getattr(self.base_model, "blocks", None)
        if blocks is None:
            # Base forward does not expose a swappable block list — the splice
            # hook does not exist for this base.  Record nothing as spliced and
            # signal the honest ceiling to the caller.
            raise RuntimeError(
                "base_model exposes no swappable `blocks` list; the OmniPEFTBlock "
                "splice hook is unavailable for this base. The route stays CALLED "
                "but not EFFECTIVE until the base forward iterates a swappable "
                "block list (scripts/model.py TokenlessLM.blocks does)."
            )
        idxs = layer_indices if layer_indices is not None else list(range(len(blocks)))
        for layer_idx in idxs:
            if not (0 <= layer_idx < len(blocks)):
                continue
            base_block = blocks[layer_idx]
            built = delta_factory(layer_idx, base_block)
            # IMPORTANT: MLX nn.Module IS a dict subclass, so a single
            # DeltaOperator also passes isinstance(built, dict).  Discriminate on
            # DeltaOperator FIRST — only a non-operator mapping is treated as a
            # pre-built {expert_id: operator} table.
            #
            # The single-operator key is the ROUTING-KEY SEAM: use the caller's
            # expert_id (== the adapter genome name the router emits) so a pushed
            # route actually contributes; fall back to a per-layer key otherwise.
            single_key = expert_id if expert_id is not None else f"layer{layer_idx}"
            if isinstance(built, DeltaOperator):
                experts = {single_key: built}
            elif isinstance(built, dict):
                experts = dict(built)
            else:
                experts = {single_key: built}
            block = OmniPEFTBlock(frozen_layer=base_block, delta_experts=experts)
            self.register_peft_block(layer_idx, block)
        return self

    def remove_block_adapters(self) -> "OmniPEFTModel":
        """Restore the original base blocks (byte-identical base forward).

        Undoes every splice performed by register_peft_block/install_block_adapters
        so ``self.base_model(tokens)`` again returns unmodified base logits.  Used
        by the parity gate to prove the spliced path degrades cleanly.
        """
        blocks = getattr(self.base_model, "blocks", None)
        if blocks is not None:
            for layer_idx, original in self._original_blocks.items():
                if 0 <= layer_idx < len(blocks):
                    blocks[layer_idx] = original
        self._original_blocks.clear()
        self._peft_blocks.clear()
        return self
