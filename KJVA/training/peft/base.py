"""
peft/base.py — Universal Delta Intermediate Representation

Every PEFT method is a DeltaOperator: a frozen-weight-aware MLX module that
produces a trainable delta from hidden states or weight matrices.

Architecture doctrine:
  Base model = frozen intelligence substrate
  DeltaOperator = adaptation primitive
  OmniPEFTBlock = frozen_layer + [delta_experts] + router
  OmniPEFTModel = base + compiler + registry + governance

Delta families map every known PEFT into one shared language:
  WEIGHT_ADDITIVE   — LoRA, DoRA, AdaLoRA, LoHa, LoKr, VeRA, PiSSA, rsLoRA, OLoRA, RoSA
  ACTIVATION        — IA³, learned gates, scaling vectors
  PROMPT            — Prompt tuning, Prefix tuning, P-tuning
  MODULE            — Houlsby/Pfeiffer bottleneck adapters, parallel adapters
  STRUCTURAL        — OFT, BOFT, FourierFT (structure-preserving transforms)
  SPARSE            — BitFit, DiffPruning, FishMask, FAR
  ROUTING           — X-LoRA, UniPELT, MAM, Compacter (multi-primitive composition)
  ALIGNMENT         — SFT, DPO, IPO, KTO, ORPO, PPO-RLHF, GRPO (training objective)
"""
from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Any

import mlx.core as mx
import mlx.nn as nn


# ---------------------------------------------------------------------------
# Delta family taxonomy
# ---------------------------------------------------------------------------

class DeltaFamily(Enum):
    WEIGHT_ADDITIVE = auto()   # compact weight-space updates (LoRA family)
    ACTIVATION      = auto()   # scale/gate hidden activations (IA³ family)
    PROMPT          = auto()   # learned context injection (prefix/prompt family)
    MODULE          = auto()   # residual transform modules (adapter family)
    STRUCTURAL      = auto()   # structure-preserving transforms (OFT family)
    SPARSE          = auto()   # sparse / selective weight updates (BitFit family)
    ROUTING         = auto()   # dynamic multi-primitive composition (X-LoRA family)
    ALIGNMENT       = auto()   # training objective methods (DPO/RLHF family)


# ---------------------------------------------------------------------------
# Adapter genome record — serializable identity + governance metadata
# ---------------------------------------------------------------------------

@dataclass
class AdapterGenomeRecord:
    name: str
    version: str
    base_model: str
    peft_method: str
    delta_family: str
    purpose_domains: list[str] = field(default_factory=list)
    purpose_tasks: list[str] = field(default_factory=list)
    training_corpus: str = ""
    training_config: dict[str, Any] = field(default_factory=dict)
    evaluation: dict[str, Any] = field(default_factory=dict)
    routing_activate_when: list[str] = field(default_factory=list)
    routing_never_activate_when: list[str] = field(default_factory=list)
    compatible_with: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)
    mergeable: bool = True
    hot_swappable: bool = True
    rollback_previous: str = ""
    signature: str = ""           # ADR-0002 §9.2 rule 1: HMAC signature (empty = unsigned)
    content_hash: str = ""        # ADR-0002 §9.2 rule 1: sha256 over the adapter IR; the HMAC
                                  # is computed over (content_hash|method|family). Empty = no
                                  # cryptographic verify possible (only presence can be checked).

    def to_yaml_dict(self) -> dict:
        return {
            "adapter_genome": {
                "name": self.name,
                "version": self.version,
                "base_model": self.base_model,
                "peft_method": self.peft_method,
                "delta_family": self.delta_family,
                "purpose": {
                    "domains": self.purpose_domains,
                    "tasks": self.purpose_tasks,
                },
                "training": {
                    "corpus": self.training_corpus,
                    **self.training_config,
                },
                "evaluation": self.evaluation,
                "routing": {
                    "activate_when": self.routing_activate_when,
                    "never_activate_when": self.routing_never_activate_when,
                },
                "compatibility": {
                    "compatible_with": self.compatible_with,
                    "conflicts_with": self.conflicts_with,
                },
                "deployment": {
                    "mergeable": self.mergeable,
                    "hot_swappable": self.hot_swappable,
                },
                "rollback": {
                    "previous_stable": self.rollback_previous,
                },
            }
        }

    def to_json(self) -> str:
        return json.dumps(self.to_yaml_dict(), indent=2)


# ---------------------------------------------------------------------------
# DeltaOperator — abstract base for every PEFT method
# ---------------------------------------------------------------------------

class DeltaOperator(nn.Module, abc.ABC):
    """
    Abstract base class for all PEFT adaptation primitives.

    A DeltaOperator wraps or augments a frozen layer, computing a trainable
    delta that is added to (or composed with) the frozen layer's output.

    Subclasses must implement:
      - forward(x) → delta_output  (the adaptation delta, NOT the full output)
      - family property
      - genome_config property (method-specific config dict for the genome record)

    The caller is responsible for adding the delta to the frozen base output:
      full_output = frozen_output + delta_operator(x)

    Exception: PROMPT and ALIGNMENT families may override the full forward pass
    signature since they operate on different inputs (token sequences, pairs, etc.)
    """

    @property
    @abc.abstractmethod
    def family(self) -> DeltaFamily:
        ...

    @abc.abstractmethod
    def __call__(self, x: mx.array, **kwargs) -> mx.array:
        """Return the adaptation delta (or modified output for prompt/alignment)."""
        ...

    @property
    def genome_config(self) -> dict[str, Any]:
        """Return method-specific config fields for the adapter genome record."""
        return {}

    def to_genome_record(
        self,
        name: str = "unnamed",
        version: str = "1.0.0",
        base_model: str = "base_tokenless_v1",
        corpus: str = "domain_corpus_v1",
        **kwargs,
    ) -> AdapterGenomeRecord:
        return AdapterGenomeRecord(
            name=name,
            version=version,
            base_model=base_model,
            peft_method=self.__class__.__name__.lower(),
            delta_family=self.family.name,
            training_corpus=corpus,
            training_config=self.genome_config,
            **kwargs,
        )

    def num_trainable_params(self) -> int:
        from mlx.utils import tree_flatten
        total = 0
        for _, arr in tree_flatten(self.trainable_parameters()):
            total += int(arr.size)
        return total

    def freeze_base_weights(self) -> None:
        """Freeze all parameters that are designated as fixed base weights.
        Subclasses set self._frozen_keys to the list of attribute names to freeze.
        """
        frozen_keys = getattr(self, "_frozen_keys", [])
        for key in frozen_keys:
            module = getattr(self, key, None)
            if module is not None and hasattr(module, "freeze"):
                module.freeze()


# ---------------------------------------------------------------------------
# Helpers used across multiple PEFT families
# ---------------------------------------------------------------------------

def kaiming_uniform(shape: tuple[int, ...], a: float = 0.01) -> mx.array:
    """Kaiming uniform init for weight matrices."""
    fan_in = shape[1] if len(shape) >= 2 else shape[0]
    bound = (3.0 ** 0.5) * (2.0 / (1 + a ** 2)) ** 0.5 / (fan_in ** 0.5)
    return mx.random.uniform(low=-bound, high=bound, shape=shape)


def zeros_like_shape(shape: tuple[int, ...]) -> mx.array:
    return mx.zeros(shape)


def orthogonal_init(rows: int, cols: int) -> mx.array:
    """Return a (rows, cols) matrix with orthonormal rows (rows<=cols) or columns (rows>cols)."""
    import numpy as np
    if rows <= cols:
        # Orthonormal rows: QR on (cols, rows), return Q.T
        mat = np.random.randn(cols, rows).astype(np.float32)
        q, _ = np.linalg.qr(mat)
        return mx.array(q.T)   # (rows, cols)
    else:
        # Orthonormal columns: QR on (rows, cols)
        mat = np.random.randn(rows, cols).astype(np.float32)
        q, _ = np.linalg.qr(mat)
        return mx.array(q[:rows, :cols])  # (rows, cols)


# ---------------------------------------------------------------------------
# Route plan — used by router and conflict resolver
# ---------------------------------------------------------------------------

@dataclass
class ActiveExpert:
    expert_id: str
    weight: float  # contribution weight [0, 1]
    layer_idx: int | None = None


@dataclass
class RoutePlan:
    active_experts: list[ActiveExpert] = field(default_factory=list)
    budget_vram_mb: float = float("inf")
    safety_pass: bool = True
    conflict_free: bool = True

    def total_weight(self) -> float:
        return sum(e.weight for e in self.active_experts)


# ---------------------------------------------------------------------------
# Hardware / budget constraints
# ---------------------------------------------------------------------------

@dataclass
class HardwareBudget:
    train_vram_mb: float = 16_000    # 16 GB unified memory (M2)
    infer_vram_mb: float = 16_000
    latency_target_ms: float = 100.0
    deployment_target: str = "local_apple_silicon"


@dataclass
class AdaptationConstraints:
    hardware: HardwareBudget = field(default_factory=HardwareBudget)
    max_trainable_params: int = 10_000_000
    retention_requirement: float = 0.92   # minimum base-model retention score
    safety_level: str = "medium"
    allow_quantization: bool = True
    prefer_mergeable: bool = True
