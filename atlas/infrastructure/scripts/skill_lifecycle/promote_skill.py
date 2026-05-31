#!/usr/bin/env python3
"""Promote a skill from candidate/ to active/, registering + routing it.

Usage:
  promote_skill.py SKILL_<CONCEPT>_<NNN> [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = REPO_ROOT / "platform" / "sdlc" / "13_skills"
ACTIVE_DIR = SKILLS_ROOT / "active"
CANDIDATE_DIR = SKILLS_ROOT / "candidate"
REGISTRY_PATH = SKILLS_ROOT / "skills.registry.yaml"
ROUTER_PATH = REPO_ROOT / "platform" / "systems" / "37_command_protocol" / "trigger_router.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_id", help="Canonical SKILL_<CONCEPT>_<NNN>")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    src_yaml = CANDIDATE_DIR / f"{args.skill_id}.yaml"
    src_pb = CANDIDATE_DIR / f"{args.skill_id}.playbook.md"
    if not src_yaml.exists():
        print(f"ERROR: {src_yaml} not found in candidate/", file=sys.stderr)
        return 2
    if (ACTIVE_DIR / f"{args.skill_id}.yaml").exists():
        print(f"ERROR: {args.skill_id} already exists in active/", file=sys.stderr)
        return 2

    d = yaml.safe_load(src_yaml.read_text())
    d["status"] = "active"
    if d.get("tier") in (None, "experimental"):
        d["tier"] = "starter"

    print(f"PROMOTE {args.skill_id}: candidate/ -> active/  (tier={d['tier']})")
    if args.dry_run:
        return 0

    (ACTIVE_DIR / f"{args.skill_id}.yaml").write_text(yaml.safe_dump(d, sort_keys=False))
    if src_pb.exists():
        (ACTIVE_DIR / f"{args.skill_id}.playbook.md").write_text(src_pb.read_text())
        src_pb.unlink()
    src_yaml.unlink()

    reg = yaml.safe_load(REGISTRY_PATH.read_text())
    names = {e["name"] for e in reg.get("skills", [])}
    if args.skill_id not in names:
        reg["skills"].append(
            {
                "name": args.skill_id,
                "path": f"platform/sdlc/13_skills/active/{args.skill_id}.yaml",
            }
        )
        reg["skills"] = sorted(reg["skills"], key=lambda x: x["name"])
        reg["total"] = len(reg["skills"])
        REGISTRY_PATH.write_text(yaml.safe_dump(reg, sort_keys=False))

    print("Done. Run validate_skill_router_integration.py to confirm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
