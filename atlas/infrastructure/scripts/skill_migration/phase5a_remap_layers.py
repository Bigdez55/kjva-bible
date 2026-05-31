#!/usr/bin/env python3
"""Phase 5a — remap `layer: active` (deprecated) to canonical layers.

Derives the proper canonical layer for each skill from its `domains:` array.
Mapping rules (most-specific wins, first match):

  domains contain kernel/genos/super_c/compiler   -> core
  domains contain testing/validation/security     -> verification
  domains contain documentation                   -> documentation
  domains contain ci_cd/release/cloud_ops         -> integration
  domains contain governance/agent_orchestration  -> governance
  domains contain skills (sole or primary)        -> meta
  domains contain frontend/dashboard/ipos/        -> application
                  visualization/kpi_reporting
  domains contain ai/ai_insights/ml_ops/oracle    -> integration
  fallback                                        -> application

Modes:
  --dry-run   Show what would change
  --apply     Apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "active"


def derive_layer(domains: list[str]) -> str:
    ds = set(domains or [])

    if ds & {"kernel", "genos", "super_c", "compiler"}:
        return "core"
    if ds & {"testing", "validation"}:
        return "verification"
    # security is verification if alone, integration if with auth
    if "security" in ds and not (ds & {"auth"}):
        return "verification"
    if "documentation" in ds:
        return "documentation"
    if ds & {"ci_cd", "release", "cloud_ops"}:
        return "integration"
    if ds & {"governance", "agent_orchestration"}:
        return "governance"
    # meta only if skills is the dominant signal (first or alone)
    if "skills" in ds and len(ds) <= 2:
        return "meta"
    if ds & {"ai", "ai_insights", "ml_ops"}:
        return "integration"
    if ds & {"auth", "security"}:
        return "integration"
    if ds & {
        "frontend",
        "dashboard",
        "ipos",
        "visualization",
        "kpi_reporting",
        "accessibility",
        "performance",
    }:
        return "application"
    return "application"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        print("ERROR: specify --dry-run or --apply", file=sys.stderr)
        return 2

    changed = 0
    skipped = 0
    layer_distribution: dict[str, int] = {}

    for path in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        d = yaml.safe_load(path.read_text()) or {}
        layer = d.get("layer")
        if layer != "active":
            skipped += 1
            continue
        new_layer = derive_layer(d.get("domains") or [])
        d["layer"] = new_layer
        layer_distribution[new_layer] = layer_distribution.get(new_layer, 0) + 1
        if not args.dry_run:
            path.write_text(yaml.safe_dump(d, sort_keys=False))
        changed += 1

    print(f"=== Phase 5a Layer Remap ({'DRY RUN' if args.dry_run else 'APPLIED'}) ===")
    print(f"Skills checked:          {changed + skipped}")
    print(f"Skills with layer:active: {changed}")
    print(f"Other layers (skipped):  {skipped}")
    print()
    print("New layer distribution among remapped:")
    for layer in sorted(layer_distribution):
        print(f"  {layer:15s}  {layer_distribution[layer]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
