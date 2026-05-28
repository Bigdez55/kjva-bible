#!/usr/bin/env python3
"""Tier-aware skill schema validator.

Validates each active SKILL_*.yaml against the per-tier requirement matrix
defined in schemas/skill/skill.tiered.schema.yaml.

Modes:
  --lenient (default) — log violations, exit 0
  --strict             — log violations, exit non-zero on any violation
  --tier TIER          — only validate skills at the given tier
  --dir DIR            — directory to scan (default: platform/sdlc/13_skills/active)
  --skill_id ID        — validate one specific skill by id
  --check-refinement-blocks — additionally verify improvement_metrics/use_telemetry/refinement_log are well-formed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
TIERED_SCHEMA = REPO_ROOT / "schemas" / "skill" / "skill.tiered.schema.yaml"
DEFAULT_SKILLS_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "active"


def load_tiered_schema() -> dict[str, Any]:
    with TIERED_SCHEMA.open() as f:
        return yaml.safe_load(f)


def resolve_required_fields(schema: dict[str, Any], tier: str) -> set[str]:
    """Resolve the full set of required fields for a tier, walking inheritance."""
    tiers = schema.get("tiers", {})
    if tier not in tiers:
        return set(schema["field_categories"]["base"]["fields"])

    visited: set[str] = set()
    required_categories: set[str] = set()

    def visit(t: str) -> None:
        if t in visited or t not in tiers:
            return
        visited.add(t)
        for parent in tiers[t].get("inherits", []) or []:
            visit(parent)
        for cat in tiers[t].get("required_categories", []) or []:
            required_categories.add(cat)

    visit(tier)
    fields: set[str] = set()
    for cat in required_categories:
        fields.update(schema["field_categories"][cat]["fields"])
    return fields


def validate_skill_file(
    path: Path, schema: dict[str, Any], check_refinement: bool = False
) -> list[str]:
    """Return a list of human-readable violations for one skill file."""
    violations: list[str] = []
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        return [f"{path.name}: YAML parse error: {e}"]

    if not isinstance(data, dict):
        return [f"{path.name}: not a YAML mapping"]

    skill_id = data.get("id", path.stem)
    tier = data.get("tier")
    if tier is None:
        # Skills without an explicit tier are validated against base-only requirements
        # (gives Phase 0/1/2 grace period to backfill).
        tier = "experimental"
        violations.append(f"{skill_id}: missing 'tier' field (validating as experimental)")

    required = resolve_required_fields(schema, tier)

    for field in sorted(required):
        if field not in data:
            violations.append(f"{skill_id} (tier={tier}): missing required field '{field}'")
        elif data[field] in (None, "", [], {}):
            violations.append(f"{skill_id} (tier={tier}): required field '{field}' is empty")

    if check_refinement:
        # Verify refinement blocks are well-formed even if empty
        im = data.get("improvement_metrics")
        if im is not None:
            if not isinstance(im, dict):
                violations.append(f"{skill_id}: improvement_metrics must be a mapping")
            else:
                for k in ("invocation_count", "correction_count", "refinement_count"):
                    if k in im and not isinstance(im[k], int):
                        violations.append(f"{skill_id}: improvement_metrics.{k} must be int")
        tel = data.get("use_telemetry")
        if tel is not None and not isinstance(tel, list):
            violations.append(f"{skill_id}: use_telemetry must be a list")
        rlog = data.get("refinement_log")
        if rlog is not None and not isinstance(rlog, list):
            violations.append(f"{skill_id}: refinement_log must be a list")

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on any violation")
    parser.add_argument("--lenient", action="store_true", help="Log only, exit 0 (default)")
    parser.add_argument("--tier", default=None, help="Only validate skills at this tier")
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_SKILLS_DIR,
        help="Directory of SKILL_*.yaml files",
    )
    parser.add_argument("--skill_id", default=None, help="Validate one skill by id")
    parser.add_argument(
        "--check-refinement-blocks",
        action="store_true",
        help="Also verify improvement_metrics/use_telemetry/refinement_log shapes",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON report instead of text"
    )
    args = parser.parse_args()

    schema = load_tiered_schema()
    skills_dir = args.dir
    if not skills_dir.exists():
        print(f"FAIL: skills directory not found: {skills_dir}", file=sys.stderr)
        return 2

    files = sorted(skills_dir.glob("SKILL_*.yaml"))
    if args.skill_id:
        files = [f for f in files if f.stem == args.skill_id]
        if not files:
            print(f"FAIL: no skill matching id={args.skill_id}", file=sys.stderr)
            return 2

    total_violations: list[str] = []
    skills_with_violations = 0
    total_checked = 0

    for path in files:
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            data = {}
        if args.tier and data.get("tier") != args.tier:
            continue

        total_checked += 1
        violations = validate_skill_file(
            path, schema, check_refinement=args.check_refinement_blocks
        )
        if violations:
            skills_with_violations += 1
            total_violations.extend(violations)

    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": schema.get("version"),
                    "checked": total_checked,
                    "skills_with_violations": skills_with_violations,
                    "total_violations": len(total_violations),
                    "violations": total_violations,
                },
                indent=2,
            )
        )
    else:
        for v in total_violations:
            print(v)
        print()
        print(f"=== Tiered Schema Validation ===")
        print(f"Schema version: {schema.get('version')}")
        print(f"Skills checked: {total_checked}")
        print(f"Skills with violations: {skills_with_violations}")
        print(f"Total violations: {len(total_violations)}")

    if args.strict and total_violations:
        print("STRICT MODE: FAIL", file=sys.stderr)
        return 1
    print("PASS" if not total_violations else "PASS (lenient mode — violations logged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
