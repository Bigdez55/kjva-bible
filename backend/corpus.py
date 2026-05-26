"""
corpus.py — In-memory verse index built from verses.jsonl at startup.

Loads once at startup (~36,822 records). All lookups are O(1) dict access.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_DATA_DIR = Path(__file__).parent.parent / "data"
_VERSES_PATH = _DATA_DIR / "verses.jsonl"


class VerseIndex:
    def __init__(self):
        self._by_ref: dict[str, dict] = {}          # "GEN 1:1" → verse record
        self._by_id: dict[str, dict] = {}           # "GEN.1.1" → verse record
        self._books: list[dict] = []                # ordered book metadata
        self._book_chapters: dict[str, list[int]] = {}  # book → sorted chapter list
        self._chapter_verses: dict[str, list[dict]] = {}  # "GEN:1" → verse list
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
