#!/usr/bin/env python3
"""
architecture_map_watcher.py — local change producer for the live map (step 11).

Posts file-change events to POST /api/architecture-map/events (the SSE sink). Deliberately
NOT a daemon: a persistent watcher over a 40k-file OneDrive repo is the always-on/runaway
class that caused prior OOM storms. Two bounded modes only:

  once            (default) — diff HEAD~1..HEAD + working tree, POST the events, exit.
                  Intended to be invoked from a git post-commit/post-merge hook (operator wires it).
  --watch --max-seconds N   — poll `git status` every --interval seconds and POST deltas,
                  for AT MOST N seconds (hard cap, then exits). Opt-in, never left running.

No daemon is installed automatically (that would be a config-writing action). Wire the hook
yourself: `echo 'python3 .../architecture_map_watcher.py once' >> .git/hooks/post-commit`.
"""
from __future__ import annotations
import argparse, json, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATUS = {"A": "file.created", "M": "file.updated", "D": "file.deleted", "R": "file.renamed", "?": "file.created"}

def git(*a) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout

def post(url: str, events: list[dict]) -> int:
    if not events: return 0
    data = json.dumps({"events": events}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read()).get("published", 0)
    except Exception as e:
        print(f"  POST failed ({e}) — is the ATLAS service up on that port?", file=sys.stderr)
        return -1

def regenerate() -> None:
    """Read-only refresh of the map data + docs HTML truth overlay on the commit hook.
    Runs generate_map_data.py (which fuses census + spec-build + proof — NO app boot, NO probe
    fleet) under a hard timeout. Bounded and idempotent; failure is reported, never fatal."""
    stamp = (git("log", "-1", "--format=%cs") or "unstamped").strip() or "unstamped"
    gen = Path(__file__).resolve().parent / "generate_map_data.py"
    try:
        r = subprocess.run([sys.executable, str(gen), "--stamp", stamp],
                           cwd=ROOT, capture_output=True, text=True, timeout=120)
        tail = (r.stdout or r.stderr or "").strip().splitlines()[-1:] or ["(no output)"]
        print(f"  regen: {tail[0]}")
    except subprocess.TimeoutExpired:
        print("  regen: TIMEOUT (120s) — skipped, not fatal", file=sys.stderr)
    except Exception as e:
        print(f"  regen: failed ({e}) — skipped, not fatal", file=sys.stderr)


def porcelain_events(actor="watcher") -> list[dict]:
    evs = []
    for line in git("status", "--porcelain").splitlines():
        if not line.strip(): continue
        xy, path = line[:2], line[3:]
        code = "D" if "D" in xy else ("?" if "?" in xy else ("A" if "A" in xy else "M"))
        evs.append({"type": STATUS.get(code, "file.updated"), "path": path, "actor": actor, "source": "local"})
    return evs

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", default="once", choices=["once", "watch"])
    ap.add_argument("--url", default="http://127.0.0.1:4317/api/architecture-map/events")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--max-seconds", type=float, default=120.0, help="hard cap — the watcher ALWAYS exits by here")
    a = ap.parse_args()

    if a.mode == "once" and not a.watch:
        regenerate()  # refresh the fused truth map before announcing the change
        evs = []
        for line in git("diff", "--name-status", "HEAD~1", "HEAD").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                evs.append({"type": STATUS.get(parts[0][0], "file.updated"), "path": parts[-1],
                            "actor": "git", "source": "local", "commit": (git("rev-parse", "HEAD") or "").strip()[:9]})
        evs += porcelain_events()
        n = post(a.url, evs)
        print(f"posted {n} event(s) from HEAD~1..HEAD + working tree")
        return 0 if n >= 0 else 1

    # bounded watch — polls, posts deltas, ALWAYS stops at --max-seconds (no daemon)
    print(f"watch: polling every {a.interval}s for up to {a.max_seconds}s (bounded; will exit)")
    seen = {tuple(sorted((e["type"], e["path"]) for e in porcelain_events()))}
    start = time.monotonic(); ticks = 0
    while time.monotonic() - start < a.max_seconds:
        time.sleep(a.interval); ticks += 1
        cur = porcelain_events()
        key = tuple(sorted((e["type"], e["path"]) for e in cur))
        if key not in seen:
            seen.add(key)
            print(f"  tick {ticks}: {len(cur)} pending → posting"); post(a.url, cur)
    print(f"watch: max-seconds reached after {ticks} ticks — exiting (not a daemon)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
