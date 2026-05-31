#!/usr/bin/env python3
"""Phase 4 — auto-promote external imports to canonical (skill_numbers 1000-1042).

Reads platform/systems/18_registry/agent_skill_imports/normalized_skill_registry.yaml
and creates a canonical SKILL_<CONCEPT>_001.yaml + .playbook.md pair for each
external skill that has no canonical counterpart.

Each promoted skill is created as:
  - tier: starter
  - status: active           (lives in active/, invokable)
  - source: promoted_external
  - skill_number: 1000-1042
  - domains: [imported, <best-guess>]
  - aliases: [<original external ID lowercased>]
  - playbook body: stub with provenance header listing source repos and
                    raw_safe_text path; weekly audit pipeline refines

Modes:
  --dry-run  Show what would happen
  --apply    Apply
  --skip-existing  Skip imports that already have a canonical match
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "active"
EXTERNAL_REGISTRY = (
    REPO_ROOT
    / "platform"
    / "systems"
    / "18_registry"
    / "agent_skill_imports"
    / "normalized_skill_registry.yaml"
)
REGISTRY_PATH = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "skills.registry.yaml"
ROUTER_PATH = (
    REPO_ROOT / "platform" / "systems" / "37_command_protocol" / "trigger_router.yaml"
)

EXTERNAL_BAND_START = 1000
EXTERNAL_BAND_END = 1999

# Best-guess domain mapping for the 43 external imports
EXTERNAL_DOMAIN_MAP: dict[str, list[str]] = {
    "SKILL_ADR": ["imported", "documentation", "architecture"],
    "SKILL_AGENT_DISPATCH": ["imported", "agent_orchestration"],
    "SKILL_AI_GOVERNANCE_CITADEL": ["imported", "ai", "governance"],
    "SKILL_API_CONTRACT": ["imported", "architecture", "documentation"],
    "SKILL_BUILD_TOOLCHAIN_CI": ["imported", "ci_cd", "super_c"],
    "SKILL_CI_PREFLIGHT": ["imported", "ci_cd", "validation"],
    "SKILL_COMPILE_CHECK": ["imported", "super_c", "compiler"],
    "SKILL_COMPILER_DISCIPLINE": ["imported", "super_c", "compiler"],
    "SKILL_COMPLIANCE_CHECK": ["imported", "governance", "security"],
    "SKILL_DESKTOP_UI_ACCESSIBILITY": ["imported", "accessibility", "frontend"],
    "SKILL_DOCS_SYNC": ["imported", "documentation"],
    "SKILL_E2E_AUDIT_DISPATCH": ["imported", "testing", "validation"],
    "SKILL_FREESTANDING_C_KERNEL": ["imported", "kernel", "super_c"],
    "SKILL_FULL_TEST_MATRIX": ["imported", "testing"],
    "SKILL_FUZZ_MODULE": ["imported", "testing", "security"],
    "SKILL_HW_DRIVER_VERIFY": ["imported", "kernel", "validation"],
    "SKILL_ISO_BUILD": ["imported", "genos", "ci_cd"],
    "SKILL_KERNEL_DEBUG": ["imported", "kernel", "genos"],
    "SKILL_LANGUAGE_GATE": ["imported", "super_c", "validation"],
    "SKILL_NEW_GENSD_SERVICE": ["imported", "genos", "architecture"],
    "SKILL_NEW_KERNEL_MODULE": ["imported", "kernel", "genos"],
    "SKILL_NEW_PLATFORM_SERVICE": ["imported", "architecture", "backend"],
    "SKILL_NEW_XFRAME_WIDGET": ["imported", "genos", "frontend"],
    "SKILL_QEMU_BOOT_TEST": ["imported", "kernel", "testing"],
    "SKILL_README": ["imported", "documentation"],
    "SKILL_RELEASE_PREP": ["imported", "release", "ci_cd"],
    "SKILL_RESPONSE_ACCURACY_CORRECTIVE": ["imported", "validation", "ai"],
    "SKILL_SECURITY_AUDIT": ["imported", "security", "validation"],
    "SKILL_SECURITY_CRYPTO_ENGINEERING": ["imported", "security", "auth"],
    "SKILL_SKILL": ["imported", "skills"],
    "SKILL_SPRINT_CI_GEN": ["imported", "ci_cd", "agent_orchestration"],
    "SKILL_SPRINT_KICKOFF": ["imported", "agent_orchestration"],
    "SKILL_SPRINT_RETRO": ["imported", "agent_orchestration", "skills"],
    "SKILL_SPRINT3_XNET": ["imported", "genos", "architecture"],
    "SKILL_SPRINT3_XPKG": ["imported", "genos", "release"],
    "SKILL_SPRINT3_XSEC": ["imported", "genos", "security"],
    "SKILL_STATIC_ANALYSIS": ["imported", "validation", "testing"],
    "SKILL_SUBSYSTEMS_FROM_SCRATCH": ["imported", "kernel", "architecture"],
    "SKILL_TUTORIAL_AUTHORING_DISCIPLINE": ["imported", "documentation", "skills"],
    "SKILL_WAL_DEBUG": ["imported", "kernel", "observability"],
    "SKILL_XISC_CLOUD_TOOLCHAIN": ["imported", "super_c", "cloud_ops"],
    "SKILL_XKABI_CAPABILITY": ["imported", "genos", "security"],
    "SKILL_XMIND_TEST": ["imported", "testing"],
}


def derive_layer(domains: list[str]) -> str:
    """Pick a layer from domain hints."""
    if any(d in domains for d in ("kernel", "genos", "super_c", "compiler")):
        return "core"
    if any(d in domains for d in ("ci_cd", "release", "release")):
        return "integration"
    if "documentation" in domains:
        return "documentation"
    if any(d in domains for d in ("testing", "validation", "security")):
        return "verification"
    if any(d in domains for d in ("governance", "agent_orchestration", "skills")):
        return "governance"
    if "frontend" in domains:
        return "application"
    return "integration"


def normalize_alias(external_id: str) -> str:
    """SKILL_ADR -> adr, SKILL_NEW_KERNEL_MODULE -> new-kernel-module."""
    if external_id.startswith("SKILL_"):
        external_id = external_id[len("SKILL_") :]
    return external_id.lower().replace("_", "-")


def canonical_id_from_external(external_id: str) -> str:
    """SKILL_ADR -> SKILL_ADR_001. If already exists in native form, add disambiguator.

    Most imports collide with potential native names (e.g., SKILL_COMPILER_DISCIPLINE
    already exists as native). We use a suffix to disambiguate.
    """
    base = external_id if external_id.startswith("SKILL_") else f"SKILL_{external_id}"
    return f"{base}_001"


def find_collision(canonical_id: str) -> bool:
    return (ACTIVE_DIR / f"{canonical_id}.yaml").exists()


def load_used_numbers() -> set[int]:
    used: set[int] = set()
    for p in ACTIVE_DIR.glob("SKILL_*.yaml"):
        d = yaml.safe_load(p.read_text()) or {}
        sn = d.get("skill_number")
        if isinstance(sn, str) and sn.isdigit():
            sn = int(sn)
        if isinstance(sn, int):
            used.add(sn)
    return used


def allocate_number(used: set[int]) -> int:
    for n in range(EXTERNAL_BAND_START, EXTERNAL_BAND_END + 1):
        if n not in used:
            return n
    raise RuntimeError("external band exhausted")


def make_skill_yaml(
    canonical_id: str,
    external_id: str,
    name: str,
    domains: list[str],
    surfaces: list[str],
    repos: list[str],
    sha256: str,
    preferred_source: str,
    skill_number: int,
) -> dict[str, Any]:
    return {
        "id": canonical_id,
        "title": name.replace("-", " ").replace("_", " ").title()[:140],
        "version": "1.0.0",
        "layer": derive_layer(domains),
        "domains": domains,
        "tier": "starter",
        "status": "active",
        "source": "promoted_external",
        "aliases": [normalize_alias(external_id)],
        "playbook": f"platform/sdlc/13_skills/active/{canonical_id}.playbook.md",
        "runtime_projection": True,
        "runtime_projection_targets": ["claude", "codex", "gemini"],
        "refinement": "auto",
        "skill_number": skill_number,
        "improvement_metrics": {
            "invocation_count": 0,
            "correction_count": 0,
            "last_correction": None,
            "corrections_per_100_uses": None,
            "last_refinement": None,
            "refinement_count": 0,
            "tier_promotion_history": [],
        },
        "provenance": {
            "imported_from_surfaces": surfaces,
            "source_repos": repos,
            "source_hash_sha256": sha256,
            "preferred_source_path": preferred_source,
            "promoted_on": dt.date.today().isoformat(),
            "promotion_method": "auto_promote_external (Phase 4)",
        },
    }


def make_playbook_body(
    canonical_id: str,
    external_id: str,
    name: str,
    surfaces: list[str],
    repos: list[str],
    preferred_source: str,
    source_count: int,
) -> str:
    return f"""# {canonical_id}

> **STUB** — promoted from external assistant surfaces. Awaiting first invocation
> telemetry. The skill_refinery weekly audit (`audit_external_promotions.py`)
> will refine this stub into a full playbook as patterns accumulate.

## Provenance

- Original identifier: `{external_id}`
- Original name: `{name}`
- Source surfaces: {", ".join(f"`{s}`" for s in surfaces)}
- Discovered in {source_count} files across {len(repos)} repositories:
  {", ".join(f"`{r}`" for r in repos)}
- Preferred source path (raw_safe_text): `{preferred_source}`

## Status

- `tier: starter` — needs telemetry to prove production readiness
- `status: active` — invokable; usage feeds the refinement engine
- `source: promoted_external` — provenance band 1000-1999

## Behavior

This stub captures the skill's identity and provenance only. When invoked,
the post-invocation telemetry hook records the invocation context. As
patterns emerge from real use, the Phase 8 refinement engine consolidates
them into actionable gates and rules below.

## Refinement Triggers

This skill will gain content when:

1. The Phase 4 weekly audit (`audit_external_promotions.py`) detects the
   skill has been invoked ≥3 times and proposes content from observed
   patterns
2. A human author runs `promote_skill.py` to upgrade tier and provide
   content directly
3. The original raw source file at `{preferred_source}` is restored to
   the repository and a one-shot promotion script re-runs

## Cross-References

- See [TAXONOMY.md](../TAXONOMY.md) for domain definitions
- See [LIFECYCLE.md](../LIFECYCLE.md) for promotion criteria
- See `infrastructure/scripts/skill_promotion/audit_external_promotions.py`
"""


def update_registry(new_entries: list[dict[str, str]], dry_run: bool) -> None:
    reg = yaml.safe_load(REGISTRY_PATH.read_text())
    existing = {e["name"] for e in reg.get("skills", [])}
    for e in new_entries:
        if e["name"] not in existing:
            reg["skills"].append({"name": e["name"], "path": e["path"]})
    reg["skills"] = sorted(reg["skills"], key=lambda x: x["name"])
    reg["total"] = len(reg["skills"])
    reg["last_updated"] = dt.date.today().isoformat()
    if not dry_run:
        REGISTRY_PATH.write_text(yaml.safe_dump(reg, sort_keys=False))


def update_router(new_entries: list[dict[str, str]], dry_run: bool) -> None:
    router = yaml.safe_load(ROUTER_PATH.read_text())
    if "promoted_external_skills" not in router:
        router["promoted_external_skills"] = {
            "description": (
                "Auto-populated by Phase 4 external promotion. Each entry maps "
                "the alias to the canonical skill_id. Generated by "
                "infrastructure/scripts/skill_promotion/auto_promote_external.py."
            ),
            "entries": [],
        }
    existing = {
        e["skill_id"]
        for e in router["promoted_external_skills"]["entries"]
    }
    for e in new_entries:
        if e["name"] not in existing:
            router["promoted_external_skills"]["entries"].append(
                {
                    "skill_id": e["name"],
                    "alias": e["alias"],
                    "phrases": [f"/{e['alias']}", e["alias"].replace("-", " ")],
                }
            )
    if not dry_run:
        ROUTER_PATH.write_text(yaml.safe_dump(router, sort_keys=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--skip-existing", action="store_true", default=True)
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        print("ERROR: specify --dry-run or --apply", file=sys.stderr)
        return 2

    external_data = yaml.safe_load(EXTERNAL_REGISTRY.read_text())
    external_skills = external_data.get("skills", [])

    used_numbers = load_used_numbers()
    new_entries: list[dict[str, str]] = []
    skipped = 0
    created = 0

    for ext in external_skills:
        ext_id = ext["id"]
        canonical_id = canonical_id_from_external(ext_id)

        if find_collision(canonical_id):
            print(f"  SKIP {ext_id}: canonical {canonical_id} already exists")
            skipped += 1
            continue

        domains = EXTERNAL_DOMAIN_MAP.get(ext_id, ["imported"])
        sn = allocate_number(used_numbers)
        used_numbers.add(sn)

        yaml_data = make_skill_yaml(
            canonical_id=canonical_id,
            external_id=ext_id,
            name=ext.get("name", canonical_id),
            domains=domains,
            surfaces=ext.get("surfaces", []),
            repos=ext.get("repos", []),
            sha256=ext.get("sha256", ""),
            preferred_source=ext.get("preferred_source", ""),
            skill_number=sn,
        )
        playbook_body = make_playbook_body(
            canonical_id=canonical_id,
            external_id=ext_id,
            name=ext.get("name", ""),
            surfaces=ext.get("surfaces", []),
            repos=ext.get("repos", []),
            preferred_source=ext.get("preferred_source", ""),
            source_count=ext.get("source_count", 0),
        )

        yaml_path = ACTIVE_DIR / f"{canonical_id}.yaml"
        playbook_path = ACTIVE_DIR / f"{canonical_id}.playbook.md"

        print(
            f"  CREATE {canonical_id} (skill_number={sn}, layer={yaml_data['layer']}, "
            f"domains={domains[:2]}{'...' if len(domains) > 2 else ''})"
        )

        if not args.dry_run:
            yaml_path.write_text(yaml.safe_dump(yaml_data, sort_keys=False))
            playbook_path.write_text(playbook_body)

        new_entries.append(
            {
                "name": canonical_id,
                "path": str(yaml_path.relative_to(REPO_ROOT)),
                "alias": normalize_alias(ext_id),
            }
        )
        created += 1

    if new_entries:
        update_registry(new_entries, args.dry_run)
        update_router(new_entries, args.dry_run)

    print()
    print(f"=== Phase 4 External Promotion Summary ===")
    print(f"External imports examined: {len(external_skills)}")
    print(f"Promoted (new canonical):   {created}")
    print(f"Skipped (collision):       {skipped}")
    if args.dry_run:
        print("(DRY RUN — no files were written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
