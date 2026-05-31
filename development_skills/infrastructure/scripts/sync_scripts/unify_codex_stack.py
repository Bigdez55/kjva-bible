#!/usr/bin/env python3
"""One-command Codex uniformity orchestrator.

Runs, in order:
1) harvest_claude_universal.py
2) register_codex_projects.py
3) sync_to_child_repo.py across every repo in 18_registry/repo_ledger.yaml (except central root)
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parents[3]
ONEDRIVE = ROOT.parent
LEDGER = ROOT / "platform" / "systems" / "18_registry" / "repo_ledger.yaml"


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.check_call(cmd)


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
                s += 3
            if s > score:
                score = s
                best = root
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-harvest", action="store_true")
    ap.add_argument("--skip-register", action="store_true")
    ap.add_argument("--skip-sync", action="store_true")
    args = ap.parse_args()

    harvest = ROOT / "infrastructure/scripts" / "sync_scripts" / "harvest_claude_universal.py"
    register = ROOT / "infrastructure/scripts" / "sync_scripts" / "register_codex_projects.py"
    sync = ROOT / "infrastructure/scripts" / "sync_scripts" / "sync_to_child_repo.py"

    if not args.skip_harvest:
        run(["python3", str(harvest)])

    if not args.skip_register:
        run(["python3", str(register)])

    if args.skip_sync:
        print("Skipped repo sync step.")
        return

    ledger = yaml.safe_load(LEDGER.read_text())
    repos = ledger.get("repo_ledger", {}).get("repos", [])
    children = [p for p in ONEDRIVE.iterdir() if p.is_dir()]

    synced = 0
    skipped = 0
    for repo in repos:
        name = str(repo.get("name", "")).strip()
        if not name or name == "ATLAS":
            continue
        root = pick_repo_root(name, repo.get("local_path"), children)
        if root is None:
            print(f"SKIP {name}: no local root")
            skipped += 1
            continue
        run(["python3", str(sync), "--target", str(root)])
        synced += 1

    print(f"Done. synced={synced} skipped={skipped}")


if __name__ == "__main__":
    main()
