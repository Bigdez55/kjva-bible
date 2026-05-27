#!/usr/bin/env python3
"""Enforce the full-router-integration invariant.

Every skill in 13_skills/active/ must be (1) registered in skills.registry.yaml
and (2) routed in 37_command_protocol/trigger_router.yaml. This gate keeps the
"every skill router-integrated, at all times" rule true continuously — a skill
added by hand without registration or routing fails the build.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = ROOT / "platform" / "sdlc" / "13_skills" / "active"
REGISTRY = ROOT / "platform" / "sdlc" / "13_skills" / "skills.registry.yaml"
ROUTER = ROOT / "platform" / "systems" / "37_command_protocol" / "trigger_router.yaml"


def main() -> int:
    failures: list[str] = []

    for required in (ACTIVE, REGISTRY, ROUTER):
        if not required.exists():
            print("FAIL: skill router integration")
            print(f"  - missing required path: {required.relative_to(ROOT)}")
            return 1

    disk = sorted(p.stem for p in ACTIVE.glob("SKILL_*.yaml"))
    disk_set = set(disk)

    registry = yaml.safe_load(REGISTRY.read_text()) or {}
    reg_entries = registry.get("skills", []) or []
    reg_names = [str(e.get("name", "")) for e in reg_entries if isinstance(e, dict)]
    reg_set = set(reg_names)
    declared_total = registry.get("total")

    # exact-token extraction — skill IDs are maximal SKILL_[A-Z0-9_]+ tokens
    router_tokens = set(re.findall(r"SKILL_[A-Z0-9_]+", ROUTER.read_text()))

    if declared_total != len(reg_names):
        failures.append(
            f"registry 'total' ({declared_total}) != entry count ({len(reg_names)})"
        )
    for skill in sorted(disk_set - reg_set):
        failures.append(f"active skill not registered in skills.registry.yaml: {skill}")
    for skill in sorted(reg_set - disk_set):
        failures.append(f"registry entry has no active skill file: {skill}")
    for skill in sorted(disk_set - router_tokens):
        failures.append(f"active skill not routed in trigger_router.yaml: {skill}")
    for skill in sorted(n for n in reg_set if reg_names.count(n) > 1):
        failures.append(f"duplicate registry entry: {skill}")

    if failures:
        print("FAIL: skill router integration")
        for item in failures:
            print(f"  - {item}")
        return 1

    print(
        f"PASS: skill router integration "
        f"({len(disk)} active skills — all registered and routed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
