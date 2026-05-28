#!/usr/bin/env python3
"""Phase 2 in-corpus backfill script.

Mechanical fixes only — does not touch the 133 `layer: active` remappings
(those need per-skill judgment, deferred to Phase 5 where renames cascade).

Fixes applied:
  1. Backfill `source: native` on every active SKILL_*.yaml (180 skills)
  2. Backfill `tier: active` on the 23 skills missing it
  3. Remove deprecated singular `domain:` field from 12 skills (keep `domains:` array;
     if singular was the only source, merge it into the array first)
  4. Rename SKILL_CONTEXT_COMPILATION_002 → SKILL_CONTEXT_COMPILATION_001
     (no _001 sibling exists; updates id, playbook reference, registry, router)
  5. Resolve skill_number 140 collision by renumbering
     SKILL_CODEX_GEMINI_REPOSITORY_ACQUISITION_001 to the next available number
     (SKILL_THREAD_TO_SKILL_REFINERY_CLOSURE_001 keeps 140 per user intent)
  6. Initialize empty improvement_metrics block on every active skill (bootstrap
     Phase 8's telemetry counters at zero)

Validators that must pass after each fix:
  - validate_skill_router_integration.py (the sacred invariant)
  - validate_tiered_schema.py (lenient until Phase 2 done; strict after)
  - validate_taxonomy.py (lenient until Phase 5 done)

Modes:
  --dry-run    Show what would change; write nothing
  --apply      Actually apply changes
  --step STEP  Only run a specific step (1-6)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "active"
REGISTRY_PATH = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "skills.registry.yaml"
ROUTER_PATH = (
    REPO_ROOT / "platform" / "systems" / "37_command_protocol" / "trigger_router.yaml"
)


def load_skill(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def dump_skill(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


def step1_backfill_source(dry_run: bool) -> int:
    """Add source: native to skills missing it."""
    changed = 0
    for path in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        d = load_skill(path)
        if "source" not in d:
            d["source"] = "native"
            if not dry_run:
                dump_skill(path, d)
            changed += 1
    print(f"  Step 1: {changed} skills gained source: native")
    return changed


def step2_backfill_tier(dry_run: bool) -> int:
    """Add tier: active to skills missing it (all 180 have status: active)."""
    changed = 0
    for path in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        d = load_skill(path)
        if "tier" not in d:
            d["tier"] = "active"
            if not dry_run:
                dump_skill(path, d)
            changed += 1
    print(f"  Step 2: {changed} skills gained tier: active")
    return changed


def step3_remove_singular_domain(dry_run: bool) -> int:
    """Remove deprecated singular `domain:` field; merge into `domains:` if needed."""
    changed = 0
    for path in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        d = load_skill(path)
        if "domain" not in d:
            continue
        singular = d["domain"]
        domains = d.get("domains") or []
        if not isinstance(domains, list):
            domains = []
        if singular and singular not in domains:
            domains.insert(0, singular)
            d["domains"] = domains
        del d["domain"]
        if not dry_run:
            dump_skill(path, d)
        changed += 1
    print(f"  Step 3: {changed} skills had singular `domain:` removed")
    return changed


def step4_rename_context_compilation_002(dry_run: bool) -> int:
    """Rename CONTEXT_COMPILATION_002 -> _001 (no _001 exists)."""
    old_yaml = ACTIVE_DIR / "SKILL_CONTEXT_COMPILATION_002.yaml"
    old_pb = ACTIVE_DIR / "SKILL_CONTEXT_COMPILATION_002.playbook.md"
    new_yaml = ACTIVE_DIR / "SKILL_CONTEXT_COMPILATION_001.yaml"
    new_pb = ACTIVE_DIR / "SKILL_CONTEXT_COMPILATION_001.playbook.md"

    if not old_yaml.exists():
        if new_yaml.exists():
            print("  Step 4: already renamed (CONTEXT_COMPILATION_001 exists)")
            return 0
        print("  Step 4: nothing to do (CONTEXT_COMPILATION_002 not found)")
        return 0
    if new_yaml.exists():
        print(
            "  Step 4: SKIP — both _002 and _001 exist; collision resolved manually",
            file=sys.stderr,
        )
        return 0

    d = load_skill(old_yaml)
    d["id"] = "SKILL_CONTEXT_COMPILATION_001"
    # Update playbook path reference
    if "playbook" in d and isinstance(d["playbook"], str):
        d["playbook"] = d["playbook"].replace(
            "SKILL_CONTEXT_COMPILATION_002", "SKILL_CONTEXT_COMPILATION_001"
        )

    if not dry_run:
        dump_skill(new_yaml, d)
        old_yaml.unlink()
        if old_pb.exists():
            old_pb.rename(new_pb)

        # Update registry
        reg = yaml.safe_load(REGISTRY_PATH.read_text())
        for entry in reg.get("skills", []):
            if entry.get("name") == "SKILL_CONTEXT_COMPILATION_002":
                entry["name"] = "SKILL_CONTEXT_COMPILATION_001"
                if "path" in entry:
                    entry["path"] = entry["path"].replace("_002", "_001")
        REGISTRY_PATH.write_text(yaml.safe_dump(reg, sort_keys=False))

        # Update router: any reference to _002 becomes _001
        router_text = ROUTER_PATH.read_text()
        new_router = router_text.replace(
            "SKILL_CONTEXT_COMPILATION_002", "SKILL_CONTEXT_COMPILATION_001"
        )
        if new_router != router_text:
            ROUTER_PATH.write_text(new_router)

    print("  Step 4: renamed SKILL_CONTEXT_COMPILATION_002 -> _001")
    return 1


def step5_resolve_skill_number_140(dry_run: bool) -> int:
    """Renumber SKILL_CODEX_GEMINI_REPOSITORY_ACQUISITION_001 away from 140.

    SKILL_THREAD_TO_SKILL_REFINERY_CLOSURE_001 keeps 140 (user intent).
    """
    target = ACTIVE_DIR / "SKILL_CODEX_GEMINI_REPOSITORY_ACQUISITION_001.yaml"
    if not target.exists():
        print("  Step 5: target file not found")
        return 0

    # Find next available skill_number in the native band (1-499)
    used: set[int] = set()
    for path in ACTIVE_DIR.glob("SKILL_*.yaml"):
        d = load_skill(path)
        sn = d.get("skill_number")
        if isinstance(sn, str) and sn.isdigit():
            sn = int(sn)
        if isinstance(sn, int):
            used.add(sn)

    next_n = 1
    while next_n in used and next_n < 500:
        next_n += 1
    if next_n >= 500:
        print("  Step 5: FAIL — no available skill_number in native band 1-499", file=sys.stderr)
        return -1

    d = load_skill(target)
    old_n = d.get("skill_number")
    d["skill_number"] = next_n
    if not dry_run:
        dump_skill(target, d)
    print(f"  Step 5: SKILL_CODEX_GEMINI_REPOSITORY_ACQUISITION_001 skill_number {old_n} -> {next_n}")
    return 1


def step6_initialize_improvement_metrics(dry_run: bool) -> int:
    """Initialize empty improvement_metrics on every active skill."""
    changed = 0
    base = {
        "invocation_count": 0,
        "correction_count": 0,
        "last_correction": None,
        "corrections_per_100_uses": None,
        "last_refinement": None,
        "refinement_count": 0,
        "tier_promotion_history": [],
    }
    for path in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        d = load_skill(path)
        if "improvement_metrics" not in d:
            d["improvement_metrics"] = base.copy()
            d["improvement_metrics"]["tier_promotion_history"] = []
            if not dry_run:
                dump_skill(path, d)
            changed += 1
    print(f"  Step 6: {changed} skills gained empty improvement_metrics block")
    return changed


STEPS = {
    1: step1_backfill_source,
    2: step2_backfill_tier,
    3: step3_remove_singular_domain,
    4: step4_rename_context_compilation_002,
    5: step5_resolve_skill_number_140,
    6: step6_initialize_improvement_metrics,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--step", type=int, choices=range(1, 7), default=None)
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("ERROR: specify --dry-run or --apply", file=sys.stderr)
        return 2

    dry = args.dry_run
    print(f"=== Phase 2 Backfill ({'DRY RUN' if dry else 'APPLY'}) ===")
    steps = [args.step] if args.step else range(1, 7)
    for s in steps:
        rc = STEPS[s](dry)
        if rc < 0:
            return 1
    print("=== Done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
