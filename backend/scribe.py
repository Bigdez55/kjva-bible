"""
scribe.py — KJVA Apex Scribe Orchestrator (ScribeAnswerEngine).

One unified function over the corpus. The user enters one prompt; the engine infers
intent and answers as a scripture-grounded scribe: reference -> exact text; quote ->
its source; topic/word/question -> direct matches + related terms + witnesses grouped
across the canon + a deterministic exegetical breakdown + follow-up paths.

Doctrine: the CORPUS is the scripture database; this engine is the scribe over it. Every
verse and reference returned is real (retrieved, never generated). A reference that does
not resolve ABSTAINS — it never falls through to generation. The 18M model is NOT used
here yet (deferred per the execution spec: build retrieval/graph/planner first, then train
scribe behavior). All organization below is deterministic and corpus-grounded.
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional

from corpus import _content_tokens, _norm, _QUESTION_WORDS, _STOPWORDS, get_index

# ---- canon sections (finer than ot/nt/apocrypha) --------------------------
_SECTION_OF: dict[str, str] = {}
_SECTIONS: list[tuple[str, str, list[str]]] = [
    ("torah", "Torah / Law", ["GEN", "EXO", "LEV", "NUM", "DEU"]),
    ("history", "History", ["JOS", "JDG", "RUT", "1SA", "2SA", "1KI", "2KI",
                            "1CH", "2CH", "EZR", "NEH", "EST"]),
    ("writings", "Writings / Wisdom", ["JOB", "PSA", "PRO", "ECC", "SNG"]),
    ("prophets", "Prophets", ["ISA", "JER", "LAM", "EZK", "DAN", "HOS", "JOL", "AMO",
                              "OBA", "JON", "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL"]),
    ("gospels", "Gospels", ["MAT", "MRK", "LUK", "JHN"]),
    ("acts", "Acts", ["ACT"]),
    ("epistles", "Epistles", ["ROM", "1CO", "2CO", "GAL", "EPH", "PHP", "COL", "1TH", "2TH",
                              "1TI", "2TI", "TIT", "PHM", "HEB", "JAS", "1PE", "2PE",
                              "1JN", "2JN", "3JN", "JUD"]),
    ("apocalypse", "Apocalypse", ["REV"]),
    ("apocrypha", "Apocrypha", ["TOB", "JDT", "ESG", "WIS", "SIR", "BAR", "S3Y", "SUS",
                                "BEL", "1MA", "2MA", "1ES", "MAN", "2ES"]),
]
_SECTION_ORDER = [key for key, _name, _books in _SECTIONS]
_SECTION_NAME = {key: name for key, name, _books in _SECTIONS}
for _key, _name, _books in _SECTIONS:
    for _b in _books:
        _SECTION_OF[_b] = _key

# Scope -> allowed canon_category set (for the follow-up "Torah only / NT / Apocrypha").
_SCOPE_CANON = {
    "ot": {"old_testament"}, "nt": {"new_testament"}, "apocrypha": {"apocrypha"},
    "torah": {"old_testament"},  # narrowed further by section below
}

# Curated thematic lexicon: topic -> related KJV/Apocrypha terms (all appear in corpus).
# Seeds the topic graph for common themes; unknown topics fall back to stem + co-occurrence.
_THEMATIC_LEXICON: dict[str, list[str]] = {
    "enemies": ["enemy", "enemies", "adversary", "adversaries", "foe", "foes", "wicked",
                "persecute", "persecuted", "oppress", "oppressor", "hate", "hateth",
                "haters", "avenge", "vengeance", "smite"],
    "wisdom": ["wisdom", "wise", "understanding", "knowledge", "prudence", "instruction",
               "counsel", "discretion", "folly", "fool"],
    "faith": ["faith", "faithful", "believe", "believed", "trust", "belief", "assurance"],
    "law": ["law", "commandment", "commandments", "statutes", "judgments", "ordinances",
            "precepts", "testimonies"],
    "commandments": ["commandment", "commandments", "statutes", "precepts", "law", "ordinances"],
    "mercy": ["mercy", "merciful", "mercies", "compassion", "pity", "kindness",
              "lovingkindness", "forgive"],
    "false witness": ["witness", "false", "lie", "lying", "lieth", "deceit", "slander", "testify"],
    "idolatry": ["idol", "idols", "idolatry", "graven", "image", "images", "gods", "abomination"],
    "oppression": ["oppress", "oppression", "oppressor", "afflict", "affliction", "vex", "burden"],
    "sabbath": ["sabbath", "sabbaths", "rest", "seventh", "hallow", "holy"],
    "kingdom": ["kingdom", "king", "reign", "throne", "dominion", "heaven"],
    "resurrection": ["resurrection", "raise", "raised", "rise", "risen", "dead", "live"],
    "grace": ["grace", "gracious", "favour", "mercy", "gift"],
    "judgment": ["judgment", "judge", "judged", "condemn", "recompense", "justice"],
    "love": ["love", "loved", "charity", "beloved", "lovingkindness", "affection"],
    "fear": ["fear", "feared", "afraid", "dread", "terror", "reverence"],
    "hope": ["hope", "hoped", "trust", "expectation", "wait"],
    "sin": ["sin", "sins", "sinned", "iniquity", "transgression", "trespass", "wickedness"],
    "righteousness": ["righteous", "righteousness", "just", "justice", "upright", "integrity"],
    "prayer": ["pray", "prayer", "prayed", "supplication", "intercession", "beseech"],
    "forgiveness": ["forgive", "forgiven", "pardon", "mercy", "blot"],
    "repentance": ["repent", "repented", "turn", "return", "contrite"],
    "salvation": ["salvation", "save", "saved", "saviour", "deliver", "redeem", "redemption"],
    "covenant": ["covenant", "oath", "promise", "vow"],
    "shepherd": ["shepherd", "shepherds", "sheep", "flock", "pasture", "fold"],
}


class ScribeAnswerEngine:
    """Stateless orchestrator over the verse index. Construct once; call answer()."""

    def __init__(self) -> None:
        self.index = get_index()

    # ---- intent ----------------------------------------------------------
    def classify_intent(self, query: str, parsed: dict) -> str:
        if parsed["is_reference_attempt"]:
            if parsed["status"] != "FOUND":
                return "INVALID_REFERENCE"
            return "REFERENCE_RANGE" if len(parsed["references"]) > 1 else "EXACT_REFERENCE"
        ql = query.strip().lower()
        words = [w for w in _norm(query).split() if w not in _STOPWORDS]
        if re.match(r"^(cross[\s-]?references?|x-?ref|related to|references? for|parallels? (to|for))\b", ql):
            return "CROSS_REFERENCE"
        if re.match(r"^(doctrine of|the doctrine|teaching on|study on the doctrine)\b", ql) or "doctrine" in words:
            return "DOCTRINE_STUDY"
        if re.match(r"^(explain|define|meaning of|what is|what does|what do)\b", ql):
            return "GENERAL_SCRIBE_EXPLANATION"
        if "?" in query or any(w in _norm(query).split() for w in _QUESTION_WORDS):
            return "QUESTION_ANSWER"
        if len(words) == 1:
            return "WORD_STUDY"
        if len(words) <= 3:
            return "TOPIC_SEARCH"
        return "KEYWORD_SEARCH"

    # Intents that should surface a grounded Q&A block (Answer / Witnesses / Explanation).
    _QA_INTENTS = {"QUESTION_ANSWER", "GENERAL_SCRIBE_EXPLANATION"}
    _DOCTRINE_INTENTS = {"DOCTRINE_STUDY"}

    @staticmethod
    def _strip_intent_prefix(query: str) -> str:
        """Strip a leading intent cue ('cross reference ...', 'doctrine of ...',
        'explain ...') so the remainder can be parsed/searched as the real subject."""
        return re.sub(
            r"^\s*(cross[\s-]?references?|x-?ref|related to|references? for|parallels? (to|for)|"
            r"doctrine of|the doctrine of|teaching on|explain|define|meaning of|what is|what does|what do)\b[:\s]*",
            "", query.strip(), flags=re.IGNORECASE,
        ).strip() or query.strip()

    # ---- related-term expansion (the topic/word graph) -------------------
    def expand_terms(self, query: str, *, limit: int = 12) -> list[str]:
        ix = self.index
        base = [w for w in _content_tokens(query) if w not in _QUESTION_WORDS]
        if not base:
            base = _content_tokens(query)
        out: list[str] = []
        seen: set[str] = set()

        def add(term: str) -> None:
            t = term.lower()
            if t in seen or t not in ix._inverted:   # must be a real corpus term
                return
            seen.add(t)
            out.append(t)

        # 1) the literal query terms
        for t in base:
            add(t)
        # 2) curated thematic lexicon (exact query, or any base term that is a topic key)
        had_curated = False
        for key in (query.strip().lower(), *base):
            rels = _THEMATIC_LEXICON.get(key)
            if rels:
                had_curated = True
                for rel in rels:
                    add(rel)
        # 3) stem expansion ONLY for topics the curated lexicon does not cover — curated
        #    topics already carry their morphology, and broad stems pull false friends
        #    ("mercy" -> "merchant"). For unknown topics, share a 4-char prefix.
        if not had_curated:
            for t in base:
                if len(t) >= 4:
                    stem = t[:4]
                    for cand in ix._inverted:
                        if cand.startswith(stem):
                            add(cand)
                    if len(out) >= limit * 2:
                        break
        # 4) corpus co-occurrence: terms frequently sharing verses with the base terms,
        #    down-weighted by global frequency (avoid generic words).
        cooc: dict[str, float] = {}
        for t in base:
            postings = ix._inverted.get(t, ())[:1500]
            for idx in postings:
                for term in set(_content_tokens(ix._all[idx]["text"])):
                    if term in seen or term in base:
                        continue
                    idf = math.log(ix._n_docs / max(1, ix._doc_freq.get(term, 1)))
                    if idf < 1.5:           # skip very common words
                        continue
                    cooc[term] = cooc.get(term, 0.0) + idf
        for term, _score in sorted(cooc.items(), key=lambda kv: -kv[1])[:6]:
            add(term)

        return out[:limit]

    # ---- retrieval over expanded terms -----------------------------------
    def _gather(self, terms: list[str], *, scope_canon: Optional[set[str]],
                section: Optional[str], limit: int) -> list[dict]:
        """Collect verses matching ANY expanded term, scored by how many distinct
        expanded terms they contain, weighted by term rarity. Real verses only."""
        ix = self.index
        weights = {t: math.log(ix._n_docs / max(1, ix._doc_freq.get(t, 1))) for t in terms}
        score: dict[int, float] = {}
        matched: dict[int, set[str]] = {}
        for t in terms:
            for idx in ix._inverted.get(t, ()):
                v = ix._all[idx]
                if scope_canon and v["canon_category"] not in scope_canon:
                    continue
                if section and _SECTION_OF.get(v["book"]) != section:
                    continue
                score[idx] = score.get(idx, 0.0) + weights[t]
                matched.setdefault(idx, set()).add(t)
        ranked = sorted(score.items(),
                        key=lambda kv: (-len(matched[kv[0]]), -kv[1], ix._all[kv[0]]["book_order"]))
        out = []
        for idx, sc in ranked[:max(1, limit)]:
            v = ix._all[idx]
            out.append(ix._verse_out(v, sc, sorted(matched[idx], key=lambda t: -weights[t])))
        return out

    def group_by_section(self, verses: list[dict]) -> list[dict]:
        buckets: dict[str, list[dict]] = {}
        for v in verses:
            buckets.setdefault(_SECTION_OF.get(v["book_code"], "other"), []).append(v)
        groups = []
        for key in _SECTION_ORDER:
            if buckets.get(key):
                groups.append({"section": key, "name": _SECTION_NAME[key], "verses": buckets[key]})
        return groups

    # ---- exegetical planner (deterministic, grounded) --------------------
    def _plan_topic(self, query: str, terms: list[str], groups: list[dict],
                    witnesses: list[dict]) -> dict:
        sections_present = [g["name"] for g in groups]
        return {
            "definition": (
                f"Scriptures across the KJV + Apocrypha corpus on '{query.strip()}'. "
                f"Related terms searched: {', '.join(terms[:8])}."
            ),
            "structure": [
                "Direct witnesses (the term itself)",
                "Related-term witnesses",
                "Grouped by canon section",
                "Synthesis (only from the verses below)",
            ],
            "synthesis": (
                f"{len(witnesses)} witnesses span {len(groups)} canon section(s): "
                f"{', '.join(sections_present)}. The theme recurs line upon line across these "
                f"sections; the synthesis rests only on the retrieved verses — no claim beyond them."
            ),
            "takeaway": (
                "These are the corpus witnesses for the theme. Interpretation should not exceed "
                "what the cited verses state; deeper theological cross-reference is a later, curated layer."
            ),
        }

    def _plan_verse(self, verse: dict, xrefs: list[dict]) -> dict:
        return {
            "structure": ["Exact verse", "Immediate context", "Key terms",
                          "Cross-references", "Canonical theme", "Caution against overclaiming"],
            "key_terms": sorted(set(_content_tokens(verse["text"])),
                                key=lambda t: -math.log(self.index._n_docs /
                                                        max(1, self.index._doc_freq.get(t, 1))))[:8],
            "cross_reference_count": len(xrefs),
            "takeaway": "Exact scripture above; cross-references are lexical/topical, not yet theological. "
                        "Do not overclaim beyond the cited text.",
        }

    def _plan_doctrine(self, query: str, groups: list[dict], witnesses: list[dict]) -> dict:
        return {
            "structure": ["Core claim", "Supporting scriptures", "Boundary scriptures",
                          "Tensions / harmonization", "Conclusion"],
            "core_claim": f"Doctrine study of '{query.strip()}', grounded only in the witnesses below.",
            "supporting_count": len(witnesses),
            "sections_present": [g["name"] for g in groups],
            "takeaway": "Presented as the corpus witnesses attest. Boundary cases, tensions, and "
                        "harmonization need curated doctrine maps (a later layer) — do not treat this "
                        "lexical gathering as settled systematic doctrine.",
        }

    def _format_qa(self, question: str, witnesses: list[dict]) -> dict:
        """The spec's grounded Q&A block: Answer / Scripture witnesses / Explanation.
        Retrieval-only; no uncited claims, no fabricated references."""
        if not witnesses:
            return {"answer": "I do not have a grounded verse match for that question in the "
                              "KJV+Apocrypha corpus.", "witnesses": [], "explanation": ""}
        top = witnesses[:3]
        return {
            "answer": f"The corpus answers '{question.strip()}' through {len(top)} "
                      f"witness{'es' if len(top) != 1 else ''} (retrieved, not generated):",
            "witnesses": [{"reference": w["reference"], "text": w["text"]} for w in top],
            "explanation": "Synthesis rests only on the retrieved verses above; no claim is made "
                           "beyond what they state, and no reference is invented.",
        }

    # ---- the unified entry point -----------------------------------------
    def answer(self, query: str, *, book: str = "", canon: str = "",
               scope: str = "", limit: int = 12) -> dict:
        ix = self.index
        q = (query or "").strip()
        base = {"query": q, "intent": "none", "status": "INVALID", "answer": "",
                "primary": [], "related_terms": [], "witnesses_by_section": [],
                "cross_references": [], "exegesis": None, "qa": None,
                "follow_up": [], "reason": "", "scope": scope or "full"}
        if not q:
            return {**base, "reason": "Empty query."}

        book_code = ix._resolve_book_code(book) if book else None
        if book and book_code is None:
            return {**base, "reason": f"'{book}' is not a recognized book."}
        canon_v = ix._canon_of(canon)
        scope_canon = _SCOPE_CANON.get(scope) if scope else None
        section = "torah" if scope == "torah" else None
        if canon_v:
            scope_canon = {canon_v} if not scope_canon else (scope_canon & {canon_v})

        # Detect an explicit intent cue and extract the real SUBJECT so the cue words
        # ("cross reference ...", "doctrine of ...", "explain ...") don't pollute parsing.
        ql = q.lower()
        cue = None
        if re.match(r"^(cross[\s-]?references?|x-?ref|related to|references? for|parallels? (to|for))\b", ql):
            cue = "CROSS_REFERENCE"
        elif re.match(r"^(doctrine of|the doctrine|teaching on)\b", ql) or "doctrine" in _norm(q).split():
            cue = "DOCTRINE_STUDY"
        elif re.match(r"^(explain|define|meaning of)\b", ql):
            cue = "GENERAL_SCRIBE_EXPLANATION"
        subject = self._strip_intent_prefix(q) if cue else q

        parsed = ix.parse_reference(subject)
        intent = cue or self.classify_intent(subject, parsed)

        # Reference / range -> exact corpus text + cross-references (corpus-locked).
        if parsed["is_reference_attempt"]:
            if parsed["status"] != "FOUND":
                return {**base, "intent": "INVALID_REFERENCE", "status": parsed["status"],
                        "reason": parsed["reason"]}
            results = parsed["results"]
            primary = [ix._verse_out(v, 1.0, []) for v in results]
            xrefs = ix._auto_xref(results, limit=limit)
            if intent == "CROSS_REFERENCE":
                answer = (f"Cross-references for {primary[0]['reference']} (lexical/topical) — "
                          f"{len(xrefs)} related passages.")
            else:
                answer = f"{primary[0]['reference']} — {primary[0]['text']}"
            return {**base, "intent": intent, "status": "FOUND",
                    "answer": answer, "primary": primary, "cross_references": xrefs,
                    "exegesis": self._plan_verse(results[0], xrefs)}

        # Exact quote -> source verse + cross-references.
        quote = ix._exact_quote(subject, book_code, canon_v)
        if quote:
            xrefs = ix._auto_xref([quote], limit=limit)
            return {**base, "intent": "REFERENCE_PREFIX", "status": "FOUND",
                    "answer": f"{quote['ref']} — {quote['text']}",
                    "primary": [ix._verse_out(quote, 1.0, [])], "cross_references": xrefs,
                    "exegesis": self._plan_verse(quote, xrefs)}

        # Topic / word / question / doctrine -> expansion + grouped witnesses + plan.
        terms = self.expand_terms(subject, limit=limit)
        witnesses = self._gather(terms, scope_canon=scope_canon, section=section, limit=40)
        if not witnesses:
            return {**base, "intent": intent, "status": "NOT_FOUND", "related_terms": terms,
                    "qa": (self._format_qa(q, []) if intent in self._QA_INTENTS else None),
                    "reason": f"No scripture in the corpus matches '{subject}'"
                              + (f" within {scope or canon}." if (scope or canon) else ".")}
        groups = self.group_by_section(witnesses)
        literal = [w for w in _content_tokens(subject) if w not in _QUESTION_WORDS] or _content_tokens(subject)
        direct = [w for w in witnesses if any(t in w["matched_terms"] for t in literal)][:8]
        primary = direct or witnesses[:8]
        n = len(witnesses)
        answer = (
            f"'{subject}' appears across {len(groups)} section(s) of the canon — "
            f"{n} witnesses (real scripture). Related terms: {', '.join(terms[:8])}."
        )
        follow_up = [
            {"label": "Torah only", "scope": "torah"},
            {"label": "New Testament", "scope": "nt"},
            {"label": "Apocrypha", "scope": "apocrypha"},
            {"label": "Full canon", "scope": "full"},
        ]
        exegesis = (self._plan_doctrine(subject, groups, witnesses)
                    if intent in self._DOCTRINE_INTENTS
                    else self._plan_topic(subject, terms, groups, witnesses))
        qa = self._format_qa(q, primary) if intent in self._QA_INTENTS else None
        return {**base, "intent": intent, "status": "FOUND", "answer": answer,
                "primary": primary, "related_terms": terms,
                "witnesses_by_section": groups, "follow_up": follow_up,
                "exegesis": exegesis, "qa": qa}


_engine: Optional[ScribeAnswerEngine] = None


def get_scribe() -> ScribeAnswerEngine:
    global _engine
    if _engine is None:
        _engine = ScribeAnswerEngine()
    return _engine
