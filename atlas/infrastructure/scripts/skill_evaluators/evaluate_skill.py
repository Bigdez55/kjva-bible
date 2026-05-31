#!/usr/bin/env python3
"""Validate skill yaml against schema; verify referenced validation_tests files exist."""
import sys, json, yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schemas" / "skill" / "skill.schema.json"

PATH_ALIASES = {
    "08_verification/": "platform/sdlc/08_verification/",
    "13_skills/": "platform/sdlc/13_skills/",
    "apps/atlas/": "apps/frontend/atlas/",
}

def normalize_ref(raw: str) -> str:
    for old, new in PATH_ALIASES.items():
        if raw.startswith(old):
            return new + raw[len(old):]
    return raw

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
        normalized = normalize_ref(raw)
        candidates = []
        if normalized.endswith((".yaml", ".ts", ".tsx")) or "/" in normalized:
            candidates.append(ROOT / normalized)
        candidates.append(ROOT / "platform" / "sdlc" / "08_verification" / "skill_tests" / f"{normalized}.yaml")
        candidates.append(ROOT / "platform" / "sdlc" / "08_verification" / "regression_cases" / f"{normalized}.yaml")
        if not any(c.exists() for c in candidates):
            failures.append(t)
    if failures:
        print(f"FAIL: validation_tests missing: {failures}"); sys.exit(1)
    print(f"OK: {skill.get('id')} valid; {len(tests)} test(s) exist")

if __name__ == "__main__":
    main()
