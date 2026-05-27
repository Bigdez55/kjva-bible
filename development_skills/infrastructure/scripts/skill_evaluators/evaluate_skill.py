#!/usr/bin/env python3
"""Validate skill yaml against schema; verify referenced validation_tests files exist."""
import sys, json, yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "26_schemas" / "skill" / "skill.schema.json"

def main():
    if len(sys.argv) < 2:
        print("usage: evaluate_skill.py <skill.yaml>"); sys.exit(2)
    p = Path(sys.argv[1])
    if not p.is_absolute():
        p = ROOT / p
    skill = yaml.safe_load(p.read_text())
    schema = json.loads(SCHEMA.read_text())
    missing = [k for k in schema.get("required", []) if k not in skill]
    if missing:
        print(f"FAIL: missing required keys: {missing}"); sys.exit(1)
    tests = skill.get("validation_tests", []) or []
    failures = []
    for t in tests:
        raw = str(t)
        candidates = []
        if raw.endswith(".yaml") or "/" in raw:
            candidates.append(ROOT / raw)
        candidates.append(ROOT / "08_verification" / "skill_tests" / f"{raw}.yaml")
        candidates.append(ROOT / "08_verification" / "regression_cases" / f"{raw}.yaml")
        if not any(c.exists() for c in candidates):
            failures.append(t)
    if failures:
        print(f"FAIL: validation_tests missing: {failures}"); sys.exit(1)
    print(f"OK: {skill.get('id')} valid; {len(tests)} test(s) exist")

if __name__ == "__main__":
    main()
