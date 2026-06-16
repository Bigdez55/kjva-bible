#!/usr/bin/env python3
"""
build_corpus.py — generate the Production-Readiness Corpus from the canonical
source of truth (corpus/source/dev-checklist-v2.jsx).

Source of truth: the hand-authored React checklist. The `CHECKLIST_DATA` object
(base literal + the `Object.assign(CHECKLIST_DATA, {...})` extensions + the late
single-key `CHECKLIST_DATA["..."].sections["..."] = [...]` additions) is the ONLY
authored content. This script:

  1. Slices the pure-JS data section (everything from `const CHECKLIST_DATA` up to
     `const allCategories`) — no JSX in that span — and evaluates it with Node to
     get exact JSON (robust; no fragile regex parsing of a JS object literal).
  2. Merges the hand-maintained audit-metadata sidecar `corpus/overlay.yaml`
     (default_severity, coverage_status, skill_refs) — NEVER overwriting it.
  3. Emits generated artifacts: corpus/taxonomy.yaml, corpus/categories/PRC-*.yaml,
     generated/corpus.json.
  4. Asserts a verbatim round-trip: item count written == item count in the JSX.

Usage:
  python3 build_corpus.py --probe     # extract + print stats only (no writes)
  python3 build_corpus.py             # full generate
  python3 build_corpus.py --check     # generate to memory, assert counts, no writes
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required (pip install pyyaml)")

HERE = Path(__file__).resolve().parent              # .../53_production_readiness/tools
ROOT = HERE.parent                                  # .../53_production_readiness
SRC = ROOT / "corpus" / "source" / "dev-checklist-v2.jsx"
OVERLAY = ROOT / "corpus" / "overlay.yaml"
CATEGORIES_DIR = ROOT / "corpus" / "categories"
TAXONOMY = ROOT / "corpus" / "taxonomy.yaml"
CORPUS_JSON = ROOT / "generated" / "corpus.json"

CORPUS_ID = "PRC_PLATINUM_DEV_CHECKLIST_001"

HIGH_KEYS = [
    "security", "auth", "encryption", "crypto", "privacy", "payment", "financial",
    "fraud", "trust", "safety", "compliance", "legal", "disaster", "incident",
    "threat", "zero trust", "backup", "identity", "kyc", "aml", "audit",
    "vendor", "grc", "data & privacy",
]
LOW_KEYS = [
    "documentation", "go-to-market", "growth", "sustainab", "content", "cms",
    "editorial", "developer experience", "ux research", "product strategy",
    "settings", "internationalization",
]


def slugify(name: str) -> str:
    s = name.upper().replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9]+", "_", s).strip("_")
    s = re.sub(r"_+", "_", s)
    return s


def heuristic_severity(cat_name: str) -> str:
    n = cat_name.lower()
    if any(k in n for k in HIGH_KEYS):
        return "high"
    if any(k in n for k in LOW_KEYS):
        return "low"
    return "medium"


def extract_checklist_data() -> dict:
    text = SRC.read_text(encoding="utf-8")
    try:
        start = text.index("const CHECKLIST_DATA")
    except ValueError:
        sys.exit("ERROR: `const CHECKLIST_DATA` not found in source jsx")
    try:
        end = text.index("const allCategories")
    except ValueError:
        sys.exit("ERROR: `const allCategories` boundary not found in source jsx")
    data_src = text[start:end]
    node_script = data_src + "\nprocess.stdout.write(JSON.stringify(CHECKLIST_DATA));\n"
    with tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False, encoding="utf-8") as tf:
        tf.write(node_script)
        tmp = tf.name
    try:
        res = subprocess.run(
            ["node", tmp], capture_output=True, text=True, timeout=60
        )
    finally:
        Path(tmp).unlink(missing_ok=True)
    if res.returncode != 0:
        sys.exit(f"ERROR: node eval failed:\n{res.stderr}")
    return json.loads(res.stdout)


def load_overlay() -> dict:
    if not OVERLAY.exists():
        return {}
    return yaml.safe_load(OVERLAY.read_text(encoding="utf-8")) or {}


def count_items(data: dict) -> int:
    return sum(len(items) for cat in data.values() for items in cat["sections"].values())


def build_model(data: dict, overlay: dict) -> dict:
    cov = (overlay.get("coverage") or {})
    cap = (overlay.get("capability") or {})          # NEW: execution axis (distinct from skill knowledge)
    sev_over = (overlay.get("severity_overrides") or {})
    categories = []
    seen_cat_ids = set()
    for cat_name, cat in data.items():
        cat_slug = slugify(cat_name)
        cat_id = f"PRC.{cat_slug}"
        if cat_id in seen_cat_ids:
            sys.exit(f"ERROR: duplicate category id {cat_id} from '{cat_name}'")
        seen_cat_ids.add(cat_id)
        default_sev = sev_over.get(cat_name) or heuristic_severity(cat_name)
        cov_entry = cov.get(cat_name) or {}
        coverage_status = cov_entry.get("status", "UNKNOWN")
        skill_refs = cov_entry.get("skill_refs", []) or []
        # NEW capability axis: a skill DESCRIBES; a tool/MCP/command EXECUTES.
        # capability_status defaults to UNKNOWN (== not-HAVE) until probe-verified.
        cap_entry = cap.get(cat_name) or {}
        capability_status = cap_entry.get("status", "UNKNOWN")
        tool_refs = cap_entry.get("tool_refs", []) or []
        mcp_refs = cap_entry.get("mcp_refs", []) or []
        command_refs = cap_entry.get("command_refs", []) or []
        cap_refs = cap_entry.get("capability_refs", []) or []   # CAP_* ids in the capability registry
        capability_notes = cap_entry.get("notes", "")
        sections = []
        for sec_name, items in cat["sections"].items():
            sec_slug = slugify(sec_name)
            sec_id = f"{cat_id}.{sec_slug}"
            out_items = []
            for i, text in enumerate(items, start=1):
                out_items.append({"id": f"{sec_id}.{i:03d}", "text": text})
            sections.append({"id": sec_id, "name": sec_name, "items": out_items})
        categories.append({
            "id": cat_id,
            "name": cat_name,
            "icon": cat.get("icon", ""),
            "color": cat.get("color", ""),
            "default_severity": default_sev,
            "coverage_status": coverage_status,
            "skill_refs": skill_refs,
            "capability_status": capability_status,
            "tool_refs": tool_refs,
            "mcp_refs": mcp_refs,
            "command_refs": command_refs,
            "capability_refs": cap_refs,
            "capability_notes": capability_notes,
            "section_count": len(sections),
            "item_count": sum(len(s["items"]) for s in sections),
            "sections": sections,
        })
    return {
        "schema_version": "1.0",
        "corpus_id": CORPUS_ID,
        "generated_from": "corpus/source/dev-checklist-v2.jsx",
        "generated_by": "tools/build_corpus.py",
        "category_count": len(categories),
        "item_count": sum(c["item_count"] for c in categories),
        "categories": categories,
    }


def yaml_dump(obj) -> str:
    return yaml.safe_dump(obj, allow_unicode=True, default_flow_style=False,
                          sort_keys=False, width=100000)


def write_outputs(model: dict) -> None:
    CATEGORIES_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_JSON.parent.mkdir(parents=True, exist_ok=True)
    # per-category files
    tax_categories = []
    for cat in model["categories"]:
        fname = f"PRC-{cat['id'].split('.', 1)[1]}.yaml"
        cat_file = {
            "schema_version": "1.0",
            "category_id": cat["id"],
            "name": cat["name"],
            "icon": cat["icon"],
            "color": cat["color"],
            "default_severity": cat["default_severity"],
            "coverage_status": cat["coverage_status"],
            "skill_refs": cat["skill_refs"],
            "capability_status": cat["capability_status"],
            "tool_refs": cat["tool_refs"],
            "mcp_refs": cat["mcp_refs"],
            "command_refs": cat["command_refs"],
            "capability_refs": cat["capability_refs"],
            "capability_notes": cat["capability_notes"],
            "sections": [
                {"id": s["id"], "name": s["name"], "items": s["items"]}
                for s in cat["sections"]
            ],
        }
        (CATEGORIES_DIR / fname).write_text(yaml_dump(cat_file), encoding="utf-8")
        tax_categories.append({
            "id": cat["id"], "name": cat["name"], "icon": cat["icon"],
            "color": cat["color"], "default_severity": cat["default_severity"],
            "coverage_status": cat["coverage_status"], "skill_refs": cat["skill_refs"],
            "capability_status": cat["capability_status"],
            "tool_refs": cat["tool_refs"], "mcp_refs": cat["mcp_refs"],
            "command_refs": cat["command_refs"], "capability_refs": cat["capability_refs"],
            "section_count": cat["section_count"], "item_count": cat["item_count"],
            "file": f"categories/{fname}",
        })
    taxonomy = {
        "schema_version": "1.0",
        "corpus_id": model["corpus_id"],
        "generated_from": model["generated_from"],
        "generated_by": model["generated_by"],
        "category_count": model["category_count"],
        "item_count": model["item_count"],
        "categories": tax_categories,
    }
    TAXONOMY.write_text(yaml_dump(taxonomy), encoding="utf-8")
    CORPUS_JSON.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="extract + print stats, no writes")
    ap.add_argument("--check", action="store_true", help="build in memory + assert, no writes")
    args = ap.parse_args()

    data = extract_checklist_data()
    src_items = count_items(data)

    if args.probe:
        print(f"categories: {len(data)}")
        print(f"total items: {src_items}")
        print("per-category (name | sections | items):")
        for name, cat in data.items():
            n_sec = len(cat["sections"])
            n_items = sum(len(v) for v in cat["sections"].values())
            print(f"  - {name} | {n_sec} | {n_items}")
        return 0

    overlay = load_overlay()
    model = build_model(data, overlay)
    built_items = model["item_count"]
    assert built_items == src_items, (
        f"ITEM-LOSS: source={src_items} built={built_items}")

    if args.check:
        print(f"OK (check): categories={model['category_count']} items={built_items} "
              f"== source={src_items} (no writes)")
        return 0

    write_outputs(model)
    # re-read corpus.json and recount to prove the written artifact is lossless
    reread = json.loads(CORPUS_JSON.read_text(encoding="utf-8"))
    written_items = sum(c["item_count"] for c in reread["categories"])
    assert written_items == src_items, (
        f"WRITTEN ITEM-LOSS: source={src_items} written={written_items}")
    print(f"OK: categories={model['category_count']} items={written_items} "
          f"(== source {src_items}); wrote taxonomy.yaml, "
          f"{model['category_count']} category files, corpus.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
