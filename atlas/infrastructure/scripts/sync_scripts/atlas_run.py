#!/usr/bin/env python3
"""
atlas_run.py — the governed runner. ALL agent/automation-launched commands go through it.

This is the "neutral process governor" wrapper (previously PROPOSED in the integration layer):
it bounds every child command with a hard timeout and SIGKILLs the whole process group on
timeout/exit so nothing leaks (the F-04 storm/leak class). Each run is logged for traceability.

Usage:
  atlas_run.py run --repo <repo> [--timeout SECONDS] [--tag T] -- <command> [args...]
  (timeout 0 = no limit, e.g. watch mode; default 900s)
"""
from __future__ import annotations
import argparse, json, os, signal, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LOG = ROOT / "platform/systems/21_repo_sync/federation_logs/atlas_run.jsonl"


def main() -> int:
    # Split our own flags from the child command at the first "--" (REMAINDER mixes badly
    # with optionals — it would greedily swallow --repo/--timeout before parsing them).
    raw = sys.argv[1:]
    if "--" in raw:
        i = raw.index("--"); pre, argv = raw[:i], raw[i + 1:]
    else:
        pre, argv = raw, []
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("--repo", default="atlas")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--tag", default="")
    a = ap.parse_args(pre)

    if not argv:
        print("atlas_run: no command after --", file=sys.stderr)
        return 2

    env = dict(os.environ, ATLAS_PROC="1", ATLAS_RUN_REPO=a.repo)
    start = time.time()
    proc = subprocess.Popen(argv, cwd=ROOT, env=env, start_new_session=True)
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        pgid = proc.pid
    rc, timed_out = None, False
    try:
        rc = proc.wait(timeout=(a.timeout or None))
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        rc = 124
    finally:
        # no-residue: kill the whole group even on the success path
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    rec = {"repo": a.repo, "tag": a.tag, "argv": argv, "rc": rc,
           "timed_out": timed_out, "secs": round(time.time() - start, 2)}
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass
    if timed_out:
        print(f"atlas_run: TIMEOUT >{a.timeout}s — process group killed (no residue).", file=sys.stderr)
    return rc if isinstance(rc, int) else 1


if __name__ == "__main__":
    sys.exit(main())
