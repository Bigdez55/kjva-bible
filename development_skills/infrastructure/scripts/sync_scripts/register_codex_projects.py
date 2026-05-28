#!/usr/bin/env python3
"""Register all known repo roots as trusted Codex projects and ensure baseline MCP settings."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parents[3]
ONEDRIVE = ROOT.parent
LEDGER = ROOT / "platform" / "systems" / "18_registry" / "repo_ledger.yaml"
CODEX_CONFIG = Path.home() / ".codex" / "config.toml"


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def find_git_roots(base: Path) -> list[Path]:
    roots: list[Path] = []
    if (base / ".git").exists():
        roots.append(base)
    for p in base.glob("*"):
        if p.is_dir() and (p / ".git").exists():
            roots.append(p)
        if p.is_dir():
            for q in p.glob("*"):
                if q.is_dir() and (q / ".git").exists():
                    roots.append(q)
    uniq: list[Path] = []
    seen: set[str] = set()
    for p in roots:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def pick_repo_root(name: str, local_path: str | None, children: Iterable[Path]) -> Path | None:
    candidates: list[Path] = []
    if local_path:
        candidates.append(Path(local_path))

    target = norm(name)
    for p in children:
        n = norm(p.name)
        if n == target or target in n or n in target:
            candidates.append(p)

    deduped: list[Path] = []
    seen: set[str] = set()
    for p in candidates:
        if p.exists():
            key = str(p.resolve())
            if key not in seen:
                seen.add(key)
                deduped.append(p)

    if not deduped:
        return None

    best: Path | None = None
    score = -10**9
    for base in deduped:
        roots = find_git_roots(base) or [base]
        for root in roots:
            s = 0
            rn = norm(root.name)
            if rn == target:
                s += 10
            if target in rn or rn in target:
                s += 4
            if root != base:
                s -= len(root.relative_to(base).parts)
            if (root / "development_skills").exists():
                s += 2
            if s > score:
                score = s
                best = root
    return best


def has_project_block(config_text: str, path: str) -> bool:
    pat = f'[projects."{path}"]'
    alt = f"[projects.'{path}']"
    return pat in config_text or alt in config_text


def ensure_mcp_docker_block(config_text: str) -> str:
    if "[mcp_servers.MCP_DOCKER]" in config_text:
        return config_text
    block = """
[mcp_servers]
[mcp_servers.MCP_DOCKER]
command = 'docker'
args = ['mcp', 'gateway', 'run']
"""
    return config_text.rstrip() + "\n" + block + "\n"


def main() -> None:
    if not LEDGER.exists():
        raise SystemExit(f"Missing ledger: {LEDGER}")
    if not CODEX_CONFIG.exists():
        raise SystemExit(f"Missing Codex config: {CODEX_CONFIG}")

    repos = yaml.safe_load(LEDGER.read_text()).get("repo_ledger", {}).get("repos", [])
    children = [p for p in ONEDRIVE.iterdir() if p.is_dir()]

    config = CODEX_CONFIG.read_text()
    config = ensure_mcp_docker_block(config)

    added = 0
    for repo in repos:
        name = str(repo.get("name", "")).strip()
        if not name:
            continue
        root = pick_repo_root(name, repo.get("local_path"), children)
        if root is None:
            continue
        project_path = root.resolve().as_posix()
        if has_project_block(config, project_path):
            continue
        config += f'\n[projects."{project_path}"]\ntrust_level = "trusted"\n'
        added += 1

    CODEX_CONFIG.write_text(config)
    print(f"Updated {CODEX_CONFIG}")
    print(f"Added trusted project entries: {added}")


if __name__ == "__main__":
    main()

