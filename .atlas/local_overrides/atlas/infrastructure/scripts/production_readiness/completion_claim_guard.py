#!/usr/bin/env python3
"""
completion_claim_guard.py — pre-commit gate: a completion CLAIM must be probe-backed.

The false-completion hole is self-report: an agent writes "done/proven/ready/
PRODUCTION READY" into a file and commits it, with nothing checking whether it is
true. This guard blocks that at commit time.

Logic (fast — does NOT run the 3,378-item audit):
  1. Look at the STAGED files for completion-claim markers
     (READY_FOR_PUBLIC_RELEASE, state: "proven", "production ready", "fully wired",
      "all gates proven", releaseRecommendation: "...READY...").
  2. If any staged file carries such a claim, run the evidence probe suite.
  3. If the probe suite is not all-pass, BLOCK the commit (exit 1) and name the
     failing probes. The claim is unbacked.
  4. Also run derive_gate_state.py --check so a hand-edited production-readiness.ts
     that disagrees with probes is blocked.

Bypassable only with `git commit --no-verify` (logged by git). CI is the real floor.

Exit 0 = allow commit; exit 1 = block.
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROBE_RUNNER = ROOT / "platform" / "systems" / "53_production_readiness" / "probes" / "probe_runner.py"
DERIVE = ROOT / "infrastructure" / "scripts" / "production_readiness" / "derive_gate_state.py"

CLAIM_PATTERNS = [
    r"READY_FOR_PUBLIC_RELEASE",
    r"releaseRecommendation\s*[:=]\s*['\"][^'\"]*READY[^'\"]*['\"]",
    r"\bstate:\s*['\"]proven['\"]",
    r"production[\s_-]?ready",
    r"fully\s+wired",
    r"all\s+(seven\s+)?gates\s+(are\s+)?proven",
    r"PUBLIC_RELEASE_READY",
]
CLAIM_RX = re.compile("|".join(CLAIM_PATTERNS), re.IGNORECASE)

# files that legitimately DISCUSS the markers (this guard, the probes, the skill docs,
# memory, the corpus that catalogs the patterns) — claims inside them are not release claims.
EXEMPT_SUBSTR = [
    "completion_claim_guard.py",
    "probe_runner.py",
    "derive_gate_state.py",
    "53_production_readiness/",          # the corpus/probes/registry describe the patterns
    "13_skills/",                        # skill playbooks quote the forbidden phrases
    ".playbook.md",
    "MISS_LOG",
    "/memory/",
    "release-gate-assertion",
    "37_command_protocol/",              # trigger_router/commands catalog claim PHRASES for routing
    "trigger_router.yaml",
    "commands.registry.yaml",
    # production-readiness.ts is GOVERNED by derive_gate_state.py --check (its authoritative
    # state is the generated <derived-gate-state> block, derived from probes). It legitimately
    # carries legacy per-gate `state: "proven"` evidence prose; raw-marker-scanning it would
    # false-positive. The derive --check below is its real, stronger gate.
    "production-readiness.ts",
    # ML training lab & bookworm engine — "production-ready" here means ML model maturity,
    # not ATLAS release state. These paths are entirely outside the release-gate scope.
    "51_bookworm_training_lab/",
    "38_bookworm_engine/",
    "38_bookworm_canonical_bridge",
]


def staged_files() -> list[str]:
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                         cwd=ROOT, capture_output=True, text=True)
    return [f for f in out.stdout.splitlines() if f.strip()]


def staged_content(path: str) -> str:
    out = subprocess.run(["git", "show", f":{path}"], cwd=ROOT, capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else ""


def main() -> int:
    files = staged_files()

    # GATE A (always): if production-readiness.ts is staged, its derived state must match
    # probe reality. This is the authoritative, stronger replacement for raw-marker-scanning
    # that file — a hand-edited release claim that disagrees with probes is blocked here.
    prt_staged = any("production-readiness.ts" in f for f in files)
    if prt_staged:
        derive = subprocess.run([sys.executable, str(DERIVE), "--check"], cwd=ROOT,
                                capture_output=True, text=True)
        if derive.returncode != 0:
            print("BLOCKED: production-readiness.ts disagrees with probe-derived state.")
            print("  " + (derive.stdout.strip().replace("\n", "\n  ") or derive.stderr.strip()))
            print("  fix: python3 infrastructure/scripts/production_readiness/derive_gate_state.py --write")
            print("  Override (logged): git commit --no-verify.")
            return 1

    # GATE B: any OTHER staged file asserting completion/readiness must be probe-backed.
    claim_files: list[tuple[str, str]] = []
    for f in files:
        if any(s in f for s in EXEMPT_SUBSTR):
            continue
        content = staged_content(f)
        m = CLAIM_RX.search(content)
        if m:
            claim_files.append((f, m.group(0)[:60]))

    if not claim_files:
        if prt_staged:
            print("completion-claim guard: production-readiness.ts matches probe-derived state. OK.")
        return 0  # no free-text completion claim staged — nothing to back

    print("completion-claim guard: staged files assert completion/readiness:")
    for f, snippet in claim_files:
        print(f"  - {f}  ({snippet!r})")
    print("  → verifying the claim is backed by evidence probes...")

    probe = subprocess.run([sys.executable, str(PROBE_RUNNER)], cwd=ROOT,
                           capture_output=True, text=True)
    if probe.returncode != 0:
        print("\nBLOCKED: a completion/readiness claim is staged but NOT backed by passing probes.")
        tail = [ln for ln in probe.stdout.splitlines() if "fail" in ln]
        print("  failing probes:")
        for ln in tail[:8]:
            print(f"    {ln.strip()}")
        print("\n  Fix the underlying capability (build/wire it) so the probe passes, "
              "or remove the unbacked claim. Override (logged): git commit --no-verify.")
        return 1

    print("  OK: completion claim is backed by passing probes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
