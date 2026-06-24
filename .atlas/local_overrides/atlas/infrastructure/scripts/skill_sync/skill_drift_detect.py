#!/usr/bin/env python3
"""
skill_drift_detect.py — bidirectional skill-sync drift detector + vet queue.

Operational model (canonical-authority with inbound review):
  - Development_Skills/platform/sdlc/13_skills/active/ is the CANONICAL source.
  - Each child repo mirrors skills into atlas/13_skills/active/.
  - This script compares every child skill file against canonical by content
    hash and classifies it:

      IN_SYNC      child == canonical                         (nothing to do)
      DIFF         both have it, content differs              (QUEUE for review)
      CANON_ONLY   canonical has it, child lacks it           (re-sync DOWN)
      CHILD_ONLY   child has it, canonical lacks it           (QUEUE for review)

  - DIFF / CHILD_ONLY are the cases that a blind canonical->child copy would
    silently overwrite (e.g. the 2026-05-30 other-agent SSH edits made in
    Tokenless). Instead of clobbering, we copy the child version into a review
    queue so a human (or approved agent) can PROMOTE it to canonical or REJECT.

Queue:
  platform/sdlc/13_skills/skill_refinery/inbound_queue/<repo>__<skill-file>

Usage:
  python3 skill_drift_detect.py            # report only
  python3 skill_drift_detect.py --queue    # also write DIFF/CHILD_ONLY to queue
  python3 skill_drift_detect.py --json     # machine-readable report

Nothing is ever auto-applied. Detect + queue only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

DS_ROOT = Path(
    "/Users/desmondearly/Developer/Development_Skills"
)
CANON_ACTIVE = DS_ROOT / "platform/sdlc/13_skills/active"
QUEUE_DIR = DS_ROOT / "platform/sdlc/13_skills/skill_refinery/inbound_queue"

WORKSPACE = Path("/Users/desmondearly/Developer")
CHILD_REPOS = [
    "GENESYS/GENESYS",
    "kjva-bible",
    "Storbits",
    "nexus",
    "Tokenless models",
    "Super C Academy",
    "IPOS/IPOS",
    "Apollo16-main",
    "SUPER C SNES",
]
CHILD_ACTIVE_REL = "atlas/13_skills/active"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def skill_files(active_dir: Path) -> dict[str, Path]:
    if not active_dir.is_dir():
        return {}
    return {
        p.name: p
        for p in active_dir.iterdir()
        if p.is_file() and p.name.startswith("SKILL_")
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", action="store_true", help="write DIFF/CHILD_ONLY to inbound queue")
    ap.add_argument("--json", action="store_true", help="emit JSON report")
    args = ap.parse_args()

    canon = skill_files(CANON_ACTIVE)
    canon_hashes = {name: sha(p) for name, p in canon.items()}

    report: list[dict] = []
    queued = 0

    for rel in CHILD_REPOS:
        child_active = WORKSPACE / rel / CHILD_ACTIVE_REL
        repo_name = os.path.basename(rel)
        if not child_active.is_dir():
            report.append({"repo": repo_name, "status": "NO_DEV_SKILLS"})
            continue

        child = skill_files(child_active)
        child_hashes = {name: sha(p) for name, p in child.items()}

        for name in sorted(set(canon) | set(child)):
            in_c = name in canon
            in_ch = name in child
            if in_c and in_ch:
                status = "IN_SYNC" if canon_hashes[name] == child_hashes[name] else "DIFF"
            elif in_c:
                status = "CANON_ONLY"
            else:
                status = "CHILD_ONLY"

            if status == "IN_SYNC":
                continue

            row = {"repo": repo_name, "skill": name, "status": status}
            if status == "DIFF":
                row["canon_bytes"] = canon[name].stat().st_size
                row["child_bytes"] = child[name].stat().st_size

            if args.queue and status in ("CHILD_ONLY", "DIFF"):
                QUEUE_DIR.mkdir(parents=True, exist_ok=True)
                dest = QUEUE_DIR / f"{repo_name}__{name}"
                shutil.copy2(child[name], dest)
                row["queued_to"] = str(dest.relative_to(DS_ROOT))
                queued += 1

            report.append(row)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    by_status: dict[str, int] = {}
    for r in report:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    print("=" * 72)
    print("  SKILL DRIFT REPORT - canonical vs fleet children")
    print("=" * 72)
    if not report:
        print("  All children fully in sync with canonical. Nothing to do.")
    for r in report:
        line = f"  [{r['status']:<11}] {r.get('repo',''):<14} {r.get('skill','')}"
        if "canon_bytes" in r:
            line += f"  (canon={r['canon_bytes']}B child={r['child_bytes']}B)"
        if "queued_to" in r:
            line += "  -> queued"
        print(line)
    print("-" * 72)
    print("  Totals: " + ", ".join(f"{k}={v}" for k, v in sorted(by_status.items())))
    if args.queue:
        print(f"  Queued for review: {queued} -> {QUEUE_DIR.relative_to(DS_ROOT)}/")
    else:
        print("  (run with --queue to stage DIFF/CHILD_ONLY for vetting)")
    print()
    print("  NEXT: review queued files, then PROMOTE (copy into canonical active/,")
    print("        bump version, commit) or REJECT (delete from queue; re-sync down).")
    print("        Nothing was auto-applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
