"""
peft/loader.py — Adapter genome loader (D23).

A *thin*, framework-free loader for adapter **genomes** (identity + routing +
governance metadata).  The router (peft.router.HierarchicalRouter) needs a
populated AdapterGenomeRegistry to make a route plan; this module loads genome
records into a registry without touching weight tensors.

Import-safety: pure-python (json / dataclasses / pathlib).  No torch, no mlx at
module load.  Weight tensors are NOT loaded here — if a caller ever needs the
actual adapter weights it must lazy-import mlx and read the .safetensors itself.
This keeps the routing/tournament DEFINED->CALLED path exercisable in a
weight-free, framework-free environment.
"""
from __future__ import annotations

import json
from pathlib import Path

from .base import AdapterGenomeRecord


# ---------------------------------------------------------------------------
# Genome dict → AdapterGenomeRecord
# ---------------------------------------------------------------------------

def genome_from_dict(d: dict) -> AdapterGenomeRecord:
    """
    Build an AdapterGenomeRecord from a parsed ``adapter_genome`` block.

    Accepts either the nested wrapper ``{"adapter_genome": {...}}`` (as written
    by AdapterGenomeRecord.to_yaml_dict / registry.json) or a bare inner block.
    Mirrors AdapterGenomeRegistry.load() so the two stay shape-compatible.
    """
    ag = d.get("adapter_genome", d)
    return AdapterGenomeRecord(
        name=ag["name"],
        version=ag.get("version", "1.0.0"),
        base_model=ag.get("base_model", "base_tokenless_v1"),
        peft_method=ag.get("peft_method", ""),
        delta_family=ag.get("delta_family", ""),
        purpose_domains=ag.get("purpose", {}).get("domains", []),
        purpose_tasks=ag.get("purpose", {}).get("tasks", []),
        training_corpus=ag.get("training", {}).get("corpus", ""),
        training_config={
            k: v for k, v in ag.get("training", {}).items() if k != "corpus"
        },
        evaluation=ag.get("evaluation", {}),
        routing_activate_when=ag.get("routing", {}).get("activate_when", []),
        routing_never_activate_when=ag.get("routing", {}).get("never_activate_when", []),
        compatible_with=ag.get("compatibility", {}).get("compatible_with", []),
        conflicts_with=ag.get("compatibility", {}).get("conflicts_with", []),
        mergeable=ag.get("deployment", {}).get("mergeable", True),
        hot_swappable=ag.get("deployment", {}).get("hot_swappable", True),
        rollback_previous=ag.get("rollback", {}).get("previous_stable", ""),
    )


def load_genome_json(path: str | Path) -> AdapterGenomeRecord:
    """Load a single adapter genome from a JSON file (genome dict)."""
    raw = json.loads(Path(path).read_text())
    return genome_from_dict(raw)


# ---------------------------------------------------------------------------
# Registry hydration helper
# ---------------------------------------------------------------------------

def build_registry_from_genomes(
    genomes: list[AdapterGenomeRecord],
    registry_root: str = "training/adapters",
    status: str = "gated",
):
    """
    Return an in-memory AdapterGenomeRegistry populated with the given genomes.

    Used to give the router something to route over when no on-disk registry has
    been materialised yet (e.g. smoke tests, dry runs).  Does not write to disk
    beyond the registry's own dir bootstrap; entries are registered in-process.
    """
    from .registry import AdapterGenomeRegistry, RegistryEntry
    from datetime import datetime, timezone

    reg = AdapterGenomeRegistry(registry_root=registry_root)
    now = datetime.now(timezone.utc).isoformat()
    for g in genomes:
        reg.entries[g.name] = RegistryEntry(
            genome=g,
            checkpoint_path="",
            genome_path="",
            status=status,
            registered_at=now,
        )
    return reg
