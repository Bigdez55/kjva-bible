"""
peft/registry.py — Adapter Genome Registry

Stores every trained adapter as a versioned genome record with identity,
purpose, benchmarks, compatibility rules, merge status, and rollback metadata.

Registry lives at: ml-training/adapters/
  staging/   — in-progress, unvalidated adapters
  gated/     — validated, production-ready adapters
  quarantined/ — adapters removed from active rotation
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .base import AdapterGenomeRecord
from ._yaml import dict_to_yaml


# ---------------------------------------------------------------------------
# Registry entry
# ---------------------------------------------------------------------------

@dataclass
class RegistryEntry:
    genome: AdapterGenomeRecord
    checkpoint_path: str   # relative path to adapter.safetensors or .npz
    genome_path: str       # path to adapter_genome.yaml
    status: str            # "staging", "gated", "quarantined"
    registered_at: str


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class AdapterGenomeRegistry:
    """
    Persistent, file-backed registry of all adapter genomes.

    Directory layout::

        registry_root/
          staging/
            {adapter_name}/
              adapter_genome.yaml
          gated/
            {adapter_name}/
              adapter_genome.yaml
          quarantined/
            {adapter_name}/
              adapter_genome.yaml
          registry.json          <- index of all entries
    """

    def __init__(self, registry_root: str = "ml-training/adapters") -> None:
        self.registry_root = Path(registry_root)
        self.entries: dict[str, RegistryEntry] = {}
        self._registry_file = self.registry_root / "registry.json"

        # Create base dirs
        for sub in ("staging", "gated", "quarantined"):
            (self.registry_root / sub).mkdir(parents=True, exist_ok=True)

        if self._registry_file.exists():
            self.load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(
        self,
        genome: AdapterGenomeRecord,
        checkpoint_path: str,
        status: str = "staging",
    ) -> RegistryEntry:
        """Register a new adapter genome and write its yaml file."""
        now = datetime.now(timezone.utc).isoformat()
        adapter_dir = self.registry_root / status / genome.name
        adapter_dir.mkdir(parents=True, exist_ok=True)

        genome_path = adapter_dir / "adapter_genome.yaml"
        self._write_genome_yaml(genome, genome_path)

        entry = RegistryEntry(
            genome=genome,
            checkpoint_path=checkpoint_path,
            genome_path=str(genome_path),
            status=status,
            registered_at=now,
        )
        self.entries[genome.name] = entry
        self.save()
        return entry

    def promote(self, name: str) -> None:
        """Move adapter from staging → gated. Requires non-empty evaluation scores."""
        entry = self._get(name)
        if entry.status == "gated":
            return  # already promoted

        if not entry.genome.evaluation:
            raise ValueError(
                f"Cannot promote '{name}': genome.evaluation is empty. "
                "Run evaluation before promoting to gated."
            )

        self._move_entry(name, "gated")

    def quarantine(self, name: str, reason: str) -> None:
        """Mark adapter as quarantined, adding reason to genome notes."""
        entry = self._get(name)
        entry.genome.evaluation["quarantine_reason"] = reason
        self._move_entry(name, "quarantined")

    def rollback(self, name: str) -> None:
        """Restore adapter to the version specified in genome.rollback_previous."""
        entry = self._get(name)
        prev = entry.genome.rollback_previous
        if not prev:
            raise ValueError(f"No rollback target for '{name}'.")
        if prev not in self.entries:
            raise KeyError(f"Rollback target '{prev}' not found in registry.")
        # Promote the previous version back to gated
        self.promote(prev)

    def query(
        self,
        domains: list[str] | None = None,
        tasks: list[str] | None = None,
    ) -> list[RegistryEntry]:
        """Filter entries by domain and/or task keyword overlap."""
        results: list[RegistryEntry] = []
        for entry in self.entries.values():
            if entry.status == "quarantined":
                continue
            if domains and not any(d in entry.genome.purpose_domains for d in domains):
                continue
            if tasks and not any(t in entry.genome.purpose_tasks for t in tasks):
                continue
            results.append(entry)
        return results

    def save(self) -> None:
        """Serialize all entries to registry.json."""
        data: dict = {}
        for name, entry in self.entries.items():
            data[name] = {
                "genome": entry.genome.to_yaml_dict(),
                "checkpoint_path": entry.checkpoint_path,
                "genome_path": entry.genome_path,
                "status": entry.status,
                "registered_at": entry.registered_at,
            }
        self._registry_file.write_text(json.dumps(data, indent=2))

    def load(self) -> None:
        """Read registry.json and reconstruct all entries."""
        raw = json.loads(self._registry_file.read_text())
        for name, d in raw.items():
            ag = d["genome"]["adapter_genome"]
            genome = AdapterGenomeRecord(
                name=ag["name"],
                version=ag["version"],
                base_model=ag["base_model"],
                peft_method=ag["peft_method"],
                delta_family=ag["delta_family"],
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
            self.entries[name] = RegistryEntry(
                genome=genome,
                checkpoint_path=d["checkpoint_path"],
                genome_path=d["genome_path"],
                status=d["status"],
                registered_at=d["registered_at"],
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, name: str) -> RegistryEntry:
        if name not in self.entries:
            raise KeyError(f"Adapter '{name}' not found in registry.")
        return self.entries[name]

    def _move_entry(self, name: str, new_status: str) -> None:
        """Physically move genome yaml to new status directory and update entry."""
        entry = self._get(name)
        old_dir = Path(entry.genome_path).parent
        new_dir = self.registry_root / new_status / name
        new_dir.mkdir(parents=True, exist_ok=True)

        new_genome_path = new_dir / "adapter_genome.yaml"

        if old_dir.exists() and old_dir != new_dir:
            # Copy yaml to new location
            src_yaml = Path(entry.genome_path)
            if src_yaml.exists():
                shutil.copy2(src_yaml, new_genome_path)
                src_yaml.unlink()
            # Remove old dir if empty
            try:
                old_dir.rmdir()
            except OSError:
                pass

        # Re-write yaml with latest genome state (may have been modified)
        self._write_genome_yaml(entry.genome, new_genome_path)

        entry.genome_path = str(new_genome_path)
        entry.status = new_status
        self.save()

    def _write_genome_yaml(self, genome: AdapterGenomeRecord, path: Path) -> None:
        yaml_text = dict_to_yaml(genome.to_yaml_dict())
        path.write_text(yaml_text)
