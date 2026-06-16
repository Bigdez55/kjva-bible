#!/usr/bin/env python3
"""
fuse_node_status.py — the FUSION step of the Truth Map.

Joins the four truth axes onto the ~15 *visual nodes* of the Architecture Overview
layered diagram (the boxes a developer sees), NOT the 40k file nodes. Read-only:
it consumes already-derived engine outputs (no probe fleet re-run, no app boot).

  Axis 1 STRUCTURE  — empty-dir flags (census of the mapped dirs)
  Axis 2 WIRING     — DEFINED/IMPORTED/CALLED (wired_audit.py output IF present; else not_assessed)
  Axis 3 SPEC-BUILD — compare_spec_build.py assertions (MATCH/PARTIAL/DRIFT/MISMATCH/MISSING/…)
  Axis 4 PROOF      — derive_proof_status.py verdicts (PROVEN / UNPROVEN)
  Overlay FINDINGS  — audit_findings.yaml, pinned by id/category

Per node it returns a verdict stack + a single rolled-up `state`
(green | caution | red | grey) and an `asterisk` flag (set when the node's own
spec/ADR/doc CLAIM contradicts the measured build — the highest-value signal).

The mapping table below is the contract: node id -> evidence. Every node id here
must match a `data-node="<id>"` attribute on a box in docs/ATLAS ARCHITECTURE MAP.html.
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# ── Axis-3 verdicts that mean "claimed ≠ actual" → asterisk + red ──
SPEC_RED = {"MISMATCH", "DRIFT", "MISSING"}
SPEC_CAUTION = {"PARTIAL", "WIRED_UNPROVEN", "BUILT_UNWIRED"}
ASTERISK_VERDICTS = SPEC_RED  # the node's docs assert X, evidence says not-X

# ── THE MAPPING TABLE: visual node -> evidence sources ──
# finding_ids   : audit_findings.yaml ids pinned to this box
# spec_dims     : compare_spec_build dimensions whose verdict colours this box
# proof_caps    : proof_status capabilities/probes that, when PROVEN, green-light this box
# empty_dirs    : dirs whose emptiness is a structural red flag for this box
# claim         : short human note of what the box is SUPPOSED to be (for the tooltip)
NODE_MAP = {
    "launchd_web":   {"label": "com.atlas.web :4317",  "finding_ids": ["F-01"], "claim": "launchd service running on :4317"},
    "launchd_mcp":   {"label": "com.atlas.mcp :4318",  "finding_ids": ["F-01"], "claim": "launchd service running on :4318"},
    "client_surfaces": {"label": "atlas-ui surfaces",  "spec_dims": ["atlas-ui surfaces"], "proof_caps": ["probe_page_is_live"], "claim": "all shell HTML surfaces live"},
    "api_auth":      {"label": "AUTH routes",          "finding_ids": ["F-02"], "claim": "GitHub OAuth enabled for public use"},
    "api_platform":  {"label": "PLATFORM routes",      "spec_dims": ["API route surface"], "proof_caps": ["probe_route_is_live", "CAP_TRIGGER_ROUTE"], "claim": "Next.js API routes live"},
    "api_repos":     {"label": "REPOS routes",         "finding_ids": ["W-11"], "claim": "repos page renders live"},
    "api_ops":       {"label": "OPS routes",           "spec_dims": ["API route surface"], "claim": "health/ready/metrics/proof live"},
    "nextjs_shell":  {"label": "NEXT.JS SHELL",        "spec_dims": ["API route surface"], "proof_caps": ["probe_route_is_live"], "claim": "shell serves the platform"},
    "mcp_server":    {"label": "MCP SERVER",           "proof_caps": ["CAP_MCP_SERVER_BOOT"], "claim": "MCP server boots, tools reachable"},
    "sqlite":        {"label": "SQLite / Drizzle",     "proof_caps": ["CAP_AUDIT_LOG"], "claim": "durable per-tenant store"},
    "python_router": {"label": "Python Router Layer",  "finding_ids": ["W-01"], "wiring_claim": "~40+ dead scripts (unexercised)", "claim": "route_intent.py canonical; script wiring"},
    "corpus_skills": {"label": "13_skills",            "spec_dims": ["Skill coverage (real match)"], "claim": "skills cover all 68 categories"},
    "corpus_systems":{"label": "Systems 18–53",        "finding_ids": ["S-01"], "claim": "all platform systems built & mapped"},
    "corpus_dod":    {"label": "DoD Gate",             "spec_dims": ["Validation gates", "Probe verification (proof engine)"], "claim": "validation gates tested"},
    # Repo-wide drift (190 dead refs / 47 orphans) is NOT pinned here — it belongs in the GAPS
    # panel, not a single box. This node is flagged by the EMPTY twin shells that are genuinely its own.
    "corpus_twins":  {"label": "Repo Twins",           "empty_dirs": [
                          "platform/systems/39_repo_twins/twins/Desmond_Super_C",
                          "platform/systems/39_repo_twins/twins/Tokenless_Models",
                          "platform/systems/39_repo_twins/twins/StorebitsNexusAI"],
                      "claim": "all repo-twin shells populated"},
}

# ── Axis 1 STRUCTURE: tracked dirs that are declared placeholders but hold zero files.
# Repo-wide (no single box owns them) → surfaced in the derived GAPS panel as EMPTY. ──
STRUCTURE_DIRS = [
    "infrastructure/08_verification", "infrastructure/09_release",
    "infrastructure/11_documentation", "infrastructure/23_evidence", "infrastructure/platform",
    "platform/systems/48_reserved", "platform/systems/49_reserved",
    "platform/systems/39_repo_twins/twins/Desmond_Super_C",
    "platform/systems/39_repo_twins/twins/Tokenless_Models",
    "platform/systems/39_repo_twins/twins/StorebitsNexusAI",
]


def _empty(rel: str) -> bool:
    p = ROOT / rel
    return p.is_dir() and not any(f.is_file() for f in p.rglob("*"))


def _state_rank(s: str) -> int:
    return {"grey": 0, "green": 1, "caution": 2, "red": 3}[s]


def build_node_status(spec_assertions, proof_status, findings, *, wired_report=None):
    """Pure join. All inputs are already-derived engine outputs (read-only)."""
    spec_by_dim = {a.get("dimension"): a for a in (spec_assertions or [])}
    find_by_id = {f.get("id"): f for f in (findings or [])}
    proven = set(proof_status.get("proven_capabilities", []) if proof_status else [])
    proven |= {d.get("probe") for d in (proof_status.get("proven_detail", []) if proof_status else [])}
    proven |= {d.get("capability") for d in (proof_status.get("proven_detail", []) if proof_status else [])}
    failing_probes = {f.get("probe") for f in (proof_status.get("failing", []) if proof_status else [])}

    nodes = {}
    for nid, m in NODE_MAP.items():
        axes, reasons, asterisk = {}, [], False
        state = "grey"

        # ── Axis 1 STRUCTURE ──
        empties = [d for d in m.get("empty_dirs", []) if _empty(d)]
        if empties:
            axes["structure"] = "EMPTY"; state = "red"
            reasons.append(f"EMPTY: {', '.join(empties)}")
        else:
            axes["structure"] = "present"

        # ── Axis 2 WIRING ── (only if a wired_audit artifact was supplied — never booted here)
        if wired_report and nid in wired_report:
            axes["wiring"] = wired_report[nid]
            if wired_report[nid] == "DEAD":
                state = "red"; reasons.append("DEAD: nothing imported on the runtime path")
            elif wired_report[nid] == "IMPORTED_ONLY":
                state = max(state, "caution", key=_state_rank); reasons.append("IMPORTED_ONLY: dormant")
        else:
            axes["wiring"] = "not_assessed"
            if m.get("wiring_claim"):
                asterisk = True
                reasons.append(f"claim unverified: {m['wiring_claim']} (wiring not assessed — run wired_audit.py)")

        # ── Axis 3 SPEC-vs-BUILD ──
        spec_verdicts = []
        for dim in m.get("spec_dims", []):
            a = spec_by_dim.get(dim)
            if not a:
                continue
            v = (a.get("verdict") or "").upper()
            spec_verdicts.append(v)
            if v in SPEC_RED:
                state = "red"; asterisk = True
                reasons.append(f"{v} [{dim}]: claim «{a.get('spec')}» vs build «{a.get('build')}»")
            elif v in SPEC_CAUTION:
                state = max(state, "caution", key=_state_rank)
                reasons.append(f"{v} [{dim}]: {a.get('build')}")
            elif v in ("MATCH", "PROVEN") and state in ("grey",):
                state = "green"; reasons.append(f"{v} [{dim}]: {a.get('build')}")
        if spec_verdicts:
            axes["spec_build"] = spec_verdicts if len(spec_verdicts) > 1 else spec_verdicts[0]

        # ── Axis 4 PROOF ──
        caps = m.get("proof_caps", [])
        if caps:
            hit = [c for c in caps if c in proven]
            failed = [c for c in caps if c in failing_probes]
            if failed:
                axes["proof"] = "FAIL"; state = "red"
                reasons.append(f"probe FAIL: {', '.join(failed)}")
            elif hit:
                axes["proof"] = "PROVEN"
                if state in ("grey",): state = "green"
                reasons.append(f"PROVEN: {', '.join(hit)}")
            else:
                axes["proof"] = "UNPROVEN"
                state = max(state, "caution", key=_state_rank)
                reasons.append("UNPROVEN: no probe verdict (honest grey/caution — never green)")

        # ── Findings overlay ──
        fids = []
        for fid in m.get("finding_ids", []):
            f = find_by_id.get(fid)
            if not f:
                continue
            fids.append(fid)
            st, sev = str(f.get("status", "")), str(f.get("severity", ""))
            reasons.append(f"{fid} [{sev}/{st}]: {f.get('finding', '')[:90]}")
            if sev == "FATAL" or "FAIL" in st or (st.startswith("OPEN") and sev == "HIGH"):
                state = "red"
            elif st.startswith("OPEN"):
                state = max(state, "caution", key=_state_rank)

        nodes[nid] = {
            "label": m["label"], "state": state, "asterisk": asterisk,
            "claim": m.get("claim", ""), "axes": axes,
            "finding_ids": fids, "reasons": reasons,
        }

    # ── Derived KNOWN GAPS (replaces the hand-typed F-01/F-02 list) ──
    gaps = []
    # Axis 1 STRUCTURE — empty declared-placeholder dirs (the "certain things are empty" flag)
    empties = [d for d in STRUCTURE_DIRS if _empty(d)]
    for d in empties:
        gaps.append({"kind": "structure", "verdict": "EMPTY", "ref": d,
                     "detail": "tracked directory with zero files — declared but not built",
                     "next": "populate the placeholder or remove it"})
    # Axis 3 SPEC-vs-BUILD — claim ≠ actual
    for a in (spec_assertions or []):
        v = (a.get("verdict") or "").upper()
        if v in SPEC_RED or v in SPEC_CAUTION:
            gaps.append({"kind": "spec", "verdict": v, "ref": a.get("dimension"),
                         "detail": f"{a.get('spec')} → {a.get('build')}", "next": a.get("next_action", "")})
    # Findings overlay — FATAL / OPEN-FAIL / HIGH-OPEN
    for f in (findings or []):
        st, sev = str(f.get("status", "")), str(f.get("severity", ""))
        if sev == "FATAL" or "FAIL" in st or (st.startswith("OPEN") and sev in ("FATAL", "HIGH")):
            gaps.append({"kind": "finding", "verdict": f"{sev}/{st}", "ref": f.get("id"),
                         "detail": f.get("finding", "")[:120], "next": ""})
    # severity ordering: spec-red & FATAL first, EMPTY structural next, the rest after
    def _gap_rank(g):
        v = g["verdict"].upper()
        if v.startswith(("MISMATCH", "DRIFT", "MISSING", "FATAL")):
            return 0
        if v == "EMPTY":
            return 1
        return 2
    rollup = {"red": 0, "caution": 0, "green": 0, "grey": 0}
    for n in nodes.values():
        rollup[n["state"]] += 1
    rollup["empty_dirs"] = len(empties)

    return {
        "legend": {
            "green": "CALLED + MATCH + PROVEN — real, evidence-backed",
            "caution": "PARTIAL / WIRED_UNPROVEN / UNPROVEN / OPEN finding — works or exists, not fully proven",
            "red": "EMPTY / DEAD / DRIFT / MISMATCH / MISSING / FATAL — claimed but not real",
            "grey": "not assessed — no signal (honest; never shown as green)",
            "asterisk": "* the node's own docs/ADR/spec claim contradicts the measured build",
        },
        "rollup": rollup,
        "nodes": nodes,
        "gaps": sorted(gaps, key=_gap_rank)[:24],
        "axis_note": "Axis 1 (empty dirs) + Axis 3 (spec/build) + Axis 4 (proof) + findings are live. Axis 2 (wiring) is 'not_assessed' unless a wired_audit.py artifact is supplied — the app is never booted during fusion (storm/OOM discipline).",
    }


if __name__ == "__main__":
    # Standalone self-test using the real engine outputs (read-only).
    import json, sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from compare_spec_build import build_spec_assertions
    from derive_proof_status import build_proof_status
    try:
        import yaml
        findings = (yaml.safe_load((ROOT / "infrastructure/scripts/architecture_map/data/audit_findings.yaml").read_text()) or {}).get("findings", [])
    except Exception:
        findings = []
    ns = build_node_status(build_spec_assertions("selftest"), build_proof_status(), findings)
    print(json.dumps(ns["rollup"], indent=2))
    for nid, n in ns["nodes"].items():
        ast = " *" if n["asterisk"] else ""
        print(f"  [{n['state']:>7}]{ast:2} {nid:<16} {n['label']}")
    print(f"\nDerived gaps: {len(ns['gaps'])}")
    for g in ns["gaps"][:8]:
        print(f"  - {g['verdict']:<14} {g['ref']}: {g['detail'][:70]}")
