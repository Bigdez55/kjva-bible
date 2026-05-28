#!/usr/bin/env python3
"""Import local runtime-only skills into canonical repo skill playbooks.

The repo projects canonical skills out to runtimes, so generated Codex/Claude
runtime shims are not imported back. This script only imports local runtime
skills that are not already represented by an active canonical skill alias.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
ACTIVE_DIR = ROOT / "platform" / "sdlc" / "13_skills" / "active"
ROUTER_PATH = ROOT / "platform" / "systems" / "37_command_protocol" / "trigger_router.yaml"
ARCHIVE_ROOT = (
    ROOT
    / "platform"
    / "sdlc"
    / "16_knowledge"
    / "external_collateral"
    / f"local_runtime_skills_{dt.date.today().isoformat()}"
)

RUNTIME_ROOTS = [
    ("codex", Path.home() / ".codex" / "skills", "promoted_external"),
    ("agents", Path.home() / ".agents" / "skills", "promoted_external"),
    ("claude", Path.home() / ".claude" / "skills", "migrated_user"),
]

PROMOTED_BAND = (1000, 1999)
MIGRATED_USER_BAND = (500, 999)


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def concept_from_key(value: str) -> str:
    normalized = normalize_key(value)
    return normalized.upper().replace("-", "_")


def ascii_text(value: str) -> str:
    replacements = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2192": "->",
        "\u21d2": "=>",
        "\u2265": ">=",
        "\u2264": "<=",
        "\u00a0": " ",
    }
    for src, dst in replacements.items():
        value = value.replace(src, dst)
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    raw_frontmatter = text[4:end]
    body = text[end + 5 :].lstrip()
    try:
        data = yaml.safe_load(raw_frontmatter) or {}
        if isinstance(data, dict):
            return data, body
    except yaml.YAMLError:
        pass
    fallback: dict[str, Any] = {}
    for key in ("name", "description", "version", "layer"):
        match = re.search(rf"^{key}:\s*(.+)$", raw_frontmatter, re.MULTILINE)
        if match:
            fallback[key] = match.group(1).strip().strip('"').strip("'")
    return fallback, body


def is_generated_projection(text: str) -> bool:
    return "canonical_id:" in text and (
        "Runtime projection" in text or "Source of truth:" in text
    )


def active_alias_keys() -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for path in ACTIVE_DIR.glob("SKILL_*.yaml"):
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue
        values: list[Any] = [
            data.get("id"),
            data.get("name"),
            data.get("title"),
            *(data.get("aliases") or []),
        ]
        for value in values:
            if value:
                keys.setdefault(normalize_key(str(value)), set()).add(str(data.get("id")))
    return keys


def used_skill_numbers() -> set[int]:
    used: set[int] = set()
    for path in ACTIVE_DIR.glob("SKILL_*.yaml"):
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue
        skill_number = data.get("skill_number")
        if isinstance(skill_number, str) and skill_number.isdigit():
            skill_number = int(skill_number)
        if isinstance(skill_number, int):
            used.add(skill_number)
    return used


def allocate_number(used: set[int], source: str) -> int:
    start, end = MIGRATED_USER_BAND if source == "migrated_user" else PROMOTED_BAND
    for number in range(start, end + 1):
        if number not in used:
            used.add(number)
            return number
    raise RuntimeError(f"skill number band exhausted for source={source}")


def canonical_id_for(import_key: str, existing_ids: set[str]) -> str:
    base = f"SKILL_{concept_from_key(import_key)}"
    for suffix in range(1, 1000):
        candidate = f"{base}_{suffix:03d}"
        if candidate not in existing_ids:
            existing_ids.add(candidate)
            return candidate
    raise RuntimeError(f"could not allocate canonical id for {import_key}")


def derive_layer_domains(import_key: str, frontmatter: dict[str, Any]) -> tuple[str, list[str]]:
    layer = frontmatter.get("layer")
    domains = frontmatter.get("domains")
    if isinstance(domains, str):
        domains = [domains]
    if isinstance(layer, str) and isinstance(domains, list) and domains:
        return layer, [str(item) for item in domains]

    key = normalize_key(import_key)
    if key.startswith("azure") or key.startswith("entra") or key.startswith("appinsights"):
        return "integration", ["azure", "cloud", "operations"]
    if key.startswith("microsoft-foundry"):
        return "integration", ["microsoft_foundry", "azure_ai", "agent_platform"]
    if "apex" in key or "orchestrator" in key or "coordinator" in key or "agent" in key:
        return "agent_orchestration", ["agent_orchestration", "governance"]
    if "data" in key:
        return "data", ["data_infrastructure", "platform"]
    if any(token in key for token in ("design", "product", "ui", "theme")):
        return "application", ["ui_ux", "product"]
    if any(token in key for token in ("observability", "reliability", "resilience", "performance")):
        return "operations", ["observability", "reliability"]
    if any(token in key for token in ("security", "guardian", "vanguard")):
        return "security", ["security", "governance"]
    if any(token in key for token in ("gate", "compile", "build", "seal", "reproducible")):
        return "verification", ["verification", "release"]
    return "application", ["skills"]


def title_from(import_key: str, frontmatter: dict[str, Any]) -> str:
    raw = frontmatter.get("title") or frontmatter.get("name") or import_key
    title = str(raw).replace("-", " ").replace("/", " ").strip()
    return title[:140] if len(title) > 140 else title


def description_from(frontmatter: dict[str, Any], body: str) -> str:
    description = frontmatter.get("description")
    if description:
        return str(description).strip()
    for line in body.splitlines():
        cleaned = line.strip().strip("#").strip()
        if cleaned:
            return cleaned[:220]
    return ""


def rewrite_links(body: str, archive_rel_from_playbook: str) -> str:
    def replace(match: re.Match[str]) -> str:
        label = match.group(1)
        target = match.group(2)
        if re.match(r"^[a-z]+://", target) or target.startswith(("#", "/", "mailto:")):
            return match.group(0)
        if target.startswith("<") and target.endswith(">"):
            return match.group(0)
        return f"[{label}]({archive_rel_from_playbook}/{target})"

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace, body)


def runtime_skill_files(runtime: str, root: Path) -> list[tuple[str, Path]]:
    if not root.exists():
        return []
    files: list[tuple[str, Path]] = []
    for path in sorted(root.glob("**/SKILL.md")):
        relative_parent = path.parent.relative_to(root).as_posix()
        if runtime == "codex" and relative_parent.startswith(".system/"):
            continue
        files.append((relative_parent, path))
    return files


def collect_imports() -> tuple[list[dict[str, Any]], dict[str, int]]:
    aliases = active_alias_keys()
    imports: list[dict[str, Any]] = []
    stats = {"scanned": 0, "projection_skip": 0, "duplicate_skip": 0, "missing": 0}

    for runtime, root, source in RUNTIME_ROOTS:
        for relative_parent, skill_path in runtime_skill_files(runtime, root):
            stats["scanned"] += 1
            text = skill_path.read_text(errors="ignore")
            if is_generated_projection(text):
                stats["projection_skip"] += 1
                continue
            import_key = relative_parent if "/" in relative_parent else skill_path.parent.name
            key = normalize_key(import_key)
            if key in aliases:
                stats["duplicate_skip"] += 1
                continue
            frontmatter, body = parse_frontmatter(text)
            imports.append(
                {
                    "runtime": runtime,
                    "root": root,
                    "relative_parent": relative_parent,
                    "skill_dir": skill_path.parent,
                    "skill_path": skill_path,
                    "import_key": import_key,
                    "source": source,
                    "frontmatter": frontmatter,
                    "body": body,
                }
            )
            aliases.setdefault(key, set()).add(import_key)
            stats["missing"] += 1
    return imports, stats


def write_import(item: dict[str, Any], used_numbers: set[int], existing_ids: set[str]) -> list[Path]:
    runtime = item["runtime"]
    source = item["source"]
    import_key = item["import_key"]
    frontmatter = item["frontmatter"]
    body = ascii_text(item["body"])
    description = ascii_text(description_from(frontmatter, body))
    canonical_id = canonical_id_for(import_key, existing_ids)
    skill_number = allocate_number(used_numbers, source)
    layer, domains = derive_layer_domains(import_key, frontmatter)
    title = ascii_text(title_from(import_key, frontmatter))
    alias = normalize_key(import_key)

    archive_dir = ARCHIVE_ROOT / runtime / alias
    if archive_dir.exists():
        raise FileExistsError(f"archive already exists: {archive_dir.relative_to(ROOT)}")
    archive_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(item["skill_dir"], archive_dir)

    yaml_path = ACTIVE_DIR / f"{canonical_id}.yaml"
    playbook_path = ACTIVE_DIR / f"{canonical_id}.playbook.md"
    archive_rel = archive_dir.relative_to(ROOT).as_posix()
    archive_rel_from_playbook = f"../../16_knowledge/external_collateral/{ARCHIVE_ROOT.name}/{runtime}/{alias}"

    yaml_data = {
        "id": canonical_id,
        "title": title,
        "version": str(frontmatter.get("version") or "1.0.0"),
        "layer": layer,
        "domains": domains,
        "tier": "starter",
        "status": "active",
        "source": source,
        "aliases": [alias],
        "playbook": f"platform/sdlc/13_skills/active/{canonical_id}.playbook.md",
        "runtime_projection": True,
        "runtime_projection_targets": ["claude", "codex", "gemini"],
        "refinement": "auto",
        "skill_number": skill_number,
        "provenance": {
            "imported_from_runtime": runtime,
            "original_skill_path": str(item["skill_path"]),
            "source_archive": archive_rel,
            "imported_on": dt.date.today().isoformat(),
            "import_script": "infrastructure/scripts/skill_migration/import_local_runtime_skills.py",
        },
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

    rewritten_body = rewrite_links(body, archive_rel_from_playbook).rstrip()
    header = "\n".join(
        [
            f"# {title}",
            "",
            f"<!-- Imported from {item['skill_path']} on {dt.date.today().isoformat()}. -->",
            f"<!-- Full source directory archived at {archive_rel}. -->",
            f"<!-- Runtime alias: {alias}; canonical id: {canonical_id}. -->",
            "",
        ]
    )
    if description:
        header += f"**Summary.** {description}\n\n"
    header += (
        "Relative links from the source skill body were rewritten to the archived "
        "source directory when possible.\n\n"
    )

    yaml_path.write_text(yaml.safe_dump(yaml_data, sort_keys=False), encoding="utf-8")
    playbook_path.write_text(header + rewritten_body + "\n", encoding="utf-8")
    return [yaml_path, playbook_path, archive_dir]


def sync_router_entries() -> int:
    router = yaml.safe_load(ROUTER_PATH.read_text()) or {}
    section = router.setdefault(
        "local_runtime_skills",
        {
            "description": (
                "Local runtime skills imported into canonical repo form. "
                "Generated by infrastructure/scripts/skill_migration/"
                "import_local_runtime_skills.py."
            ),
            "entries": [],
        },
    )
    entries = section.setdefault("entries", [])
    existing = {str(item.get("skill_id")) for item in entries if isinstance(item, dict)}
    added = 0
    for path in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        data = yaml.safe_load(path.read_text()) or {}
        provenance = data.get("provenance") or {}
        if (
            provenance.get("import_script")
            != "infrastructure/scripts/skill_migration/import_local_runtime_skills.py"
        ):
            continue
        skill_id = data.get("id")
        aliases = data.get("aliases") or []
        alias = aliases[0] if aliases else normalize_key(str(skill_id))
        if skill_id in existing:
            continue
        entries.append(
            {
                "skill_id": skill_id,
                "alias": alias,
                "source": provenance.get("imported_from_runtime"),
                "phrases": [f"/{alias}", str(alias).replace("-", " ")],
            }
        )
        existing.add(str(skill_id))
        added += 1
    entries.sort(key=lambda item: item.get("skill_id", ""))
    ROUTER_PATH.write_text(yaml.safe_dump(router, sort_keys=False), encoding="utf-8")
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        print("ERROR: specify --dry-run or --apply", file=sys.stderr)
        return 2

    imports, stats = collect_imports()
    print(
        "scan: "
        f"{stats['scanned']} files, "
        f"{stats['projection_skip']} generated projections skipped, "
        f"{stats['duplicate_skip']} alias duplicates skipped, "
        f"{stats['missing']} imports pending"
    )
    for item in imports:
        print(f"  IMPORT {item['runtime']}:{item['relative_parent']} -> {normalize_key(item['import_key'])}")

    if args.dry_run:
        return 0

    used_numbers = used_skill_numbers()
    existing_ids = {path.stem for path in ACTIVE_DIR.glob("SKILL_*.yaml")}
    written: list[Path] = []
    for item in imports:
        written.extend(write_import(item, used_numbers, existing_ids))
    router_added = sync_router_entries()
    print(f"written imports: {len(imports)}")
    print(f"router entries added: {router_added}")
    for path in written:
        print(f"  {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
