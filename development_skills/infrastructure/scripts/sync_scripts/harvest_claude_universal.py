#!/usr/bin/env python3
"""Harvest `.claude` skills/agents/tools from local repos into a central universal bundle.

Outputs are written under:
  .claude/universal/{skills,agents,tools}/
and indexed in:
  .claude/universal/index.yaml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
ONEDRIVE = ROOT.parent
LEDGER = ROOT / "platform" / "systems" / "18_registry" / "repo_ledger.yaml"
OUT_ROOT = ROOT / ".claude" / "universal"
CODEX_OUT_ROOT = ROOT / ".codex" / "universal"


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


def pick_repo_root(name: str, local_path: str | None, children: list[Path]) -> Path | None:
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
            if (root / ".claude").exists():
                s += 4
            if s > score:
                score = s
                best = root
    return best


def classify(claude_rel: str, filename: str) -> str | None:
    rel = claude_rel.lower()
    name = filename.lower()
    if "/skills/" in rel or name.endswith("skill.md") or name.startswith("skill_"):
        return "skills"
    if "/agents/" in rel or name.endswith("agent.md") or "_agent" in name:
        return "agents"
    if "/tools/" in rel or "tool" in name:
        return "tools"
    return None


def sanitize(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", text).strip("-").lower()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-existing", action="store_true", help="do not wipe existing universal bundle first")
    args = ap.parse_args()

    if not LEDGER.exists():
        raise SystemExit(f"Missing repo ledger: {LEDGER}")

    ledger: dict[str, Any] = yaml.safe_load(LEDGER.read_text())
    repos = ledger.get("repo_ledger", {}).get("repos", [])
    children = [p for p in ONEDRIVE.iterdir() if p.is_dir()]

    if not args.keep_existing and OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)

    for sub in ("skills", "agents", "tools"):
        (OUT_ROOT / sub).mkdir(parents=True, exist_ok=True)

    seen_sha: dict[str, dict[str, Any]] = {}
    stats = {"repos_scanned": 0, "repos_with_claude": 0, "files_indexed": 0, "files_unique": 0}

    for repo in repos:
        name = str(repo.get("name", "")).strip()
        if not name:
            continue
        root = pick_repo_root(name, repo.get("local_path"), children)
        if not root:
            continue
        stats["repos_scanned"] += 1
        claude = root / ".claude"
        if not claude.exists():
            continue
        stats["repos_with_claude"] += 1

        for p in claude.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(claude).as_posix()
            kind = classify("/" + rel, p.name)
            if kind is None:
                continue

            raw = p.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            stats["files_indexed"] += 1

            rec = {
                "repo": name,
                "repo_root": root.as_posix(),
                "source": p.as_posix(),
                "claude_rel": rel,
                "size": len(raw),
            }

            if sha not in seen_sha:
                ext = p.suffix if p.suffix else ".txt"
                out_name = f"{sha[:12]}__{sanitize(p.stem)}{ext}"
                out_path = OUT_ROOT / kind / out_name
                out_path.write_bytes(raw)
                seen_sha[sha] = {
                    "sha256": sha,
                    "kind": kind,
                    "output_path": out_path.relative_to(ROOT).as_posix(),
                    "filename": p.name,
                    "sources": [rec],
                }
                stats["files_unique"] += 1
            else:
                seen_sha[sha]["sources"].append(rec)

    bundle = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "root": ROOT.as_posix(),
        "stats": stats,
        "assets": sorted(seen_sha.values(), key=lambda x: (x["kind"], x["filename"], x["sha256"])),
    }
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "index.yaml").write_text(yaml.safe_dump(bundle, sort_keys=False))
    (OUT_ROOT / "index.json").write_text(json.dumps(bundle, indent=2))

    # Keep a Codex-native mirror so repo sync can populate `.codex/universal` uniformly.
    CODEX_OUT_ROOT.parent.mkdir(parents=True, exist_ok=True)
    if CODEX_OUT_ROOT.exists():
        shutil.rmtree(CODEX_OUT_ROOT)
    shutil.copytree(OUT_ROOT, CODEX_OUT_ROOT)

    print(f"Harvested .claude universal assets -> {OUT_ROOT}")
    print(f"Mirrored universal assets -> {CODEX_OUT_ROOT}")
    print(
        f"repos_scanned={stats['repos_scanned']} repos_with_claude={stats['repos_with_claude']} "
        f"files_indexed={stats['files_indexed']} files_unique={stats['files_unique']}"
    )


if __name__ == "__main__":
    main()
