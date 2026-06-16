#!/usr/bin/env python3
"""
update_action_log.py — Layer 1 (Repo Event Intake), git-diff source = the tracker.

Derives an append-only-style change feed from git (the source of truth for committed
changes): `git log --name-status` -> per-commit file events (created/modified/deleted/
renamed), plus the working tree (`git status --porcelain`) as pending events. Deletions
are KEPT as events (history), so "what broke / what changed" is answerable. No clock use:
timestamps come from git commit dates (deterministic).

The live runtime feed (watcher + webhook + SSE) lands in steps 10-11; this is the
git-history backbone it appends onto.

Exposes build_action_log(stamp, limit) for generate_map_data.py; runnable standalone.
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
US = "\x1f"
STATUS = {"A": "file.created", "M": "file.updated", "D": "file.deleted",
          "R": "file.renamed", "C": "file.copied", "T": "file.typechange"}

def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout

def build_action_log(stamp: str = "unstamped", limit: int = 60) -> dict:
    raw = git("log", f"-n{limit}", "--no-merges", "--date=unix",
              f"--format=%H{US}%ct{US}%an{US}%s", "--name-status")
    commits, cur = [], None
    totals = Counter()
    for line in raw.splitlines():
        if US in line:
            if cur: commits.append(cur)
            h, ct, an, subj = line.split(US)
            iso = datetime.fromtimestamp(int(ct), tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if ct.isdigit() else ct
            cur = {"commit": h[:9], "ts": iso, "author": an, "subject": subj, "changes": []}
        elif line.strip() and cur is not None:
            parts = line.split("\t")
            code = parts[0][0]
            path = parts[-1]
            etype = STATUS.get(code, "file.changed")
            cur["changes"].append({"type": etype, "path": path})
            totals[etype] += 1
    if cur: commits.append(cur)

    # working tree (uncommitted) — pending events
    pending = []
    for line in git("status", "--porcelain").splitlines():
        if not line.strip(): continue
        xy, path = line[:2], line[3:]
        code = ("D" if "D" in xy else "A" if "?" in xy or "A" in xy else "M")
        pending.append({"type": STATUS.get(code, "file.updated"), "path": path, "state": xy.strip()})

    return {
        "generated_at": stamp,
        "source": "git log --name-status (committed) + git status --porcelain (pending)",
        "commits_scanned": len(commits),
        "totals": dict(totals),
        "pending_count": len(pending),
        "pending": pending[:40],
        "commits": commits,   # most-recent first; each with its file-level changes
    }

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stamp", default="unstamped")
    ap.add_argument("--limit", type=int, default=60); a = ap.parse_args()
    log = build_action_log(a.stamp, a.limit)
    OUT = ROOT / "platform/systems/43_graph_engine/action_log/action_log.jsonl"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # one JSON object per commit (append-only friendly), newest first
    OUT.write_text("\n".join(json.dumps(c) for c in log["commits"]) + "\n")
    print(f"WROTE {OUT.relative_to(ROOT)}  ({log['commits_scanned']} commits, "
          f"{sum(log['totals'].values())} file-events, {log['pending_count']} pending)")
    print("  totals:", log["totals"])
    for c in log["commits"][:5]:
        print(f"    {c['ts']}  {c['commit']}  {len(c['changes']):>3} files  {c['subject'][:50]}")

if __name__ == "__main__":
    main()
