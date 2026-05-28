#!/usr/bin/env python3
"""Phase 3 migration: user-level ~/.claude/skills/ -> canonical SKILL_*.yaml.

Reads the Phase 1 cross-layer aliases report and applies the migration plan:

  - For each user-level skill with NO canonical match (45 of 46): create a
    new canonical SKILL_<UPPER_CONCEPT>_001.yaml + .playbook.md pair.
  - For each user-level skill WITH a canonical match (1 of 46): merge user-level
    body content into the canonical playbook (taking the user-level body as the
    new playbook source; the canonical YAML metadata is preserved).

Allocated skill_numbers: 500-999 (provenance band for source: migrated_user).

Inputs:
  - ~/.claude/skills/<kebab>/SKILL.md         (user-level skill files)
  - platform/sdlc/13_skills/skill_refinery/cross_layer_aliases_*.yaml
  - platform/sdlc/13_skills/active/             (canonical destination)
  - platform/sdlc/13_skills/skills.registry.yaml (register new entries)
  - platform/systems/37_command_protocol/trigger_router.yaml (route new entries)

Modes:
  --dry-run  Show what would happen; write nothing
  --apply    Apply the migration
  --skill KEBAB  Migrate only one skill by kebab name
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "active"
REFINERY_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery"
REGISTRY_PATH = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "skills.registry.yaml"
ROUTER_PATH = (
    REPO_ROOT / "platform" / "systems" / "37_command_protocol" / "trigger_router.yaml"
)
USER_SKILLS_DIR = Path.home() / ".claude" / "skills"

MIGRATED_USER_BAND_START = 500
MIGRATED_USER_BAND_END = 999

# Curated domain/layer mapping for high-signal skills.
# Skills not in this map get heuristic defaults.
SKILL_MAPPING: dict[str, dict[str, Any]] = {
    "verify-validate": {
        "domains": ["validation", "testing", "ci_cd", "skills"],
        "layer": "governance",
        "tier": "hardened",
    },
    "audit-assess-analyze": {
        "domains": ["governance", "validation", "skills"],
        "layer": "meta",
        "tier": "active",
    },
    "apex-directory-discipline": {
        "domains": ["apex", "governance"],
        "layer": "governance",
        "tier": "active",
    },
    "apex-parallel-deploy": {
        "domains": ["apex", "agent_orchestration", "ci_cd"],
        "layer": "governance",
        "tier": "active",
    },
    "apex-verified-machine-encoding": {
        "domains": ["apex", "super_c", "compiler"],
        "layer": "governance",
        "tier": "hardened",
    },
    "compiler-discipline": {
        "domains": ["super_c", "compiler"],
        "layer": "governance",
        "tier": "active",
    },
    "sc-empirical-surface-probe": {
        "domains": ["super_c", "compiler", "testing"],
        "layer": "governance",
        "tier": "hardened",
    },
    "sc-field-lowering-discipline": {
        "domains": ["super_c", "compiler"],
        "layer": "governance",
        "tier": "hardened",
    },
    "skill-continuous-improvement-loop": {
        "domains": ["skills", "governance"],
        "layer": "meta",
        "tier": "active",
    },
    "tutorial-authoring-discipline": {
        "domains": ["documentation", "skills"],
        "layer": "documentation",
        "tier": "active",
    },
    "one-shot-execution-planning": {
        "domains": ["agent_orchestration", "governance"],
        "layer": "governance",
        "tier": "active",
    },
    "git-remote-discipline": {
        "domains": ["governance", "ci_cd"],
        "layer": "governance",
        "tier": "active",
    },
    "agent-worktree-discipline": {
        "domains": ["agent_orchestration", "governance"],
        "layer": "governance",
        "tier": "active",
    },
    "gate-contention-isolation": {
        "domains": ["testing", "validation"],
        "layer": "verification",
        "tier": "active",
    },
    "gate-harness-process-isolation": {
        "domains": ["testing", "validation"],
        "layer": "verification",
        "tier": "active",
    },
    "pipeline-connection-map-authoring": {
        "domains": ["data_pipeline", "documentation", "architecture"],
        "layer": "documentation",
        "tier": "active",
    },
    # Frontend / dashboard codename skills (PRISM, MOSAIC, FORTRESS, VELOCITY, CANVAS, JUPYTER)
    "prism": {"domains": ["frontend", "dashboard", "ipos"], "layer": "application", "tier": "starter"},
    "mosaic": {"domains": ["frontend", "dashboard", "ipos"], "layer": "application", "tier": "starter"},
    "fortress": {"domains": ["frontend", "dashboard", "ipos"], "layer": "application", "tier": "starter"},
    "velocity": {"domains": ["frontend", "dashboard", "ipos"], "layer": "application", "tier": "starter"},
    "canvas": {"domains": ["frontend", "visualization", "ipos"], "layer": "application", "tier": "starter"},
    "jupyter": {"domains": ["frontend", "dashboard", "ipos"], "layer": "application", "tier": "starter"},
    # Capability skills (ipos product domain)
    "pulse": {"domains": ["ipos", "frontend", "observability"], "layer": "application", "tier": "starter"},
    "ai-insights": {"domains": ["ai_insights", "ai", "ipos"], "layer": "application", "tier": "starter"},
    "oracle": {"domains": ["ai", "ipos"], "layer": "integration", "tier": "starter"},
    "alert-system": {"domains": ["observability", "ipos"], "layer": "application", "tier": "starter"},
    "auth-guard": {"domains": ["auth", "security", "ipos"], "layer": "integration", "tier": "starter"},
    "beacon": {"domains": ["accessibility", "ipos"], "layer": "application", "tier": "starter"},
    "vault": {"domains": ["microsoft_365", "ipos", "ci_cd"], "layer": "integration", "tier": "starter"},
    "courier": {"domains": ["ipos", "dashboard"], "layer": "application", "tier": "starter"},
    "export-suite": {"domains": ["ipos", "dashboard"], "layer": "application", "tier": "starter"},
    "deploy-pipeline": {"domains": ["ci_cd", "release"], "layer": "integration", "tier": "starter"},
    "test-harness": {"domains": ["testing", "ipos"], "layer": "verification", "tier": "starter"},
    "sentinel": {"domains": ["testing", "ipos"], "layer": "verification", "tier": "starter"},
    "turbo": {"domains": ["performance", "ipos"], "layer": "application", "tier": "starter"},
    "perf-profiler": {"domains": ["performance", "ipos"], "layer": "application", "tier": "starter"},
    "theme-engine": {"domains": ["frontend", "ipos"], "layer": "application", "tier": "starter"},
    "prestige": {"domains": ["frontend", "ipos"], "layer": "application", "tier": "starter"},
    "responsive-layout": {"domains": ["frontend", "ipos"], "layer": "application", "tier": "starter"},
    "kpi-card-factory": {"domains": ["kpi_reporting", "ipos", "dashboard"], "layer": "application", "tier": "starter"},
    "chart-builder": {"domains": ["visualization", "ipos", "dashboard"], "layer": "application", "tier": "starter"},
    "table-master": {"domains": ["frontend", "ipos", "dashboard"], "layer": "application", "tier": "starter"},
    "dashboard-scaffold": {"domains": ["dashboard", "frontend", "ipos"], "layer": "application", "tier": "starter"},
    "data-pipeline": {"domains": ["data_pipeline", "ipos"], "layer": "integration", "tier": "starter"},
    "pipeline": {"domains": ["data_pipeline", "ipos"], "layer": "integration", "tier": "starter"},
    "spfx-dashboard-builder": {"domains": ["microsoft_365", "frontend", "ipos"], "layer": "application", "tier": "starter"},
}

HEURISTIC_DEFAULT = {
    "domains": ["skills"],
    "layer": "application",
    "tier": "starter",
}


def parse_user_skill(path: Path) -> tuple[dict[str, Any], str]:
    """Parse a user-level SKILL.md into (frontmatter dict, body str).

    Robust to unquoted colons in description values (which break strict
    YAML parsing). Falls back to regex extraction of name+description.
    """
    text = path.read_text()
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    fm_text = text[4:end]
    body = text[end + 5 :].lstrip("\n")
    try:
        frontmatter = yaml.safe_load(fm_text) or {}
        if isinstance(frontmatter, dict):
            return frontmatter, body
    except yaml.YAMLError:
        pass
    # Fallback: regex extraction of leading scalar keys (name, description)
    fm: dict[str, Any] = {}
    # name: <single-line-value>
    m = re.search(r"^name:\s*(.+)$", fm_text, re.MULTILINE)
    if m:
        fm["name"] = m.group(1).strip().strip('"').strip("'")
    # description: <can span multiple lines if continuation indented>
    desc_match = re.search(
        r"^description:\s*(>-?\s*\n((?:\s+.+\n?)+)|(.+))", fm_text, re.MULTILINE
    )
    if desc_match:
        if desc_match.group(2):  # block scalar (>)
            desc = " ".join(line.strip() for line in desc_match.group(2).splitlines())
        else:
            desc = desc_match.group(3).strip().strip('"').strip("'")
        fm["description"] = desc
    return fm, body


def kebab_to_concept(kebab: str) -> str:
    """verify-validate → VERIFY_VALIDATE."""
    return kebab.upper().replace("-", "_")


def canonical_id_from_kebab(kebab: str) -> str:
    return f"SKILL_{kebab_to_concept(kebab)}_001"


def load_existing_skill_numbers() -> set[int]:
    used: set[int] = set()
    for path in ACTIVE_DIR.glob("SKILL_*.yaml"):
        d = yaml.safe_load(path.read_text()) or {}
        sn = d.get("skill_number")
        if isinstance(sn, str) and sn.isdigit():
            sn = int(sn)
        if isinstance(sn, int):
            used.add(sn)
    return used


def allocate_skill_number(used: set[int]) -> int:
    for n in range(MIGRATED_USER_BAND_START, MIGRATED_USER_BAND_END + 1):
        if n not in used:
            return n
    raise RuntimeError("Migrated_user band 500-999 exhausted")


def derive_metadata(kebab: str, frontmatter: dict[str, Any], body: str) -> dict[str, Any]:
    """Combine curated mapping + heuristics + frontmatter to produce skill YAML."""
    mapping = SKILL_MAPPING.get(kebab, HEURISTIC_DEFAULT.copy())
    title = (
        frontmatter.get("name")
        or kebab.replace("-", " ").title()
    )
    if isinstance(title, str) and len(title) < 3:
        title = kebab.replace("-", " ").title()
    description = frontmatter.get("description") or ""
    # First line of body (after any > quote) as fallback summary
    if not description:
        for line in body.splitlines():
            stripped = line.strip().strip("#").strip().strip(">").strip()
            if stripped:
                description = stripped[:200]
                break

    return {
        "id": canonical_id_from_kebab(kebab),
        "title": str(title)[:140],
        "version": "1.0.0",
        "layer": mapping["layer"],
        "domains": mapping["domains"],
        "tier": mapping["tier"],
        "status": "active",
        "source": "migrated_user",
        "aliases": [kebab],
        "playbook": f"platform/sdlc/13_skills/active/SKILL_{kebab_to_concept(kebab)}_001.playbook.md",
        "runtime_projection": True,
        "runtime_projection_targets": ["claude", "codex", "gemini"],
        "refinement": "auto",
        "improvement_metrics": {
            "invocation_count": 0,
            "correction_count": 0,
            "last_correction": None,
            "corrections_per_100_uses": None,
            "last_refinement": None,
            "refinement_count": 0,
            "tier_promotion_history": [],
        },
    }


def write_canonical_pair(
    kebab: str,
    yaml_data: dict[str, Any],
    body: str,
    description: str,
    skill_number: int,
    dry_run: bool,
) -> tuple[Path, Path]:
    yaml_data["skill_number"] = skill_number
    canonical_id = yaml_data["id"]
    yaml_path = ACTIVE_DIR / f"{canonical_id}.yaml"
    playbook_path = ACTIVE_DIR / f"{canonical_id}.playbook.md"

    header = (
        f"# {yaml_data['title']}\n\n"
        f"<!-- Source: migrated from ~/.claude/skills/{kebab}/SKILL.md on "
        f"{dt.date.today().isoformat()} -->\n"
        f"<!-- Runtime alias: {kebab} -->\n\n"
    )
    if description and description.strip():
        header += f"**Summary.** {description.strip()}\n\n"

    if not dry_run:
        yaml_path.write_text(yaml.safe_dump(yaml_data, sort_keys=False))
        playbook_path.write_text(header + body)
    return yaml_path, playbook_path


def merge_into_existing_canonical(
    canonical_id: str, kebab: str, body: str, dry_run: bool
) -> None:
    """When user-level skill has a canonical match: add kebab to aliases and
    optionally merge body into the canonical playbook."""
    yaml_path = ACTIVE_DIR / f"{canonical_id}.yaml"
    if not yaml_path.exists():
        print(f"  WARN: canonical {canonical_id} not found; skipping merge", file=sys.stderr)
        return
    d = yaml.safe_load(yaml_path.read_text()) or {}
    aliases = d.get("aliases") or []
    if kebab not in aliases:
        aliases.insert(0, kebab)
        d["aliases"] = aliases
    # Mark as also migrated_user so provenance trail captures both origins
    if d.get("source") == "native":
        d.setdefault("provenance", {})["also_imported_from"] = "migrated_user"
    if not dry_run:
        yaml_path.write_text(yaml.safe_dump(d, sort_keys=False))
    # Note: we do NOT overwrite the canonical playbook here — for the one
    # case (apex-verified-machine-encoding) the canonical is more authoritative.


def update_registry_and_router(
    entries: list[dict[str, str]], dry_run: bool
) -> None:
    reg = yaml.safe_load(REGISTRY_PATH.read_text())
    existing = {e["name"] for e in reg.get("skills", [])}
    for entry in entries:
        if entry["name"] in existing:
            continue
        reg["skills"].append(
            {"name": entry["name"], "path": entry["path"]}
        )
    reg["skills"] = sorted(reg["skills"], key=lambda x: x["name"])
    reg["total"] = len(reg["skills"])
    reg["last_updated"] = dt.date.today().isoformat()

    if not dry_run:
        REGISTRY_PATH.write_text(yaml.safe_dump(reg, sort_keys=False))

    # Router: add a minimal routing entry that just maps the skill_id to the
    # kebab alias. Use the "behavioral_protocols" or a new "migrated_skills"
    # section — we'll add to whichever section already aggregates simple
    # skill mappings. For now, append to the existing structure.
    router = yaml.safe_load(ROUTER_PATH.read_text())
    if "migrated_skills" not in router:
        router["migrated_skills"] = {
            "description": (
                "Auto-populated by Phase 3 migration. Each entry maps a kebab "
                "name to the canonical skill_id. Generated by "
                "infrastructure/scripts/skill_migration/migrate_user_to_canonical.py."
            ),
            "entries": [],
        }
    existing_router_ids = {
        e["skill_id"]
        for e in router["migrated_skills"]["entries"]
    }
    for entry in entries:
        if entry["name"] not in existing_router_ids:
            router["migrated_skills"]["entries"].append(
                {
                    "skill_id": entry["name"],
                    "kebab": entry["kebab"],
                    "phrases": [f"/{entry['kebab']}", entry["kebab"].replace("-", " ")],
                }
            )
    if not dry_run:
        ROUTER_PATH.write_text(yaml.safe_dump(router, sort_keys=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--skill", help="Migrate only this kebab name")
    parser.add_argument(
        "--aliases-file",
        type=Path,
        default=None,
        help="Path to cross_layer_aliases_*.yaml (default: latest)",
    )
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        print("ERROR: specify --dry-run or --apply", file=sys.stderr)
        return 2

    # Find latest cross-layer aliases file
    if args.aliases_file:
        aliases_path = args.aliases_file
    else:
        aliases_files = sorted(REFINERY_DIR.glob("cross_layer_aliases_*.yaml"))
        if not aliases_files:
            print("ERROR: no cross_layer_aliases_*.yaml found", file=sys.stderr)
            return 2
        aliases_path = aliases_files[-1]
    print(f"Using alias map: {aliases_path.relative_to(REPO_ROOT)}")

    alias_data = yaml.safe_load(aliases_path.read_text())
    entries = alias_data["entries"]

    if args.skill:
        entries = [e for e in entries if e["kebab"] == args.skill]
        if not entries:
            print(f"ERROR: kebab '{args.skill}' not found in alias map", file=sys.stderr)
            return 2

    used_numbers = load_existing_skill_numbers()
    print(f"Existing skill_numbers in use: {len(used_numbers)}")

    new_registry_entries: list[dict[str, str]] = []
    created_count = 0
    merged_count = 0

    for entry in entries:
        kebab = entry["kebab"]
        canonical_match = entry.get("canonical_id")
        user_skill_md = USER_SKILLS_DIR / kebab / "SKILL.md"
        if not user_skill_md.exists():
            print(f"  SKIP {kebab}: SKILL.md not found at {user_skill_md}")
            continue

        frontmatter, body = parse_user_skill(user_skill_md)
        description = frontmatter.get("description", "")

        if canonical_match:
            print(f"  MERGE {kebab} -> {canonical_match} (low similarity; alias only)")
            merge_into_existing_canonical(canonical_match, kebab, body, args.dry_run)
            merged_count += 1
            continue

        # Create new canonical
        yaml_data = derive_metadata(kebab, frontmatter, body)
        sn = allocate_skill_number(used_numbers)
        used_numbers.add(sn)
        yp, pp = write_canonical_pair(
            kebab, yaml_data, body, description, sn, args.dry_run
        )
        print(
            f"  CREATE {yaml_data['id']} (skill_number={sn}, "
            f"tier={yaml_data['tier']}, layer={yaml_data['layer']})"
        )
        new_registry_entries.append(
            {
                "name": yaml_data["id"],
                "path": str(yp.relative_to(REPO_ROOT)),
                "kebab": kebab,
            }
        )
        created_count += 1

    if new_registry_entries:
        update_registry_and_router(new_registry_entries, args.dry_run)

    print()
    print(f"=== Phase 3 Migration Summary ===")
    print(f"Skills migrated (new canonical): {created_count}")
    print(f"Skills merged (alias added):     {merged_count}")
    print(f"Total processed:                  {created_count + merged_count}")
    if args.dry_run:
        print("(DRY RUN — no files were written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
