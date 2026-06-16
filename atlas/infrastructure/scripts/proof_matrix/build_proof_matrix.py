#!/usr/bin/env python3
"""Walk specs/ADRs/diagrams/tests/evidence/releases; emit proof_matrix.generated.yaml."""
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TRACE = yaml.safe_load((ROOT/"platform/systems/18_registry/traceability.yaml").read_text()).get("links",[])
OUT = ROOT/"platform/systems/36_proof_matrix"/"proof_matrix.generated.yaml"
OUT.parent.mkdir(parents=True, exist_ok=True)
rows = []
for link in TRACE:
    rows.append({k: link.get(k) for k in ("requirement_id","spec_id","adr_id","diagram_id","test_id","evidence_id","deployment_id")})
OUT.write_text(yaml.safe_dump({"generated":True,"total":len(rows),"rows":rows}, sort_keys=False))
print(f"Wrote {OUT}: {len(rows)} rows")
