#!/usr/bin/env python3
"""Validate assistant surface acquisition outputs."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "16_knowledge" / "external_collateral" / "assistant_surfaces_2026-05-20"
REGISTRY = ROOT / "18_registry" / "agent_skill_imports"


def load_yaml(path: Path):
    if not path.exists():
        raise AssertionError(f"Missing required output: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main() -> int:
    source_index = load_yaml(RUN / "source_index.yaml")
    manifest = load_yaml(RUN / "file_manifest.yaml")["files"]
    agents = load_yaml(REGISTRY / "normalized_agent_registry.yaml")["agents"]
    skills = load_yaml(REGISTRY / "normalized_skill_registry.yaml")["skills"]
    tools = load_yaml(REGISTRY / "normalized_tool_registry.yaml")["tools"]
    duplicates = load_yaml(REGISTRY / "assistant_surface_duplicates.yaml")["duplicate_groups"]

    assert source_index["source_count"] == len(manifest), "source index count does not match manifest"
    assert source_index["source_count"] > 0, "no assistant surface files indexed"
    assert source_index["unique_hash_count"] > 0, "no unique hashes found"
    assert len(agents) >= 50, f"expected at least 50 normalized agents, found {len(agents)}"
    assert len(skills) >= 40, f"expected at least 40 normalized skills, found {len(skills)}"
    assert len(tools) >= 1, f"expected at least one normalized tool, found {len(tools)}"
    assert duplicates, "expected duplicate groups across propagated repo assets"

    agent_names = {entry["name"] for entry in agents}
    skill_names = {entry["name"] for entry in skills}
    assert "agent-dispatch" in skill_names, "agent-dispatch must remain a skill"
    assert "agent-dispatch" not in agent_names, "agent-dispatch skill misclassified as agent"

    bad_preserved = [
        item for item in manifest
        if item["index_only_reason"] and item["preserved"]
    ]
    assert not bad_preserved, "indexed-only files must not be marked preserved"

    print(
        "assistant surface acquisition valid:",
        f"files={len(manifest)}",
        f"agents={len(agents)}",
        f"skills={len(skills)}",
        f"tools={len(tools)}",
        f"duplicates={len(duplicates)}",
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
