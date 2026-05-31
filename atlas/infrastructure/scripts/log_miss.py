#!/usr/bin/env python3
"""Append a skill miss to a correction ledger."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LEDGERS = ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery" / "correction_ledgers"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True, help="Skill ID")
    parser.add_argument("--type", required=True, help="Miss type")
    parser.add_argument("--description", required=True)
    parser.add_argument("--root-cause", required=True)
    parser.add_argument("--layer", default="L3")
    parser.add_argument("--fix", required=True)
    parser.add_argument("--regression-test-id", default="")
    args = parser.parse_args()

    path = LEDGERS / f"{args.skill}.ledger.yaml"
    if not path.exists():
        raise FileNotFoundError(path)
    ledger = yaml.safe_load(path.read_text()) or {}
    history = ledger.setdefault("correction_history", [])
    entry_id = f"{args.skill}-MISS-{len(history) + 1:03d}"
    history.append(
        {
            "entry_id": entry_id,
            "date": date.today().isoformat(),
            "miss_type": args.type,
            "description": args.description,
            "root_cause": args.root_cause,
            "fix_layer": args.layer,
            "fix_description": args.fix,
            "regression_test_id": args.regression_test_id,
            "recurrence_count": 1,
        }
    )
    if args.regression_test_id:
        tests = ledger.setdefault("regression_test_ids", [])
        if args.regression_test_id not in tests:
            tests.append(args.regression_test_id)
    ledger["last_updated"] = date.today().isoformat()
    path.write_text(yaml.safe_dump(ledger, sort_keys=False))
    print(f"Logged {entry_id} to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
