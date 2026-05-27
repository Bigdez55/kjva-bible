#!/usr/bin/env python3
"""Concatenate mermaid sources into an atlas. With --validate, also parse via mermaid-cli."""
import argparse, subprocess, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "04_architecture" / "diagrams" / "source"
OUT = ROOT / "04_architecture" / "diagrams" / "architecture_atlas.generated.md"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    files = sorted(SRC.rglob("*.mmd"))
    parts = ["# Architecture Atlas (generated)\n"]
    failed = []
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        parts.append(f"## {rel}\n\n```mermaid\n{f.read_text()}\n```\n")
        if args.validate and shutil.which("npx"):
            r = subprocess.run(["npx","-y","@mermaid-js/mermaid-cli","-i", str(f), "-o", "/tmp/_mmd.svg"], capture_output=True)
            if r.returncode != 0:
                failed.append(rel)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts))
    print(f"Atlas: {len(files)} diagrams -> {OUT}")
    if failed:
        print(f"FAIL: {len(failed)} diagrams failed validation: {failed}"); raise SystemExit(1)

if __name__ == "__main__":
    main()
