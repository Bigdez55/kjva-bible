#!/usr/bin/env python3
"""Acquire assistant surfaces from repo-local .claude/.codex/.gemini folders.

This script is intentionally non-destructive. It never rewrites source assistant
folders, and it separates raw-source preservation from operational registries.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ONEDRIVE = ROOT.parent
GITHUB = Path("/Users/desmondearly/Documents/GitHub")
RUN_ID = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
DEFAULT_OUT = ROOT / "16_knowledge" / "external_collateral" / f"assistant_surfaces_{RUN_ID}"
REGISTRY_OUT = ROOT / "18_registry" / "agent_skill_imports"

SURFACE_DIRS = {".claude", ".codex", ".gemini"}
TEXT_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg"}
INDEX_ONLY_NAMES = {
    "settings.local.json",
    "settings.json",
    "credentials.json",
    "token.json",
    "tokens.json",
    "session.json",
    "secrets.json",
}
EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".turbo",
    "backups",
    "dist",
    "raw_safe_text",
    "external_collateral",
}

EXCLUDED_RELATIVE_PREFIXES = {
    "16_knowledge/external_collateral",
    "28_archive",
    "backups",
    "apps/atlas/dist",
    "apps/atlas/node_modules",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def rel_to_root(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", text).strip("-").lower()
    return value or "unnamed"


def canonical_name(path: Path) -> str:
    stem = path.stem
    parts = [p for p in stem.split("__") if p]
    candidate = parts[-1] if parts else stem
    candidate = re.sub(r"^[0-9a-f]{8,}$", "skill", candidate)
    return slug(candidate)


def norm_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def classify(path: Path) -> str:
    parts = [p.lower() for p in path.parts]
    name = path.name.lower()
    stem = path.stem.lower()
    if "skills" in parts or name == "skill.md" or stem.startswith("skill_") or stem.endswith("-skill"):
        return "skill"
    if "agents" in parts or name.endswith("agent.md") or stem.endswith("-agent") or "_agent" in stem:
        return "agent"
    if "tools" in parts or "tool" in stem:
        return "tool"
    if "agent-memory" in parts or "memory" in stem:
        return "memory"
    if name.startswith("index.") or name.endswith(".registry.yaml"):
        return "index"
    if "commands" in parts or "prompts" in parts:
        return "prompt_or_command"
    return "support"


def is_index_only(path: Path, size: int) -> bool:
    lower_parts = {p.lower() for p in path.parts}
    if path.name.lower() in INDEX_ONLY_NAMES:
        return True
    if {"cache", "sessions", "logs", "state"} & lower_parts:
        return True
    if size > 250_000:
        return True
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return True
    return False


def should_prune_dir(path: Path) -> bool:
    if path.name in EXCLUDED_DIRS or path.name.endswith(".app"):
        return True
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        return False
    return any(rel == prefix or rel.startswith(f"{prefix}/") for prefix in EXCLUDED_RELATIVE_PREFIXES)


def find_repo_root(path: Path) -> Path:
    current = path
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return path


def discover_surface_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        stack = [root]
        while stack:
            current = stack.pop()
            if should_prune_dir(current):
                continue
            if current.name in SURFACE_DIRS:
                for item in current.rglob("*"):
                    if item.is_file() and not any(part in EXCLUDED_DIRS for part in item.parts):
                        key = item.resolve().as_posix()
                        if key not in seen:
                            seen.add(key)
                            files.append(item)
                continue
            try:
                children = list(current.iterdir())
            except OSError:
                continue
            for child in children:
                if child.is_dir() and not should_prune_dir(child):
                    stack.append(child)
    return sorted(files, key=lambda p: p.as_posix())


@dataclass
class ManifestEntry:
    source_path: str
    repo_root: str
    repo_name: str
    surface: str
    asset_type: str
    canonical_name: str
    sha256: str
    size_bytes: int
    preserved: bool
    preservation_path: str | None
    index_only_reason: str | None


@dataclass
class NormalizedEntry:
    id: str
    name: str
    asset_type: str
    preferred_source: str
    sha256: str
    source_count: int
    surfaces: list[str] = field(default_factory=list)
    repos: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    recommended_status: str = "candidate"


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def first_line(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            clean = line.strip().strip("#").strip()
            if clean:
                return clean[:180]
    except OSError:
        pass
    return ""


def build_report(
    out_root: Path,
    manifest: list[ManifestEntry],
    normalized: dict[str, list[NormalizedEntry]],
    duplicate_groups: list[dict[str, Any]],
    roots: list[Path],
) -> str:
    counts: dict[str, int] = {}
    preserved = 0
    for item in manifest:
        counts[item.asset_type] = counts.get(item.asset_type, 0) + 1
        preserved += 1 if item.preserved else 0

    lines = [
        "# Assistant Surface Acquisition Report",
        "",
        f"Generated: {utc_now()}",
        "",
        "## Scope",
        "",
        "Scanned repo roots:",
    ]
    lines.extend(f"- `{root}`" for root in roots if root.exists())
    lines.extend(
        [
            "",
            "Excluded folders: `.git`, `node_modules`, `.next`, `dist`, `build`, virtualenv/cache folders.",
            "",
            "## Results",
            "",
            f"- Files indexed: {len(manifest)}",
            f"- Safe raw files preserved: {preserved}",
            f"- Indexed-only files: {len(manifest) - preserved}",
            f"- Exact duplicate hash groups: {len(duplicate_groups)}",
            f"- Normalized agents: {len(normalized['agents'])}",
            f"- Normalized skills: {len(normalized['skills'])}",
            f"- Normalized tools: {len(normalized['tools'])}",
            "",
            "## Counts By Type",
            "",
        ]
    )
    for key in sorted(counts):
        lines.append(f"- `{key}`: {counts[key]}")
    lines.extend(
        [
            "",
            "## Operational Rule",
            "",
            "Raw assistant surfaces remain preserved as evidence. Operational use should go through the normalized registries under `18_registry/agent_skill_imports/` and then through active skill/router promotion.",
            "",
            "## Output Files",
            "",
            f"- `{rel_to_root(out_root / 'file_manifest.yaml')}`",
            f"- `{rel_to_root(out_root / 'source_index.yaml')}`",
            f"- `{rel_to_root(out_root / 'duplicate_groups.yaml')}`",
            f"- `{rel_to_root(out_root / 'normalized_agents.yaml')}`",
            f"- `{rel_to_root(out_root / 'normalized_skills.yaml')}`",
            f"- `{rel_to_root(out_root / 'normalized_tools.yaml')}`",
            f"- `{rel_to_root(REGISTRY_OUT / 'assistant_surface_inventory.yaml')}`",
            f"- `{rel_to_root(REGISTRY_OUT / 'normalized_agent_registry.yaml')}`",
            f"- `{rel_to_root(REGISTRY_OUT / 'normalized_skill_registry.yaml')}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--include-github", action="store_true", default=True)
    parser.add_argument("--no-github", action="store_false", dest="include_github")
    args = parser.parse_args()

    roots = [ONEDRIVE]
    if args.include_github and GITHUB.exists():
        roots.append(GITHUB)

    files = discover_surface_files(roots)
    out_root = args.out
    raw_root = out_root / "raw_safe_text"
    out_root.mkdir(parents=True, exist_ok=True)
    REGISTRY_OUT.mkdir(parents=True, exist_ok=True)

    manifest: list[ManifestEntry] = []
    by_sha: dict[str, list[ManifestEntry]] = {}
    by_type_name: dict[tuple[str, str], list[ManifestEntry]] = {}

    for source in files:
        raw = source.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        repo_root = find_repo_root(source)
        surface = next((part for part in source.parts if part in SURFACE_DIRS), "unknown")
        asset_type = classify(source)
        name = canonical_name(source)
        index_only = is_index_only(source, len(raw))
        preservation_path: str | None = None
        reason: str | None = None
        if index_only:
            reason = "sensitive_state_large_or_non_text"
        else:
            try:
                rel_source = source.relative_to(repo_root)
            except ValueError:
                rel_source = Path(source.name)
            dest = raw_root / slug(repo_root.name) / rel_source
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            preservation_path = rel_to_root(dest)

        entry = ManifestEntry(
            source_path=source.as_posix(),
            repo_root=repo_root.as_posix(),
            repo_name=repo_root.name,
            surface=surface,
            asset_type=asset_type,
            canonical_name=name,
            sha256=sha,
            size_bytes=len(raw),
            preserved=not index_only,
            preservation_path=preservation_path,
            index_only_reason=reason,
        )
        manifest.append(entry)
        by_sha.setdefault(sha, []).append(entry)
        by_type_name.setdefault((asset_type, norm_key(name)), []).append(entry)

    duplicate_groups = [
        {
            "sha256": sha,
            "count": len(entries),
            "asset_type": entries[0].asset_type,
            "canonical_name": entries[0].canonical_name,
            "sources": [entry.source_path for entry in entries],
        }
        for sha, entries in sorted(by_sha.items())
        if len(entries) > 1
    ]

    normalized: dict[str, list[NormalizedEntry]] = {"agents": [], "skills": [], "tools": []}
    for (asset_type, name_key), entries in sorted(by_type_name.items()):
        if asset_type not in {"agent", "skill", "tool"}:
            continue
        chosen = sorted(entries, key=lambda e: (not e.preserved, len(e.source_path), e.source_path))[0]
        summary = first_line(Path(chosen.source_path))
        normalized_entry = NormalizedEntry(
            id=f"{asset_type.upper()}_{name_key.replace('-', '_').upper()}",
            name=chosen.canonical_name,
            asset_type=asset_type,
            preferred_source=chosen.preservation_path or chosen.source_path,
            sha256=chosen.sha256,
            source_count=len(entries),
            surfaces=sorted({entry.surface for entry in entries}),
            repos=sorted({entry.repo_name for entry in entries}),
            aliases=sorted({entry.canonical_name for entry in entries if entry.canonical_name != chosen.canonical_name}),
            recommended_status="active_candidate" if summary else "candidate",
        )
        normalized[f"{asset_type}s"].append(normalized_entry)

    source_index = {
        "generated_at": utc_now(),
        "scope_roots": [root.as_posix() for root in roots if root.exists()],
        "raw_preservation_root": rel_to_root(raw_root),
        "registry_root": rel_to_root(REGISTRY_OUT),
        "source_count": len(manifest),
        "unique_hash_count": len(by_sha),
        "duplicate_group_count": len(duplicate_groups),
    }
    manifest_data = [asdict(entry) for entry in manifest]
    normalized_data = {key: [asdict(entry) for entry in value] for key, value in normalized.items()}

    write_yaml(out_root / "source_index.yaml", source_index)
    write_yaml(out_root / "file_manifest.yaml", {"files": manifest_data})
    write_yaml(out_root / "duplicate_groups.yaml", {"duplicate_groups": duplicate_groups})
    write_yaml(out_root / "normalized_agents.yaml", {"agents": normalized_data["agents"]})
    write_yaml(out_root / "normalized_skills.yaml", {"skills": normalized_data["skills"]})
    write_yaml(out_root / "normalized_tools.yaml", {"tools": normalized_data["tools"]})
    write_json(out_root / "file_manifest.json", {"files": manifest_data})

    write_yaml(REGISTRY_OUT / "assistant_surface_inventory.yaml", source_index | {"latest_run": rel_to_root(out_root)})
    write_yaml(REGISTRY_OUT / "assistant_surface_duplicates.yaml", {"duplicate_groups": duplicate_groups})
    write_yaml(REGISTRY_OUT / "normalized_agent_registry.yaml", {"agents": normalized_data["agents"]})
    write_yaml(REGISTRY_OUT / "normalized_skill_registry.yaml", {"skills": normalized_data["skills"]})
    write_yaml(REGISTRY_OUT / "normalized_tool_registry.yaml", {"tools": normalized_data["tools"]})

    report = build_report(out_root, manifest, normalized, duplicate_groups, roots)
    (out_root / "ACQUISITION_REPORT.md").write_text(report, encoding="utf-8")
    (REGISTRY_OUT / "ACQUISITION_REPORT.md").write_text(report, encoding="utf-8")

    print(f"indexed={len(manifest)} unique_hashes={len(by_sha)} duplicates={len(duplicate_groups)}")
    print(f"agents={len(normalized['agents'])} skills={len(normalized['skills'])} tools={len(normalized['tools'])}")
    print(f"wrote={rel_to_root(out_root)}")


if __name__ == "__main__":
    main()
