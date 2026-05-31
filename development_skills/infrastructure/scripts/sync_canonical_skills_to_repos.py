#!/usr/bin/env python3
"""Synchronize canonical ATLAS skill artifacts into local repo skill surfaces.

The ATLAS repo is the source of truth for active skill contracts.
This script copies the canonical active skill files into each discovered repo's
`development_skills/13_skills/active` directory and refreshes Claude/Codex
universal agent-skill libraries when the source surfaces exist.

The sync is additive and overwrite-safe:
- canonical files are copied by content hash;
- repo-local files that are not canonical are preserved;
- no git operations are performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ONEDRIVE_ROOT = REPO_ROOT.parent
CANONICAL_ACTIVE = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "active"
CANONICAL_REGISTRY = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "skills.registry.yaml"
CANONICAL_CLAUDE_UNIVERSAL = REPO_ROOT / ".claude" / "universal"
CANONICAL_CODEX_UNIVERSAL = REPO_ROOT / ".codex" / "universal"
DEFAULT_REPORT = REPO_ROOT / "23_evidence" / "skill_sync" / "canonical_skill_sync_report.json"


@dataclass
class SyncResult:
    repo: str
    active_dir: str
    active_created: bool
    active_copied: int
    active_updated: int
    active_unchanged: int
    registry_copied: bool
    claude_universal_files: int
    codex_universal_files: int


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_repos(root: Path) -> list[Path]:
    repos: list[Path] = []
    for git_dir in root.rglob(".git"):
        if not git_dir.is_dir():
            continue
        if any(part in {".Trash", "node_modules"} for part in git_dir.parts):
            continue
        repos.append(git_dir.parent)
    return sorted(set(repos), key=lambda p: str(p).lower())


def copy_tree_contents(source: Path, destination: Path) -> int:
    if not source.exists():
        return 0
    count = 0
    for src in source.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(source)
        dst = destination / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and sha256(dst) == sha256(src):
            continue
        shutil.copy2(src, dst)
        count += 1
    return count


def copy_active_skills(repo: Path) -> tuple[str, bool, int, int, int]:
    active_dir = CANONICAL_ACTIVE if repo.resolve() == REPO_ROOT.resolve() else repo / "development_skills" / "platform" / "sdlc" / "13_skills" / "active"
    created = not active_dir.exists()
    active_dir.mkdir(parents=True, exist_ok=True)

    copied = updated = unchanged = 0
    for src in sorted(CANONICAL_ACTIVE.iterdir()):
        if not src.is_file() or src.name == ".gitkeep":
            continue
        dst = active_dir / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
            copied += 1
        elif sha256(dst) != sha256(src):
            shutil.copy2(src, dst)
            updated += 1
        else:
            unchanged += 1
    return str(active_dir), created, copied, updated, unchanged


def sync_repo(repo: Path) -> SyncResult:
    active_dir, active_created, active_copied, active_updated, active_unchanged = copy_active_skills(repo)

    registry_copied = False
    if CANONICAL_REGISTRY.exists():
        dst_registry = CANONICAL_REGISTRY if repo.resolve() == REPO_ROOT.resolve() else repo / "development_skills" / "platform" / "sdlc" / "13_skills" / "skills.registry.yaml"
        dst_registry.parent.mkdir(parents=True, exist_ok=True)
        if not dst_registry.exists() or sha256(dst_registry) != sha256(CANONICAL_REGISTRY):
            shutil.copy2(CANONICAL_REGISTRY, dst_registry)
            registry_copied = True

    claude_files = copy_tree_contents(CANONICAL_CLAUDE_UNIVERSAL, repo / ".claude" / "universal")
    codex_files = copy_tree_contents(CANONICAL_CODEX_UNIVERSAL, repo / ".codex" / "universal")

    return SyncResult(
        repo=str(repo),
        active_dir=active_dir,
        active_created=active_created,
        active_copied=active_copied,
        active_updated=active_updated,
        active_unchanged=active_unchanged,
        registry_copied=registry_copied,
        claude_universal_files=claude_files,
        codex_universal_files=codex_files,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync canonical ATLAS skills to local repos.")
    parser.add_argument("--root", type=Path, default=ONEDRIVE_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repos = discover_repos(args.root)
    if args.dry_run:
        print(json.dumps({"mode": "dry-run", "repo_count": len(repos), "repos": [str(p) for p in repos]}, indent=2))
        return 0

    results = [sync_repo(repo) for repo in repos]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_repo": str(REPO_ROOT),
        "source_active_dir": str(CANONICAL_ACTIVE),
        "repo_count": len(results),
        "canonical_active_file_count": len([p for p in CANONICAL_ACTIVE.iterdir() if p.is_file() and p.name != ".gitkeep"]),
        "results": [asdict(result) for result in results],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
