"""
peft/profiler.py — Layer Plasticity Profiler

Scans a TokenlessLM config and produces a LayerPlasticityMap: a per-layer
analysis that tells the compiler which PEFT methods make sense at which layers.

Doctrine:
  Early layers  → preserve (use IA3 or tiny LoRA only)
  Middle layers → weight-space adaptation (AdaLoRA, LoRA)
  Late layers   → high-capacity adaptation (DoRA, higher-rank LoRA)
  MLP blocks    → knowledge/transformation (AdaLoRA or adapters)
  Attention     → relation/retrieval (LoRA, DoRA)
  LayerNorm     → tune cautiously only for calibration
  Embeddings    → freeze by default
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .base import AdaptationConstraints


# ---------------------------------------------------------------------------
# Layer profile
# ---------------------------------------------------------------------------

@dataclass
class LayerProfile:
    layer_idx: int
    layer_type: str  # attention_q/k/v/o, mlp_gate/up/down, layernorm, embedding
    in_features: int
    out_features: int
    recommended_methods: list[str]
    recommended_rank_min: int
    recommended_rank_max: int
    can_freeze: bool
    sensitivity: str  # "high", "medium", "low"
    is_merge_safe: bool = False
    is_bottleneck: bool = False


# ---------------------------------------------------------------------------
# Plasticity map
# ---------------------------------------------------------------------------

@dataclass
class LayerPlasticityMap:
    profiles: list[LayerProfile]
    n_layers: int
    total_params: int
    summary: dict = field(default_factory=dict)

    def get_by_type(self, layer_type: str) -> list[LayerProfile]:
        return [p for p in self.profiles if p.layer_type == layer_type]

    def get_by_layer(self, layer_idx: int) -> list[LayerProfile]:
        return [p for p in self.profiles if p.layer_idx == layer_idx]


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------

class ModelProfiler:
    """
    Produces a LayerPlasticityMap from a model config dict.

    Does NOT load actual weights — heuristic analysis only.

    Expected config keys:
      vocab_size, n_layers, d_model, d_ffn (optional), n_heads, head_dim (optional)
    """

    def profile(
        self,
        model_config_dict: dict,
        constraints: AdaptationConstraints,
    ) -> LayerPlasticityMap:
        n_layers = model_config_dict.get("n_layers", 6)
        d_model = model_config_dict.get("d_model", 384)
        d_ffn = model_config_dict.get("d_ffn", d_model * 4)
        vocab_size = model_config_dict.get("vocab_size", 16000)

        profiles: list[LayerProfile] = []

        # Embedding layer (layer_idx = -1 to signal pre-block)
        profiles.append(LayerProfile(
            layer_idx=-1,
            layer_type="embedding",
            in_features=vocab_size,
            out_features=d_model,
            recommended_methods=[],
            recommended_rank_min=0,
            recommended_rank_max=0,
            can_freeze=True,
            sensitivity="low",
            is_merge_safe=True,
            is_bottleneck=(d_model < vocab_size),
        ))

        early_end = n_layers // 3
        mid_end = 2 * n_layers // 3

        for layer_idx in range(n_layers):
            zone = self._zone(layer_idx, early_end, mid_end)
            attn_methods, rank_min, rank_max, sensitivity = self._attn_heuristic(zone)
            mlp_methods, _, _, _ = self._mlp_heuristic(zone)

            # Attention sub-modules
            for sub in ("attention_q", "attention_k", "attention_v", "attention_o"):
                profiles.append(LayerProfile(
                    layer_idx=layer_idx,
                    layer_type=sub,
                    in_features=d_model,
                    out_features=d_model,
                    recommended_methods=list(attn_methods),
                    recommended_rank_min=rank_min,
                    recommended_rank_max=rank_max,
                    can_freeze=(zone == "early"),
                    sensitivity=sensitivity,
                    is_merge_safe=(zone == "late" or zone == "early"),
                    is_bottleneck=False,
                ))

            # MLP sub-modules
            for sub, (in_f, out_f) in {
                "mlp_gate": (d_model, d_ffn),
                "mlp_up": (d_model, d_ffn),
                "mlp_down": (d_ffn, d_model),
            }.items():
                profiles.append(LayerProfile(
                    layer_idx=layer_idx,
                    layer_type=sub,
                    in_features=in_f,
                    out_features=out_f,
                    recommended_methods=list(mlp_methods),
                    recommended_rank_min=rank_min,
                    recommended_rank_max=rank_max,
                    can_freeze=(zone == "early"),
                    sensitivity=sensitivity,
                    is_merge_safe=(zone == "late" or zone == "early"),
                    is_bottleneck=(out_f < in_f),
                ))

            # LayerNorm (two per block: norm1 before attn, norm2 before mlp)
            for sub in ("layernorm",):
                profiles.append(LayerProfile(
                    layer_idx=layer_idx,
                    layer_type=sub,
                    in_features=d_model,
                    out_features=d_model,
                    recommended_methods=["bitfit"],
                    recommended_rank_min=0,
                    recommended_rank_max=0,
                    can_freeze=False,
                    sensitivity="low",
                    is_merge_safe=True,
                    is_bottleneck=False,
                ))

        total_params = self._count_params(vocab_size, d_model, d_ffn, n_layers)
        summary = {
            "n_layers": n_layers,
            "d_model": d_model,
            "d_ffn": d_ffn,
            "vocab_size": vocab_size,
            "early_layers": list(range(0, early_end)),
            "middle_layers": list(range(early_end, mid_end)),
            "late_layers": list(range(mid_end, n_layers)),
            "total_params": total_params,
        }

        return LayerPlasticityMap(
            profiles=profiles,
            n_layers=n_layers,
            total_params=total_params,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _zone(self, layer_idx: int, early_end: int, mid_end: int) -> str:
        if layer_idx < early_end:
            return "early"
        if layer_idx < mid_end:
            return "middle"
        return "late"

    def _attn_heuristic(self, zone: str) -> tuple[list[str], int, int, str]:
        """Return (methods, rank_min, rank_max, sensitivity) for attention zones."""
        if zone == "early":
            return (["ia3", "bitfit"], 1, 4, "low")
        if zone == "middle":
            return (["lora", "adalora", "ia3"], 4, 16, "medium")
        # late
        return (["dora", "lora", "adalora"], 8, 32, "high")

    def _mlp_heuristic(self, zone: str) -> tuple[list[str], int, int, str]:
        """Return (methods, rank_min, rank_max, sensitivity) for MLP zones."""
        if zone == "early":
            return (["ia3", "bitfit"], 1, 4, "low")
        if zone == "middle":
            return (["adalora", "lora", "houlsby_adapter"], 4, 16, "medium")
        return (["adalora", "lora", "houlsby_adapter", "dora"], 8, 32, "high")

    def _count_params(self, vocab_size: int, d_model: int, d_ffn: int, n_layers: int) -> int:
        """Estimate total non-embedding parameter count."""
        embed = vocab_size * d_model
        # Per-layer: 4 attn matrices (q,k,v,o) + 3 mlp matrices (gate,up,down) + layernorm
        per_layer = (
            4 * d_model * d_model
            + 2 * d_model * d_ffn  # gate + up
            + d_ffn * d_model      # down
            + 2 * d_model          # two layernorms (scale params)
        )
        return embed + n_layers * per_layer
