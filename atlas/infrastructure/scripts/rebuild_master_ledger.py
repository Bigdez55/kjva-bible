#!/usr/bin/env python3
"""Rebuild the consolidated skill-refinery master ledger."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LEDGERS = ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery" / "correction_ledgers"
OUT = ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery" / "master_ledger.yaml"


def main() -> int:
    entries = []
    for path in sorted(LEDGERS.glob("*.ledger.yaml")):
        data = yaml.safe_load(path.read_text()) or {}
        entries.append(
            {
                "skill_id": data.get("skill_id", path.stem),
                "ledger": path.relative_to(ROOT).as_posix(),
                "correction_count": len(data.get("correction_history", []) or []),
                "last_updated": data.get("last_updated", ""),
            }
        )
    OUT.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "last_updated": date.today().isoformat(),
                "total_ledgers": len(entries),
                "ledgers": entries,
            },
            sort_keys=False,
        )
    )
    print(f"Wrote {OUT}: {len(entries)} ledgers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
