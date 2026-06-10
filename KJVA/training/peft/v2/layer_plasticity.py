"""layer_plasticity.py — seven-layer plasticity map (Omni-PEFT++ §11.2 step 8).

Pure-python. Partitions a TokenlessLM into 7 plasticity zones and recommends PEFT
methods per zone (embeddings frozen; attention vs MLP get different operators;
late layers are most plastic). Mirrors the intent of v1 peft/profiler.py without
importing it (keeps this module mlx/torch-free for any-env testing).
"""
from __future__ import annotations

from dataclasses import dataclass, field

ZONES = ("embeddings", "early_attn", "early_mlp", "middle", "late_attn", "late_mlp", "layernorm")


@dataclass
class LayerPlasticityV2:
    n_layers: int
    zones: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def build(cls, model_config: dict) -> "LayerPlasticityV2":
        n = int(model_config.get("n_layers", 8))
        late_start = max(1, int(n * 0.6))
        z = {
            "embeddings": {"layers": [], "plasticity": 0.0, "recommend": []},          # frozen
            "layernorm": {"layers": list(range(n)), "plasticity": 0.1, "recommend": ["bitfit"]},
            "early_attn": {"layers": list(range(late_start)), "plasticity": 0.3,
                           "recommend": ["ia3", "lora"]},
            "early_mlp": {"layers": list(range(late_start)), "plasticity": 0.4,
                          "recommend": ["lora", "houlsby"]},
            "middle": {"layers": list(range(n // 4, 3 * n // 4)), "plasticity": 0.5,
                       "recommend": ["lora", "adalora"]},
            "late_attn": {"layers": list(range(late_start, n)), "plasticity": 0.8,
                          "recommend": ["dora", "lora"]},
            "late_mlp": {"layers": list(range(late_start, n)), "plasticity": 0.9,
                         "recommend": ["dora", "houlsby"]},
        }
        return cls(n_layers=n, zones=z)

    def zone_of(self, layer_idx: int, sublayer: str) -> str:
        """sublayer ∈ {attn, mlp, norm, embed}."""
        if sublayer == "embed":
            return "embeddings"
        if sublayer == "norm":
            return "layernorm"
        late = layer_idx >= max(1, int(self.n_layers * 0.6))
        if sublayer == "attn":
            return "late_attn" if late else "early_attn"
        return "late_mlp" if late else "early_mlp"

    def recommend(self, layer_idx: int, sublayer: str) -> list[str]:
        return list(self.zones[self.zone_of(layer_idx, sublayer)]["recommend"])

    def plasticity(self, layer_idx: int, sublayer: str) -> float:
        return float(self.zones[self.zone_of(layer_idx, sublayer)]["plasticity"])
