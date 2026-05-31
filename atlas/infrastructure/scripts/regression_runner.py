#!/usr/bin/env python3
"""Run repo-native regression cases for the v7 skills stack."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "platform" / "sdlc" / "08_verification" / "regression_cases"

sys.path.insert(0, str(ROOT / "infrastructure/scripts"))
from route_intent import route_text  # noqa: E402


def run_case(path: Path) -> tuple[bool, str]:
    case = yaml.safe_load(path.read_text()) or {}
    case_id = case.get("test_id") or case.get("id") or path.stem
    routed = route_text(case.get("input_scenario", ""))
    expected = set(case.get("expected_intents", []) or [])
    actual = set(routed.get("matched_intents", []) or [])
    missing = sorted(expected - actual)
    if missing:
        return False, f"{case_id}: missing intents {missing}; actual={sorted(actual)}"
    if case.get("expected_selected_root") and routed.get("selected_root") != case["expected_selected_root"]:
        return False, f"{case_id}: selected_root={routed.get('selected_root')} expected={case['expected_selected_root']}"
    if case.get("expected_selected_noun") and routed.get("selected_noun") != case["expected_selected_noun"]:
        return False, f"{case_id}: selected_noun={routed.get('selected_noun')} expected={case['expected_selected_noun']}"
    if case.get("expected_selected_target") and routed.get("selected_target") != case["expected_selected_target"]:
        return False, f"{case_id}: selected_target={routed.get('selected_target')} expected={case['expected_selected_target']}"
    if "expected_proof_required" in case and routed.get("proof_requirements", {}).get("required") != case["expected_proof_required"]:
        return False, f"{case_id}: proof_required={routed.get('proof_requirements')} expected={case['expected_proof_required']}"
    if case.get("expected_corrective") and routed.get("corrective_override", {}).get("trigger") != case["expected_corrective"]:
        return False, f"{case_id}: corrective={routed.get('corrective_override')} expected={case['expected_corrective']}"
    return True, f"{case_id}: pass"


def main() -> int:
    failures = []
    paths = sorted(CASES.glob("REG-*.yaml"))
    if not paths:
        print(f"No regression cases found under {CASES}")
        return 1
    for path in paths:
        ok, message = run_case(path)
        print(message)
        if not ok:
            failures.append(message)
    if failures:
        print(f"FAIL: {len(failures)} regression case(s) failed")
        return 1
    print(f"PASS: {len(paths)} regression case(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
