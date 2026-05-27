#!/usr/bin/env python3
"""Audit active skills against registry, router catalogs, and support artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
ACTIVE_DIR = ROOT / "platform" / "sdlc" / "13_skills" / "active"
REGISTRY = ROOT / "platform" / "sdlc" / "13_skills" / "skills.registry.yaml"
CANONICAL_ROUTER = ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery" / "trigger_router.yaml"
RUNTIME_ROUTER = ROOT / "platform" / "systems" / "37_command_protocol" / "trigger_router.yaml"
LEDGER_DIR = ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery" / "correction_ledgers"
REGRESSION_DIR = ROOT / "08_verification" / "regression_cases"


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def active_skills() -> set[str]:
    skills: set[str] = set()
    for path in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        data = load_yaml(path)
        skills.add(str(data.get("id") or data.get("skill_id") or path.stem))
    return skills


def registry_skills() -> set[str]:
    data = load_yaml(REGISTRY)
    skills: set[str] = set()
    for entry in data.get("skills", []) or []:
        if isinstance(entry, dict):
            skill_id = entry.get("id") or entry.get("name") or entry.get("skill_id")
            if skill_id:
                skills.add(str(skill_id))
        elif isinstance(entry, str):
            skills.add(entry)
    return skills


def router_skills(path: Path) -> set[str]:
    data = load_yaml(path)
    skills: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "skills" and isinstance(child, list):
                    skills.update(
                        item for item in child if isinstance(item, str) and item.startswith("SKILL_")
                    )
                else:
                    walk(child)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    return skills


def playbook_skills() -> set[str]:
    return {path.stem.replace(".playbook", "") for path in ACTIVE_DIR.glob("SKILL_*.playbook.md")}


def ledger_skills() -> set[str]:
    return {path.name.replace(".ledger.yaml", "") for path in LEDGER_DIR.glob("SKILL_*.ledger.yaml")}


def regression_skills() -> set[str]:
    skills: set[str] = set()
    pattern = re.compile(r"SKILL_[A-Z0-9_]+_\d+")
    for path in REGRESSION_DIR.glob("*.yaml"):
        skills.update(pattern.findall(path.read_text(encoding="utf-8", errors="ignore")))
    return skills


def build_report() -> dict[str, Any]:
    active = active_skills()
    registry = registry_skills()
    canonical_router = router_skills(CANONICAL_ROUTER)
    runtime_router = router_skills(RUNTIME_ROUTER)
    playbooks = playbook_skills()
    ledgers = ledger_skills()
    regressions = regression_skills()

    return {
        "active_yaml_count": len(active),
        "registry_count": len(registry),
        "playbook_count": len(playbooks),
        "ledger_count": len(ledgers),
        "regression_referenced_skill_count": len(regressions),
        "canonical_router_skill_count": len(canonical_router),
        "runtime_router_skill_count": len(runtime_router),
        "missing_registry": sorted(active - registry),
        "extra_registry": sorted(registry - active),
        "missing_playbook": sorted(active - playbooks),
        "missing_ledger": sorted(active - ledgers),
        "missing_canonical_router": sorted(active - canonical_router),
        "missing_runtime_router": sorted(active - runtime_router),
        "canonical_router_nonactive_refs": sorted(canonical_router - active),
        "runtime_router_nonactive_refs": sorted(runtime_router - active),
        "missing_regression_reference": sorted(active - regressions),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit full JSON report.")
    args = parser.parse_args()

    report = build_report()
    hard_fail_fields = [
        "missing_registry",
        "extra_registry",
        "missing_playbook",
        "missing_canonical_router",
        "missing_runtime_router",
        "canonical_router_nonactive_refs",
        "runtime_router_nonactive_refs",
    ]
    failing = {field: report[field] for field in hard_fail_fields if report[field]}

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Skill router integration audit")
        print(f"active_yaml_count: {report['active_yaml_count']}")
        print(f"registry_count: {report['registry_count']}")
        print(f"canonical_router_skill_count: {report['canonical_router_skill_count']}")
        print(f"runtime_router_skill_count: {report['runtime_router_skill_count']}")
        print(f"playbook_count: {report['playbook_count']}")
        print(f"ledger_count: {report['ledger_count']}")
        print(f"regression_referenced_skill_count: {report['regression_referenced_skill_count']}")
        if failing:
            print("FAIL")
            for field, items in failing.items():
                print(f"{field}: {len(items)}")
                for item in items[:50]:
                    print(f"  - {item}")
        else:
            print("PASS: registry, playbook, and router integration hard gates are closed")
            print(f"advisory_missing_ledgers: {len(report['missing_ledger'])}")
            print(f"advisory_missing_regression_references: {len(report['missing_regression_reference'])}")

    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())

