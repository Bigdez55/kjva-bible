#!/usr/bin/env python3
"""
derive_proof_status.py — Layer 6 (Proof / Drift / Status), read-only.

Reads EXISTING verdicts — it NEVER runs the probe fleet (that is the documented OOM/storm
cause). Sources: probe_results.json (probe verdicts + evidence), the vertical-slice
evidence_record, and the evidence registry. Surfaces ONLY what is genuinely proven; the
overwhelming majority of the ~3,378-item corpus stays UNPROVEN — that mostly-unproven
picture is the honest answer, not a gap to paper over.

Exposes build_proof_status() for compare_spec_build.py / generate_map_data.py.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
try:
    import yaml
except ImportError:
    print("pyyaml required", file=sys.stderr); sys.exit(2)

ROOT = Path(__file__).resolve().parents[3]
PROBES = ROOT / "platform/systems/53_production_readiness/probes/results/probe_results.json"
SLICE = ROOT / "platform/systems/22_vertical_slices/repository_organization_slice_001/evidence_record.yaml"
EVREG = ROOT / "platform/systems/23_evidence/evidence.registry.yaml"
CORPUS_ITEMS = 3378

def build_proof_status() -> dict:
    probes_total = probes_pass = 0
    proven_caps, failing = [], []
    if PROBES.exists():
        pr = json.loads(PROBES.read_text())
        results = pr.get("results", [])
        probes_total = len(results)
        for r in results:
            v = (r.get("verdict") or "").lower()
            if v == "pass":
                probes_pass += 1
                cap = r.get("capability") or r.get("category") or r.get("id")
                proven_caps.append({"capability": cap, "category": r.get("category"),
                                    "probe": r.get("id"), "evidence": str(r.get("evidence") or "")[:160]})
            else:
                failing.append({"probe": r.get("id"), "evidence": str(r.get("evidence") or "")[:160]})

    slice_info = {}
    if SLICE.exists():
        s = yaml.safe_load(SLICE.read_text()) or {}
        res = s.get("results", [])
        slice_info = {"id": "repository_organization_slice_001", "overall": s.get("overall", "?"),
                      "passed": sum(1 for r in res if r.get("result") == "PASS"),
                      "failed": sum(1 for r in res if r.get("result") == "FAIL"),
                      "total": len(res)}

    ev_total = 0
    if EVREG.exists():
        ev = yaml.safe_load(EVREG.read_text()) or {}
        ev_total = ev.get("total", len(ev.get("evidences", []) or []))

    # Distinct capabilities with a passing probe — the real "proven" set.
    distinct_caps = sorted({c["capability"] for c in proven_caps if c["capability"]})
    # KEEP TWO FIGURES SEPARATE (pass-rate != coverage depth — a standing correction):
    #  - probe PASS-RATE: of the probes that exist, how many pass.
    #  - item-level COVERAGE: real corpus items proven. Probes verify CAPABILITIES (synthetic
    #    ids), NOT corpus items — the only items genuinely proven are the slice's PASS items.
    probe_pass_rate = round(100 * probes_pass / probes_total, 1) if probes_total else 0
    proven_items = slice_info.get("passed", 0)
    item_coverage_pct = round(100 * proven_items / CORPUS_ITEMS, 2)

    return {
        "probes": {"total": probes_total, "passed": probes_pass, "failed": probes_total - probes_pass,
                   "pass_rate_pct": probe_pass_rate},
        "proven_capabilities": distinct_caps,
        "proven_detail": proven_caps,
        "failing": failing,
        "slice": slice_info,
        "evidence_packets": ev_total,
        "corpus_items": CORPUS_ITEMS,
        "item_coverage": {"proven_items": proven_items, "corpus_items": CORPUS_ITEMS, "pct": item_coverage_pct},
        "note": (f"{probes_pass}/{probes_total} capability probes pass (~{probe_pass_rate}% pass-rate; {len(distinct_caps)} capabilities). "
                 f"ITEM-LEVEL proof is separate and far smaller: ~{proven_items} corpus items proven (slice {slice_info.get('overall','?')}) "
                 f"≈ {item_coverage_pct}% of {CORPUS_ITEMS} — pass-rate is NOT coverage depth; the corpus is overwhelmingly UNPROVEN. Read-only; fleet never re-run."),
    }

if __name__ == "__main__":
    ps = build_proof_status()
    OUT = ROOT / "platform/systems/43_graph_engine/exports/proof_status.json"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(ps, indent=2))
    print(f"WROTE {OUT.relative_to(ROOT)}")
    print(f"  probes: {ps['probes']['passed']}/{ps['probes']['total']} pass | "
          f"capabilities proven: {len(ps['proven_capabilities'])} | slice: {ps['slice'].get('overall')} | "
          f"corpus proof: ~{ps['corpus_coverage_pct']}%")
    for c in ps["proven_detail"][:6]:
        print(f"    PROVEN {c['capability']:<28} ← {c['probe']}")
    for f in ps["failing"]:
        print(f"    FAIL   {f['probe']}")
