#!/usr/bin/env python3
"""
extract_repo_objects.py — Architecture-State Sync, Phase A+B (deterministic).

Scans a repo into a living object graph:
  file_inventory.yaml   — what files exist (path, type, sha8, size)
  object_inventory.yaml — classified nodes (the repo's objects)
  edge_inventory.yaml   — relationships (contains / imports / references / documents)

Deterministic only (no AI): extension/path classification, TS/JS import resolution,
markdown links. Bookworm can enrich later. Run via atlas_run.py.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, sys
from pathlib import Path
try:
    import yaml
except ImportError:
    print("pyyaml required", file=sys.stderr); sys.exit(2)

ROOT = Path(__file__).resolve().parents[3]
SCAN_DIRS = ["apps", "infrastructure", "schemas", "docs", "platform/sdlc", "platform/systems"]
EXCLUDE = ("/node_modules/", "/.next/", "/.git/", "external_collateral", "/backups/", "/__pycache__/", "/dist/",
           # the sync's OWN derived outputs — exclude so deltas reflect real source, not self-churn
           "/.snapshot/", "_inventory.yaml", "architecture_delta.yaml", "architecture_sync_summary.yaml",
           "repo.graph.json", "architecture_change_ledger.jsonl")
TS_EXT = (".ts", ".tsx", ".js", ".mjs", ".jsx")

def excluded(p): return any(x in p for x in EXCLUDE)

def classify(path: str) -> str:
    b = os.path.basename(path); p = path
    if b == "route.ts" or ("/api/" in p and b == "route.ts"): return "route"
    if p.endswith(".schema.json") or p.endswith(".schema.yaml"): return "schema"
    if re.match(r"SKILL_.*\.yaml$", b): return "skill"
    if b.endswith(".playbook.md"): return "skill_playbook"
    if b.endswith(".registry.yaml"): return "registry"
    if b.startswith("ADR-") and b.endswith(".md"): return "adr"
    if b.lower() == "readme.md": return "readme"
    if b.endswith((".test.ts", ".test.tsx", ".spec.ts")) or "/tests/" in p: return "test_file"
    if b.endswith(".tsx"): return "ui_component"
    if b.endswith((".ts", ".js", ".mjs")): return "source_file"
    if b.endswith(".py"): return "script"
    if b.endswith((".yaml", ".yml")): return "config_or_data"
    if b.endswith(".json"): return "json"
    if b.endswith((".md", ".mdx", ".html")): return "documentation_file"
    if b in ("package.json", "tsconfig.json", ".env", "next.config.ts"): return "config_file"
    return "file"

# repo objects that are legitimately standalone (no edges expected)
INTENTIONAL_STANDALONE = re.compile(r"(README|LICENSE|CHANGELOG|\.gitignore|manifest|\.registry\.yaml|AGENTS\.md|CLAUDE\.md|CODEX\.md)", re.I)

def sha8(fp: Path) -> str:
    try: return hashlib.sha256(fp.read_bytes()).hexdigest()[:8]
    except OSError: return ""

def resolve_ts(importer: str, spec: str) -> str | None:
    """Resolve a TS/JS import spec to a repo-relative file path, or None if external/unresolved."""
    if spec.startswith("@/"):                       # apps/frontend/shell/src alias
        base = "apps/frontend/shell/src/" + spec[2:]
    elif spec.startswith("."):
        base = os.path.normpath(os.path.join(os.path.dirname(importer), spec))
    else:
        return None                                  # bare npm import — external, skip
    for cand in (base, base + ".ts", base + ".tsx", base + ".js", base + ".mjs",
                 base + "/index.ts", base + "/index.tsx", base + ".json"):
        if (ROOT / cand).exists():
            return cand
    return base + ".ts"  # best-effort target (may be a dead reference → caught in reconcile)

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--repo", default="atlas")
    ap.add_argument("--stamp", default="unstamped"); a = ap.parse_args()
    TWIN = ROOT / f"platform/systems/39_repo_twins/twins/{a.repo}"
    TWIN.mkdir(parents=True, exist_ok=True)

    files, objects, edges = [], [], []
    fileset = set()
    for d in SCAN_DIRS:
        for dirpath, dirnames, filenames in os.walk(ROOT / d):
            rel = os.path.relpath(dirpath, ROOT)
            if excluded("/" + rel + "/"):
                dirnames[:] = []; continue
            dirnames[:] = [dn for dn in dirnames if not excluded("/" + dn + "/")]
            for fn in filenames:
                fp = Path(dirpath) / fn
                rp = os.path.relpath(fp, ROOT)
                if excluded("/" + rp): continue
                fileset.add(rp)

    for rp in sorted(fileset):
        fp = ROOT / rp
        try: sz = fp.stat().st_size
        except OSError: continue
        typ = classify(rp)
        files.append({"path": rp, "type": typ, "sha8": sha8(fp), "size": sz})
        objects.append({"object_id": rp, "object_type": typ, "name": os.path.basename(rp),
                        "status": "ACTIVE", "source": "filesystem"})
        # containment edge: parent dir contains file
        parent = os.path.dirname(rp)
        if parent:
            edges.append({"from": parent, "to": rp, "type": "contains", "confidence": "high", "status": "active"})
        # relationship extraction
        if typ in ("source_file", "ui_component", "route", "test_file") and rp.endswith(TS_EXT) and sz < 400_000:
            try: text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError: text = ""
            for spec in re.findall(r"""(?:import[^'"]*from|require\()\s*['"]([^'"]+)['"]""", text):
                tgt = resolve_ts(rp, spec)
                if tgt:
                    edges.append({"from": rp, "to": tgt, "type": "imports", "confidence": "high",
                                  "status": "active"})
        elif typ in ("documentation_file", "readme", "adr") and rp.endswith((".md", ".mdx")) and sz < 400_000:
            try: text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError: text = ""
            for link in re.findall(r"\]\(([^)\s#]+)", text):
                if link.startswith(("http", "mailto:", "/")): continue
                tgt = os.path.normpath(os.path.join(os.path.dirname(rp), link))
                if not tgt.startswith(".."):
                    edges.append({"from": rp, "to": tgt, "type": "documents", "confidence": "medium",
                                  "status": "active"})

    yaml.safe_dump({"schema_version": "1.0", "repo": a.repo, "stamp": a.stamp, "count": len(files),
                    "scan_dirs": SCAN_DIRS, "files": files},
                   open(TWIN / "file_inventory.yaml", "w"), sort_keys=False, allow_unicode=True)
    yaml.safe_dump({"schema_version": "1.0", "repo": a.repo, "stamp": a.stamp, "count": len(objects),
                    "objects": objects},
                   open(TWIN / "object_inventory.yaml", "w"), sort_keys=False, allow_unicode=True)
    yaml.safe_dump({"schema_version": "1.0", "repo": a.repo, "stamp": a.stamp, "count": len(edges),
                    "edges": edges},
                   open(TWIN / "edge_inventory.yaml", "w"), sort_keys=False, allow_unicode=True)
    from collections import Counter
    print(f"[{a.repo}] files={len(files)} objects={len(objects)} edges={len(edges)}")
    print("  object types:", dict(Counter(o['object_type'] for o in objects).most_common(8)))
    print("  edge types:", dict(Counter(e['type'] for e in edges)))
    return 0

if __name__ == "__main__":
    sys.exit(main())
