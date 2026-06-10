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

# Whether agent-drafted SCRIPTURE witnesses may appear in PRODUCTION denials.
# DEFAULT OFF: until the Creator ratifies them (see COVENANT_WITNESS_RATIFICATION.md),
# draft scripture is NOT production-canonical — covenants ground on owner-authored /
# registry-primary witnesses only. The non-scripture safe-redirect text (guidance,
# not doctrine) is unaffected. Flip to True only after ratification.
_DRAFT_ENRICHMENT_PRODUCTION_ENABLED = False

# DRAFT enrichment for BLOCKING covenants the owner's v1 map does not cover
# (COV-003 Privacy, COV-006 Respect). Keyed by covenant_id (these covenants have
# no clean owner category). Every ref is grounded (verified to resolve via cite()).
#
# *** AGENT-DRAFTED — PENDING CREATOR RATIFICATION. ***  These scripture choices
# are NOT owner-canonized doctrine; the registry primary remains the guaranteed
# floor. They are GATED OFF from production by _DRAFT_ENRICHMENT_PRODUCTION_ENABLED
# until the Creator ratifies them.
_DRAFT_ENRICHMENT: dict[str, dict] = {
    "COV-003": {  # Privacy — registry primary: Proverbs 11:13
        "refs": ["Proverbs 11:13", "Proverbs 20:19", "Sirach 27:16", "Sirach 19:8"],
        "redirect": "lawful confidentiality, consent-based information handling, and data protection",
    },
    "COV-006": {  # Respect — registry primary: Proverbs 15:1
        "refs": ["Proverbs 15:1", "Proverbs 12:18", "Ephesians 4:29", "Sirach 28:17"],
        "redirect": "respectful communication, de-escalation, and constructive dialogue",
    },
}

# Citation ranking: most-direct witness first. Torah (Decalogue/commandment) ->
# OT/NT non-Torah (Writings/Prophets/Gospels/Epistles) -> Apocrypha. Matches the
# owner's stated preference order (e.g. harm: Exodus 20:13, Proverbs 3:29, Wisdom 1:13).
_TORAH = {"GEN", "EXO", "LEV", "NUM", "DEU"}
_APOCRYPHA = {"TOB", "JDT", "SIR", "WIS", "BAR", "1MA", "2MA", "BEL", "SUS", "MAN",
              "1ES", "2ES", "S3Y", "ESG"}


def _source_rank(ref: str) -> int:
    code = ref.split(" ", 1)[0]
    if code in _TORAH:
        return 0
    if code in _APOCRYPHA:
        return 2
    return 1


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

            # (3) DRAFT enrichment for blocking covenants the owner map does not cover
            # (COV-003 privacy, COV-006 respect). The non-scripture redirect (guidance)
            # is always available; the agent-drafted SCRIPTURE is gated OFF from
            # production until Creator ratification.
            if cov_id in _DRAFT_ENRICHMENT:
                if not redirect:
                    redirect = _DRAFT_ENRICHMENT[cov_id]["redirect"]
                if _DRAFT_ENRICHMENT_PRODUCTION_ENABLED:
                    refs.extend(_DRAFT_ENRICHMENT[cov_id]["refs"])

            # retrieve EXACT text; keep ONLY refs that resolve (no fabrication)
            citations: list[Citation] = []
            seen: set[str] = set()
            for ref in refs:
                c = self._r.cite(ref)
                if c is not None and c.ref not in seen:
                    citations.append(c)
                    seen.add(c.ref)

            # RANK: most-direct witness first (Torah -> OT/NT -> Apocrypha), stable
            # so insertion order is preserved within a rank.
            citations.sort(key=lambda c: _source_rank(c.ref))

            out.append(GroundedCounterWitness(
                covenant_id=cov_id,
                rule=getattr(v, "rule", "") or "",
                citations=citations,
                safe_redirect=redirect,
            ))
        return out

    def structured_payload(self, enforcement_result) -> dict:
        """Machine-readable refusal payload (for audit / UI / logs). Every
        counter-witness is retrieval-provenanced; nothing here is LM-generated."""
        cws = self.for_result(enforcement_result)
        action = getattr(enforcement_result, "action", None)
        return {
            "action": getattr(action, "name", str(action)),
            "blocked": bool(getattr(enforcement_result, "is_blocked", False)),
            "covenants": [
                {
                    "covenant_id": cw.covenant_id,
                    "rule": cw.rule,
                    "category": _COVENANT_TO_CATEGORY.get(cw.covenant_id),
                    "counter_witnesses": [
                        {"reference": c.ref, "source": "retrieval",
                         "resolved": True, "text": c.text}
                        for c in cw.citations
                    ],
                    "safe_redirect": cw.safe_redirect,
                    # draft SCRIPTURE only counts as draft when actually applied to
                    # production (flag on). Gated off => owner-authored witnesses only.
                    "enrichment_status": (
                        "agent_draft_pending_ratification"
                        if (_DRAFT_ENRICHMENT_PRODUCTION_ENABLED
                            and cw.covenant_id in _DRAFT_ENRICHMENT)
                        else "owner_authored"),
                }
                for cw in cws
            ],
        }


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
