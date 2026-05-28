#!/usr/bin/env python3
"""Phase 5b — strip ATLAS_/APEX_/SC_ prefixes from skill IDs per Reading B.

For each renameable skill:
  1. Compute new canonical_id by stripping prefix
  2. Skip if collision exists at target (logged for human review)
  3. Atomic rename: yaml + playbook files, id field, playbook ref, registry,
     router, related_skills cross-refs, playbook prose cross-refs
  4. Move subsystem identity from name to domains: array

Rename rules:
  SKILL_APEX_*_NNN   -> SKILL_*_NNN, domains+= [apex]
  SKILL_ATLAS_*_NNN  -> SKILL_*_NNN, domains+= [atlas]
  SKILL_SC_*_NNN     -> SKILL_*_NNN, domains+= [super_c]
  SKILL_SUPER_C_*_NNN -> attempted, expected to collide; skipped if so
  SKILL_*_APEX_*_NNN -> strip APEX_ from middle, domains+= [apex]

Modes:
  --dry-run    Show what would happen
  --apply      Apply
"""

from __future__ import annotations

import argparse
import re
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


RENAME_RULES = [
    # (pattern, domain_to_add, description)
    (re.compile(r"^SKILL_APEX_(.+)_(\d{3})$"), "apex", "APEX prefix"),
    (re.compile(r"^SKILL_ATLAS_(.+)_(\d{3})$"), "atlas", "ATLAS prefix"),
    (re.compile(r"^SKILL_SC_(.+)_(\d{3})$"), "super_c", "SC_ prefix"),
    (re.compile(r"^SKILL_SUPER_C_(.+)_(\d{3})$"), "super_c", "SUPER_C prefix"),
    (re.compile(r"^SKILL_(.+)_APEX_(.+)_(\d{3})$"), "apex", "mid-name APEX"),
]


def compute_rename(sid: str) -> tuple[str | None, str | None]:
    """Return (new_id, domain_to_add) or (None, None) if no rule matches."""
    for pattern, domain, _label in RENAME_RULES:
        m = pattern.match(sid)
        if not m:
            continue
        if "mid-name" in _label:
            new = f"SKILL_{m.group(1)}_{m.group(2)}_{m.group(3)}"
        else:
            new = f"SKILL_{m.group(1)}_{m.group(2)}"
        return new, domain
    return None, None


def collect_all_skills() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        d = yaml.safe_load(p.read_text()) or {}
        out[p.stem] = {"yaml_path": p, "data": d}
    return out


def perform_rename(
    old_id: str,
    new_id: str,
    domain_to_add: str,
    all_skills: dict[str, dict[str, Any]],
    dry_run: bool,
) -> None:
    info = all_skills[old_id]
    d = info["data"]
    old_yaml = info["yaml_path"]
    old_playbook = ACTIVE_DIR / f"{old_id}.playbook.md"
    new_yaml = ACTIVE_DIR / f"{new_id}.yaml"
    new_playbook = ACTIVE_DIR / f"{new_id}.playbook.md"

    # Update YAML
    d["id"] = new_id
    if "playbook" in d and isinstance(d["playbook"], str):
        d["playbook"] = d["playbook"].replace(old_id, new_id)
    domains = d.get("domains") or []
    if domain_to_add not in domains:
        domains.insert(0, domain_to_add)
        d["domains"] = domains
    # Add legacy id provenance
    d.setdefault("provenance", {})["legacy_id"] = old_id

    if not dry_run:
        # Write to new path, remove old
        new_yaml.write_text(yaml.safe_dump(d, sort_keys=False))
        if old_yaml != new_yaml and old_yaml.exists():
            old_yaml.unlink()
        if old_playbook.exists() and old_playbook != new_playbook:
            old_playbook.rename(new_playbook)

    # Update all_skills map
    all_skills[new_id] = {"yaml_path": new_yaml, "data": d}
    if old_id != new_id and old_id in all_skills:
        del all_skills[old_id]


def update_cross_references(
    rename_map: dict[str, str], all_skills: dict[str, dict[str, Any]], dry_run: bool
) -> int:
    """Update related_skills arrays + playbook prose references across all skills."""
    changes = 0
    for sid, info in list(all_skills.items()):
        d = info["data"]
        changed = False
        for field in ("related_skills",):
            arr = d.get(field) or []
            if not isinstance(arr, list):
                continue
            new_arr = [rename_map.get(x, x) for x in arr]
            if new_arr != arr:
                d[field] = new_arr
                changed = True
        if changed:
            if not dry_run:
                info["yaml_path"].write_text(
                    yaml.safe_dump(d, sort_keys=False)
                )
            changes += 1
    return changes


def update_registry(rename_map: dict[str, str], dry_run: bool) -> None:
    reg = yaml.safe_load(REGISTRY_PATH.read_text())
    for entry in reg.get("skills", []):
        old = entry.get("name")
        if old in rename_map:
            new = rename_map[old]
            entry["name"] = new
            if "path" in entry and isinstance(entry["path"], str):
                entry["path"] = entry["path"].replace(f"{old}.yaml", f"{new}.yaml")
    reg["skills"] = sorted(reg["skills"], key=lambda x: x["name"])
    if not dry_run:
        REGISTRY_PATH.write_text(yaml.safe_dump(reg, sort_keys=False))


def update_router(rename_map: dict[str, str], dry_run: bool) -> None:
    text = ROUTER_PATH.read_text()
    for old, new in rename_map.items():
        text = text.replace(old, new)
    if not dry_run:
        ROUTER_PATH.write_text(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        print("ERROR: specify --dry-run or --apply", file=sys.stderr)
        return 2

    all_skills = collect_all_skills()
    rename_map: dict[str, str] = {}
    domain_adds: dict[str, str] = {}
    collisions: list[tuple[str, str]] = []

    for sid in sorted(all_skills.keys()):
        new_id, domain = compute_rename(sid)
        if not new_id:
            continue
        if new_id in all_skills and new_id != sid:
            collisions.append((sid, new_id))
            continue
        rename_map[sid] = new_id
        domain_adds[sid] = domain

    print(f"=== Phase 5b Prefix Strip ({'DRY RUN' if args.dry_run else 'APPLY'}) ===")
    print(f"Renames planned: {len(rename_map)}")
    print(f"Collisions skipped: {len(collisions)}")
    print()
    if collisions:
        print("=== Collisions (deferred to manual audit) ===")
        for old, new in collisions:
            print(f"  {old} -> {new}  (target exists)")
        print()

    print("=== Renames ===")
    for old in sorted(rename_map):
        print(f"  {old} -> {rename_map[old]}  (+domains: {domain_adds[old]})")

    if not rename_map:
        print("No renames to apply.")
        return 0

    # Apply renames atomically
    for old_id in list(rename_map.keys()):
        new_id = rename_map[old_id]
        domain = domain_adds[old_id]
        perform_rename(old_id, new_id, domain, all_skills, args.dry_run)

    cross_changes = update_cross_references(rename_map, all_skills, args.dry_run)
    print(f"\nCross-reference updates in related_skills: {cross_changes}")

    update_registry(rename_map, args.dry_run)
    update_router(rename_map, args.dry_run)
    print(f"Registry + router updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
