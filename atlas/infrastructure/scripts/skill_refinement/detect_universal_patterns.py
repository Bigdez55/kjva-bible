#!/usr/bin/env python3
"""Phase 8 — Cross-skill universal pattern detector.

Runs weekly. Aggregates correction summaries across the entire corpus
and identifies clusters appearing in >=N distinct skills. Each cluster
becomes a candidate for a universal rule (TAXONOMY.md entry or
universal_skill_invocation_policy.md addition).

Output:
  platform/sdlc/13_skills/skill_refinery/universal_patterns_<date>.yaml
  PR-ready proposals for human review.

Modes:
  --min-skills N    Minimum distinct skills to surface a pattern (default 3)
  --top N           Show top N patterns (default 10)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
TELEMETRY_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery" / "telemetry"
REFINERY = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery"


def normalize_key(text: str) -> str:
    return (text or "").lower().strip()[:120]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-skills", type=int, default=3)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    today = dt.date.today().isoformat()
    output = args.output or (REFINERY / f"universal_patterns_{today}.yaml")

    if not TELEMETRY_DIR.exists():
        print("No telemetry directory yet — nothing to analyze.")
        return 0

    by_pattern: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total_corrections = 0

    for f in sorted(TELEMETRY_DIR.glob("*.jsonl")):
        skill_id = f.stem.rsplit("_", 1)[0]  # SKILL_FOO_001_202605 -> SKILL_FOO_001
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            summary = event.get("correction_summary")
            if not summary:
                continue
            key = normalize_key(summary)
            if key:
                by_pattern[key][skill_id] += 1
                total_corrections += 1

    universal = []
    for pattern, skill_counts in by_pattern.items():
        if len(skill_counts) >= args.min_skills:
            total_count = sum(skill_counts.values())
            universal.append(
                {
                    "pattern": pattern,
                    "distinct_skills": sorted(skill_counts.keys()),
                    "skill_count": len(skill_counts),
                    "total_observations": total_count,
                }
            )

    universal.sort(key=lambda x: (-x["skill_count"], -x["total_observations"]))
    universal = universal[: args.top]

    report = {
        "generated": today,
        "total_correction_events_analyzed": total_corrections,
        "unique_patterns": len(by_pattern),
        "min_skills_threshold": args.min_skills,
        "universal_patterns": universal,
        "proposal_action": (
            "For each universal pattern, propose updating TAXONOMY.md or "
            "universal_skill_invocation_policy.md with a new global rule. "
            "Open one PR per pattern with evidence (distinct_skills list)."
        ),
    }

    REFINERY.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(report, sort_keys=False))
    print(f"Wrote: {output.relative_to(REPO_ROOT)}")
    print(f"Total corrections analyzed: {total_corrections}")
    print(f"Universal patterns (≥{args.min_skills} skills): {len(universal)}")
    if universal:
        print()
        for p in universal[: args.top]:
            print(
                f"  {p['skill_count']} skills, {p['total_observations']} hits: "
                f"{p['pattern'][:80]}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
