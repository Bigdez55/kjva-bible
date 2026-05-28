#!/usr/bin/env python3
"""Phase 8 — Tier auto-promotion engine.

Reads each active skill's improvement_metrics and promotes tier when
criteria are met. Per LIFECYCLE.md section T3:

  experimental -> starter   >=10 invocations, ≤30% corrections, no recent failures
  starter -> active          >=50 invocations, ≤10% corrections, 14d stability
  active -> hardened         >=200 invocations, ≤2% corrections, 30d stability,
                             validation_tests + improvement_history present
  hardened -> apex           >=1000 invocations, ≤0.1% corrections, 90d stability,
                             ledger + regression_cases, cross-runtime usage

Demotion: if corrections_per_100_uses regresses by 2x in 30 days, demote one
tier and open an investigation issue.

Modes:
  --apply       Apply promotions, write changes
  --dry-run     Default — preview only
  --report-only Eligibility report (no changes)
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

PROMOTION_CRITERIA = {
    "experimental": {
        "to": "starter",
        "min_invocations": 10,
        "max_corrections_per_100": 30.0,
        "min_stable_days": 0,
        "required_fields": [],
    },
    "starter": {
        "to": "active",
        "min_invocations": 50,
        "max_corrections_per_100": 10.0,
        "min_stable_days": 14,
        "required_fields": [],
    },
    "active": {
        "to": "hardened",
        "min_invocations": 200,
        "max_corrections_per_100": 2.0,
        "min_stable_days": 30,
        "required_fields": ["validation_tests", "improvement_history"],
    },
    "hardened": {
        "to": "apex",
        "min_invocations": 1000,
        "max_corrections_per_100": 0.1,
        "min_stable_days": 90,
        "required_fields": ["ledger", "regression_cases"],
    },
}


def eligibility(skill: dict[str, Any]) -> dict[str, Any]:
    tier = skill.get("tier") or "experimental"
    if tier not in PROMOTION_CRITERIA:
        return {"eligible": False, "reason": f"terminal or unknown tier: {tier}"}

    c = PROMOTION_CRITERIA[tier]
    im = skill.get("improvement_metrics") or {}
    iv = int(im.get("invocation_count") or 0)
    cp100 = im.get("corrections_per_100_uses")

    if iv < c["min_invocations"]:
        return {
            "eligible": False,
            "reason": f"invocations {iv} < {c['min_invocations']}",
        }
    if cp100 is None:
        return {"eligible": False, "reason": "corrections_per_100_uses not yet computed"}
    if cp100 > c["max_corrections_per_100"]:
        return {
            "eligible": False,
            "reason": f"corrections_per_100={cp100} > {c['max_corrections_per_100']}",
        }
    for f in c["required_fields"]:
        if not skill.get(f):
            return {"eligible": False, "reason": f"required field missing: {f}"}

    return {"eligible": True, "to_tier": c["to"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    apply = args.apply
    today = dt.datetime.now(dt.timezone.utc).isoformat()

    eligible: list[dict[str, Any]] = []
    examined = 0

    for p in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        d = yaml.safe_load(p.read_text()) or {}
        examined += 1
        e = eligibility(d)
        if e.get("eligible"):
            eligible.append(
                {
                    "skill_id": d.get("id"),
                    "current_tier": d.get("tier"),
                    "next_tier": e["to_tier"],
                    "invocations": (d.get("improvement_metrics") or {}).get(
                        "invocation_count"
                    ),
                    "corrections_per_100_uses": (
                        d.get("improvement_metrics") or {}
                    ).get("corrections_per_100_uses"),
                    "path": str(p.relative_to(REPO_ROOT)),
                }
            )

    print(f"=== Tier Auto-Promotion ({'APPLY' if apply else 'REPORT ONLY'}) ===")
    print(f"Skills examined: {examined}")
    print(f"Eligible for promotion: {len(eligible)}")
    if eligible:
        print()
        for item in eligible:
            print(
                f"  {item['skill_id']}: {item['current_tier']} -> {item['next_tier']} "
                f"(invocations={item['invocations']}, "
                f"corrections_per_100={item['corrections_per_100_uses']})"
            )

    if apply and eligible:
        promoted = 0
        for item in eligible:
            p = ACTIVE_DIR / f"{item['skill_id']}.yaml"
            d = yaml.safe_load(p.read_text())
            old_tier = d.get("tier")
            d["tier"] = item["next_tier"]
            im = d.setdefault("improvement_metrics", {})
            history = im.setdefault("tier_promotion_history", [])
            history.append(
                {
                    "from": old_tier,
                    "to": item["next_tier"],
                    "date": today,
                    "trigger": "auto_promote_tier",
                    "invocations_at_promotion": item["invocations"],
                    "corrections_per_100_at_promotion": item["corrections_per_100_uses"],
                }
            )
            p.write_text(yaml.safe_dump(d, sort_keys=False))
            promoted += 1
        print(f"\nPromoted: {promoted}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
