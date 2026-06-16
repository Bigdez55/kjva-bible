"""Deterministic serialization helpers for Atlas Platform Core models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return data if isinstance(data, dict) else {"value": data}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


def slug(value: str, max_len: int = 80) -> str:
    """Create a stable ASCII-safe id fragment for filenames and YAML IDs."""

    text = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    parts = [part for part in text.split("_") if part]
    slug_value = "_".join(parts)
    if not slug_value:
        return "node"
    return slug_value[:max_len]


def load_text(path: Path, limit: int = 800) -> str:
    if not path.exists():
        return ""
    return path.read_text(errors="ignore").strip()[:limit]
