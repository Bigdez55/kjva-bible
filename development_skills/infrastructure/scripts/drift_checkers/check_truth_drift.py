#!/usr/bin/env python3
"""Content-hash drift detector. OneDrive-safe (does not use mtime). See ADR-0008."""
import hashlib, json, sys, argparse, yaml
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "20_drift_detection" / "drift_state.yaml"
REPORT = ROOT / "20_drift_detection" / "drift_reports" / "truth_drift_report.json"

WATCH = [
    "19_truth_state",
    "04_architecture",
    "11_documentation",
    "platform/sdlc/13_skills/active",
    "18_registry",
    "26_schemas",
]

def hash_dir(rel):
    base = ROOT / rel
    if not base.exists():
        return None
    h = hashlib.sha256()
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        h.update(p.relative_to(ROOT).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-write", action="store_true", help="Do not update drift report/state files")
    args = ap.parse_args()

    state = yaml.safe_load(STATE.read_text()) if STATE.exists() else {}
    last = (state or {}).get("hashes", {})
    findings = []
    new_hashes = {}
    for w in WATCH:
        cur = hash_dir(w)
        new_hashes[w] = cur
        if w in last and last[w] != cur:
            findings.append({"path": w, "from": last[w][:12], "to": (cur or "")[:12]})

    report_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "findings": findings,
        "watched": WATCH,
    }
    if not args.no_write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report_payload, indent=2))

        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(yaml.safe_dump({"hashes": new_hashes, "updated": datetime.now(timezone.utc).isoformat()}, sort_keys=False))

    action = "Checked" if args.no_write else f"Wrote {REPORT}"
    print(f"{action}: {len(findings)} findings")
    if args.check and findings:
        sys.exit(1)

if __name__ == "__main__":
    main()
