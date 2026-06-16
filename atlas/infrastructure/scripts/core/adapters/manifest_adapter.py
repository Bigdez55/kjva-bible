from __future__ import annotations

from atlas_models import load_text, read_yaml
from atlas_paths import ROOT


def load() -> dict:
    root_manifest = ROOT / "atlas.manifest.yaml"
    project_manifest = ROOT / "18_registry" / "project.manifest.yaml"
    apex_version = ROOT / "APEX_VERSION.md"
    bookworm_manifest = ROOT / "38_bookworm_engine" / "bookworm.manifest.yaml"
    return {
        "atlas_manifest": "present" if root_manifest.exists() else "missing",
        "project_manifest": "present" if project_manifest.exists() else "missing",
        "apex_version": load_text(apex_version, 120).splitlines()[0] if apex_version.exists() else "missing",
        "bookworm_manifest": "present" if bookworm_manifest.exists() and bookworm_manifest.stat().st_size else "missing",
        "root_manifest_data": read_yaml(root_manifest),
        "project_manifest_data": read_yaml(project_manifest).get("project", {}),
    }
