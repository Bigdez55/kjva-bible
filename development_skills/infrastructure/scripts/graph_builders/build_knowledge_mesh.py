#!/usr/bin/env python3
"""Build a real knowledge mesh: nodes (files with metadata) + edges (markdown link references)."""
import re, yaml, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "16_knowledge" / "knowledge_mesh"
NODES = OUT_DIR / "nodes.yaml"
EDGES = OUT_DIR / "edges.yaml"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    nodes = []
    edges = []
    for p in ROOT.rglob("*"):
        if not p.is_file(): continue
        if any(part.startswith(".") for part in p.parts): continue
        if p.suffix not in (".md",".yaml",".yml",".mmd"): continue
        rel = p.relative_to(ROOT).as_posix()
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        nodes.append({"id": rel, "kind": p.suffix.lstrip("."), "size": len(text), "sha": hashlib.sha256(text.encode()).hexdigest()[:12]})
        if p.suffix == ".md":
            for m in LINK_RE.findall(text):
                if m.startswith(("http://","https://","mailto:")): continue
                edges.append({"from": rel, "to": m, "kind": "md_link"})
    NODES.write_text(yaml.safe_dump({"total": len(nodes), "nodes": nodes}, sort_keys=False))
    EDGES.write_text(yaml.safe_dump({"total": len(edges), "edges": edges}, sort_keys=False))
    print(f"Mesh: {len(nodes)} nodes, {len(edges)} edges")

if __name__ == "__main__":
    main()
