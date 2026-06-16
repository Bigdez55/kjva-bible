#!/usr/bin/env python3
"""
validate_documentation_capture.py — Atlas Documentation Capture gate.

Real, runnable check (NOT a stub). Verifies that changes are captured in Atlas
documentation state, per 11_documentation/change_capture/documentation_capture_policy.md.

Checks (honest, evidence-based):
  1. >=1 agent_run_record exists for recent work.
  2. Files changed in the working tree / last commit appear in the change ledger.
  3. Every change-record file entry carries a doc_impact classification.
  4. NO_DOC_IMPACT entries carry a justification `reason`.
  5. Reports undocumented changed files (changed but absent from any change record).

Modes:
  (default) ADVISORY — prints PASS/WARN, writes the report, exits 0. The script is
            EXECUTABLE but NOT yet wired into pre-commit (wiring is the next step;
            a hard gate on an unpopulated ledger would block every commit).
  --strict  blocks (exit 1) if there are undocumented changes or unclassified impact.
  --against {worktree|HEAD}  what to compare (default worktree: staged+unstaged).

Output report: platform/sdlc/08_verification/validation_reports/documentation_capture_validation.md
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHANGE_LEDGER = ROOT / "platform/sdlc/11_documentation/change_capture/change_ledger.jsonl"
RUN_RECORDS = ROOT / "platform/sdlc/12_agents/agent_activity/agent_run_records.jsonl"
REPORT = ROOT / "platform/sdlc/08_verification/validation_reports/documentation_capture_validation.md"

# Files that never need a change record (transient / generated / vendored).
IGNORE_PREFIX = ("node_modules/", ".next/", "platform/sdlc/16_knowledge/external_collateral/")
IGNORE_EXACT = (".metadata_never_index",)


def jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def changed_files(against: str) -> list[str]:
    if against == "HEAD":
        cmd = ["git", "diff", "--name-only", "HEAD~1..HEAD"]
    else:
        cmd = ["git", "status", "--short", "--porcelain"]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    files = []
    for l in out:
        f = (l[3:] if against == "worktree" else l).strip().strip('"')
        if not f or f.startswith(IGNORE_PREFIX) or f in IGNORE_EXACT:
            continue
        files.append(f)
    return files


def documented_files(records: list[dict]) -> dict[str, list[str]]:
    """path -> doc_impact labels, across all change records."""
    out: dict[str, list[str]] = {}
    for rec in records:
        for ft in rec.get("files_touched", []):
            p = ft.get("path", "").strip().strip('"')
            if p:
                out[p] = ft.get("doc_impact", []) or []
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--against", choices=["worktree", "HEAD"], default="worktree")
    args = ap.parse_args()

    runs = jsonl(RUN_RECORDS)
    changes = jsonl(CHANGE_LEDGER)
    documented = documented_files(changes)
    changed = changed_files(args.against)

    undocumented = [f for f in changed if f not in documented]
    no_impact_missing_reason = [
        ft.get("path") for rec in changes for ft in rec.get("files_touched", [])
        if "NO_DOC_IMPACT" in (ft.get("doc_impact") or []) and not ft.get("reason")
    ]
    unclassified = [p for p, labels in documented.items() if not labels]

    ok = not undocumented and not no_impact_missing_reason and not unclassified
    verdict = "PASS" if ok else "WARN"

    lines = [
        "# Documentation Capture Validation",
        "",
        f"_mode: {'strict' if args.strict else 'advisory'} · against: {args.against}_",
        "",
        f"- agent_run_records: **{len(runs)}**",
        f"- change records: **{len(changes)}** (covering {len(documented)} file paths)",
        f"- changed files inspected: **{len(changed)}**",
        f"- undocumented changes: **{len(undocumented)}**",
        f"- NO_DOC_IMPACT without reason: **{len(no_impact_missing_reason)}**",
        f"- files with empty doc_impact: **{len(unclassified)}**",
        "",
        f"## Verdict: {verdict}",
        "",
    ]
    if undocumented:
        lines += ["### Undocumented changed files (need a change record)", *[f"- `{f}`" for f in undocumented], ""]
    if no_impact_missing_reason:
        lines += ["### NO_DOC_IMPACT missing justification", *[f"- `{f}`" for f in no_impact_missing_reason], ""]
    if not runs:
        lines += ["> NOTE: no agent_run_record found — capture has not been dogfooded yet.", ""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines))

    print(f"documentation-capture: {verdict} "
          f"({len(undocumented)} undocumented, {len(runs)} run-records, {len(changes)} change-records)")
    print(f"  report: {REPORT.relative_to(ROOT)}")
    if args.strict and not ok:
        print("  STRICT: blocking — undocumented or unclassified changes exist.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
