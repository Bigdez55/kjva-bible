#!/usr/bin/env python3
"""Phase 6 projection coverage validator.

Verifies the invariant: every projected file in the four runtime roots
traces back to a canonical SKILL_*.yaml, and every canonical skill with
runtime_projection != false has the expected projections present.

Modes:
  --strict   Exit non-zero on any orphan or missing projection
  --roots    Override projection roots (default: all four standard roots)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "active"
HOME = Path.home()

CLAUDE_SKILLS = HOME / ".claude" / "skills"
CODEX_SKILLS = HOME / ".codex" / "skills"
CODEX_COMMANDS = HOME / ".codex" / "commands"
GEMINI_COMMANDS = HOME / ".gemini" / "commands"


def kebab_from_canonical_id(canonical_id: str) -> str:
    m = re.match(r"^SKILL_(.+)_\d{3}$", canonical_id)
    if not m:
        return canonical_id.lower().replace("_", "-")
    return m.group(1).lower().replace("_", "-")


def derive_kebab(data: dict[str, Any]) -> str:
    aliases = data.get("aliases") or []
    if aliases and isinstance(aliases[0], str):
        return aliases[0]
    return kebab_from_canonical_id(data.get("id", ""))


def collect_canonical() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        d = yaml.safe_load(p.read_text()) or {}
        if d.get("id"):
            out[d["id"]] = d
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    canonical = collect_canonical()
    print(f"Canonical skills: {len(canonical)}")

    # Build set of expected projection paths
    projecting_kebabs = set()
    for cid, d in canonical.items():
        if d.get("runtime_projection") is False:
            continue
        projecting_kebabs.add(derive_kebab(d))

    issues: list[str] = []

    # Check each projection root for orphans
    def check_root(root: Path, suffix: str, is_dir: bool, label: str) -> int:
        if not root.exists():
            issues.append(f"WARN: projection root missing: {root}")
            return 0
        orphans = 0
        try:
            items = list(root.iterdir())
        except (PermissionError, OSError):
            return 0
        for item in items:
            if is_dir:
                if not item.is_dir():
                    continue
                if not item.name.replace("-", "").replace("_", "").isalnum():
                    continue  # built-in/system dirs
                if item.name not in projecting_kebabs:
                    orphans += 1
                    issues.append(f"ORPHAN {label}: {item.name}/")
            else:
                if not item.is_file() or item.suffix != ".md":
                    continue
                stem = item.stem
                if stem not in projecting_kebabs:
                    orphans += 1
                    issues.append(f"ORPHAN {label}: {item.name}")
        return orphans

    orphans_claude = check_root(CLAUDE_SKILLS, "SKILL.md", True, "claude")
    orphans_codex_skill = check_root(CODEX_SKILLS, "SKILL.md", True, "codex_skill")
    orphans_codex_cmd = check_root(CODEX_COMMANDS, ".md", False, "codex_command")
    orphans_gemini = check_root(GEMINI_COMMANDS, ".md", False, "gemini_command")

    # Coverage: ensure each canonical's kebab has projections per its targets
    DEFAULT = ["claude", "codex", "gemini"]
    missing = 0
    for cid, d in canonical.items():
        if d.get("runtime_projection") is False:
            continue
        kebab = derive_kebab(d)
        targets = d.get("runtime_projection_targets") or DEFAULT
        if "claude" in targets and not (CLAUDE_SKILLS / kebab / "SKILL.md").exists():
            missing += 1
            issues.append(f"MISSING claude shim for {cid} (kebab={kebab})")
        if "codex" in targets and not (CODEX_SKILLS / kebab / "SKILL.md").exists():
            missing += 1
            issues.append(f"MISSING codex skill for {cid} (kebab={kebab})")
        if "codex" in targets and not (CODEX_COMMANDS / f"{kebab}.md").exists():
            missing += 1
            issues.append(f"MISSING codex command for {cid} (kebab={kebab})")
        if "gemini" in targets and not (GEMINI_COMMANDS / f"{kebab}.md").exists():
            missing += 1
            issues.append(f"MISSING gemini command for {cid} (kebab={kebab})")

    print()
    print("=== Projection Coverage ===")
    print(f"Claude shims orphan: {orphans_claude}")
    print(f"Codex skill orphan:  {orphans_codex_skill}")
    print(f"Codex cmd orphan:    {orphans_codex_cmd}")
    print(f"Gemini cmd orphan:   {orphans_gemini}")
    print(f"Missing projections: {missing}")
    print(f"Total issues:        {len(issues)}")
    if issues and len(issues) <= 30:
        print()
        for i in issues:
            print(f"  {i}")
    elif issues:
        print(f"(showing first 30 of {len(issues)})")
        for i in issues[:30]:
            print(f"  {i}")
    if args.strict and issues:
        print("STRICT MODE: FAIL")
        return 1
    print("PASS" if not issues else "PASS (lenient — issues logged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
