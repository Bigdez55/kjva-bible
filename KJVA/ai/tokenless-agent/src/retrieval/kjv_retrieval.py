"""ai/tokenless-agent/src/retrieval/kjv_retrieval.py

Self-contained KJV+Apocrypha exact-verse retrieval over models v7's OWN corpus
(training/corpus/eng_kjv_clean_v1/corpus.txt — 36,822 verses, one "REF text" per
line). NO cross-repo dependency.

WHY THIS EXISTS (ADR product requirement): an 18.98M byte-LM CONFABULATES verses
under free generation ("PSA 105:1 The LORD is my strength…" is a hallucination).
Accurate scripture must be RETRIEVED from the corpus, never generated. This module
returns exact bytes with an exact-source pointer; the caller sets generation_invoked
=False so the LM never produces verse text.

API:
    r = get_retriever()
    r.cite("Psalm 105:1")     -> Citation(ref="PSA 105:1", text="O give thanks…", …)
    r.search("give thanks")   -> [Citation, …] ranked
    r.detect(message)         -> ScriptureIntent(kind="reference"|"search"|None, …)
    r.answer(message)         -> grounded response dict (generation_invoked=False) or None
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from functools import lru_cache

_THIS = Path(__file__).resolve()
# retrieval/ -> src/ -> tokenless-agent/ -> ai/ -> models v7/
_MODELS_V7 = _THIS.parents[4]
_CORPUS = _MODELS_V7 / "training" / "corpus" / "eng_kjv_clean_v1" / "corpus.txt"

# Natural book name / abbreviation -> canonical 3-letter corpus code.
# Codes are exactly those used in corpus.txt refs (e.g. "PSA 105:1").
_BOOK_ALIASES: dict[str, str] = {}


def _alias(code: str, *names: str) -> None:
    _BOOK_ALIASES[code.upper()] = code
    for n in names:
        _BOOK_ALIASES[n.lower().replace(" ", "")] = code


# Old Testament
_alias("GEN", "genesis", "gen", "gn"); _alias("EXO", "exodus", "exo")
_alias("LEV", "leviticus", "lev", "lv"); _alias("NUM", "numbers", "num", "nm")
_alias("DEU", "deuteronomy", "deut", "deu"); _alias("JOS", "joshua", "josh", "jos")
_alias("JDG", "judges", "judg", "jdg"); _alias("RUT", "ruth", "rut", "ru")
_alias("1SA", "1samuel", "1sam", "1sa", "isamuel"); _alias("2SA", "2samuel", "2sam", "2sa")
_alias("1KI", "1kings", "1kgs", "1ki"); _alias("2KI", "2kings", "2kgs", "2ki")
_alias("1CH", "1chronicles", "1chron", "1chr", "1ch"); _alias("2CH", "2chronicles", "2chron", "2chr", "2ch")
_alias("EZR", "ezra", "ezr"); _alias("NEH", "nehemiah", "neh"); _alias("EST", "esther", "est")
_alias("JOB", "job"); _alias("PSA", "psalm", "psalms", "psa", "ps", "pss")
_alias("PRO", "proverbs", "prov", "pro", "prv"); _alias("ECC", "ecclesiastes", "eccl", "ecc", "qoh")
_alias("SNG", "songofsolomon", "song", "sng", "canticles", "sos")
_alias("ISA", "isaiah", "isa"); _alias("JER", "jeremiah", "jer")
_alias("LAM", "lamentations", "lam"); _alias("EZK", "ezekiel", "ezek", "ezk")
_alias("DAN", "daniel", "dan", "dn"); _alias("HOS", "hosea", "hos")
_alias("JOL", "joel", "jol"); _alias("AMO", "amos", "amo")
_alias("OBA", "obadiah", "obad", "oba"); _alias("JON", "jonah", "jon")
_alias("MIC", "micah", "mic"); _alias("NAM", "nahum", "nam", "nah")
_alias("HAB", "habakkuk", "hab"); _alias("ZEP", "zephaniah", "zeph", "zep")
_alias("HAG", "haggai", "hag"); _alias("ZEC", "zechariah", "zech", "zec")
_alias("MAL", "malachi", "mal")
# New Testament
_alias("MAT", "matthew", "matt", "mat", "mt"); _alias("MRK", "mark", "mrk", "mk")
_alias("LUK", "luke", "luk", "lk"); _alias("JHN", "john", "jhn", "jn")
_alias("ACT", "acts", "act"); _alias("ROM", "romans", "rom")
_alias("1CO", "1corinthians", "1cor", "1co"); _alias("2CO", "2corinthians", "2cor", "2co")
_alias("GAL", "galatians", "gal"); _alias("EPH", "ephesians", "eph")
_alias("PHP", "philippians", "phil", "php"); _alias("COL", "colossians", "col")
_alias("1TH", "1thessalonians", "1thess", "1th"); _alias("2TH", "2thessalonians", "2thess", "2th")
_alias("1TI", "1timothy", "1tim", "1ti"); _alias("2TI", "2timothy", "2tim", "2ti")
_alias("TIT", "titus", "tit"); _alias("PHM", "philemon", "phlm", "phm")
_alias("HEB", "hebrews", "heb"); _alias("JAS", "james", "jas", "jms")
_alias("1PE", "1peter", "1pet", "1pe"); _alias("2PE", "2peter", "2pet", "2pe")
_alias("1JN", "1john", "1jn", "1jhn"); _alias("2JN", "2john", "2jn")
_alias("3JN", "3john", "3jn"); _alias("JUD", "jude", "jud")
_alias("REV", "revelation", "rev", "apocalypse")
# Apocrypha (codes as they appear in the corpus)
_alias("TOB", "tobit", "tob"); _alias("JDT", "judith", "jdt")
_alias("WIS", "wisdom", "wisdomofsolomon", "wis"); _alias("SIR", "sirach", "ecclesiasticus", "sir")
_alias("BAR", "baruch", "bar"); _alias("1MA", "1maccabees", "1macc", "1ma")
_alias("2MA", "2maccabees", "2macc", "2ma"); _alias("MAN", "prayerofmanasseh", "man")
_alias("BEL", "belandthedragon", "bel"); _alias("SUS", "susanna", "sus")

# "Book Chapter:Verse" — book may be "1 John", "Psalm", "song of solomon", a code, etc.
_REF_RE = re.compile(
    r"\b((?:[123]\s*)?[A-Za-z][A-Za-z ]{1,24}?)\s*\.?\s*(\d{1,3})\s*[:.]\s*(\d{1,3})\b")


@dataclass(frozen=True)
class Citation:
    ref: str
    text: str
    source: str = "eng_kjv_clean_v1"        # exact-source pointer (ADR §8 / §11)
    score: float = 1.0


@dataclass(frozen=True)
class ScriptureIntent:
    kind: str | None                          # "reference" | "search" | None
    refs: list[str] = field(default_factory=list)
    query: str = ""


def _normalize_book(token: str) -> str | None:
    # The ref regex may capture leading filler ("What does John" before "3:16").
    # Try the longest valid word-suffix: "What does John"->"John", "1 John" stays.
    words = token.strip().split()
    for start in range(len(words)):
        cand = "".join(words[start:]).lower()
        if cand in _BOOK_ALIASES:
            return _BOOK_ALIASES[cand]
    up = token.strip().upper().replace(" ", "")
    return up if up in _BOOK_ALIASES.values() else None


class KJVRetriever:
    """Exact-verse retrieval over the local clean corpus. Read-only, deterministic."""

    def __init__(self, corpus_path: Path = _CORPUS) -> None:
        self.corpus_path = corpus_path
        self._verses: dict[str, str] = {}
        self._order: list[str] = []
        self._load()

    def _load(self) -> None:
        if not self.corpus_path.exists():
            raise FileNotFoundError(f"KJV corpus not found: {self.corpus_path}")
        line_re = re.compile(r"^([1-3A-Z]{2,3} \d{1,3}:\d{1,3}) (.*)$")
        for raw in self.corpus_path.read_text(encoding="utf-8").splitlines():
            m = line_re.match(raw)
            if not m:
                continue
            ref, text = m.group(1), m.group(2).lstrip("¶ ").strip()
            self._verses[ref] = text
            self._order.append(ref)

    # ── exact citation ────────────────────────────────────────────────────────
    def normalize_ref(self, ref: str) -> str | None:
        m = _REF_RE.search(ref)
        if not m:
            return None
        code = _normalize_book(m.group(1))
        if not code:
            return None
        return f"{code} {int(m.group(2))}:{int(m.group(3))}"

    def cite(self, ref: str) -> Citation | None:
        norm = self.normalize_ref(ref)
        if norm and norm in self._verses:
            return Citation(ref=norm, text=self._verses[norm])
        return None

    # ── keyword search (deterministic scoring; no LM) ─────────────────────────
    def search(self, query: str, top_k: int = 5) -> list[Citation]:
        terms = [t for t in re.findall(r"[a-zA-Z]+", query.lower()) if len(t) > 2]
        if not terms:
            return []
        scored: list[tuple[float, str]] = []
        for ref in self._order:
            low = self._verses[ref].lower()
            hits = sum(low.count(t) for t in terms)
            if hits:
                # phrase bonus if the full query substring appears
                bonus = 2.0 if query.strip().lower() in low else 0.0
                scored.append((hits + bonus, ref))
        scored.sort(key=lambda x: (-x[0], self._order.index(x[1])))
        out = []
        for sc, ref in scored[:top_k]:
            out.append(Citation(ref=ref, text=self._verses[ref], score=float(sc)))
        return out

    # ── intent detection ──────────────────────────────────────────────────────
    def detect(self, message: str) -> ScriptureIntent:
        refs = []
        for m in _REF_RE.finditer(message):
            code = _normalize_book(m.group(1))
            if code:
                refs.append(f"{code} {int(m.group(2))}:{int(m.group(3))}")
        if refs:
            return ScriptureIntent(kind="reference", refs=refs)
        scripture_cue = re.search(
            r"\b(verse|scripture|bible|kjv|psalm|gospel|what does .* say|quote)\b",
            message, re.I)
        if scripture_cue:
            return ScriptureIntent(kind="search", query=message)
        return ScriptureIntent(kind=None)

    # ── grounded answer (the product surface; LM never writes verse text) ─────
    def answer(self, message: str) -> dict | None:
        intent = self.detect(message)
        if intent.kind == "reference":
            cits = [self.cite(r) for r in intent.refs]
            cits = [c for c in cits if c]
            if cits:
                body = "\n".join(f"{c.ref}  {c.text}" for c in cits)
                return {"text": body, "generation_invoked": False,
                        "grounded": True, "citations": [c.ref for c in cits],
                        "source": "eng_kjv_clean_v1"}
            return {"text": "That reference is not in the KJV+Apocrypha corpus.",
                    "generation_invoked": False, "grounded": True, "citations": []}
        if intent.kind == "search":
            cits = self.search(message, top_k=3)
            if cits:
                body = "\n".join(f"{c.ref}  {c.text}" for c in cits)
                return {"text": body, "generation_invoked": False,
                        "grounded": True, "citations": [c.ref for c in cits],
                        "source": "eng_kjv_clean_v1"}
        return None  # not a scripture query — caller routes elsewhere

    @property
    def verse_count(self) -> int:
        return len(self._verses)


@lru_cache(maxsize=1)
def get_retriever() -> KJVRetriever:
    return KJVRetriever()
