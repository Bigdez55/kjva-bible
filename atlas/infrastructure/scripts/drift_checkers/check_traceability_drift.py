#!/usr/bin/env python3
"""Every active spec must appear in 18_registry/traceability.yaml as a spec_id."""
import sys, yaml
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
trace = yaml.safe_load((ROOT/"platform/systems/18_registry/traceability.yaml").read_text()).get("links",[])
covered = {l.get("spec_id") for l in trace}
specs = set()
for p in (ROOT/"platform/sdlc/03_specs").rglob("SPEC-*.yaml"):
    s = yaml.safe_load(p.read_text())
    if s and s.get("status")=="active":
        specs.add(s["id"])
missing = specs - covered
if missing:
    print("uncovered specs:", missing); sys.exit(1)
print(f"OK: {len(specs)} specs covered")
