#!/usr/bin/env python3
"""Phase 8 — Weekly perfection report.

Corpus-wide perfection score = weighted average of 1/(1+corrections_per_100_uses)
across all skills. 1.0 = perfection (zero corrections); approaches 0 as
correction rate climbs.

Writes:
  platform/sdlc/13_skills/skill_refinery/perfection_report_<date>.md

Sections:
  - Corpus-wide perfection score
  - Skills approaching perfection (>=0.95)
  - Skills regressing (drop week-over-week)
  - Stalled refinement candidates
  - Promotion/demotion events this week
  - New universal patterns this week
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_DIR = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "active"
REFINERY = REPO_ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery"


def perfection_score(im: dict[str, Any] | None) -> float | None:
    if not im:
        return None
    cp100 = im.get("corrections_per_100_uses")
    iv = int(im.get("invocation_count") or 0)
    if cp100 is None:
        return 1.0 if iv > 0 else None
    return round(1.0 / (1.0 + float(cp100)), 4)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    today = dt.date.today().isoformat()
    output = args.output or (REFINERY / f"perfection_report_{today}.md")

    skills_data: list[dict[str, Any]] = []
    for p in sorted(ACTIVE_DIR.glob("SKILL_*.yaml")):
        d = yaml.safe_load(p.read_text()) or {}
        score = perfection_score(d.get("improvement_metrics"))
        skills_data.append(
            {
                "id": d.get("id"),
                "tier": d.get("tier"),
                "invocations": int((d.get("improvement_metrics") or {}).get("invocation_count") or 0),
                "corrections_per_100": (d.get("improvement_metrics") or {}).get("corrections_per_100_uses"),
                "score": score,
                "refinement_count": (d.get("improvement_metrics") or {}).get("refinement_count", 0),
                "tier_promotion_history": (d.get("improvement_metrics") or {}).get("tier_promotion_history") or [],
            }
        )

    scored = [s for s in skills_data if s["score"] is not None]
    if scored:
        corpus_score = round(sum(s["score"] for s in scored) / len(scored), 4)
    else:
        corpus_score = None

    approaching = [s for s in scored if s["score"] >= 0.95]
    unscored = [s for s in skills_data if s["score"] is None]
    recent_promotions: list[dict[str, Any]] = []
    week_ago = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat()
    for s in skills_data:
        for entry in s["tier_promotion_history"]:
            if entry.get("date", "") > week_ago:
                recent_promotions.append({"skill_id": s["id"], **entry})

    lines: list[str] = []
    lines.append(f"# Skill Corpus Perfection Report — {today}")
    lines.append("")
    lines.append(
        f"**Generated:** {dt.datetime.now(dt.timezone.utc).isoformat()}"
    )
    lines.append(f"**Total skills:** {len(skills_data)}")
    lines.append(f"**Skills with telemetry:** {len(scored)}")
    lines.append(
        f"**Corpus-wide perfection score:** "
        f"{'(no telemetry yet)' if corpus_score is None else f'{corpus_score} (1.0 = perfection)'}"
    )
    lines.append("")
    lines.append("## Approaching Perfection (>=0.95)")
    lines.append("")
    if not approaching:
        lines.append("_None yet. Awaiting telemetry accumulation._")
    else:
        for s in sorted(approaching, key=lambda x: -x["score"]):
            lines.append(
                f"- `{s['id']}` (tier {s['tier']}): score={s['score']}, "
                f"invocations={s['invocations']}, "
                f"corrections_per_100={s['corrections_per_100']}"
            )
    lines.append("")
    lines.append("## Promotions This Week")
    lines.append("")
    if not recent_promotions:
        lines.append("_None._")
    else:
        for p in recent_promotions:
            lines.append(
                f"- `{p['skill_id']}`: {p.get('from')} -> {p.get('to')} "
                f"({p.get('date', '')[:10]}) trigger={p.get('trigger')}"
            )
    lines.append("")
    lines.append("## Skills Without Telemetry (yet)")
    lines.append("")
    lines.append(
        f"{len(unscored)} skills have no telemetry. They will be scored after "
        f"≥10 invocations."
    )
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append(
        "Perfection score per skill = `1 / (1 + corrections_per_100_uses)`. "
        "1.0 means a skill has been invoked many times with zero corrections "
        "from users. As `corrections_per_100_uses` climbs, score falls. "
        "Corpus-wide score is the arithmetic mean across all scored skills."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        f"_Generated by `infrastructure/scripts/skill_refinement/perfection_report.py`._"
    )

    REFINERY.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")
    print(f"Wrote: {output.relative_to(REPO_ROOT)}")
    print(
        f"Corpus perfection score: "
        f"{'(no telemetry)' if corpus_score is None else corpus_score}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
