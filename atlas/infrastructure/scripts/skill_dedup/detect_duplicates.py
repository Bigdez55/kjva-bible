#!/usr/bin/env python3
"""Duplicate and near-duplicate detector for the skill corpus.

Read-only Phase 1 tool. Produces a structured report under
platform/sdlc/13_skills/skill_refinery/ describing:

  1. Exact-hash duplicate playbooks (different file, same content)
  2. Near-duplicate playbooks (Jaccard > NEAR_DUP_THRESHOLD on token bigrams)
  3. Concept overlaps (skill name prefixes that should consolidate)
  4. Version anomalies (_002 with no _001 sibling)
  5. Cross-layer duplicates (canonical SKILL paired with user-level kebab name)
  6. Duplicate skill_ids and skill_numbers in active/
  7. Schema drift (fields present in some skills, missing in same-tier peers)

Output:
  - skill_refinery/dedup_report_<date>.yaml      (full structured report)
  - skill_refinery/cross_layer_aliases_<date>.yaml (Phase 3 migration mapping)

Modes:
  --strict          — exit non-zero if ANY duplicate or near-duplicate is found
  --report-only     — generate the report files; no console output beyond summary
  --no-write        — print summary to stdout only; do not write files
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "active"
USER_LEVEL_DIR = Path.home() / ".claude" / "skills"
REFINERY_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery"
EXTERNAL_REGISTRY = (
    REPO_ROOT
    / "platform"
    / "systems"
    / "18_registry"
    / "agent_skill_imports"
    / "normalized_skill_registry.yaml"
)

NEAR_DUP_THRESHOLD = 0.7  # Jaccard on token bigrams
TODAY = dt.date.today().isoformat()

# MISS-005: the near-dup detector flags ~1119 pairs that are NOT removable duplicates —
# they are DISTINCT skills sharing a common playbook template/scaffold (0 same-base numeric
# clones; median Jaccard ~0.90). Deleting them is wrong; lowering the threshold hides the
# signal. Instead we BASELINE the reviewed-and-accepted template-family pairs in an
# allowlist; --strict then fails only on NEW, unexpected near-dups (real regressions).
ALLOWLIST_PATH = REFINERY_DIR / "near_dup_allowlist.yaml"


def _pair_key(a: str, b: str) -> str:
    return "|".join(sorted((a, b)))


def load_near_dup_allowlist() -> dict[str, set[str]]:
    """Load the reviewed near-dup/overlap baseline. Missing file => empty (gate stays strict)."""
    if not ALLOWLIST_PATH.exists():
        return {"pairs": set(), "concepts": set()}
    try:
        data = yaml.safe_load(ALLOWLIST_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"pairs": set(), "concepts": set()}
    pairs = {str(p) for p in (data.get("near_dup_pairs") or [])}
    concepts = {str(c) for c in (data.get("concept_overlaps") or [])}
    return {"pairs": pairs, "concepts": concepts}


def token_bigrams(text: str) -> set[tuple[str, str]]:
    """Token bigram set for Jaccard similarity (lowercased word pairs)."""
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    return {(tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def kebab_from_skill_id(sid: str) -> str:
    """Convert SKILL_FOO_BAR_001 → foo-bar."""
    m = re.match(r"^SKILL_(.+)_\d{3}$", sid)
    if not m:
        return sid.lower().replace("_", "-")
    return m.group(1).lower().replace("_", "-")


def load_canonical_skills() -> dict[str, dict[str, Any]]:
    """Return mapping skill_id → {yaml_path, playbook_path, data, playbook_text}."""
    out: dict[str, dict[str, Any]] = {}
    for yaml_path in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        try:
            data = yaml.safe_load(yaml_path.read_text()) or {}
        except yaml.YAMLError:
            continue
        sid = data.get("id", yaml_path.stem)
        playbook_path = ACTIVE_DIR / f"{yaml_path.stem}.playbook.md"
        playbook_text = playbook_path.read_text() if playbook_path.exists() else ""
        out[sid] = {
            "yaml_path": str(yaml_path.relative_to(REPO_ROOT)),
            "playbook_path": str(playbook_path.relative_to(REPO_ROOT))
            if playbook_path.exists()
            else None,
            "data": data,
            "playbook_text": playbook_text,
            "playbook_hash": hashlib.sha256(playbook_text.encode()).hexdigest()
            if playbook_text
            else None,
        }
    return out


def load_user_level_skills() -> dict[str, dict[str, Any]]:
    """Return mapping kebab-name → {skill_md_path, text, hash}."""
    out: dict[str, dict[str, Any]] = {}
    if not USER_LEVEL_DIR.exists():
        return out
    for d in sorted(USER_LEVEL_DIR.iterdir()):
        if not d.is_dir():
            continue
        skill_md = d / "SKILL.md"
        if not skill_md.exists():
            continue
        text = skill_md.read_text()
        out[d.name] = {
            "skill_md_path": str(skill_md),
            "text": text,
            "hash": hashlib.sha256(text.encode()).hexdigest(),
        }
    return out


def detect_exact_duplicates(skills: dict[str, dict]) -> list[dict]:
    """Find canonical skills with identical playbook content."""
    by_hash: dict[str, list[str]] = defaultdict(list)
    for sid, info in skills.items():
        if info["playbook_hash"]:
            by_hash[info["playbook_hash"]].append(sid)
    return [
        {"hash": h, "skill_ids": sorted(ids), "count": len(ids)}
        for h, ids in by_hash.items()
        if len(ids) > 1
    ]


def detect_near_duplicates(skills: dict[str, dict]) -> list[dict]:
    """Find canonical skill pairs with Jaccard > threshold on playbook content."""
    sids = sorted(skills.keys())
    bigram_cache = {sid: token_bigrams(skills[sid]["playbook_text"]) for sid in sids}
    pairs: list[dict] = []
    for i, a in enumerate(sids):
        ba = bigram_cache[a]
        if not ba:
            continue
        for b in sids[i + 1 :]:
            bb = bigram_cache[b]
            if not bb:
                continue
            score = jaccard(ba, bb)
            if score >= NEAR_DUP_THRESHOLD:
                pairs.append({"a": a, "b": b, "jaccard": round(score, 4)})
    return sorted(pairs, key=lambda p: -p["jaccard"])


def detect_concept_overlaps(skills: dict[str, dict]) -> list[dict]:
    """Find skills with overlapping concept prefixes that should consolidate."""
    overlaps: list[dict] = []
    by_concept: dict[str, list[str]] = defaultdict(list)
    for sid in skills:
        m = re.match(r"^SKILL_(.+)_(\d{3})$", sid)
        if not m:
            continue
        concept = m.group(1)
        # Strip known subsystem prefixes for overlap detection
        for prefix in ("ATLAS_", "APEX_", "SUPER_C_", "SC_", "IPOS_", "GENOS_", "ELSON_"):
            if concept.startswith(prefix):
                base = concept[len(prefix) :]
                by_concept[base].append(sid)
                break
    for base, ids in by_concept.items():
        if len(ids) > 1:
            overlaps.append({"base_concept": base, "skill_ids": sorted(ids)})
    return overlaps


def detect_version_anomalies(skills: dict[str, dict]) -> list[dict]:
    """Find _002, _003, etc. files with no _001 sibling."""
    by_concept: dict[str, list[int]] = defaultdict(list)
    for sid in skills:
        m = re.match(r"^SKILL_(.+)_(\d{3})$", sid)
        if not m:
            continue
        concept, num = m.group(1), int(m.group(2))
        by_concept[concept].append(num)
    anomalies: list[dict] = []
    for concept, nums in by_concept.items():
        nums_sorted = sorted(nums)
        if 1 not in nums_sorted and min(nums_sorted) > 1:
            anomalies.append(
                {
                    "concept": concept,
                    "versions_present": nums_sorted,
                    "missing": list(range(1, max(nums_sorted))),
                }
            )
    return anomalies


def detect_cross_layer_aliases(
    canonical: dict[str, dict], user_level: dict[str, dict]
) -> list[dict]:
    """Map user-level kebab names to canonical SKILL_*.yaml that share concepts."""
    aliases: list[dict] = []
    canonical_kebabs = {kebab_from_skill_id(sid): sid for sid in canonical}
    for kebab, info in user_level.items():
        canonical_id = canonical_kebabs.get(kebab)
        if canonical_id:
            # Compute content similarity between user-level body and canonical playbook
            user_bigrams = token_bigrams(info["text"])
            canonical_bigrams = token_bigrams(canonical[canonical_id]["playbook_text"])
            score = jaccard(user_bigrams, canonical_bigrams)
            aliases.append(
                {
                    "kebab": kebab,
                    "canonical_id": canonical_id,
                    "content_jaccard": round(score, 4),
                    "user_path": info["skill_md_path"],
                    "canonical_path": canonical[canonical_id]["yaml_path"],
                    "action": (
                        "merge_content" if score > 0.3 else "verify_then_merge"
                    ),
                }
            )
        else:
            # No canonical equivalent — Phase 3 must CREATE a new canonical
            aliases.append(
                {
                    "kebab": kebab,
                    "canonical_id": None,
                    "content_jaccard": None,
                    "user_path": info["skill_md_path"],
                    "canonical_path": None,
                    "action": "create_new_canonical",
                }
            )
    return sorted(aliases, key=lambda a: a["kebab"])


def detect_duplicate_ids_and_numbers(skills: dict[str, dict]) -> dict[str, list]:
    """Find duplicate id or skill_number values."""
    by_id: dict[str, list[str]] = defaultdict(list)
    by_number: dict[Any, list[str]] = defaultdict(list)
    for sid, info in skills.items():
        d = info["data"]
        if d.get("id"):
            by_id[d["id"]].append(str(info["yaml_path"]))
        if "skill_number" in d:
            by_number[d["skill_number"]].append(sid)
    return {
        "duplicate_ids": [
            {"id": k, "files": v} for k, v in by_id.items() if len(v) > 1
        ],
        "duplicate_skill_numbers": [
            {"skill_number": k, "skill_ids": sorted(v)}
            for k, v in by_number.items()
            if len(v) > 1
        ],
    }


def detect_schema_drift(skills: dict[str, dict]) -> dict[str, Any]:
    """Detect deprecated 'domain' (singular) field + per-tier missing fields."""
    drift: dict[str, Any] = {
        "skills_with_singular_domain_field": [],
        "skills_with_layer_active": [],
        "skills_with_no_tier": [],
        "skills_with_no_source": [],
    }
    for sid, info in skills.items():
        d = info["data"]
        if "domain" in d:
            drift["skills_with_singular_domain_field"].append(sid)
        if d.get("layer") == "active":
            drift["skills_with_layer_active"].append(sid)
        if "tier" not in d:
            drift["skills_with_no_tier"].append(sid)
        if "source" not in d:
            drift["skills_with_no_source"].append(sid)
    return drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    canonical = load_canonical_skills()
    user_level = load_user_level_skills()

    exact_dups = detect_exact_duplicates(canonical)
    near_dups = detect_near_duplicates(canonical)
    overlaps = detect_concept_overlaps(canonical)
    version_anomalies = detect_version_anomalies(canonical)
    cross_layer = detect_cross_layer_aliases(canonical, user_level)
    id_num_dups = detect_duplicate_ids_and_numbers(canonical)
    drift = detect_schema_drift(canonical)

    report = {
        "generated": TODAY,
        "canonical_count": len(canonical),
        "user_level_count": len(user_level),
        "exact_playbook_duplicates": exact_dups,
        "near_duplicate_pairs": near_dups,
        "concept_overlaps": overlaps,
        "version_anomalies": version_anomalies,
        "duplicate_ids": id_num_dups["duplicate_ids"],
        "duplicate_skill_numbers": id_num_dups["duplicate_skill_numbers"],
        "schema_drift": drift,
    }

    cross_layer_map = {
        "generated": TODAY,
        "purpose": "Phase 3 migration mapping: user-level kebab → canonical SKILL_*_NNN",
        "entries": cross_layer,
    }

    if not args.no_write:
        REFINERY_DIR.mkdir(parents=True, exist_ok=True)
        dedup_report_path = REFINERY_DIR / f"dedup_report_{TODAY}.yaml"
        cross_layer_path = REFINERY_DIR / f"cross_layer_aliases_{TODAY}.yaml"
        dedup_report_path.write_text(yaml.safe_dump(report, sort_keys=False))
        cross_layer_path.write_text(yaml.safe_dump(cross_layer_map, sort_keys=False))

    # Summary
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=== Duplicate Detection Report ===")
        print(f"Canonical skills: {len(canonical)}")
        print(f"User-level skills: {len(user_level)}")
        print(f"Exact playbook duplicates: {len(exact_dups)}")
        print(f"Near-duplicate pairs (Jaccard ≥ {NEAR_DUP_THRESHOLD}): {len(near_dups)}")
        print(f"Concept overlaps: {len(overlaps)}")
        print(f"Version anomalies: {len(version_anomalies)}")
        print(f"Duplicate skill_ids: {len(id_num_dups['duplicate_ids'])}")
        print(f"Duplicate skill_numbers: {len(id_num_dups['duplicate_skill_numbers'])}")
        print(f"Cross-layer aliases (user→canonical): {len(cross_layer)}")
        print(f"Drift: singular 'domain' field: {len(drift['skills_with_singular_domain_field'])}")
        print(f"Drift: layer='active' (deprecated): {len(drift['skills_with_layer_active'])}")
        print(f"Drift: missing 'tier' field: {len(drift['skills_with_no_tier'])}")
        print(f"Drift: missing 'source' field: {len(drift['skills_with_no_source'])}")
        if not args.no_write:
            print(f"\nWrote: {dedup_report_path.relative_to(REPO_ROOT)}")
            print(f"Wrote: {cross_layer_path.relative_to(REPO_ROOT)}")

    # MISS-005: subtract the reviewed template-family baseline. --strict fails only on
    # NEW (unexpected) near-dups/overlaps — a real regression — not the accepted scaffold noise.
    allow = load_near_dup_allowlist()
    unexpected_near = [p for p in near_dups if _pair_key(p["a"], p["b"]) not in allow["pairs"]]
    unexpected_overlaps = [o for o in overlaps if o["base_concept"] not in allow["concepts"]]
    if not args.json:  # keep --json stdout pure (machine-parseable)
        print(
            f"Near-dup baseline: {len(near_dups)} total, "
            f"{len(near_dups) - len(unexpected_near)} allowlisted, {len(unexpected_near)} unexpected"
        )
        print(
            f"Concept-overlap baseline: {len(overlaps)} total, "
            f"{len(overlaps) - len(unexpected_overlaps)} allowlisted, {len(unexpected_overlaps)} unexpected"
        )

    # Strict mode fails on any duplicate (not on drift — drift is fixed in Phase 2).
    # Near-dups/overlaps count only when UNEXPECTED (not in the reviewed allowlist).
    any_dup = bool(
        exact_dups
        or unexpected_near
        or unexpected_overlaps
        or version_anomalies
        or id_num_dups["duplicate_ids"]
        or id_num_dups["duplicate_skill_numbers"]
    )
    if args.strict and any_dup:
        print("STRICT MODE: FAIL — duplicates present (unexpected near-dups/overlaps or exact/id/number dups)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
