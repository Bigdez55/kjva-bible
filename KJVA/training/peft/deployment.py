"""
peft/deployment.py — Deployment and Export Manager

Handles all deployment modes:
  - Merged: fold adapter weights into base model (fastest inference)
  - Semi-merged: stable deltas merged, dynamic modules kept external
  - Hot-swappable: one adapter at a time, swapped at runtime
  - Routed: multiple adapters activated dynamically
  - Quantized edge export: compressed for consumer hardware
  - Cloud service: packaged for cloud inference endpoints
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
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
    CLOUD_SERVICE  = "cloud_service"


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

    def merge(
        self,
        adapter_path: str,
        output_path: str,
        alpha: float = 16.0,
        rank: int = 8,
        residuals_output: str | None = None,
    ) -> str:
        """Fold LoRA deltas into base safetensors and write merged weights.

        Calls apply_adapter() from scripts/merge_omni_to_safetensors.py to
        perform the actual weight arithmetic: W_merged = W_frozen + (B @ A) * (alpha/rank).
        IA3, BitFit, and PrefixTuning are intentionally not baked — they are
        jointly optimized and require the MLX hot-swap path (serve_adapted_model.py).

        If residuals_output is given, extract IA3+BitFit+Prefix into a separate NPZ.
        Returns the path to the written merge manifest.
        """
        # Locate the merge script relative to this file
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        merge_script = scripts_dir / "merge_omni_to_safetensors.py"

        # Import apply_adapter and helpers from merge script at runtime
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "merge_omni_to_safetensors", str(merge_script)
        )
        merge_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(merge_mod)

        output = Path(output_path)
        output.mkdir(parents=True, exist_ok=True)

        merged_safetensors = output / "merged_weights.safetensors"

        # Load base weights and apply LoRA deltas
        weights = merge_mod.load_safetensors_as_numpy(self.base_model_path)
        weights = merge_mod.apply_adapter(
            weights, adapter_path, alpha=alpha, rank=rank, verbose=False
        )
        merge_mod.save_safetensors(weights, str(merged_safetensors))

        sha = merge_mod.sha256_file(str(merged_safetensors))
        size_mb = merged_safetensors.stat().st_size / (1 << 20)

        residuals_result: dict = {}
        if residuals_output:
            residuals_result = merge_mod.extract_residuals(
                adapter_path, residuals_output, verbose=False
            )

        manifest = {
            "merge_manifest": {
                "base_model_path": self.base_model_path,
                "adapter_path": adapter_path,
                "output_path": str(output),
                "merged_safetensors": str(merged_safetensors),
                "merged_sha256": sha,
                "size_mb": round(size_mb, 2),
                "alpha": alpha,
                "rank": rank,
                "merge_strategy": "additive",
                "baked_operators": ["lora"],
                "skipped_operators": ["ia3", "bitfit", "prefix_tuning"],
                "residuals_npz": residuals_output,
                "residual_count": residuals_result.get("residual_count", 0),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "complete",
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
        alpha: float = 16.0,
        rank: int = 8,
        gguf_dtype: str = "q4_0",
    ) -> DeploymentPackage:
        """Create a self-contained deployment package directory and return a
        DeploymentPackage descriptor.

        Mode-specific dispatch:
          SEMI_MERGED    — bake LoRA into safetensors via apply_adapter(); extract
                           IA3+BitFit+Prefix as residuals NPZ for the MLX runtime path.
          MERGED         — bake LoRA via apply_adapter() (same arithmetic, residuals omitted).
          EDGE_QUANTIZED — bake LoRA first, then invoke safetensors_to_gguf.py to
                           produce a GGUF file at the requested dtype.
          HOT_SWAPPABLE / ROUTED / CLOUD_SERVICE — copy adapter weights as-is.
        """
        pkg_dir = self.export_dir / genome.name
        pkg_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        adapter_paths: list[str] = []
        genome_paths: list[str] = []
        routing_policy_path: str | None = None

        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"

        # --- Mode-specific dispatch ---
        if mode in (DeploymentMode.SEMI_MERGED, DeploymentMode.MERGED):
            import importlib.util
            merge_script = scripts_dir / "merge_omni_to_safetensors.py"
            spec = importlib.util.spec_from_file_location(
                "merge_omni_to_safetensors", str(merge_script)
            )
            merge_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(merge_mod)

            merged_path = str(pkg_dir / "merged_weights.safetensors")
            weights = merge_mod.load_safetensors_as_numpy(self.base_model_path)
            weights = merge_mod.apply_adapter(
                weights, adapter_path, alpha=alpha, rank=rank, verbose=False
            )
            merge_mod.save_safetensors(weights, merged_path)
            adapter_paths.append(merged_path)

            if mode == DeploymentMode.SEMI_MERGED:
                residuals_path = str(pkg_dir / "residuals.npz")
                merge_mod.extract_residuals(adapter_path, residuals_path, verbose=False)
                adapter_paths.append(residuals_path)

        elif mode == DeploymentMode.EDGE_QUANTIZED:
            import importlib.util
            merge_script = scripts_dir / "merge_omni_to_safetensors.py"
            spec = importlib.util.spec_from_file_location(
                "merge_omni_to_safetensors", str(merge_script)
            )
            merge_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(merge_mod)

            merged_safetensors = str(pkg_dir / "merged_weights.safetensors")
            weights = merge_mod.load_safetensors_as_numpy(self.base_model_path)
            weights = merge_mod.apply_adapter(
                weights, adapter_path, alpha=alpha, rank=rank, verbose=False
            )
            merge_mod.save_safetensors(weights, merged_safetensors)

            gguf_path = str(pkg_dir / f"{genome.name}.gguf")
            gguf_script = scripts_dir / "safetensors_to_gguf.py"
            base_model_dir = Path(self.base_model_path).parent
            subprocess.run(
                [
                    sys.executable,
                    str(gguf_script),
                    "--weights", merged_safetensors,
                    "--config", str(base_model_dir / "model_config.json"),
                    "--vocab", str(base_model_dir / "byte_vocab.json"),
                    "--output", gguf_path,
                    "--dtype", gguf_dtype,
                ],
                check=True,
            )
            adapter_paths.append(gguf_path)

        else:
            # HOT_SWAPPABLE, ROUTED, CLOUD_SERVICE: copy adapter weights as-is
            src_adapter = Path(adapter_path)
            if src_adapter.exists():
                dest_adapter = pkg_dir / src_adapter.name
                shutil.copy2(src_adapter, dest_adapter)
                adapter_paths.append(str(dest_adapter))
            else:
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
