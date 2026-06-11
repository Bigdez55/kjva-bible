"""Omni-PEFT++ v2 layer (§11.1 "Add" set).

Framework-neutral (numpy/stdlib) so it imports and tests without torch or mlx.
Modules: adapter_ir, adapter_genome_v2, layer_plasticity, tournament_v2, determinism.
"""
from . import (
    adapter_ir, adapter_genome_v2,
    layer_plasticity, tournament_v2, determinism,
)
from .adapter_ir import AdapterIR
from .adapter_genome_v2 import AdapterGenomeV2
from .layer_plasticity import LayerPlasticityV2
from .tournament_v2 import TournamentV2, Candidate

__all__ = [
    "adapter_ir", "adapter_genome_v2", "layer_plasticity",
    "tournament_v2", "determinism",
    "AdapterIR", "AdapterGenomeV2", "LayerPlasticityV2",
    "TournamentV2", "Candidate",
]
