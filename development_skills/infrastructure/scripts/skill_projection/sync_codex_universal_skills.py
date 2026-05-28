#!/usr/bin/env python3
"""Synchronize canonical active skills into the repo-local Codex universal bundle.

The live Codex runtime shims are generated into ``~/.codex/skills``. This script
keeps the repository-distributable universal skill bundle in sync at:

  .codex/universal/skills/<projection-name>/SKILL.md

It is intentionally additive by default. It updates canonical projections and
    the generated catalog, but it does not delete unrelated or legacy files.
    Existing skill shims are preserved by default; use ``--refresh-existing`` to
    rewrite them from the current canonical playbooks.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "active"
UNIVERSAL_SKILLS = REPO_ROOT / ".codex" / "universal" / "skills"
CATALOG_PATH = UNIVERSAL_SKILLS / "SKILL_CATALOG.md"
TODAY = dt.date.today().isoformat()

DEFAULT_TARGETS = ["claude", "codex", "gemini"]

VERIFY_VALIDATE_TERMS = {
    "verify",
    "validate",
    "validation",
    "test",
    "testing",
    "gate",
    "gates",
    "regression",
    "compile",
    "check",
    "ci",
    "e2e",
    "fuzz",
    "coverage",
    "qa",
}

AUDIT_ASSESS_TERMS = {
    "audit",
    "auditor",
    "assess",
    "assessment",
    "analyze",
    "analysis",
    "review",
    "integrity",
    "sentinel",
    "guardian",
    "drift",
    "truth",
    "reconcile",
    "reconciliation",
    "compliance",
    "red-team",
    "security",
}

CATEGORY_ORDER = [
    "VERIFY_VALIDATE",
    "AUDIT_ASSESS_ANALYZE",
    "ATLAS",
    "AZURE_CLOUD",
    "MICROSOFT_FOUNDRY",
    "AGENT_ORCHESTRATION",
    "PLATFORM_ARCHITECTURE",
    "DATA_INFRASTRUCTURE",
    "FRONTEND_UI",
    "SECURITY_GOVERNANCE",
    "RELEASE_DEPLOY",
    "DOMAIN_ELSON",
    "DOMAIN_GENOS",
    "DOMAIN_IPOS",
    "META_SKILLS",
    "OTHER",
]


@dataclass(frozen=True)
class SkillProjection:
    projection_name: str
    skill_id: str
    title: str
    source: str
    category: str
    quality_disciplines: list[str]
    domains: list[str]
    layer: str
    tier: str
    destination: str
    exists_before: bool
    changed: bool


def kebab_from_canonical_id(canonical_id: str) -> str:
    """SKILL_FOO_BAR_001 -> foo-bar."""
    match = re.match(r"^SKILL_(.+)_\d{3}$", canonical_id)
    if not match:
        return canonical_id.lower().replace("_", "-")
    return match.group(1).lower().replace("_", "-")


def derive_projection_name(data: dict[str, Any], used_names: set[str] | None = None) -> str:
    """Mirror generate_runtime_shims.py naming exactly, including raw aliases."""
    aliases = data.get("aliases") or []
    canonical_name = kebab_from_canonical_id(data.get("id", ""))
    preferred = aliases[0] if aliases and isinstance(aliases[0], str) else canonical_name

    if used_names is None:
        return preferred
    if preferred not in used_names:
        return preferred
    if canonical_name != preferred and canonical_name not in used_names:
        return canonical_name

    skill_number = data.get("skill_number") or 0
    candidate = f"{preferred}-{skill_number}"
    if candidate not in used_names:
        return candidate

    fallback_id = data.get("id", "unknown").lower().replace("_", "-")
    return f"{preferred}-{fallback_id}"


def yaml_quote(value: str) -> str:
    value = value.replace("\n", " ").replace("\r", " ").strip()
    if not value:
        return '""'
    if any(char in value for char in (":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", ">", "!", "%", "@", "`", '"')):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def read_playbook(skill_id: str) -> str:
    path = ACTIVE_DIR / f"{skill_id}.playbook.md"
    if not path.exists():
        return f"<!-- canonical playbook missing for {skill_id} -->\n"
    return path.read_text(encoding="utf-8")


def derive_description(data: dict[str, Any], playbook_body: str) -> str:
    title = data.get("title") or data.get("id", "")
    for line in playbook_body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("<!--") or stripped.startswith(">"):
            continue
        if stripped.startswith("**Summary."):
            stripped = stripped[len("**Summary.") :].strip().rstrip("*").strip()
        return f"{title} - {stripped[:160]}"
    return title


def codex_universal_shim(data: dict[str, Any], projection_name: str, playbook_body: str) -> str:
    description = derive_description(data, playbook_body)
    skill_id = data["id"]
    return f"""---
name: {projection_name}
description: {yaml_quote(description)}
source: platform/sdlc/13_skills/active/{skill_id}.yaml
canonical_id: {skill_id}
generated: {TODAY}
runtime: codex_universal
---

> **Repo-local Codex universal projection of `{skill_id}`.** Edit the canonical, not this file.
> Source of truth: `platform/sdlc/13_skills/active/{skill_id}.playbook.md`
> Regenerated by: `infrastructure/scripts/skill_projection/sync_codex_universal_skills.py`

{playbook_body.rstrip()}
"""


def collect_canonical_skills() -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for path in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if data.get("id") and data.get("runtime_projection") is not False:
            skills.append(data)
    return skills


def searchable_text(data: dict[str, Any], projection_name: str) -> str:
    values = [
        projection_name,
        data.get("id", ""),
        data.get("title", ""),
        data.get("layer", ""),
        data.get("source", ""),
        " ".join(str(item) for item in data.get("aliases") or []),
        " ".join(str(item) for item in data.get("domains") or []),
    ]
    return " ".join(values).lower().replace("_", "-")


def quality_disciplines(data: dict[str, Any], projection_name: str) -> list[str]:
    words = set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", searchable_text(data, projection_name)))
    out: list[str] = []
    if words & VERIFY_VALIDATE_TERMS:
        out.append("verify_validate")
    if words & AUDIT_ASSESS_TERMS:
        out.append("audit_assess_analyze")
    return out


def primary_category(data: dict[str, Any], projection_name: str, disciplines: list[str]) -> str:
    text = searchable_text(data, projection_name)
    domains = {str(item).lower() for item in data.get("domains") or []}
    skill_id = data.get("id", "")

    if "audit_assess_analyze" in disciplines:
        return "AUDIT_ASSESS_ANALYZE"
    if "verify_validate" in disciplines:
        return "VERIFY_VALIDATE"
    if "atlas" in text or skill_id == "SKILL_MCP_001":
        return "ATLAS"
    if "microsoft-foundry" in text or "foundry" in text:
        return "MICROSOFT_FOUNDRY"
    if "azure" in text or "azure" in domains:
        return "AZURE_CLOUD"
    if "elson" in text or "bot-status" in text:
        return "DOMAIN_ELSON"
    if "genos" in text or "xframe" in text or "kernel" in text or "qemu" in text:
        return "DOMAIN_GENOS"
    if "ipos" in text:
        return "DOMAIN_IPOS"
    if any(term in text for term in ("agent", "orchestrator", "coordinator", "dispatch")):
        return "AGENT_ORCHESTRATION"
    if any(term in text for term in ("data", "postgres", "kusto", "storage", "pipeline")):
        return "DATA_INFRASTRUCTURE"
    if any(term in text for term in ("ui", "ux", "frontend", "design", "react", "electron", "chrome")):
        return "FRONTEND_UI"
    if any(term in text for term in ("security", "auth", "rbac", "compliance", "governance")):
        return "SECURITY_GOVERNANCE"
    if any(term in text for term in ("deploy", "release", "preview", "ci-cd", "devops")):
        return "RELEASE_DEPLOY"
    if any(term in text for term in ("architecture", "platform", "service", "gateway", "tenant")):
        return "PLATFORM_ARCHITECTURE"
    if "skills" in domains or data.get("layer") == "meta":
        return "META_SKILLS"
    return "OTHER"


def relative(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def sync(dry_run: bool, refresh_existing: bool) -> tuple[list[SkillProjection], int, int]:
    UNIVERSAL_SKILLS.mkdir(parents=True, exist_ok=True)
    projections: list[SkillProjection] = []
    written = 0
    unchanged = 0
    used_names: set[str] = set()

    for data in collect_canonical_skills():
        projection_name = derive_projection_name(data, used_names)
        used_names.add(projection_name)
        playbook_body = read_playbook(data["id"])
        content = codex_universal_shim(data, projection_name, playbook_body)
        destination = UNIVERSAL_SKILLS / projection_name / "SKILL.md"
        exists_before = destination.exists()
        changed = not exists_before or (
            refresh_existing and destination.read_text(encoding="utf-8") != content
        )

        if changed:
            written += 1
            if not dry_run:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")
        else:
            unchanged += 1

        disciplines = quality_disciplines(data, projection_name)
        projections.append(
            SkillProjection(
                projection_name=projection_name,
                skill_id=data["id"],
                title=data.get("title") or data["id"],
                source=data.get("source", ""),
                category=primary_category(data, projection_name, disciplines),
                quality_disciplines=disciplines,
                domains=[str(item) for item in data.get("domains") or []],
                layer=str(data.get("layer", "")),
                tier=str(data.get("tier", "")),
                destination=relative(destination),
                exists_before=exists_before,
                changed=changed,
            )
        )

    catalog = render_catalog(projections)
    catalog_changed = not CATALOG_PATH.exists() or CATALOG_PATH.read_text(encoding="utf-8") != catalog
    if catalog_changed:
        written += 1
        if not dry_run:
            CATALOG_PATH.write_text(catalog, encoding="utf-8")
    else:
        unchanged += 1

    return projections, written, unchanged


def render_catalog(projections: list[SkillProjection]) -> str:
    by_category: dict[str, list[SkillProjection]] = defaultdict(list)
    for projection in sorted(projections, key=lambda item: item.projection_name.lower()):
        by_category[projection.category].append(projection)

    missing_before = [item for item in projections if not item.exists_before]
    changed = [item for item in projections if item.changed]
    lines = [
        "# Codex Universal Skill Catalog",
        "",
        f"Generated: {TODAY}",
        f"Canonical active skills: {len(projections)}",
        f"Missing before sync: {len(missing_before)}",
        f"Changed in last sync: {len(changed)}",
        "",
        "This catalog is generated from `platform/sdlc/13_skills/active/*.yaml`.",
        "Edit canonical skill YAML/playbook files, then rerun `infrastructure/scripts/skill_projection/sync_codex_universal_skills.py --apply`.",
        "",
        "Quality discipline categories:",
        "- VERIFY_VALIDATE: verification, validation, test, gate, compile, regression, and CI skills.",
        "- AUDIT_ASSESS_ANALYZE: audit, assessment, analysis, integrity, drift, compliance, security, and review skills.",
        "",
    ]

    for category in CATEGORY_ORDER:
        items = by_category.get(category, [])
        if not items:
            continue
        lines.extend([f"## {category}", ""])
        for item in items:
            discipline_text = ", ".join(item.quality_disciplines) if item.quality_disciplines else "none"
            domain_text = ", ".join(item.domains) if item.domains else "none"
            lines.append(
                f"- {item.projection_name} -> {item.skill_id} | tier={item.tier or 'n/a'} | layer={item.layer or 'n/a'} | domains={domain_text} | disciplines={discipline_text}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="preview without writing")
    parser.add_argument("--apply", action="store_true", help="write repo-local Codex universal skill projections")
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="rewrite existing universal skill shims from canonical playbooks",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("ERROR: specify --dry-run or --apply")
        return 2

    projections, written, unchanged = sync(
        dry_run=args.dry_run,
        refresh_existing=args.refresh_existing,
    )
    present_after = sum(1 for item in projections if item.exists_before or item.changed)
    payload = {
        "mode": "dry_run" if args.dry_run else "applied",
        "refresh_existing": args.refresh_existing,
        "canonical_active_projected": len(projections),
        "present_after": present_after,
        "missing_before": sum(1 for item in projections if not item.exists_before),
        "changed_or_new_files": written,
        "unchanged_files": unchanged,
        "categories": {
            category: sum(1 for item in projections if item.category == category)
            for category in CATEGORY_ORDER
            if any(item.category == category for item in projections)
        },
        "missing_projection_names": [
            item.projection_name for item in projections if not item.exists_before
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
