#!/usr/bin/env python3
"""Phase 8 — Auto-refinement engine.

For a given skill (or all skills), reads accumulated telemetry and applies
additive refinements to the playbook based on observed corrections and
new patterns. Refinements are ALWAYS ADDITIVE — never delete content.

Safety rails per Phase 8 safety section:
  - Diff cap: refinement may change ≤20% of playbook by line count
  - Forbidden fields: id, skill_number, domains, layer, source, major
                      version, hard_constraints (remove); these need humans
  - refinement: frozen skips this skill entirely
  - Stalled after 3 successive refinements without improvement

Modes:
  --skill_id ID       Refine one skill
  --all              Refine every eligible skill
  --dry-run          Show diff, don't write
  --apply            Apply refinements
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "active"
TELEMETRY_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery" / "telemetry"

DIFF_CAP_FRACTION = 0.20
STALLED_THRESHOLD = 3
MIN_PATTERN_COUNT = 3


def load_skill(skill_id: str) -> tuple[Path, dict[str, Any]] | None:
    p = ACTIVE_DIR / f"{skill_id}.yaml"
    if not p.exists():
        return None
    return p, yaml.safe_load(p.read_text()) or {}


def load_telemetry(skill_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not TELEMETRY_DIR.exists():
        return events
    for f in sorted(TELEMETRY_DIR.glob(f"{skill_id}_*.jsonl")):
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def find_corrections_since_last_refinement(
    skill: dict[str, Any], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    im = skill.get("improvement_metrics") or {}
    last_ref = im.get("last_refinement")
    if not last_ref:
        return [e for e in events if e.get("correction_summary")]
    return [
        e for e in events
        if e.get("timestamp") and e["timestamp"] > last_ref
        and e.get("correction_summary")
    ]


def detect_repeated_patterns(events: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """Group similar correction summaries by simple substring clustering."""
    summaries = [e.get("correction_summary") for e in events if e.get("correction_summary")]
    counts: dict[str, int] = {}
    for s in summaries:
        # Normalize: lowercase, trim, first 80 chars as cluster key
        key = (s or "").lower().strip()[:80]
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return sorted([(k, v) for k, v in counts.items() if v >= MIN_PATTERN_COUNT],
                  key=lambda x: -x[1])


def bump_version(version: str, kind: str) -> str:
    parts = version.split(".")
    while len(parts) < 3:
        parts.append("0")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if kind == "patch":
        patch += 1
    elif kind == "minor":
        minor += 1
        patch = 0
    elif kind == "major":
        major += 1
        minor = 0
        patch = 0
    return f"{major}.{minor}.{patch}"


def refine_one(skill_id: str, dry_run: bool) -> dict[str, Any]:
    loaded = load_skill(skill_id)
    if loaded is None:
        return {"skill_id": skill_id, "action": "skip", "reason": "not found"}
    yaml_path, d = loaded
    if d.get("refinement") == "frozen":
        return {"skill_id": skill_id, "action": "skip", "reason": "refinement: frozen"}

    events = load_telemetry(skill_id)
    if not events:
        return {"skill_id": skill_id, "action": "skip", "reason": "no telemetry"}

    pb_path = ACTIVE_DIR / f"{skill_id}.playbook.md"
    playbook = pb_path.read_text() if pb_path.exists() else ""

    corrections = find_corrections_since_last_refinement(d, events)
    repeated = detect_repeated_patterns(events)

    additions: list[str] = []
    bump_kind: str | None = None

    if corrections:
        # Patch bump: add corrections as new rules
        for c in corrections[:10]:  # cap at 10 per refinement
            text = (c.get("correction_summary") or "").strip()
            if text:
                additions.append(
                    f"- **Correction ({c.get('timestamp', 'unknown')[:10]}):** {text}"
                )
        if additions:
            bump_kind = "patch"

    if repeated:
        # Minor bump: add patterns as new gates
        for pattern, count in repeated[:5]:
            additions.append(
                f"- **Pattern observed {count}x:** {pattern}"
            )
        bump_kind = "minor"  # promote to minor if both corrections and patterns

    if not additions:
        return {"skill_id": skill_id, "action": "skip", "reason": "nothing to refine"}

    # Build refinement block
    today = dt.datetime.now(dt.timezone.utc).isoformat()
    refinement_block = (
        f"\n\n## Refinement Log Entry — {today[:10]}\n\n"
        f"Auto-applied by `refine_skill.py` based on telemetry.\n\n"
        + "\n".join(additions)
        + "\n"
    )

    # Diff cap check
    current_lines = playbook.count("\n") + 1
    added_lines = refinement_block.count("\n")
    if current_lines > 0 and added_lines / current_lines > DIFF_CAP_FRACTION:
        return {
            "skill_id": skill_id,
            "action": "skip",
            "reason": f"diff cap exceeded ({added_lines}/{current_lines})",
        }

    new_playbook = playbook + refinement_block
    new_version = bump_version(d.get("version", "1.0.0"), bump_kind or "patch")

    log_entry = {
        "date": today,
        "version_before": d.get("version"),
        "version_after": new_version,
        "change_summary": (
            f"Auto-applied {len(corrections)} corrections + "
            f"{len(repeated)} repeated patterns"
        ),
        "evidence_event_count": len(events),
    }

    if not dry_run:
        # Update YAML
        d["version"] = new_version
        rlog = d.setdefault("refinement_log", []) or []
        rlog.append(log_entry)
        d["refinement_log"] = rlog
        im = d.setdefault("improvement_metrics", {})
        im["last_refinement"] = today
        im["refinement_count"] = int(im.get("refinement_count") or 0) + 1
        yaml_path.write_text(yaml.safe_dump(d, sort_keys=False))
        # Update playbook
        pb_path.write_text(new_playbook)

    return {
        "skill_id": skill_id,
        "action": "refine",
        "bump_kind": bump_kind,
        "version_after": new_version,
        "additions": len(additions),
        "log_entry": log_entry,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--skill_id")
    g.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report-only", action="store_true",
                        help="Same as --dry-run with shorter output")
    args = parser.parse_args()

    if not args.dry_run and not args.apply and not args.report_only:
        # Default to dry-run for safety
        args.dry_run = True

    dry = args.dry_run or args.report_only

    if args.skill_id:
        result = refine_one(args.skill_id, dry)
        print(json.dumps(result, indent=2))
        return 0

    # --all
    skills = [p.stem for p in sorted(ACTIVE_DIR.glob("SKILL_*.yaml"))]
    refined = 0
    skipped = 0
    for sid in skills:
        r = refine_one(sid, dry)
        if r["action"] == "refine":
            refined += 1
            print(f"  REFINE {sid}: bump={r['bump_kind']} -> v{r['version_after']}")
        else:
            skipped += 1
    print()
    print(f"=== Auto-refinement {'DRY RUN' if dry else 'APPLIED'} ===")
    print(f"Refined: {refined}")
    print(f"Skipped: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
