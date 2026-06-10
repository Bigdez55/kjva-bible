"""
peft/deployment.py — Deployment and Export Manager

Handles all deployment modes:
  - Merged: fold adapter weights into base model (fastest inference)
  - Semi-merged: stable deltas merged, dynamic modules kept external
  - Hot-swappable: one adapter at a time, swapped at runtime
  - Routed: multiple adapters activated dynamically
  - Quantized edge export: compressed for consumer hardware
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from .base import AdapterGenomeRecord
from ._yaml import dict_to_yaml


# ---------------------------------------------------------------------------
# Deployment mode
# ---------------------------------------------------------------------------

class DeploymentMode(Enum):
    MERGED         = "merged"
    SEMI_MERGED    = "semi_merged"
    HOT_SWAPPABLE  = "hot_swappable"
    ROUTED         = "routed"
    EDGE_QUANTIZED = "edge_quantized"


# ---------------------------------------------------------------------------
# Deployment package
# ---------------------------------------------------------------------------

@dataclass
class DeploymentPackage:
    name: str
    mode: DeploymentMode
    base_model_path: str
    adapter_paths: list[str] = field(default_factory=list)
    genome_paths: list[str] = field(default_factory=list)
    routing_policy_path: str | None = None
    manifest_path: str = ""
    created_at: str = ""


# ---------------------------------------------------------------------------
# Deployment manager
# ---------------------------------------------------------------------------

class DeploymentManager:
    """
    Packages, merges, and exports adapter + base-model combinations
    for various deployment targets.
    """

    def __init__(
        self,
        base_model_path: str,
        export_dir: str = "training/exports",
    ) -> None:
        self.base_model_path = base_model_path
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def merge(self, adapter_path: str, output_path: str) -> str:
        """
        Produce a merge manifest describing how the adapter weights should be
        folded into the base model.

        Actual weight arithmetic is deferred to the training loop (which has
        access to live MLX arrays). This method creates the directory
        structure and writes the merge contract.
        """
        output = Path(output_path)
        output.mkdir(parents=True, exist_ok=True)

        manifest = {
            "merge_manifest": {
                "base_model_path": self.base_model_path,
                "adapter_path": adapter_path,
                "output_path": str(output),
                "merge_strategy": "additive",  # W_merged = W_base + (B @ A) * (alpha / rank)
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
                "note": (
                    "Execute merge via training loop: "
                    "merged_weight = base_weight + adapter_delta * scale"
                ),
            }
        }

        manifest_path = output / "merge_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        return str(manifest_path)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(
        self,
        genome: AdapterGenomeRecord,
        adapter_path: str,
        mode: DeploymentMode,
    ) -> DeploymentPackage:
        """
        Create a self-contained deployment package directory and return a
        DeploymentPackage descriptor.
        """
        pkg_dir = self.export_dir / genome.name
        pkg_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        adapter_paths: list[str] = []
        genome_paths: list[str] = []
        routing_policy_path: str | None = None

        # Copy adapter weights if the source exists
        src_adapter = Path(adapter_path)
        if src_adapter.exists():
            dest_adapter = pkg_dir / src_adapter.name
            shutil.copy2(src_adapter, dest_adapter)
            adapter_paths.append(str(dest_adapter))
        else:
            # Record the intended path even if file doesn't exist yet
            adapter_paths.append(adapter_path)

        # Write genome yaml
        genome_yaml_path = pkg_dir / "adapter_genome.yaml"
        genome_yaml_path.write_text(dict_to_yaml(genome.to_yaml_dict()))
        genome_paths.append(str(genome_yaml_path))

        # Write routing policy for ROUTED mode
        if mode == DeploymentMode.ROUTED:
            routing_policy_path = self._write_routing_policy(genome, pkg_dir)

        package = DeploymentPackage(
            name=genome.name,
            mode=mode,
            base_model_path=self.base_model_path,
            adapter_paths=adapter_paths,
            genome_paths=genome_paths,
            routing_policy_path=routing_policy_path,
            created_at=now,
        )

        manifest_path = self._write_manifest(package, pkg_dir)
        package.manifest_path = manifest_path

        return package

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_manifest(self, package: DeploymentPackage, pkg_dir: Path) -> str:
        """Serialize package as JSON manifest and write to disk."""
        manifest = {
            "deployment_manifest": {
                "name": package.name,
                "mode": package.mode.value,
                "base_model_path": package.base_model_path,
                "adapter_paths": package.adapter_paths,
                "genome_paths": package.genome_paths,
                "routing_policy_path": package.routing_policy_path,
                "created_at": package.created_at,
            }
        }
        manifest_path = pkg_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        return str(manifest_path)

    def _write_routing_policy(
        self, genome: AdapterGenomeRecord, pkg_dir: Path
    ) -> str:
        """Write a routing_policy.yaml for ROUTED deployments."""
        policy = {
            "routing_policy": {
                "adapter_name": genome.name,
                "activate_when": genome.routing_activate_when,
                "never_activate_when": genome.routing_never_activate_when,
                "compatible_with": genome.compatible_with,
                "conflicts_with": genome.conflicts_with,
                "hot_swappable": genome.hot_swappable,
                "mergeable": genome.mergeable,
            }
        }
        policy_path = pkg_dir / "routing_policy.yaml"
        policy_path.write_text(dict_to_yaml(policy))
        return str(policy_path)
