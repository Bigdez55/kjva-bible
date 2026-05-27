#!/usr/bin/env python3
"""Load a skill playbook and correction ledger as pre-flight context."""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def find_skill(value: str) -> Path:
    active = ROOT / "platform" / "sdlc" / "13_skills" / "active"
    candidates = [active / f"{value}.yaml"]
    candidates.extend(active.glob(f"*{value.upper()}*.yaml"))
    candidates.extend(active.glob(f"*{value}*.yaml"))
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"No skill matched {value}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True, help="Skill ID or search token")
    args = parser.parse_args()

    skill_path = find_skill(args.skill)
    skill = yaml.safe_load(skill_path.read_text()) or {}
    playbook = ROOT / skill.get("playbook", "")
    ledger = ROOT / skill.get("ledger", "")

    print(f"# Pre-Flight Skill Context: {skill.get('title', skill.get('id'))}")
    print("\n## Skill YAML\n")
    print("```yaml")
    print(yaml.safe_dump(skill, sort_keys=False).rstrip())
    print("```")
    if playbook.exists():
        print("\n## Playbook\n")
        print(playbook.read_text().rstrip())
    if ledger.exists():
        print("\n## Correction Ledger\n")
        print("```yaml")
        print(ledger.read_text().rstrip())
        print("```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
