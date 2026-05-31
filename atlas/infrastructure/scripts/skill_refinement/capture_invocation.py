#!/usr/bin/env python3
"""Phase 8 — Telemetry capture for every skill invocation.

Called by post-invocation hooks (~/.claude/hooks/post_skill.sh,
~/.codex/hooks/post_command.sh, ~/.gemini/hooks/post_command.sh) and
by route_intent.py --emit-telemetry for playbook applications.

Writes two records per invocation:
  1. Per-skill ring buffer in skill's `use_telemetry:` field (bounded N=100)
  2. Append to global JSONL: skill_refinery/telemetry/<skill_id>_<YYYYMM>.jsonl

Telemetry JSONL files are gitignored — they may contain user PII in
free-text `correction_summary`. Only aggregated metrics flow to commits.

Usage (any runtime):
  capture_invocation.py --skill_id SKILL_FOO_BAR_001 \
                        --outcome success \
                        --invoker claude \
                        [--correction "user said don't do X"] \
                        [--context-hash <sha256-of-input>]

Outcomes:
  success     normal completion
  partial     incomplete but useful
  failure     error or abandoned
  corrected   user redirected mid-execution (triggers refinement)
  abandoned   user did not engage with output
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "active"
TELEMETRY_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery" / "telemetry"

RING_BUFFER_SIZE = 100
VALID_OUTCOMES = {"success", "partial", "failure", "corrected", "abandoned"}
VALID_INVOKERS = {"claude", "codex", "gemini", "mcp", "playbook", "test", "unknown"}


def find_skill_yaml(skill_id: str) -> Path | None:
    """Locate the YAML file for a skill_id."""
    candidate = ACTIVE_DIR / f"{skill_id}.yaml"
    if candidate.exists():
        return candidate
    # Fuzzy match (suffix without _001)
    matches = list(ACTIVE_DIR.glob(f"{skill_id}*.yaml"))
    if len(matches) == 1:
        return matches[0]
    return None


def update_skill_metrics(
    skill_path: Path, outcome: str, has_correction: bool
) -> None:
    """Update improvement_metrics counters on the canonical yaml."""
    d = yaml.safe_load(skill_path.read_text()) or {}
    im = d.setdefault(
        "improvement_metrics",
        {
            "invocation_count": 0,
            "correction_count": 0,
            "last_correction": None,
            "corrections_per_100_uses": None,
            "last_refinement": None,
            "refinement_count": 0,
            "tier_promotion_history": [],
        },
    )
    im["invocation_count"] = int(im.get("invocation_count") or 0) + 1
    if has_correction or outcome == "corrected":
        im["correction_count"] = int(im.get("correction_count") or 0) + 1
        im["last_correction"] = dt.datetime.now(dt.timezone.utc).isoformat()
    iv = im["invocation_count"]
    cc = im["correction_count"]
    if iv >= 10:
        im["corrections_per_100_uses"] = round(100.0 * cc / iv, 4)
    skill_path.write_text(yaml.safe_dump(d, sort_keys=False))


def append_ring_buffer(skill_path: Path, event: dict[str, Any]) -> None:
    d = yaml.safe_load(skill_path.read_text()) or {}
    buf = d.setdefault("use_telemetry", []) or []
    buf.append(event)
    if len(buf) > RING_BUFFER_SIZE:
        buf = buf[-RING_BUFFER_SIZE:]
    d["use_telemetry"] = buf
    skill_path.write_text(yaml.safe_dump(d, sort_keys=False))


def append_jsonl(skill_id: str, event: dict[str, Any]) -> Path:
    TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
    yyyymm = dt.datetime.now(dt.timezone.utc).strftime("%Y%m")
    path = TELEMETRY_DIR / f"{skill_id}_{yyyymm}.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(event) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill_id", required=True)
    parser.add_argument("--outcome", required=True, choices=sorted(VALID_OUTCOMES))
    parser.add_argument("--invoker", default="unknown", choices=sorted(VALID_INVOKERS))
    parser.add_argument("--correction", default=None,
                        help="Free text describing user correction (PII risk; gitignored)")
    parser.add_argument("--context-hash", default=None,
                        help="sha256 hash of input context (privacy-preserving)")
    parser.add_argument("--silent", action="store_true",
                        help="Don't print to stdout")
    args = parser.parse_args()

    yaml_path = find_skill_yaml(args.skill_id)
    if not yaml_path:
        if not args.silent:
            print(f"WARN: skill not found: {args.skill_id}", file=sys.stderr)
        return 0  # non-fatal: hooks should not block invocation

    # Generate context_hash if not provided
    ctx_hash = args.context_hash
    if not ctx_hash:
        ctx_hash = hashlib.sha256(
            f"{args.skill_id}|{args.invoker}|{dt.datetime.now(dt.timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16]

    event = {
        "skill_id": args.skill_id,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "invoker": args.invoker,
        "outcome": args.outcome,
        "context_hash": ctx_hash,
        "correction_summary": args.correction,
    }

    try:
        update_skill_metrics(yaml_path, args.outcome, bool(args.correction))
        # Strip PII from ring buffer: don't include correction_summary in canonical yaml
        ring_event = {k: v for k, v in event.items() if k != "correction_summary"}
        if args.correction:
            ring_event["had_correction"] = True
        append_ring_buffer(yaml_path, ring_event)
        jsonl_path = append_jsonl(args.skill_id, event)
        if not args.silent:
            print(
                f"telemetry: {args.skill_id} outcome={args.outcome} invoker={args.invoker} "
                f"-> {jsonl_path.relative_to(REPO_ROOT)}"
            )
    except Exception as e:
        if not args.silent:
            print(f"WARN: telemetry capture failed: {e}", file=sys.stderr)
        return 0  # non-fatal
    return 0


if __name__ == "__main__":
    sys.exit(main())
