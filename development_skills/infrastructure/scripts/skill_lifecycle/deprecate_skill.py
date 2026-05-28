#!/usr/bin/env python3
"""Deprecate an active skill (move to deprecated/, mark status, drop from registry/router).

Usage:
  deprecate_skill.py SKILL_<CONCEPT>_<NNN> --reason "<text>"
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = REPO_ROOT / "platform" / "sdlc" / "13_skills"
ACTIVE_DIR = SKILLS_ROOT / "active"
DEPRECATED_DIR = SKILLS_ROOT / "deprecated"
REGISTRY_PATH = SKILLS_ROOT / "skills.registry.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_id")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    src_yaml = ACTIVE_DIR / f"{args.skill_id}.yaml"
    src_pb = ACTIVE_DIR / f"{args.skill_id}.playbook.md"
    if not src_yaml.exists():
        print(f"ERROR: {src_yaml} not found in active/", file=sys.stderr)
        return 2
    if not args.reason.strip():
        print("ERROR: --reason text required", file=sys.stderr)
        return 2

    d = yaml.safe_load(src_yaml.read_text())
    d["status"] = "deprecated"
    d["deprecation_reason"] = args.reason
    d["deprecated_on"] = dt.date.today().isoformat()

    print(f"DEPRECATE {args.skill_id}: active/ -> deprecated/")
    print(f"  reason: {args.reason}")
    if args.dry_run:
        return 0

    DEPRECATED_DIR.mkdir(exist_ok=True)
    (DEPRECATED_DIR / f"{args.skill_id}.yaml").write_text(yaml.safe_dump(d, sort_keys=False))
    if src_pb.exists():
        (DEPRECATED_DIR / f"{args.skill_id}.playbook.md").write_text(src_pb.read_text())
        src_pb.unlink()
    src_yaml.unlink()

    reg = yaml.safe_load(REGISTRY_PATH.read_text())
    reg["skills"] = [e for e in reg.get("skills", []) if e.get("name") != args.skill_id]
    reg["total"] = len(reg["skills"])
    REGISTRY_PATH.write_text(yaml.safe_dump(reg, sort_keys=False))

    print("Done. Re-run validators + regenerate MASTER_INDEX + projection.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
