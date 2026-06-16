#!/usr/bin/env python3
"""Related-skills cross-reference linter (REPORT-ONLY).

Reads the structured `related_skills:` field of every canonical
SKILL_*.yaml in platform/sdlc/13_skills/active/ and verifies that each
referenced id resolves to an existing active skill id. Reports danglers
(rename rot / refs to skills that were never created).

This linter NEVER rewrites YAML. A PyYAML load->dump round-trip reorders
keys, strips comments, and reflows scalars — exactly the corruption hazard
the skill corpus must avoid. Repointing/dropping danglers is a human (or
central-commit) action; this tool only surfaces what needs fixing and, for
known renames, prints the obvious target.

The valid-id universe is built from the active tier only — that is the set a
runtime `related_skills` ref is expected to resolve into. The candidate /
experimental / deprecated / superseded tiers are consulted ONLY to tell apart
"repoint to a moved skill" from "drop a never-created ref", so the
recommendation is honest.

Exit codes:
  0  no danglers (or --strict not set)
  1  danglers found AND --strict
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / "platform" / "sdlc" / "13_skills"
ACTIVE_DIR = SKILLS_ROOT / "active"
OTHER_TIERS = ["candidate", "experimental", "deprecated", "superseded"]

# Known-rename repoint map: dangling ref -> resolvable active id.
# Only obvious 1:1 renames where the target clearly supersedes the old name.
# Everything not listed here and not resolvable is recommended for DROP.
KNOWN_RENAMES: dict[str, str] = {
    "SKILL_CONTEXT_COMPILATION_002": "SKILL_CONTEXT_COMPILATION_001",
    "SKILL_CONTINUOUS_INTEGRATION_PIPELINE_001": "SKILL_CI_PIPELINE_001",
    "SKILL_DATA_PIPELINE_FIRST_001": "SKILL_DATA_PIPELINE_001",
    "SKILL_OBSERVABILITY_001": "SKILL_OBSERVABILITY_NEXUS_001",
}


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


def collect_ids(directory: Path) -> set[str]:
    ids: set[str] = set()
    if not directory.exists():
        return ids
    for p in sorted(directory.glob("SKILL_*.yaml")):
        d = load_yaml(p)
        if d.get("id"):
            ids.add(str(d["id"]))
    return ids


def collect_other_tier_ids() -> set[str]:
    ids: set[str] = set()
    for tier in OTHER_TIERS:
        ids |= collect_ids(SKILLS_ROOT / tier)
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any dangling related_skills ref is found.",
    )
    args = parser.parse_args()

    valid_active = collect_ids(ACTIVE_DIR)
    other_tier = collect_other_tier_ids()
    print(f"Active skills (valid related_skills targets): {len(valid_active)}")

    total_refs = 0
    danglers: list[tuple[str, str, str]] = []  # (source_skill, dangling_ref, recommendation)

    for p in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        d = load_yaml(p)
        src = str(d.get("id") or p.stem)
        refs = d.get("related_skills") or []
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, str):
                continue
            total_refs += 1
            if ref in valid_active:
                continue
            # Dangling — classify
            if ref in KNOWN_RENAMES and KNOWN_RENAMES[ref] in valid_active:
                rec = f"REPOINT -> {KNOWN_RENAMES[ref]}"
            elif ref in other_tier:
                rec = "REPOINT/PROMOTE (target exists in a non-active tier)"
            else:
                rec = "DROP (no resolvable target in any tier)"
            danglers.append((src, ref, rec))

    print(f"Total structured related_skills refs: {total_refs}")
    print(f"Dangling refs: {len(danglers)}")
    if danglers:
        print()
        print("=== Dangling related_skills (source_skill -> dangling_ref :: recommendation) ===")
        for src, ref, rec in danglers:
            print(f"  {src}")
            print(f"      {ref}  ::  {rec}")
    else:
        print("PASS: every related_skills ref resolves to an active skill id.")

    if args.strict and danglers:
        print()
        print("STRICT MODE: FAIL")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
