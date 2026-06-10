"""Pre-training alignment dataset audit.

Usage:
    python3 audit_alignment_dataset.py [<file1.jsonl> <file2.jsonl> ...]

If no files given, audits all alignment_*_v1.jsonl in the same directory.
Exit 0 = PASS, exit 1 = FAIL.

Gates:
  AUDIT-1: No owner/any authority can hard_stop an ABSOLUTE covenant category
  AUDIT-2: No Council/persona names appear in expected_output of non-refusing rows
  AUDIT-3: invalid_citation_abstention rows must have required_action=reject_and_abstain
  AUDIT-4: scripture_grounded_answer rows must use retrieve_exact or retrieve_then_respond
  AUDIT-5: creator_sovereign rows must not have allowed_authority=owner
  AUDIT-6: canonical_weight_authority hard_stop rows must have allowed_authority=none/creator_only
  AUDIT-7: hard_stop rows must not have allowed_authority=any/owner
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

PERSONA_NAMES = ["ahki", "council", "sarah", "esther", "magen", "ezri", "bookworm", "desmond"]
ABSOLUTE_COVENANTS = {
    "harm_prevention", "false_witness", "manipulation",
    "identity_integrity", "canonical_weight_authority", "oppression_or_exploitation",
}
REQUIRED_KEYS = {
    "instruction", "input", "expected_output", "category",
    "constitutional_basis", "required_action", "allowed_authority",
    "forbidden_failure_modes", "benchmark_axis",
}


def load_rows(paths: list[Path]) -> list[dict]:
    rows = []
    parse_errors = []
    for path in paths:
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                obj["_file"] = path.name
                obj["_row"] = i + 1
                missing = REQUIRED_KEYS - set(obj.keys())
                if missing:
                    parse_errors.append(f"{path.name}:{i+1}: missing keys {missing}")
                rows.append(obj)
            except json.JSONDecodeError as e:
                parse_errors.append(f"{path.name}:{i+1}: JSON error: {e}")
    return rows, parse_errors


def audit(rows: list[dict]) -> tuple[list[str], list[str]]:
    failures, warnings = [], []

    for r in rows:
        loc = f"{r['_file']}:{r['_row']}"

        # AUDIT-1
        if (r.get("allowed_authority") in ("owner", "any")
                and r.get("required_action") == "hard_stop"
                and r.get("category") in ABSOLUTE_COVENANTS):
            failures.append(f"{loc} AUDIT-1: owner/any on hard_stop for {r['category']}")

        # AUDIT-2
        for pname in PERSONA_NAMES:
            pat = r"\b" + pname + r"\b"
            if re.search(pat, json.dumps(r), re.IGNORECASE):
                is_blocking = r.get("category") == "identity_integrity" and r.get("required_action") == "hard_stop"
                in_forbidden = any(pname.lower() in f.lower() for f in r.get("forbidden_failure_modes", []))
                in_output = re.search(pat, r.get("expected_output", ""), re.IGNORECASE)
                if not is_blocking and not in_forbidden and in_output and r.get("required_action") not in ("hard_stop", "reject_unauthenticated"):
                    failures.append(f"{loc} AUDIT-2: persona '{pname}' in expected_output of non-refusing row")

        # AUDIT-3
        if r.get("category") == "invalid_citation_abstention":
            if r.get("required_action") != "reject_and_abstain":
                failures.append(f"{loc} AUDIT-3: invalid_citation_abstention required_action={r.get('required_action')}")

        # AUDIT-4
        if r.get("category") in ("scripture_grounded_answer", "retrieval_first_scripture_response"):
            if r.get("required_action") not in ("retrieve_exact", "retrieve_then_respond", "generate_with_attribution"):
                warnings.append(f"{loc} AUDIT-4: scripture category has required_action={r.get('required_action')}")

        # AUDIT-6
        if r.get("category") == "canonical_weight_authority" and r.get("required_action") == "hard_stop":
            if r.get("allowed_authority") not in ("none", "creator_only"):
                failures.append(f"{loc} AUDIT-6: weight authority hard_stop allows {r.get('allowed_authority')}")

        # AUDIT-7
        if r.get("required_action") == "hard_stop" and r.get("allowed_authority") in ("any", "owner"):
            failures.append(f"{loc} AUDIT-7: hard_stop with allowed_authority={r.get('allowed_authority')}")

    # AUDIT-5 (cross-row)
    creator_rows = [r for r in rows if r.get("category") == "creator_sovereign_authority"]
    for r in creator_rows:
        if r.get("allowed_authority") == "owner":
            failures.append(f"{r['_file']}:{r['_row']} AUDIT-5: creator_sovereign allowed_authority=owner")

    return failures, warnings


def main() -> int:
    here = Path(__file__).parent
    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
    else:
        paths = sorted(here.glob("alignment_*_v1.jsonl"))

    if not paths:
        print("No alignment JSONL files found.")
        return 1

    rows, parse_errors = load_rows(paths)

    print(f"=== ALIGNMENT DATASET AUDIT ===")
    print(f"Files: {[p.name for p in paths]}")
    print(f"Total rows: {len(rows)}")
    if parse_errors:
        print(f"\nPARSE ERRORS ({len(parse_errors)}):")
        for e in parse_errors:
            print(f"  {e}")
        return 1

    failures, warnings = audit(rows)

    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  FAIL: {f}")
    else:
        print("FAILURES: none")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  WARN: {w}")
    else:
        print("WARNINGS: none")

    verdict = "PASS" if not failures else "FAIL"
    print(f"\nAUDIT RESULT: {verdict}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
