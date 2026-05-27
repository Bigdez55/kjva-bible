"""
corpus.py — In-memory verse index built from verses.jsonl at startup.

Loads once at startup (~36,822 records). All lookups are O(1) dict access.
"""
from __future__ import annotations

import json
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
})

_DATA_DIR = Path(__file__).parent.parent / "data"
_VERSES_PATH = _DATA_DIR / "verses.jsonl"


class VerseIndex:
    def __init__(self):
        self._by_ref: dict[str, dict] = {}          # "GEN 1:1" → verse record
        self._by_id: dict[str, dict] = {}           # "GEN.1.1" → verse record
        self._books: list[dict] = []                # ordered book metadata
        self._book_chapters: dict[str, list[int]] = {}  # book → sorted chapter list
        self._chapter_verses: dict[str, list[dict]] = {}  # "GEN:1" → verse list
        self._book_name_map: dict[str, str] = {}    # lowercase name/code → uppercase code
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        seen_books: dict[str, dict] = {}
        book_order: dict[str, int] = {}

        with open(_VERSES_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                v = json.loads(line)
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
                    book_order[book] = v["book_order"]
                    # Build book name lookup map
                    self._book_name_map[book.lower()] = book
                    self._book_name_map[v["book_name"].lower()] = book
                    self._book_name_map[v["book_full_name"].lower()] = book

                ch_key = f"{book}:{v['chapter']}"
                self._chapter_verses.setdefault(ch_key, []).append(v)
                if book not in self._book_chapters:
                    self._book_chapters[book] = []
                if v["chapter"] not in self._book_chapters[book]:
                    self._book_chapters[book].append(v["chapter"])

        # Sort
        self._books = sorted(seen_books.values(), key=lambda b: b["order"])
        for book in self._book_chapters:
            self._book_chapters[book].sort()

        self._loaded = True

    def books(self) -> list[dict]:
        return self._books

    def chapters(self, book: str) -> list[int]:
        return self._book_chapters.get(book.upper(), [])

    def verses_in_chapter(self, book: str, chapter: int) -> list[dict]:
        return self._chapter_verses.get(f"{book.upper()}:{chapter}", [])

    def get_verse(self, book: str, chapter: int, verse: int) -> Optional[dict]:
        ref = f"{book.upper()} {chapter}:{verse}"
        return self._by_ref.get(ref)

    def _resolve_book_code(self, name_part: str) -> Optional[str]:
        """Resolve a book name or abbreviation to its uppercase code."""
        key = name_part.lower()
        # Exact match first
        code = self._book_name_map.get(key)
        if code:
            return code
        # Partial prefix match (min 3 chars) — "prov" → "proverbs" → "PRO"
        if len(key) >= 3:
            for stored, c in self._book_name_map.items():
                if stored.startswith(key):
                    return c
        return None

    def lookup_ref(self, ref_str: str) -> Optional[dict]:
        """Parse a verse reference and return the verse record.

        Handles:
          'John 3:16'    — name + chapter:verse
          'GEN 1:1'      — code + chapter:verse
          'Prov 31:10'   — partial abbreviation
          'Prov 31'      — chapter-only → returns verse 1 of that chapter
          'Num 15:37-41' — range → returns first verse (use lookup_ref_range for all)
        """
        s = ref_str.strip()
        # Strip trailing range suffix so "Num 15:37-41" parses as "Num 15:37"
        s_single = re.sub(r"-\d+$", "", s)

        # Try chapter:verse — exact match first, then leading match (ref + trailing text)
        for pattern in (r"^(.+?)\s+(\d+):(\d+)$", r"^(.+?)\s+(\d+):(\d+)\b"):
            m = re.match(pattern, s_single)
            if m:
                code = self._resolve_book_code(m.group(1).strip())
                if code:
                    return self.get_verse(code, int(m.group(2)), int(m.group(3)))

        # Try chapter-only form (e.g. "Prov 31") → return verse 1
        for pattern in (r"^(.+?)\s+(\d+)$", r"^(.+?)\s+(\d+)\b"):
            m = re.match(pattern, s_single)
            if m:
                code = self._resolve_book_code(m.group(1).strip())
                if code:
                    return self.get_verse(code, int(m.group(2)), 1)

        return None

    def lookup_ref_range(self, ref_str: str) -> list[dict]:
        """Like lookup_ref but returns all verses for range refs like 'Numbers 15:37-41'.

        Returns a list with one or more verse records, or empty list on no match.
        """
        s = ref_str.strip()
        # Range: "Book C:V1-V2"
        m = re.match(r"^(.+?)\s+(\d+):(\d+)-(\d+)$", s)
        if m:
            code = self._resolve_book_code(m.group(1).strip())
            if code:
                chapter = int(m.group(2))
                v_start, v_end = int(m.group(3)), int(m.group(4))
                verses = []
                for vn in range(v_start, v_end + 1):
                    v = self.get_verse(code, chapter, vn)
                    if v:
                        verses.append(v)
                return verses

        # Single verse / chapter-only — delegate to lookup_ref
        v = self.lookup_ref(ref_str)
        return [v] if v else []

    def search_prefix(self, query: str) -> Optional[dict]:
        """Find the best matching verse for a text query via four tiers.

        Tier 1 (≥8 chars)  — verse text starts with the normalized query
        Tier 2 (≥20 chars) — query is a continuous substring of verse text
        Tier 3 (≥2 content words) — all non-stopword words appear anywhere in verse
                             (handles paraphrases like "no private interpretation")
        Tier 4 (1 content word) — verse text starts with that single word
                             (handles misquotes like "Study and" → 2TI 2:15)
        """
        q_norm = _norm(query.strip())

        # Tier 1: prefix (relaxed to 8 chars — short distinctive verse openings work here)
        if len(q_norm) >= 8:
            for v in self._by_ref.values():
                if _norm(v["text"]).startswith(q_norm):
                    return v

        # Tiers 2-4 need at least 6 chars of query content
        if len(q_norm) < 6:
            return None

        # Tier 2: substring (stricter threshold — short phrases appear in too many verses)
        if len(q_norm) >= 20:
            for v in self._by_ref.values():
                if q_norm in _norm(v["text"]):
                    return v

        # Tier 3: all content keywords present anywhere in verse
        words = [w for w in q_norm.split() if w not in _STOPWORDS]
        if len(words) >= 2:
            for v in self._by_ref.values():
                v_norm = _norm(v["text"])
                if all(w in v_norm for w in words):
                    return v

        # Tier 4: single distinctive word — only match if the verse STARTS with it
        # (avoids matching "lord" or "god" against hundreds of verses)
        if len(words) == 1:
            for v in self._by_ref.values():
                if _norm(v["text"]).startswith(words[0]):
                    return v

        return None

    def build_corpus_context(self, verse: dict, partial_text: str = "") -> str:
        """Build training-format context block up to and including the target verse line.

        The model was trained on blocks shaped:
          <|source:kjv:CANON:BOOK:CHAP|>
          Book: ...
          Chapter: N
          Canon: ...

          BOOK C:1 verse text
          BOOK C:2 verse text
          ...
          BOOK C:N [partial_text]

        Putting the target verse last means inference.py's tail-truncation preserves
        the most relevant context even when the chapter exceeds max_seq_len.
        """
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

    def search_text(self, query: str, limit: int = 20) -> list[dict]:
        """Naive substring search — placeholder until embedding adapter ships."""
        q = query.lower()
        results = []
        for v in self._by_ref.values():
            if q in v["text"].lower():
                results.append(v)
                if len(results) >= limit:
                    break
        return results


# Module-level singleton
_index = VerseIndex()


def get_index() -> VerseIndex:
    return _index
