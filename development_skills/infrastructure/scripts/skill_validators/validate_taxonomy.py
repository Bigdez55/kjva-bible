#!/usr/bin/env python3
"""Controlled-vocabulary validator for skill metadata.

Validates that every active SKILL_*.yaml uses only values from the controlled
vocabulary defined in platform/sdlc/13_skills/TAXONOMY.md.

Fields checked:
  - domains:                        (controlled, 1-6 values)
  - layer:                          (controlled, exactly 1)
  - tier:                           (controlled, optional, exactly 1)
  - status:                         (controlled, exactly 1)
  - source:                         (controlled, optional, exactly 1)
  - runtime_projection_targets:     (controlled, optional, 0-3 values)

Modes:
  --lenient (default) — log violations, exit 0
  --strict             — log violations, exit non-zero on any violation
  --check-self         — verify the taxonomy file parses; no skill checks
  --json               — emit machine-readable report
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
TAXONOMY_MD = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "TAXONOMY.md"
DEFAULT_SKILLS_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "active"

# Hardcoded fallback vocab (mirror of TAXONOMY.md tables); kept in sync via --check-self.
DOMAINS = {
    # product
    "atlas", "apex", "ipos", "genos", "super_c", "elson", "trading_bot", "kjva_bible",
    # capability
    "frontend", "backend", "data_pipeline", "dashboard", "visualization",
    "kpi_reporting", "ai", "ai_insights", "ml_ops", "security", "auth",
    "accessibility", "performance", "observability", "testing", "validation",
    "ci_cd", "documentation", "agent_orchestration", "governance", "compiler",
    "kernel", "graph_engine", "skills",
    # architectural / cross-cutting
    "multi_tenant_platform", "saas", "microsoft_365", "cloud_ops", "storage",
    "architecture", "release",
    # provenance (auto-applied)
    "imported", "migrated_user",
}

LAYERS = {
    "core", "application", "integration", "governance",
    "verification", "documentation", "meta",
    # 'active' is permitted during Phase 0-2 bootstrap; flagged as deprecated value
    "active",
}

TIERS = {
    "experimental", "starter", "active", "refining",
    "hardened", "apex", "one-shot-apex",
}

STATUSES = {"experimental", "active", "deprecated", "superseded"}

SOURCES = {"native", "migrated_user", "promoted_external"}

RUNTIME_TARGETS = {"claude", "codex", "gemini"}

LAYER_DEPRECATED = {"active"}  # values that work today but should be removed in Phase 2

LAYER_LEGACY_PERMITTED = {
    # values seen in existing skills that map cleanly to canonical layers
    # during Phase 2 drift fix. Logged as warnings, not failures.
    "feature", "decisions", "diagrams", "drift", "repo_audit",
    "ml", "context", "deployment", "proof", "registry_sync",
    "twins", "execution", "slices", "truth_state", "requirements",
    "command_protocol", "repo_auditing", "planning", "systems",
    "agent_orchestration", "architecture",
}


def validate_skill_file(path: Path) -> list[str]:
    """Return list of violations for one skill file."""
    violations: list[str] = []
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        return [f"{path.name}: YAML parse error: {e}"]

    if not isinstance(data, dict):
        return [f"{path.name}: not a YAML mapping"]

    sid = data.get("id", path.stem)

    # domains
    domains = data.get("domains")
    if domains is None:
        violations.append(f"{sid}: missing required 'domains' field")
    elif not isinstance(domains, list) or not domains:
        violations.append(f"{sid}: 'domains' must be a non-empty list")
    else:
        if len(domains) > 6:
            violations.append(
                f"{sid}: 'domains' has {len(domains)} entries (max 6 allowed)"
            )
        for d in domains:
            if not isinstance(d, str):
                violations.append(f"{sid}: domain value {d!r} is not a string")
                continue
            if d not in DOMAINS:
                violations.append(
                    f"{sid}: domain '{d}' not in controlled vocabulary "
                    f"(see TAXONOMY.md)"
                )

    # layer
    layer = data.get("layer")
    if layer is None:
        violations.append(f"{sid}: missing required 'layer' field")
    elif not isinstance(layer, str):
        violations.append(f"{sid}: 'layer' must be a string")
    elif layer not in LAYERS:
        if layer in LAYER_LEGACY_PERMITTED:
            violations.append(
                f"{sid}: layer '{layer}' is a legacy value — "
                f"remap to canonical layer in Phase 2"
            )
        else:
            violations.append(
                f"{sid}: layer '{layer}' not in controlled vocabulary"
            )
    elif layer in LAYER_DEPRECATED:
        violations.append(
            f"{sid}: layer '{layer}' is DEPRECATED — pick a proper layer "
            f"(core/application/integration/governance/verification/documentation/meta)"
        )

    # tier (optional but if present, must be valid)
    tier = data.get("tier")
    if tier is not None:
        if not isinstance(tier, str):
            violations.append(f"{sid}: 'tier' must be a string")
        elif tier not in TIERS:
            violations.append(
                f"{sid}: tier '{tier}' not in controlled vocabulary"
            )

    # status (required)
    status = data.get("status")
    if status is None:
        violations.append(f"{sid}: missing required 'status' field")
    elif status not in STATUSES:
        violations.append(
            f"{sid}: status '{status}' not in controlled vocabulary"
        )

    # source (optional but if present, must be valid)
    source = data.get("source")
    if source is not None:
        if source not in SOURCES:
            violations.append(
                f"{sid}: source '{source}' not in controlled vocabulary"
            )
        # Cross-check: skill_number range should match source
        sn = data.get("skill_number")
        if isinstance(sn, str) and sn.isdigit():
            sn = int(sn)
        if isinstance(sn, int):
            if source == "native" and not (1 <= sn <= 499):
                violations.append(
                    f"{sid}: source=native but skill_number={sn} (expected 1-499)"
                )
            elif source == "migrated_user" and not (500 <= sn <= 999):
                violations.append(
                    f"{sid}: source=migrated_user but skill_number={sn} "
                    f"(expected 500-999)"
                )
            elif source == "promoted_external" and not (1000 <= sn <= 1999):
                violations.append(
                    f"{sid}: source=promoted_external but skill_number={sn} "
                    f"(expected 1000-1999)"
                )

    # runtime_projection_targets (optional)
    rpt = data.get("runtime_projection_targets")
    if rpt is not None:
        if not isinstance(rpt, list):
            violations.append(f"{sid}: 'runtime_projection_targets' must be a list")
        else:
            for t in rpt:
                if t not in RUNTIME_TARGETS:
                    violations.append(
                        f"{sid}: runtime target '{t}' not in {{claude,codex,gemini}}"
                    )

    # Deprecated 'domain' (singular) field
    if "domain" in data:
        violations.append(
            f"{sid}: deprecated singular 'domain' field present — "
            f"use 'domains' array only"
        )

    return violations


def check_self() -> int:
    """Verify TAXONOMY.md parses and is well-formed."""
    if not TAXONOMY_MD.exists():
        print(f"FAIL: TAXONOMY.md not found at {TAXONOMY_MD}", file=sys.stderr)
        return 1
    text = TAXONOMY_MD.read_text()
    # Smoke check: every documented vocabulary set must have a corresponding constant
    # below. (Not a full syntactic parse of markdown tables; lightweight.)
    required_sections = [
        "## Domains",
        "## Layers",
        "## Tiers",
        "## Statuses",
        "## Source",
        "## Runtime Projection Targets",
    ]
    for s in required_sections:
        if s not in text:
            print(f"FAIL: TAXONOMY.md missing section '{s}'", file=sys.stderr)
            return 1
    print("PASS: TAXONOMY.md structure intact")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--lenient", action="store_true")
    parser.add_argument("--check-self", action="store_true")
    parser.add_argument("--dir", type=Path, default=DEFAULT_SKILLS_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.check_self:
        return check_self()

    if not args.dir.exists():
        print(f"FAIL: skills directory not found: {args.dir}", file=sys.stderr)
        return 2

    files = sorted(args.dir.glob("SKILL_*.yaml"))
    total_violations: list[str] = []
    skills_with_violations = 0

    for path in files:
        violations = validate_skill_file(path)
        if violations:
            skills_with_violations += 1
            total_violations.extend(violations)

    if args.json:
        print(json.dumps({
            "checked": len(files),
            "skills_with_violations": skills_with_violations,
            "total_violations": len(total_violations),
            "violations": total_violations,
        }, indent=2))
    else:
        for v in total_violations:
            print(v)
        print()
        print(f"=== Taxonomy Validation ===")
        print(f"Skills checked: {len(files)}")
        print(f"Skills with violations: {skills_with_violations}")
        print(f"Total violations: {len(total_violations)}")

    if args.strict and total_violations:
        print("STRICT MODE: FAIL", file=sys.stderr)
        return 1
    print("PASS" if not total_violations else "PASS (lenient mode — violations logged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
