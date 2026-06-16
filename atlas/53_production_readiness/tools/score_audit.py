#!/usr/bin/env python3
"""
score_audit.py — deterministic scorer for a production-readiness audit run.

Reads:
  generated/corpus.json           (the corpus: categories -> sections -> items)
  rubric/scoring_rubric.yaml       (tier thresholds)
  <audit_state.yaml>               (the verdicts INPUT)

Emits next to the state file:
  gap_report.yaml                  (per-category tier, counts, failed items + linked skill)
  summary.md                       (scannable view)

audit_state.yaml schema:
  target: ATLAS
  profile: desktop_electron            # informational
  required_tier: gold                  # informational (the goal)
  in_scope_categories: [ ... ]         # optional; default = all categories
  na_categories: [ ... ]               # optional; whole categories marked N/A
  severity_overrides: { <item_id>: critical }   # optional per-item
  verdicts:                            # the judgments; any unlisted in-scope item = unknown
    PRC.SECURITY_AND_AUTHENTICATION.AUTHENTICATION.001: pass
    PRC.SECURITY_AND_AUTHENTICATION.AUTHENTICATION.002: fail

Verdict values: pass | fail | na | unknown
  na      -> excluded from denominators
  unknown -> NOT passed, but tracked separately as "not yet assessed"

TWO HONEST METRICS (never conflated):
  assessed_pass_rate = pass / (pass + fail)         over ITEMS ACTUALLY JUDGED
  coverage_depth     = (pass + fail) / in_scope_items   how much of the corpus was assessed
A high pass-rate over a tiny coverage is explicitly shown as exactly that.

Usage:
  python3 score_audit.py <audit_state.yaml>
  python3 score_audit.py --selfcheck    # run the built-in ATLAS oracle assertion
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CORPUS_JSON = ROOT / "generated" / "corpus.json"
RUBRIC = ROOT / "rubric" / "scoring_rubric.yaml"
RUNS = ROOT.parent / "23_evidence" / "production_readiness_runs"

SEVERITIES = ["critical", "high", "medium", "low"]
TIER_ORDER = ["platinum", "gold", "silver", "bronze", "none"]


def tier_rank(t: str) -> int:
    return TIER_ORDER.index(t) if t in TIER_ORDER else len(TIER_ORDER)


def tally(scope_items, verdicts, sev_over, cat_default):
    """Return per-severity buckets + a flat totals dict + failed-item list."""
    buckets = {s: {"pass": 0, "fail": 0, "unknown": 0, "na": 0} for s in SEVERITIES}
    failed = []
    for iid, item in scope_items:
        sev = sev_over.get(iid) or item.get("severity") or cat_default
        if sev not in buckets:
            sev = "medium"
        v = verdicts.get(iid, "unknown")
        if v not in ("pass", "fail", "na", "unknown"):
            v = "unknown"
        buckets[sev][v] += 1
        if v == "fail":
            failed.append({"id": iid, "severity": sev, "text": item.get("text", "")})
    totals = {"pass": 0, "fail": 0, "unknown": 0, "na": 0}
    for s in SEVERITIES:
        for k in totals:
            totals[k] += buckets[s][k]
    return buckets, totals, failed


def severity_pass_ratios(buckets):
    """pass / (pass+fail+unknown) per severity. unknown counts as NOT passed."""
    ratios = {}
    for s in SEVERITIES:
        b = buckets[s]
        denom = b["pass"] + b["fail"] + b["unknown"]
        ratios[s] = 1.0 if denom == 0 else b["pass"] / denom
    return ratios


def achieved_tier(ratios, buckets, rubric):
    tiers = rubric["tiers"]
    achieved = "none"
    for tier in ("bronze", "silver", "gold"):
        req = tiers[tier]["requires"]
        if all(ratios.get(s, 1.0) >= thr for s, thr in req.items()):
            blockers = tiers[tier].get("no_open_blockers_in", [])
            if any(buckets[s]["fail"] > 0 for s in blockers):
                break
            achieved = tier
        else:
            break
    if achieved == "gold":
        req = tiers["platinum"]["requires"]
        if all(ratios.get(s, 1.0) >= thr for s, thr in req.items()):
            achieved = "platinum_candidate"
    return achieved


def score(state: dict, corpus: dict, rubric: dict) -> dict:
    verdicts = state.get("verdicts", {}) or {}
    sev_over = state.get("severity_overrides", {}) or {}
    na_categories = set(state.get("na_categories", []) or [])
    in_scope = state.get("in_scope_categories")  # None => all

    cats_report = []
    agg = {"pass": 0, "fail": 0, "unknown": 0, "na": 0}
    none_cov_with_gap = True
    min_tier = "platinum"
    any_assessed = False

    for cat in corpus["categories"]:
        if in_scope is not None and cat["name"] not in in_scope:
            continue
        if cat["name"] in na_categories:
            cats_report.append({"category": cat["name"], "id": cat["id"],
                                "tier": "na", "coverage_status": cat["coverage_status"]})
            continue
        scope_items = [(it["id"], it) for s in cat["sections"] for it in s["items"]]
        buckets, totals, failed = tally(scope_items, verdicts, sev_over, cat["default_severity"])
        ratios = severity_pass_ratios(buckets)
        tier = achieved_tier(ratios, buckets, rubric)
        eff_tier = "platinum" if tier == "platinum_candidate" else tier

        for k in agg:
            agg[k] += totals[k]
        if totals["pass"] + totals["fail"] > 0:
            any_assessed = True
        if tier_rank(eff_tier) > tier_rank(min_tier):
            min_tier = eff_tier

        gap = None
        if eff_tier in ("none", "bronze", "silver") or totals["fail"] > 0:
            if cat["coverage_status"] == "NONE":
                gap = {"type": "NO-SKILL GAP", "fix_skill": cat["skill_refs"]}
                if not cat["skill_refs"]:
                    none_cov_with_gap = False
            else:
                gap = {"type": "link_skill", "fix_skill": cat["skill_refs"]}

        cats_report.append({
            "category": cat["name"], "id": cat["id"], "tier": eff_tier,
            "coverage_status": cat["coverage_status"], "counts": totals,
            "pass_ratio": {s: round(ratios[s], 4) for s in SEVERITIES},
            "failed_items": failed[:50], "gap": gap, "skill_refs": cat["skill_refs"],
        })

    floor_tier = min_tier
    if floor_tier == "platinum":
        gold_plus = all(tier_rank(c["tier"]) <= tier_rank("gold")
                        for c in cats_report if c["tier"] != "na")
        if not (gold_plus and none_cov_with_gap):
            floor_tier = "gold"

    in_scope_items = agg["pass"] + agg["fail"] + agg["unknown"]
    assessed = agg["pass"] + agg["fail"]

    # HONESTY GATE: a tier cannot be CERTIFIED without assessing the corpus.
    # Empty severity buckets score 1.0 (vacuously), so an unassessed category would
    # otherwise inflate to a medal. Until coverage_depth clears the rubric floor, the
    # overall result is "incomplete" carrying the floor of what WAS verified — never a
    # certified medal off 1% coverage. (Unknown must never read as pass; see the
    # honest-audit-metrics discipline.)
    cert_floor = float((rubric.get("certification") or {}).get("min_coverage_depth_percent", 90))
    # TWO honest metrics — never conflated into one number.
    assessed_pass_rate = None if assessed == 0 else round(100 * agg["pass"] / assessed, 1)
    coverage_depth = 0.0 if in_scope_items == 0 else round(100 * assessed / in_scope_items, 1)

    if not any_assessed:
        overall_tier = "not_assessed"
    elif coverage_depth < cert_floor:
        overall_tier = f"incomplete (floor: {floor_tier}, coverage {coverage_depth}% < {cert_floor}%)"
    else:
        overall_tier = floor_tier

    return {
        "schema_version": "1.0",
        "target": state.get("target"),
        "profile": state.get("profile"),
        "required_tier": state.get("required_tier"),
        "assessed": any_assessed,
        "overall_tier": overall_tier,           # "incomplete" until coverage clears the cert floor
        "floor_tier": floor_tier,               # worst tier among what WAS verified
        "certification_floor_percent": cert_floor,
        "assessed_pass_rate_percent": assessed_pass_rate,   # pass / (pass+fail) over judged items
        "coverage_depth_percent": coverage_depth,           # (pass+fail) / in_scope items
        "totals": agg,
        "in_scope_items": in_scope_items,
        "categories": cats_report,
    }


def write_reports(report: dict, out_dir: Path) -> None:
    (out_dir / "gap_report.yaml").write_text(
        yaml.safe_dump(report, allow_unicode=True, sort_keys=False, width=100000),
        encoding="utf-8")
    t = report
    lines = [
        f"# Production-Readiness Audit — {t.get('target','?')}", "",
        f"- **Overall tier:** `{t['overall_tier']}` (goal: `{t.get('required_tier','?')}`)",
        (f"- **Assessed pass-rate:** {t['assessed_pass_rate_percent']}% "
         f"(pass {t['totals']['pass']} / fail {t['totals']['fail']} of items actually judged)"
         if t["assessed"] else "- **Assessed pass-rate:** n/a — project NOT assessed this run"),
        f"- **Coverage depth:** {t['coverage_depth_percent']}% of in-scope corpus assessed "
        f"({t['totals']['pass'] + t['totals']['fail']} of {t['in_scope_items']} items; "
        f"{t['totals']['unknown']} still unknown)",
        "", "_Two honest numbers: pass-rate is over what was checked; coverage depth is how much was checked._",
        "", "| Category | Coverage | Tier | pass | fail | unknown | gap |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in t["categories"]:
        if c["tier"] == "na":
            lines.append(f"| {c['category']} | {c['coverage_status']} | na | - | - | - | - |")
            continue
        ct = c["counts"]
        g = ""
        if c.get("gap"):
            isno = c["gap"]["type"] == "NO-SKILL GAP"
            g = ("**NO-SKILL → " if isno else "") + ",".join(c["gap"]["fix_skill"]) + ("**" if isno else "")
        lines.append(f"| {c['category']} | {c['coverage_status']} | {c['tier']} | "
                     f"{ct['pass']} | {ct['fail']} | {ct['unknown']} | {g} |")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def selfcheck() -> int:
    """Independent oracle for the ATLAS run.

    Asserts the numbers that come from TWO independent sources and are stable
    regardless of corpus size: pass=19 and fail=6 (these match both the
    ATLAS audit_state.yaml verdict tally AND the fleet-audit workflow's
    separately-reported critical counts). `unknown` is intentionally NOT
    asserted — it is derived from corpus size and changes when the corpus grows.
    Also asserts the cross-check identity pass+fail+na+unknown == in-scope items.
    """
    corpus = json.loads(CORPUS_JSON.read_text())
    rubric = yaml.safe_load(RUBRIC.read_text())
    state = yaml.safe_load((RUNS / "ATLAS-2026-05-31" / "audit_state.yaml").read_text())
    r = score(state, corpus, rubric)
    t = r["totals"]
    in_scope = r["in_scope_items"]
    identity_ok = (t["pass"] + t["fail"] + t["unknown"] + t["na"]) == (in_scope + t["na"])
    ok = t["pass"] == 19 and t["fail"] == 6 and identity_ok
    print(f"SELFCHECK ATLAS pass={t['pass']}(exp 19) fail={t['fail']}(exp 6) "
          f"na={t['na']} unknown={t['unknown']} in_scope={in_scope} "
          f"identity={'ok' if identity_ok else 'BROKEN'} -> {'PASS' if ok else 'FAIL'}")
    print(f"  assessed_pass_rate={r['assessed_pass_rate_percent']}% "
          f"coverage_depth={r['coverage_depth_percent']}% tier={r['overall_tier']}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("state", nargs="?", help="path to audit_state.yaml")
    ap.add_argument("--selfcheck", action="store_true", help="run the ATLAS oracle assertion")
    args = ap.parse_args()
    if args.selfcheck:
        return selfcheck()
    if not args.state:
        ap.error("state path required (or use --selfcheck)")
    state_path = Path(args.state).resolve()
    state = yaml.safe_load(state_path.read_text(encoding="utf-8")) or {}
    corpus = json.loads(CORPUS_JSON.read_text(encoding="utf-8"))
    rubric = yaml.safe_load(RUBRIC.read_text(encoding="utf-8"))
    report = score(state, corpus, rubric)
    write_reports(report, state_path.parent)
    print(f"OK: {report['target']} -> tier={report['overall_tier']} "
          f"assessed_pass_rate={report['assessed_pass_rate_percent']}% "
          f"coverage_depth={report['coverage_depth_percent']}% "
          f"(pass {report['totals']['pass']}/fail {report['totals']['fail']}/unknown {report['totals']['unknown']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
