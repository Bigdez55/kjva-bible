"""
counter_witness.py — grounded constitutional refusals.

When the covenant enforcer BLOCKS a request, this module dresses that already-made
denial with COUNTER-WITNESS scripture — verses that stand against the requested
action — using EXACT text RETRIEVED from the KJV+Apocrypha corpus, never generated.

Doctrine (owner-directed): the model classifies/routes; the retriever supplies the
scripture; the formatter cites retrieved text. NO scripture is fabricated.

Hard invariants:
  - This module NEVER decides whether to block. It is presentation-only, strictly
    downstream of `CovenantEnforcer.enforce()` (the verdict is unchanged).
  - Every verse string emitted is a `Citation` produced by `KJVRetriever.cite()`.
    A reference that does not resolve is OMITTED — never approximated, never
    generated. A denial with zero resolved citations still denies (without verses).

Counter-witness sources, in priority order:
  1. GUARANTEED — the per-covenant `scripture` ref carried on each violation
     (always present in COVENANT_REGISTRY; no fragile join required).
  2. OPTIONAL ENRICHMENT — the owner's category->references map
     (alignment_counter_witness_v1.jsonl), applied only where a covenant maps
     cleanly to a category. Missing/partial enrichment never weakens (1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .kjv_retrieval import KJVRetriever, Citation


# Covenant -> owner counter-witness category, ONLY where the mapping is clean.
# (theft/oppression etc. have no single registry covenant; left unmapped so the
# guaranteed registry-scripture path still grounds every violation.)
_COVENANT_TO_CATEGORY: dict[str, str] = {
    "COV-001": "harm_prevention",
    "COV-002": "false_witness",
    "COV-007": "manipulation",
    "COV-009": "identity_integrity",
    "COV-010": "canonical_weight_authority",
}

# GENERIC, category-appropriate redirects. The owner's per-row safe_redirect is
# scenario-specific (e.g. the poison-water row offers "water-safety"), which
# mis-fires when applied to a different request in the same category (a bomb
# request must not be offered "water-safety"). Use a neutral per-category line.
_GENERIC_REDIRECT: dict[str, str] = {
    "harm_prevention": "lawful safety, de-escalation, and protective resources",
    "false_witness": "honest communication, factual verification, and lawful reporting",
    "theft_or_fraud": "fraud protection, account security, and lawful recourse",
    "oppression_or_exploitation": "fair-treatment practices, protection of the vulnerable, and lawful remedies",
    "manipulation": "honest communication, conflict resolution, and restorative mediation",
    "identity_integrity": "scripture study, governance questions, and Bible-related help",
    "canonical_weight_authority": "the promotion gate, review requirements, and the attestation process",
}

# enrichment dataset (owner-authored, audited); resolved across layouts
_PROGRAMS_CANDIDATES = (
    "training/corpus/programs/alignment_counter_witness_v1.jsonl",
    "models v7/training/corpus/programs/alignment_counter_witness_v1.jsonl",
)


@dataclass
class GroundedCounterWitness:
    """A violation + its RETRIEVED counter-witness citations (provenance-stamped)."""
    covenant_id: str
    rule: str
    citations: list[Citation] = field(default_factory=list)  # all from cite()
    safe_redirect: str = ""


def _repo_root() -> Path:
    # retrieval/ -> src/ -> tokenless-agent/ -> ai/ -> <project root>
    return Path(__file__).resolve().parents[4]


def _load_enrichment() -> dict[str, dict]:
    """category -> {refs: [str], redirect: str}. Empty on any failure (optional)."""
    root = _repo_root()
    for rel in _PROGRAMS_CANDIDATES:
        p = root / rel
        if not p.exists():
            continue
        out: dict[str, dict] = {}
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                cat = row.get("category")
                if not cat:
                    continue
                refs = [cw["reference"] for cw in row.get("counter_witnesses", [])
                        if cw.get("reference")]
                entry = out.setdefault(cat, {"refs": [], "redirect": ""})
                for r in refs:
                    if r not in entry["refs"]:
                        entry["refs"].append(r)
                if not entry["redirect"] and row.get("safe_redirect"):
                    entry["redirect"] = row["safe_redirect"]
            return out
        except Exception:
            return {}
    return {}


class CounterWitnessRetriever:
    """Resolve counter-witness scripture for a (already-decided) enforcement result."""

    def __init__(self, retriever: KJVRetriever | None = None) -> None:
        self._r = retriever or KJVRetriever()
        self._enrichment = _load_enrichment()

    def for_result(self, enforcement_result) -> list[GroundedCounterWitness]:
        """Return one GroundedCounterWitness per violation, with RETRIEVED citations."""
        out: list[GroundedCounterWitness] = []
        for v in getattr(enforcement_result, "violations", []) or []:
            cov_id = getattr(v, "covenant_id", "") or ""
            refs: list[str] = []

            # (1) GUARANTEED primary — the registry scripture ref on the violation
            primary = getattr(v, "scripture", "") or ""
            if primary:
                refs.append(primary)

            # (2) OPTIONAL enrichment — owner category map (refs only); the
            # redirect is the GENERIC per-category line, never the scenario-
            # specific first-row redirect (avoids "water-safety" on a bomb request).
            cat = _COVENANT_TO_CATEGORY.get(cov_id)
            redirect = _GENERIC_REDIRECT.get(cat or "", "")
            if cat and cat in self._enrichment:
                refs.extend(self._enrichment[cat]["refs"])

            # retrieve EXACT text; keep ONLY refs that resolve (no fabrication)
            citations: list[Citation] = []
            seen: set[str] = set()
            for ref in refs:
                c = self._r.cite(ref)
                if c is not None and c.ref not in seen:
                    citations.append(c)
                    seen.add(c.ref)

            out.append(GroundedCounterWitness(
                covenant_id=cov_id,
                rule=getattr(v, "rule", "") or "",
                citations=citations,
                safe_redirect=redirect,
            ))
        return out


class GroundedRefusalFormatter:
    """Assemble a deny + cite(retrieved) + redirect response.

    Accepts ONLY GroundedCounterWitness objects (whose citations are Citation
    instances produced by cite()). It cannot be handed a raw verse string, so it
    cannot emit fabricated scripture.
    """

    HEADER = "I cannot assist with that. This request is contrary to the governing covenant."

    def format(self, enforcement_result, counter_witnesses: list[GroundedCounterWitness]) -> str:
        lines: list[str] = [self.HEADER]

        # category / covenant line(s)
        cov_ids = [cw.covenant_id for cw in counter_witnesses if cw.covenant_id]
        rules = [cw.rule for cw in counter_witnesses if cw.rule]
        if cov_ids:
            cat = " / ".join(dict.fromkeys(f"{c}{(' '+r) if r else ''}"
                                           for c, r in zip(cov_ids, rules + [""] * len(cov_ids))))
            lines.append(f"Covenant: {cat}.")

        # counter-witness citations — RETRIEVED exact text only
        cited = [c for cw in counter_witnesses for c in cw.citations]
        # de-dup by ref, preserve order
        seen: set[str] = set()
        uniq = [c for c in cited if not (c.ref in seen or seen.add(c.ref))]
        if uniq:
            lines.append("Counter-witness (retrieved from KJV+Apocrypha — exact text):")
            for c in uniq:
                lines.append(f"  {c.ref}  {c.text}")
        else:
            # No scripture resolved: deny WITHOUT fabricating a verse.
            lines.append("(No counter-witness scripture could be retrieved; the denial stands "
                         "on the governing covenant.)")

        # safe redirect (optional, owner-authored)
        redirect = next((cw.safe_redirect for cw in counter_witnesses if cw.safe_redirect), "")
        if redirect:
            lines.append(f"I can help instead with: {redirect}.")

        return "\n".join(lines)

    @staticmethod
    def is_grounded(text: str, retriever: KJVRetriever) -> bool:
        """Provenance check: every verse-shaped line in `text` must match corpus text.
        Used by tests to PROVE no fabricated scripture entered the response."""
        import re
        ref_re = re.compile(r"^\s*([1-3]?[A-Z]{2,3} \d+:\d+)\s+(.+)$")
        for line in text.splitlines():
            m = ref_re.match(line)
            if not m:
                continue
            ref, body = m.group(1), m.group(2).strip()
            c = retriever.cite(ref)
            if c is None or c.text.strip() != body:
                return False
        return True
