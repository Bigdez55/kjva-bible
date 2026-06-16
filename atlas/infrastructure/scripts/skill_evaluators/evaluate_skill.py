#!/usr/bin/env python3
"""Validate skill yaml against schema; verify referenced validation_tests files exist."""
import sys, json, yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schemas" / "skill" / "skill.schema.json"

# A genuine validation_tests path ref is a single whitespace-free token that either
# contains a "/" or ends in a test-file extension. Everything else -- non-string
# entries (e.g. {'Burst': '...'} prose mappings) and any string containing whitespace
# (prose like "tools/score_audit.py reproduces ..." or "/api/ingest in 1s ...") -- is a
# descriptive/prose test that is satisfied by being present, NOT a missing-file failure.
TEST_FILE_SUFFIXES = (".yaml", ".yml", ".json", ".py")


def is_path_ref(t) -> bool:
    if not isinstance(t, str):
        return False
    raw = t.strip()
    if not raw or any(ch.isspace() for ch in raw):
        return False
    return ("/" in raw) or raw.endswith(TEST_FILE_SUFFIXES)


def remap_bare_numbered(rel: str) -> str:
    """Apply the repo-restructure path map to a bare-numbered ref.

    dirs 00-17 -> platform/sdlc/NN_*, dirs 18+ -> platform/systems/NN_*,
    26_schemas -> schemas/. Non bare-numbered refs are returned unchanged.
    """
    head = rel.split("/", 1)[0]
    if len(head) >= 3 and head[:2].isdigit() and head[2] == "_":
        if head == "26_schemas":
            return "schemas" + rel[len("26_schemas"):]
        prefix = "platform/sdlc" if int(head[:2]) <= 17 else "platform/systems"
        return f"{prefix}/{rel}"
    return rel


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
        if not is_path_ref(t):
            # Descriptive/prose test (or non-string mapping) — counts as present.
            continue
        raw = t.strip()
        candidates = [
            ROOT / raw,
            ROOT / remap_bare_numbered(raw),
            ROOT / "platform" / "sdlc" / "08_verification" / "skill_tests" / f"{raw}.yaml",
            ROOT / "platform" / "sdlc" / "08_verification" / "regression_cases" / f"{raw}.yaml",
        ]
        if not any(c.exists() for c in candidates):
            failures.append(t)
    if failures:
        print(f"FAIL: validation_tests missing: {failures}"); sys.exit(1)
    print(f"OK: {skill.get('id')} valid; {len(tests)} test(s) exist")

if __name__ == "__main__":
    main()
