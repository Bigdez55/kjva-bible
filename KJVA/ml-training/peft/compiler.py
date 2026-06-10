"""
peft/compiler.py — PEFT Compiler and Planner

The compiler is the brain of Omni-PEFT. It takes:
  - A LayerPlasticityMap (from ModelProfiler)
  - A TaskFingerprint (from TaskFingerprinter)
  - AdaptationConstraints (hardware + quality budgets)

And outputs an AdaptationPlan: a concrete, layer-by-layer specification
of which PEFT methods to apply, with what ranks, to which modules.

Core principle: cheapest sufficient change.
  Start with the smallest reversible adaptation.
  Escalate only when evidence demands it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid

from .base import AdaptationConstraints, HardwareBudget
from .profiler import LayerPlasticityMap, LayerProfile
from .fingerprint import TaskFingerprint, DomainShift
from ._yaml import dict_to_yaml


# ---------------------------------------------------------------------------
# Layer adaptation spec
# ---------------------------------------------------------------------------

@dataclass
class LayerAdaptationSpec:
    layer_idx: int
    module_name: str       # e.g., "attn.q", "attn.v", "mlp.gate"
    peft_method: str
    rank: int | None
    alpha: float | None
    extra_config: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Adaptation plan
# ---------------------------------------------------------------------------

@dataclass
class AdaptationPlan:
    plan_id: str
    base_model: str
    training_substrate: str          # "qlora", "float16", "float32"
    layer_specs: list[LayerAdaptationSpec]
    prompt_spec: dict | None
    alignment_method: str | None
    estimated_trainable_params: int
    hardware: HardwareBudget
    compiled_at: str                 # ISO timestamp

    def to_yaml_dict(self) -> dict:
        specs = [
            {
                "layer_idx": s.layer_idx,
                "module_name": s.module_name,
                "peft_method": s.peft_method,
                "rank": s.rank,
                "alpha": s.alpha,
                "extra_config": s.extra_config,
            }
            for s in self.layer_specs
        ]
        return {
            "adaptation_plan": {
                "plan_id": self.plan_id,
                "base_model": self.base_model,
                "training_substrate": self.training_substrate,
                "compiled_at": self.compiled_at,
                "estimated_trainable_params": self.estimated_trainable_params,
                "hardware": {
                    "train_vram_mb": self.hardware.train_vram_mb,
                    "infer_vram_mb": self.hardware.infer_vram_mb,
                    "latency_target_ms": self.hardware.latency_target_ms,
                    "deployment_target": self.hardware.deployment_target,
                },
                "prompt_spec": self.prompt_spec,
                "alignment_method": self.alignment_method,
                "layer_specs": specs,
            }
        }

    def summary_str(self) -> str:
        method_counts: dict[str, int] = {}
        for s in self.layer_specs:
            method_counts[s.peft_method] = method_counts.get(s.peft_method, 0) + 1
        method_summary = ", ".join(f"{m}×{c}" for m, c in sorted(method_counts.items()))
        return (
            f"AdaptationPlan [{self.plan_id[:8]}]\n"
            f"  Base model       : {self.base_model}\n"
            f"  Substrate        : {self.training_substrate}\n"
            f"  Trainable params : {self.estimated_trainable_params:,}\n"
            f"  Layer specs      : {len(self.layer_specs)} total  ({method_summary})\n"
            f"  Alignment        : {self.alignment_method or 'none'}\n"
            f"  Compiled at      : {self.compiled_at}\n"
        )


# ---------------------------------------------------------------------------
# Rank tables keyed by DomainShift
# ---------------------------------------------------------------------------

_RANK_BY_SHIFT: dict[DomainShift, tuple[int, int]] = {
    DomainShift.NONE:      (1, 4),
    DomainShift.LOW:       (4, 8),
    DomainShift.MEDIUM:    (8, 16),
    DomainShift.HIGH:      (16, 32),
    DomainShift.VERY_HIGH: (32, 64),
}

# Trainable param estimation per method (conservative heuristic):
#   LoRA-family : rank * (in_features + out_features)
#   IA3         : out_features  (a single learned scaling vector)
#   BitFit      : out_features  (bias terms only)
#   Prefix      : prompt_len * d_model * n_layers (handled separately)
#   Adapter     : 2 * bottleneck_dim * d_model  (two projections)

def _estimate_params(method: str, rank: int | None, in_f: int, out_f: int) -> int:
    if method in ("lora", "adalora", "dora", "qlora", "rsloRA", "pissa"):
        r = rank or 8
        return r * (in_f + out_f)
    if method in ("ia3",):
        return out_f
    if method in ("bitfit",):
        return out_f
    if method in ("houlsby_adapter", "pfeiffer_adapter"):
        bottleneck = max(16, (in_f + out_f) // 16)
        return 2 * bottleneck * in_f
    if method in ("prefix",):
        return in_f * 8  # rough approximation
    return rank * (in_f + out_f) if rank else out_f


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

class PEFTCompiler:
    """
    Translates a LayerPlasticityMap + TaskFingerprint + AdaptationConstraints
    into a concrete, validated AdaptationPlan.
    """

    def plan(
        self,
        plasticity_map: LayerPlasticityMap,
        fingerprint: TaskFingerprint,
        constraints: AdaptationConstraints,
    ) -> AdaptationPlan:
        hw = constraints.hardware

        # Determine training substrate
        substrate = "qlora" if hw.train_vram_mb < 12_000 else "float16"

        # Domain-shift → rank range
        rank_min, rank_max = _RANK_BY_SHIFT[fingerprint.domain_shift]
        # Use midpoint as default rank
        default_rank = (rank_min + rank_max) // 2

        specs: list[LayerAdaptationSpec] = []
        total_params = 0

        for profile in plasticity_map.profiles:
            # Skip embeddings — frozen by default
            if profile.layer_type == "embedding":
                continue

            # Skip fully frozen early layers unless fingerprint demands it
            if profile.can_freeze and fingerprint.domain_shift == DomainShift.NONE:
                continue

            # Intersect layer's recommended methods with fingerprint's stack
            candidate_methods = self._intersect(
                profile.recommended_methods,
                fingerprint.recommended_peft_stack,
            )
            if not candidate_methods:
                continue

            # Pick the best method (first intersection hit = preferred)
            method = candidate_methods[0]

            # Clamp rank to profile's allowed range
            rank = self._clamp_rank(default_rank, profile.recommended_rank_min, profile.recommended_rank_max)
            alpha = float(rank) * 2.0  # standard LoRA convention: alpha = 2 * rank

            # Estimate params for budget check
            param_est = _estimate_params(method, rank, profile.in_features, profile.out_features)

            # Budget gate — reduce rank if over limit
            if total_params + param_est > constraints.max_trainable_params:
                rank = max(1, rank // 2)
                alpha = float(rank) * 2.0
                param_est = _estimate_params(method, rank, profile.in_features, profile.out_features)
                if total_params + param_est > constraints.max_trainable_params:
                    continue  # skip this layer entirely — budget exhausted

            module_name = self._module_name(profile.layer_type)
            specs.append(LayerAdaptationSpec(
                layer_idx=profile.layer_idx,
                module_name=module_name,
                peft_method=method,
                rank=rank if method not in ("ia3", "bitfit", "prefix") else None,
                alpha=alpha if method not in ("ia3", "bitfit", "prefix") else None,
                extra_config={"substrate": substrate} if method == "qlora" else {},
            ))
            total_params += param_est

        # Prompt spec: include if prefix/prompt is in the stack
        prompt_spec: dict | None = None
        if any(m in ("prefix", "prompt") for m in fingerprint.recommended_peft_stack):
            prompt_spec = {
                "method": "prefix",
                "num_virtual_tokens": 20,
                "init_strategy": "random",
            }

        return AdaptationPlan(
            plan_id=str(uuid.uuid4()),
            base_model="kjv_tokenless_v1",
            training_substrate=substrate,
            layer_specs=specs,
            prompt_spec=prompt_spec,
            alignment_method=None,
            estimated_trainable_params=total_params,
            hardware=hw,
            compiled_at=datetime.now(timezone.utc).isoformat(),
        )

    def dry_run_report(self, plan: AdaptationPlan) -> str:
        lines = [plan.summary_str()]
        if plan.layer_specs:
            lines.append("  Layer breakdown:")
            for s in plan.layer_specs[:20]:  # cap display at 20 rows
                rank_str = f"  rank={s.rank}" if s.rank else ""
                lines.append(f"    [{s.layer_idx:2d}] {s.module_name:<16} {s.peft_method}{rank_str}")
            if len(plan.layer_specs) > 20:
                lines.append(f"    ... and {len(plan.layer_specs) - 20} more")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _intersect(self, layer_methods: list[str], stack: list[str]) -> list[str]:
        """Return methods present in both lists, preserving stack order."""
        stack_set = set(stack)
        return [m for m in layer_methods if m in stack_set]

    def _clamp_rank(self, rank: int, r_min: int, r_max: int) -> int:
        if r_max == 0:
            return 0
        return max(r_min if r_min > 0 else 1, min(rank, r_max))

    def _module_name(self, layer_type: str) -> str:
        _map = {
            "attention_q": "attn.q",
            "attention_k": "attn.k",
            "attention_v": "attn.v",
            "attention_o": "attn.o",
            "mlp_gate": "mlp.gate",
            "mlp_up": "mlp.up",
            "mlp_down": "mlp.down",
            "layernorm": "layernorm",
        }
        return _map.get(layer_type, layer_type)
