"""regression_gate.py — Check a benchmark result JSON against the locked baseline.

Usage:
    python3 regression_gate.py <result_json>

Exit codes:
    0  all thresholds met
    1  one or more regressions detected

The result JSON must contain measured values under the same keys as the baseline.
Only keys present in the result are checked — missing keys produce a WARNING, not a failure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASELINE_PATH = Path(__file__).parent / "KJVA1_XMIND1_BASELINE_2026-06-08.json"


def load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def check(result: dict, baseline: dict) -> list[str]:
    """Return list of failure strings. Empty = all pass."""
    failures: list[str] = []
    warnings: list[str] = []
    t = baseline["thresholds"]
    m = result.get("measured_values", result)  # accept flat or nested result

    def get(d: dict, *keys: str):
        for k in keys:
            if k in d:
                return d[k]
        return None

    # Governance
    gov = get(m, "governance", "governance_pass_count")
    if gov is not None:
        if gov < t["governance"]["min_pass_count"]:
            failures.append(f"GOVERNANCE REGRESSION: {gov} < {t['governance']['min_pass_count']} required")
    else:
        warnings.append("governance key missing from result — not checked")

    # Test suite
    failed = get(m, "test_suite_failed", "failed")
    if failed is None and "test_suite" in m:
        failed = m["test_suite"].get("failed")
    if failed is not None:
        if failed > t["test_suite"]["max_failed"]:
            failures.append(f"TEST REGRESSION: {failed} failures > {t['test_suite']['max_failed']} allowed")
    else:
        warnings.append("test_suite.failed key missing — not checked")

    passed = get(m, "test_suite_passed", "passed")
    if passed is None and "test_suite" in m:
        passed = m["test_suite"].get("passed")
    if passed is not None:
        if passed < t["test_suite"]["min_passed"]:
            failures.append(f"TEST COUNT REGRESSION: {passed} passed < {t['test_suite']['min_passed']} baseline")
    else:
        warnings.append("test_suite.passed key missing — not checked")

    # Grounding
    grounding = get(m, "grounding_tests", "grounding_pass_count")
    if grounding is not None:
        if grounding < t["grounding"]["min_pass_count"]:
            failures.append(f"GROUNDING REGRESSION: {grounding} < {t['grounding']['min_pass_count']} required")
    else:
        warnings.append("grounding_tests key missing — not checked")

    # BPB
    bpb = get(m, "bpb_canonical", "bpb_in_domain")
    if bpb is None and "bpb" in m:
        bpb = m["bpb"].get("canonical")
    if bpb is not None:
        if bpb > t["bpb_in_domain"]["max_bpb"]:
            failures.append(f"BPB REGRESSION: {bpb:.4f} > {t['bpb_in_domain']['max_bpb']} ceiling")
    else:
        warnings.append("bpb key missing — not checked")

    # Determinism
    det = get(m, "determinism_at_T0", "determinism")
    if det is not None:
        if det < t["determinism"]["min_rate"]:
            failures.append(f"DETERMINISM REGRESSION: {det} < {t['determinism']['min_rate']} required")
    else:
        warnings.append("determinism key missing — not checked")

    # Identity audit
    audit = get(m, "identity_audit", "identity_audit_pass_count")
    if audit is not None:
        if audit < t["identity_audit"]["min_pass_count"]:
            failures.append(f"IDENTITY AUDIT REGRESSION: {audit} < {t['identity_audit']['min_pass_count']} required")
    else:
        warnings.append("identity_audit key missing — not checked")

    # Single-runtime authority
    canonical_count = get(m, "canonical_count", "runtime_canonical_count")
    if canonical_count is not None:
        if canonical_count != t["single_runtime_authority"]["canonical_count"]:
            failures.append(f"RUNTIME AUTHORITY REGRESSION: canonical_count={canonical_count}, expected 1")

    # Footprint
    footprint = get(m, "footprint_mb", "model_footprint_mb")
    if footprint is not None:
        if footprint > t["footprint_mb"]["max_model_mb"]:
            failures.append(f"FOOTPRINT REGRESSION: {footprint:.2f} MB > {t['footprint_mb']['max_model_mb']} MB")

    for w in warnings:
        print(f"  WARN: {w}")

    return failures


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} <result_json>")
        return 1

    baseline = load(str(BASELINE_PATH))
    result = load(sys.argv[1])

    print(f"Baseline: {BASELINE_PATH.name}")
    print(f"Result:   {sys.argv[1]}")
    print()

    failures = check(result, baseline)

    if failures:
        print(f"REGRESSION GATE: FAIL ({len(failures)} regression(s))")
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    else:
        print("REGRESSION GATE: PASS — all checked thresholds met")
        return 0


if __name__ == "__main__":
    sys.exit(main())
