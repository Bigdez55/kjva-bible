"""
corpus.py — In-memory verse index built from verses.jsonl at startup.

THE CORPUS IS THE SCRIPTURE DATABASE. The model is the scribe interface over it.
Every scripture result returned here is exact retrieved text — never generated.

Loads once at startup (~36,822 records). Reference lookup is O(1) dict access;
search / cross-reference / Q&A use an inverted term index built at load time.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Optional


def _norm(text: str) -> str:
    """Lowercase and strip punctuation for fuzzy text comparison."""
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "in", "is", "it", "to", "for",
    "with", "be", "by", "as", "at", "from", "on", "are", "was", "were",
    "unto", "thy", "thee", "thou", "thine", "hath", "shall", "will",
    "that", "which", "this", "these", "those", "them", "they", "their",
    "he", "she", "his", "her", "him", "we", "us", "our", "you", "your",
    "i", "me", "my", "but", "not", "all", "no", "so", "if", "then",
    "shalt", "ye", "have", "had", "him", "into", "out", "up", "down",
    "o", "lo", "yea", "also", "when", "where", "there", "here", "now",
})

# Question words stripped from Q&A queries before keyword retrieval.
_QUESTION_WORDS = frozenset({
    "what", "who", "whom", "whose", "why", "how", "when", "where", "which",
    "does", "do", "did", "is", "are", "was", "were", "can", "should", "would",
    "tell", "about", "say", "says", "said", "mean", "means", "bible", "scripture",
    "verse", "verses", "god", "lord",
})

_DATA_DIR = Path(__file__).parent.parent / "data"
_VERSES_PATH = _DATA_DIR / "verses.jsonl"

# Canon-section aliases accepted in filters.
_CANON_ALIASES = {
    "ot": "old_testament", "old": "old_testament", "old_testament": "old_testament",
    "nt": "new_testament", "new": "new_testament", "new_testament": "new_testament",
    "apoc": "apocrypha", "apocrypha": "apocrypha", "deuterocanon": "apocrypha",
}

# Leading numeral normalization: roman numerals & ordinals -> digit. Applied to the
# book part of a reference so "II Timothy", "Second Timothy", "2 Tim" all collapse.
_NUM_PREFIX = {
    "i": "1", "ii": "2", "iii": "3",
    "1st": "1", "2nd": "2", "3rd": "3",
    "first": "1", "second": "2", "third": "3",
    "1": "1", "2": "2", "3": "3",
}

# Curated book aliases (digit-normalized; roman/ordinal handled by _normalize_book_token
# BEFORE lookup, so only digit forms are registered here). Codes + book names are also
# auto-registered from the corpus at load time. This is BOOK-NAME normalization — not
# per-verse hardcoding. Ambiguous 2-char stubs are deliberately omitted.
_CURATED_ALIASES: dict[str, str] = {
    "gn": "GEN", "gen": "GEN",
    "ex": "EXO", "exo": "EXO", "exod": "EXO",
    "lv": "LEV", "lev": "LEV",
    "nm": "NUM", "nu": "NUM", "num": "NUM", "numb": "NUM",
    "dt": "DEU", "deu": "DEU", "deut": "DEU",
    "jos": "JOS", "josh": "JOS", "jsh": "JOS",
    "jdg": "JDG", "judg": "JDG", "jg": "JDG",
    "ru": "RUT", "rut": "RUT", "rth": "RUT",
    "1sa": "1SA", "1sam": "1SA", "1 sam": "1SA", "1 sa": "1SA",
    "2sa": "2SA", "2sam": "2SA", "2 sam": "2SA", "2 sa": "2SA",
    "1ki": "1KI", "1kgs": "1KI", "1 kgs": "1KI", "1 ki": "1KI", "1kg": "1KI",
    "2ki": "2KI", "2kgs": "2KI", "2 kgs": "2KI", "2 ki": "2KI", "2kg": "2KI",
    "1ch": "1CH", "1chr": "1CH", "1chron": "1CH", "1 chr": "1CH", "1 ch": "1CH",
    "2ch": "2CH", "2chr": "2CH", "2chron": "2CH", "2 chr": "2CH", "2 ch": "2CH",
    "ezr": "EZR", "ezra": "EZR",
    "neh": "NEH",
    "est": "EST", "esth": "EST",
    "jb": "JOB", "job": "JOB",
    "ps": "PSA", "psa": "PSA", "pss": "PSA", "pslm": "PSA", "psalm": "PSA", "psalms": "PSA",
    "pr": "PRO", "pro": "PRO", "prv": "PRO", "prov": "PRO",
    "ec": "ECC", "ecc": "ECC", "eccl": "ECC", "eccles": "ECC", "qoh": "ECC",
    "sng": "SNG", "song": "SNG", "sos": "SNG", "cant": "SNG",
    "canticles": "SNG", "song of songs": "SNG", "song of solomon": "SNG",
    "is": "ISA", "isa": "ISA", "isai": "ISA",
    "jer": "JER",
    "lam": "LAM",
    "ezk": "EZK", "eze": "EZK", "ezek": "EZK",
    "dn": "DAN", "dan": "DAN",
    "hos": "HOS",
    "jl": "JOL", "joe": "JOL", "joel": "JOL",
    "am": "AMO", "amo": "AMO", "amos": "AMO",
    "ob": "OBA", "oba": "OBA", "obad": "OBA",
    "jon": "JON", "jnh": "JON", "jonah": "JON",
    "mic": "MIC", "micah": "MIC",
    "nam": "NAM", "nah": "NAM", "nahum": "NAM",
    "hab": "HAB", "habak": "HAB",
    "zep": "ZEP", "zph": "ZEP", "zeph": "ZEP",
    "hag": "HAG",
    "zec": "ZEC", "zch": "ZEC", "zech": "ZEC",
    "mal": "MAL",
    "tob": "TOB", "tobit": "TOB",
    "jdt": "JDT", "jth": "JDT", "judith": "JDT",
    "esg": "ESG", "esther greek": "ESG", "greek esther": "ESG",
    "additions to esther": "ESG", "add esth": "ESG",
    "wis": "WIS", "wisd": "WIS", "wisdom": "WIS", "wisdom of solomon": "WIS",
    "sir": "SIR", "ecclus": "SIR", "sirach": "SIR", "ecclesiasticus": "SIR",
    "bar": "BAR", "baruch": "BAR",
    "s3y": "S3Y", "song of three": "S3Y", "song of the three": "S3Y",
    "prayer of azariah": "S3Y", "three children": "S3Y",
    "sus": "SUS", "susanna": "SUS",
    "bel": "BEL", "bel and the dragon": "BEL",
    "1ma": "1MA", "1mac": "1MA", "1macc": "1MA", "1 macc": "1MA", "1 mac": "1MA",
    "2ma": "2MA", "2mac": "2MA", "2macc": "2MA", "2 macc": "2MA", "2 mac": "2MA",
    "1es": "1ES", "1esd": "1ES", "1 esd": "1ES", "1 esdras": "1ES",
    "2es": "2ES", "2esd": "2ES", "2 esd": "2ES", "2 esdras": "2ES",
    "man": "MAN", "pr man": "MAN", "prayer of manasses": "MAN",
    "prayer of manasseh": "MAN", "manasses": "MAN", "manasseh": "MAN",
    "mt": "MAT", "mat": "MAT", "matt": "MAT", "matth": "MAT",
    "mk": "MRK", "mr": "MRK", "mrk": "MRK", "mark": "MRK",
    "lk": "LUK", "lu": "LUK", "luk": "LUK", "luke": "LUK",
    "jn": "JHN", "jhn": "JHN", "joh": "JHN", "john": "JHN",
    "ac": "ACT", "act": "ACT", "acts": "ACT",
    "ro": "ROM", "rom": "ROM", "rm": "ROM",
    "1co": "1CO", "1cor": "1CO", "1 cor": "1CO", "1 co": "1CO",
    "2co": "2CO", "2cor": "2CO", "2 cor": "2CO", "2 co": "2CO",
    "ga": "GAL", "gal": "GAL",
    "eph": "EPH",
    "php": "PHP", "phil": "PHP", "philip": "PHP", "phlp": "PHP",
    "col": "COL",
    "1th": "1TH", "1thess": "1TH", "1thes": "1TH", "1 thess": "1TH", "1 th": "1TH",
    "2th": "2TH", "2thess": "2TH", "2thes": "2TH", "2 thess": "2TH", "2 th": "2TH",
    "1ti": "1TI", "1tim": "1TI", "1 tim": "1TI", "1 ti": "1TI",
    "2ti": "2TI", "2tim": "2TI", "2 tim": "2TI", "2 ti": "2TI",
    "tit": "TIT", "titus": "TIT",
    "phm": "PHM", "phlm": "PHM", "philem": "PHM", "philemon": "PHM",
    "heb": "HEB", "hebr": "HEB", "hebrews": "HEB",
    "jas": "JAS", "jam": "JAS", "jm": "JAS", "james": "JAS",
    "1pe": "1PE", "1pet": "1PE", "1 pet": "1PE", "1 pe": "1PE", "1pt": "1PE",
    "2pe": "2PE", "2pet": "2PE", "2 pet": "2PE", "2 pe": "2PE", "2pt": "2PE",
    "1jn": "1JN", "1jhn": "1JN", "1 jn": "1JN", "1 john": "1JN", "1joh": "1JN",
    "2jn": "2JN", "2jhn": "2JN", "2 jn": "2JN", "2 john": "2JN",
    "3jn": "3JN", "3jhn": "3JN", "3 jn": "3JN", "3 john": "3JN",
    "jud": "JUD", "jude": "JUD",
    "rev": "REV", "rv": "REV", "apoc": "REV", "apocalypse": "REV",
    "revelation": "REV", "revelations": "REV",
}


def _normalize_book_token(name: str) -> str:
    """Normalize a book name/abbrev for alias lookup: lowercase, drop punctuation,
    collapse whitespace, convert a leading roman numeral / ordinal word to a digit."""
    s = re.sub(r"[^\w\s]", " ", name.strip().lower())
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(r"^(i{1,3}|1st|2nd|3rd|first|second|third|[123])\s+(.+)$", s)
    if m and m.group(1) in _NUM_PREFIX:
        s = f"{_NUM_PREFIX[m.group(1)]} {m.group(2)}"
    return s


def _content_tokens(text: str) -> list[str]:
    """Lowercase content words (>=3 chars, non-stopword) for indexing/search."""
    return [w for w in _norm(text).split() if len(w) >= 3 and w not in _STOPWORDS]


class VerseIndex:
    def __init__(self):
        self._by_ref: dict[str, dict] = {}          # "GEN 1:1" -> verse record
        self._by_id: dict[str, dict] = {}           # "GEN.1.1" -> verse record
        self._all: list[dict] = []                  # all verse records, load order
        self._books: list[dict] = []                # ordered book metadata
        self._book_chapters: dict[str, list[int]] = {}
        self._chapter_verses: dict[str, list[dict]] = {}
        self._book_name_map: dict[str, str] = {}    # normalized name/alias -> code
        self._inverted: dict[str, list[int]] = {}   # content term -> verse indices (into _all)
        self._doc_freq: dict[str, int] = {}         # content term -> document frequency
        self._n_docs: int = 0
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        seen_books: dict[str, dict] = {}

        with open(_VERSES_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                v = json.loads(line)
                idx = len(self._all)
                self._all.append(v)
                self._by_ref[v["ref"]] = v
                self._by_id[v["id"]] = v

                book = v["book"]
                if book not in seen_books:
                    seen_books[book] = {
                        "code": book,
                        "name": v["book_name"],
                        "full_name": v["book_full_name"],
                        "canon_category": v["canon_category"],
                        "order": v["book_order"],
                    }
                    # auto-register code + names (normalized)
                    self._book_name_map[_normalize_book_token(book)] = book
                    self._book_name_map[_normalize_book_token(v["book_name"])] = book
                    self._book_name_map[_normalize_book_token(v["book_full_name"])] = book

                ch_key = f"{book}:{v['chapter']}"
                self._chapter_verses.setdefault(ch_key, []).append(v)
                self._book_chapters.setdefault(book, [])
                if v["chapter"] not in self._book_chapters[book]:
                    self._book_chapters[book].append(v["chapter"])

                # inverted index (unique terms per verse)
                for term in set(_content_tokens(v["text"])):
                    self._inverted.setdefault(term, []).append(idx)

        # merge curated aliases (do not overwrite an auto-registered exact name)
        for alias, code in _CURATED_ALIASES.items():
            self._book_name_map.setdefault(_normalize_book_token(alias), code)

        self._books = sorted(seen_books.values(), key=lambda b: b["order"])
        for book in self._book_chapters:
            self._book_chapters[book].sort()
        self._n_docs = len(self._all)
        self._doc_freq = {t: len(idxs) for t, idxs in self._inverted.items()}
        self._loaded = True

    # ---- browse ----------------------------------------------------------
    def books(self) -> list[dict]:
        return self._books

    def chapters(self, book: str) -> list[int]:
        return self._book_chapters.get(book.upper(), [])

    def verses_in_chapter(self, book: str, chapter: int) -> list[dict]:
        return self._chapter_verses.get(f"{book.upper()}:{chapter}", [])

    def get_verse(self, book: str, chapter: int, verse: int) -> Optional[dict]:
        return self._by_ref.get(f"{book.upper()} {chapter}:{verse}")

    # ---- book resolution -------------------------------------------------
    def _resolve_book_code(self, name_part: str) -> Optional[str]:
        """Resolve a book name/abbreviation/roman-numeral to its uppercase code.
        Returns None if unrecognized or ambiguous."""
        key = _normalize_book_token(name_part)
        code = self._book_name_map.get(key)
        if code:
            return code
        if len(key) >= 3:
            cands = {c for stored, c in self._book_name_map.items() if stored.startswith(key)}
            if len(cands) == 1:
                return next(iter(cands))
        return None

    # ---- structured reference parsing (the abstain contract) -------------
    def parse_reference(self, text: str) -> dict:
        """Parse a possible scripture reference into a structured result.

        Returns a dict:
          status: FOUND | NOT_FOUND | AMBIGUOUS | INVALID | NONE
          is_reference_attempt: bool   (looks like "<book> <num>...")
          references: [ref, ...]       (resolved refs when FOUND)
          results:    [verse record, ...]
          reason:     human-readable explanation (for abstain UI)

        NONE  -> not reference-shaped (caller may try prefix search / generation).
        Any reference-SHAPED input that does not resolve returns INVALID/NOT_FOUND
        so the caller ABSTAINS — it must never fall through to raw generation.
        """
        s = text.strip()
        m = re.match(r"^(.+?)\s+(\d+)(?::(\d+)(?:\s*-\s*(\d+))?)?$", s)
        if not m:
            return {"status": "NONE", "is_reference_attempt": False,
                    "references": [], "results": [], "reason": ""}

        book_part = m.group(1).strip()
        chapter = int(m.group(2))
        v_start = int(m.group(3)) if m.group(3) else None
        v_end = int(m.group(4)) if m.group(4) else None

        code = self._resolve_book_code(book_part)
        if code is None:
            return {"status": "INVALID", "is_reference_attempt": True,
                    "references": [], "results": [],
                    "reason": f"'{book_part}' is not a recognized book of the KJV + Apocrypha canon."}

        book_name = next((b["name"] for b in self._books if b["code"] == code), code)

        if v_start is None:
            # chapter-only -> verse 1 of that chapter
            verse = self.get_verse(code, chapter, 1)
            if verse:
                return {"status": "FOUND", "is_reference_attempt": True,
                        "references": [verse["ref"]], "results": [verse], "reason": ""}
            return {"status": "NOT_FOUND", "is_reference_attempt": True,
                    "references": [], "results": [],
                    "reason": f"{book_name} has no chapter {chapter}."}

        end = v_end if v_end is not None else v_start
        results = [self.get_verse(code, chapter, vn) for vn in range(v_start, end + 1)]
        results = [v for v in results if v]
        if results:
            return {"status": "FOUND", "is_reference_attempt": True,
                    "references": [v["ref"] for v in results], "results": results, "reason": ""}
        return {"status": "NOT_FOUND", "is_reference_attempt": True,
                "references": [], "results": [],
                "reason": f"{book_name} {chapter}:{v_start}"
                          f"{('-' + str(v_end)) if v_end else ''} is not in the corpus."}

    # ---- legacy reference helpers (kept; used by retrieval-first path) ----
    def lookup_ref(self, ref_str: str) -> Optional[dict]:
        parsed = self.parse_reference(ref_str)
        return parsed["results"][0] if parsed["results"] else None

    def lookup_ref_range(self, ref_str: str) -> list[dict]:
        return self.parse_reference(ref_str)["results"]

    def search_prefix(self, query: str) -> Optional[dict]:
        """Find the best matching verse for a text query via four tiers (prefix,
        substring, all-keywords, single-leading-word). Corpus-locked, no generation."""
        q_norm = _norm(query.strip())
        if len(q_norm) >= 8:
            for v in self._all:
                if _norm(v["text"]).startswith(q_norm):
                    return v
        if len(q_norm) < 6:
            return None
        if len(q_norm) >= 20:
            for v in self._all:
                if q_norm in _norm(v["text"]):
                    return v
        words = [w for w in q_norm.split() if w not in _STOPWORDS]
        if len(words) >= 2:
            for v in self._all:
                v_norm = _norm(v["text"])
                if all(w in v_norm for w in words):
                    return v
        if len(words) == 1:
            for v in self._all:
                if _norm(v["text"]).startswith(words[0]):
                    return v
        return None

    def build_corpus_context(self, verse: dict, partial_text: str = "") -> str:
        """Build training-format context block up to and including the target verse."""
        ch_verses = self.verses_in_chapter(verse["book"], verse["chapter"])
        header = (
            f"<|source:kjv:{verse['canon_category']}:{verse['book']}:{verse['chapter']}|>\n"
            f"Book: {verse['book_full_name']}\n"
            f"Chapter: {verse['chapter']}\n"
            f"Canon: {verse['canon_category']}\n\n"
        )
        lines = []
        for v in ch_verses:
            if v["verse"] < verse["verse"]:
                lines.append(f"{v['book']} {v['chapter']}:{v['verse']} {v['text']}")
            elif v["verse"] == verse["verse"]:
                lines.append(f"{v['book']} {v['chapter']}:{v['verse']} {partial_text}")
                break
        return header + "\n".join(lines)

    # ---- canon / book filter helpers ------------------------------------
    def _canon_of(self, filter_value: str) -> Optional[str]:
        if not filter_value:
            return None
        return _CANON_ALIASES.get(filter_value.strip().lower())

    def _hit(self, v: dict, book_code: Optional[str], canon: Optional[str]) -> bool:
        if book_code and v["book"] != book_code:
            return False
        if canon and v["canon_category"] != canon:
            return False
        return True

    def _verse_out(self, v: dict, score: float, matched: list[str]) -> dict:
        return {
            "reference": v["ref"], "book": v["book_name"], "book_code": v["book"],
            "chapter": v["chapter"], "verse": v["verse"], "canon": v["canon_category"],
            "text": v["text"], "score": round(float(score), 4), "matched_terms": matched,
        }

    # ---- SEARCH: corpus keyword/phrase retrieval ------------------------
    def search(self, query: str, *, book: str = "", canon: str = "", limit: int = 20) -> dict:
        """Case-insensitive corpus search. Ranks exact-phrase > all-terms > partial.
        Returns a structured payload (status / results / reason). Real verses only."""
        q = (query or "").strip()
        if not q:
            return {"status": "INVALID", "results": [], "count": 0,
                    "reason": "Empty query."}
        book_code = self._resolve_book_code(book) if book else None
        if book and book_code is None:
            return {"status": "INVALID", "results": [], "count": 0,
                    "reason": f"'{book}' is not a recognized book."}
        canon_v = self._canon_of(canon)

        q_norm = _norm(q)
        terms = [w for w in q_norm.split() if w not in _STOPWORDS] or q_norm.split()
        # candidate verse indices: union of postings for query terms
        cand: set[int] = set()
        for t in terms:
            cand.update(self._inverted.get(t, ()))
        # exact-phrase candidates: scan only if the phrase is short enough to matter
        scored: list[tuple[float, dict, list[str]]] = []
        for idx in cand:
            v = self._all[idx]
            if not self._hit(v, book_code, canon_v):
                continue
            v_norm = _norm(v["text"])
            matched = [t for t in terms if t in v_norm]
            if not matched:
                continue
            frac = len(matched) / len(terms)
            # rarity-weighted term score
            rar = sum(math.log(self._n_docs / max(1, self._doc_freq.get(t, 1))) for t in matched)
            phrase_bonus = 3.0 if (len(q_norm) >= 6 and q_norm in v_norm) else 0.0
            all_terms_bonus = 1.0 if frac == 1.0 else 0.0
            score = phrase_bonus + all_terms_bonus + frac + 0.1 * rar
            scored.append((score, v, matched))
        scored.sort(key=lambda x: (-x[0], x[1]["book_order"], x[1]["chapter"], x[1]["verse"]))
        results = [self._verse_out(v, sc, m) for sc, v, m in scored[:max(1, limit)]]
        status = "FOUND" if results else "NOT_FOUND"
        reason = "" if results else f"No verses in the corpus match '{q}'."
        return {"status": status, "results": results, "count": len(results), "reason": reason}

    # ---- CROSS-REFERENCE: deterministic lexical/topical -----------------
    def cross_reference(self, ref: str, *, limit: int = 12) -> dict:
        """Lexical/topical cross-reference: distinctive terms of the input verse ->
        rank other verses sharing rare terms. Real references only. Not theological."""
        parsed = self.parse_reference(ref)
        if parsed["status"] != "FOUND" or not parsed["results"]:
            return {"status": parsed["status"] if parsed["status"] != "NONE" else "INVALID",
                    "source": None, "results": [], "count": 0,
                    "reason": parsed["reason"] or f"'{ref}' is not a recognized reference.",
                    "method": "lexical/topical"}
        src = parsed["results"][0]
        src_idx = self._all.index(src) if src in self._all else None
        # distinctive terms of the source verse, weighted by rarity
        terms = set(_content_tokens(src["text"]))
        weights = {t: math.log(self._n_docs / max(1, self._doc_freq.get(t, 1))) for t in terms}
        cand: dict[int, float] = {}
        shared: dict[int, list[str]] = {}
        for t in terms:
            for idx in self._inverted.get(t, ()):
                if idx == src_idx:
                    continue
                cand[idx] = cand.get(idx, 0.0) + weights[t]
                shared.setdefault(idx, []).append(t)
        ranked = sorted(cand.items(), key=lambda kv: -kv[1])
        results = []
        for idx, score in ranked[:max(1, limit)]:
            v = self._all[idx]
            sh = sorted(shared[idx], key=lambda t: -weights[t])
            results.append({**self._verse_out(v, score, sh), "shared_terms": sh})
        return {
            "status": "FOUND" if results else "NOT_FOUND",
            "source": {"reference": src["ref"], "text": src["text"]},
            "results": results, "count": len(results),
            "method": "lexical/topical",
            "reason": "" if results else "No lexical cross-references found.",
        }

    # ---- Q&A: retrieval-grounded ----------------------------------------
    def qa(self, question: str, *, context_ref: str = "", limit: int = 3) -> dict:
        """Retrieval-grounded Q&A. Returns scripture witnesses (exact text) most
        relevant to the question. No fabricated references; abstains if none found."""
        q = (question or "").strip()
        if not q:
            return {"status": "INVALID", "witnesses": [], "reason": "Empty question."}
        # strip question words for keyword retrieval
        keywords = [w for w in _content_tokens(q) if w not in _QUESTION_WORDS]
        search_query = " ".join(keywords) if keywords else q
        res = self.search(search_query, limit=limit)
        witnesses = res["results"]
        if not witnesses:
            return {
                "status": "NOT_FOUND", "witnesses": [], "keywords": keywords,
                "reason": "I do not have a grounded verse match for that question "
                          "in the KJV+Apocrypha corpus.",
            }
        shared_terms = sorted(
            {t for w in witnesses for t in w["matched_terms"]},
            key=lambda t: self._doc_freq.get(t, 0),
        )
        return {
            "status": "FOUND", "witnesses": witnesses, "keywords": keywords,
            "shared_terms": shared_terms, "reason": "",
        }

    # ---- UNIFIED STUDY: one query -> real scripture + auto cross-refs ----
    def _exact_quote(self, q: str, book_code, canon_v) -> Optional[dict]:
        """Return the verse a query is an exact substring of, so a typed QUOTE resolves
        to its real verse. A quote must be a multi-word fragment (>=3 words, >=12 chars) —
        a single word, even a long one like "resurrection", is a TOPIC, not a quote."""
        qn = _norm(q)
        if len(qn.split()) < 3 or len(qn) < 12:
            return None
        for v in self._all:
            if self._hit(v, book_code, canon_v) and qn in _norm(v["text"]):
                return v
        return None

    def _auto_xref(self, source_verses: list[dict], *, limit: int = 8, exclude=None) -> list[dict]:
        """Aggregate deterministic lexical/topical cross-references for one or more
        source verses (rarity-weighted shared terms). Real references only."""
        exclude = set(exclude or set())
        for v in source_verses:
            exclude.add(v["ref"])
        weights: dict[str, float] = {}
        for v in source_verses:
            for t in set(_content_tokens(v["text"])):
                w = math.log(self._n_docs / max(1, self._doc_freq.get(t, 1)))
                if w > weights.get(t, 0.0):
                    weights[t] = w
        cand: dict[int, float] = {}
        shared: dict[int, list[str]] = {}
        for t, w in weights.items():
            for idx in self._inverted.get(t, ()):
                if self._all[idx]["ref"] in exclude:
                    continue
                cand[idx] = cand.get(idx, 0.0) + w
                shared.setdefault(idx, []).append(t)
        ranked = sorted(cand.items(), key=lambda kv: -kv[1])[:max(1, limit)]
        out = []
        for idx, score in ranked:
            v = self._all[idx]
            sh = sorted(shared[idx], key=lambda t: -weights[t])
            out.append({**self._verse_out(v, score, sh), "shared_terms": sh})
        return out

    def study(self, query: str, *, book: str = "", canon: str = "", limit: int = 8) -> dict:
        """THE unified scripture function. One query -> real scripture (exact reference,
        exact quote, or ranked topic matches) ALWAYS with automatic cross-references.

        The corpus is the knowledge: every returned verse is real (no fabrication). A
        reference that does not resolve ABSTAINS rather than guessing. intent is one of
        reference | quote | topic.
        """
        q = (query or "").strip()
        if not q:
            return {"intent": "none", "status": "INVALID", "query": q,
                    "primary": [], "cross_references": [], "reason": "Empty query."}

        book_code = self._resolve_book_code(book) if book else None
        if book and book_code is None:
            return {"intent": "none", "status": "INVALID", "query": q,
                    "primary": [], "cross_references": [],
                    "reason": f"'{book}' is not a recognized book."}
        canon_v = self._canon_of(canon)

        # 1) Reference-shaped -> exact corpus text, or ABSTAIN (never guess/generate).
        parsed = self.parse_reference(q)
        if parsed["is_reference_attempt"]:
            if parsed["status"] != "FOUND":
                return {"intent": "reference", "status": parsed["status"], "query": q,
                        "primary": [], "cross_references": [], "reason": parsed["reason"]}
            primary = [self._verse_out(v, 1.0, []) for v in parsed["results"]]
            xrefs = self._auto_xref(parsed["results"], limit=limit)
            return {"intent": "reference", "status": "FOUND", "query": q,
                    "primary": primary, "cross_references": xrefs, "reason": ""}

        # 2) Exact quote -> the real verse it comes from.
        quote = self._exact_quote(q, book_code, canon_v)
        if quote:
            return {"intent": "quote", "status": "FOUND", "query": q,
                    "primary": [self._verse_out(quote, 1.0, [])],
                    "cross_references": self._auto_xref([quote], limit=limit), "reason": ""}

        # 3) Topic / question -> strip question words ("what does the bible say about..."),
        #    then rank real matches (the concordance) + correlate.
        keywords = [w for w in _content_tokens(q) if w not in _QUESTION_WORDS]
        search_q = " ".join(keywords) if keywords else q
        sr = self.search(search_q, book=book, canon=canon, limit=limit)
        if sr["status"] != "FOUND":
            return {"intent": "topic", "status": "NOT_FOUND", "query": q,
                    "primary": [], "cross_references": [],
                    "reason": sr["reason"] or "No scripture in the corpus matches that."}
        primary = sr["results"]
        top_verses = [self._by_ref[r["reference"]] for r in primary[:3]]
        xrefs = self._auto_xref(top_verses, limit=limit,
                                exclude={r["reference"] for r in primary})
        return {"intent": "topic", "status": "FOUND", "query": q,
                "primary": primary, "cross_references": xrefs, "reason": ""}

    # ---- legacy substring search (kept for compatibility) ---------------
    def search_text(self, query: str, limit: int = 20) -> list[dict]:
        q = query.lower()
        results = []
        for v in self._all:
            if q in v["text"].lower():
                results.append(v)
                if len(results) >= limit:
                    break
        return results


# Module-level singleton
_index = VerseIndex()


def get_index() -> VerseIndex:
    return _index
