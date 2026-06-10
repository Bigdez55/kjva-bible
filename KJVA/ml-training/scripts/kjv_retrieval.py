#!/usr/bin/env python3
"""Shared retrieval and citation helpers for KJV bundle validation/runtime."""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


STOPWORDS = {
    "a", "an", "and", "are", "as", "be", "but", "by", "for", "from", "he",
    "her", "him", "his", "i", "in", "is", "it", "me", "my", "of", "on",
    "or", "our", "she", "that", "the", "their", "them", "they", "this",
    "to", "unto", "was", "we", "with", "ye", "you", "your",
}


BOOK_ALIASES = {
    "genesis": "GEN",
    "gen": "GEN",
    "exodus": "EXO",
    "exo": "EXO",
    "leviticus": "LEV",
    "numbers": "NUM",
    "deuteronomy": "DEU",
    "joshua": "JOS",
    "judges": "JDG",
    "ruth": "RUT",
    "1 samuel": "1SA",
    "first samuel": "1SA",
    "2 samuel": "2SA",
    "second samuel": "2SA",
    "1 kings": "1KI",
    "first kings": "1KI",
    "2 kings": "2KI",
    "second kings": "2KI",
    "1 chronicles": "1CH",
    "first chronicles": "1CH",
    "2 chronicles": "2CH",
    "second chronicles": "2CH",
    "ezra": "EZR",
    "nehemiah": "NEH",
    "esther": "EST",
    "job": "JOB",
    "psalm": "PSA",
    "psalms": "PSA",
    "psa": "PSA",
    "proverbs": "PRO",
    "proverb": "PRO",
    "pro": "PRO",
    "ecclesiastes": "ECC",
    "song of solomon": "SNG",
    "song of songs": "SNG",
    "canticles": "SNG",
    "isaiah": "ISA",
    "jeremiah": "JER",
    "lamentations": "LAM",
    "ezekiel": "EZK",
    "daniel": "DAN",
    "hosea": "HOS",
    "joel": "JOL",
    "amos": "AMO",
    "obadiah": "OBA",
    "jonah": "JON",
    "micah": "MIC",
    "nahum": "NAM",
    "habakkuk": "HAB",
    "zephaniah": "ZEP",
    "haggai": "HAG",
    "zechariah": "ZEC",
    "malachi": "MAL",
    "matthew": "MAT",
    "mat": "MAT",
    "mark": "MRK",
    "luke": "LUK",
    "john": "JHN",
    "joh": "JHN",
    "jhn": "JHN",
    "acts": "ACT",
    "romans": "ROM",
    "1 corinthians": "1CO",
    "first corinthians": "1CO",
    "2 corinthians": "2CO",
    "second corinthians": "2CO",
    "galatians": "GAL",
    "ephesians": "EPH",
    "philippians": "PHP",
    "colossians": "COL",
    "1 thessalonians": "1TH",
    "first thessalonians": "1TH",
    "2 thessalonians": "2TH",
    "second thessalonians": "2TH",
    "1 timothy": "1TI",
    "first timothy": "1TI",
    "2 timothy": "2TI",
    "second timothy": "2TI",
    "titus": "TIT",
    "philemon": "PHM",
    "hebrews": "HEB",
    "james": "JAS",
    "1 peter": "1PE",
    "first peter": "1PE",
    "2 peter": "2PE",
    "second peter": "2PE",
    "1 john": "1JN",
    "first john": "1JN",
    "2 john": "2JN",
    "second john": "2JN",
    "3 john": "3JN",
    "third john": "3JN",
    "jude": "JUD",
    "revelation": "REV",
    "revelation of john": "REV",
    "tobit": "TOB",
    "judith": "JDT",
    "additions to esther": "ESG",
    "wisdom": "WIS",
    "wisdom of solomon": "WIS",
    "sirach": "SIR",
    "ecclesiasticus": "SIR",
    "baruch": "BAR",
    "song of the three children": "S3Y",
    "susanna": "SUS",
    "bel and the dragon": "BEL",
    "1 maccabees": "1MA",
    "first maccabees": "1MA",
    "2 maccabees": "2MA",
    "second maccabees": "2MA",
    "1 esdras": "1ES",
    "first esdras": "1ES",
    "prayer of manasses": "MAN",
    "prayer of manasseh": "MAN",
    "2 esdras": "2ES",
    "second esdras": "2ES",
}


def norm_key(text: str) -> str:
    text = text.lower()
    text = text.replace(".", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def terms(text: str) -> list[str]:
    return [t for t in norm_key(text).split() if t and t not in STOPWORDS]


@dataclass
class SearchHit:
    doc: dict[str, Any]
    score: float


class KJVRetriever:
    def __init__(self, corpus_dir: Path):
        self.corpus_dir = corpus_dir
        self.verses_path = corpus_dir / "verses.jsonl"
        self.index_path = corpus_dir / "retrieval_index.json"
        self.manifest_path = corpus_dir / "manifest.json"
        if self.index_path.exists():
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            self.corpus_id = data.get("corpus_id", "")
            self.docs = data.get("documents", [])
        elif self.verses_path.exists():
            self.corpus_id = ""
            self.docs = [
                json.loads(line)
                for line in self.verses_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            for doc in self.docs:
                doc.setdefault("search_text", " ".join([
                    doc.get("ref", ""),
                    doc.get("book_name", ""),
                    doc.get("book_full_name", ""),
                    doc.get("text", ""),
                ]))
        else:
            raise FileNotFoundError(f"missing KJV retrieval artifacts in {corpus_dir}")

        self.by_id = {doc["id"]: doc for doc in self.docs}
        self.by_ref = {
            (doc["book"], int(doc["chapter"]), int(doc["verse"])): doc
            for doc in self.docs
        }
        self.aliases = dict(BOOK_ALIASES)
        for doc in self.docs:
            book = doc["book"]
            for value in [book, doc.get("book_name", ""), doc.get("book_full_name", "")]:
                key = norm_key(value)
                if key:
                    self.aliases[key] = book

        self.doc_terms: list[Counter[str]] = []
        df: Counter[str] = Counter()
        for doc in self.docs:
            counts = Counter(terms(doc.get("search_text", "")))
            self.doc_terms.append(counts)
            df.update(counts.keys())
        n_docs = max(1, len(self.docs))
        self.idf = {
            term: math.log((1 + n_docs) / (1 + count)) + 1.0
            for term, count in df.items()
        }

    @property
    def retrieval_docs(self) -> int:
        return len(self.docs)

    def _book_from_text(self, text: str) -> str | None:
        key = norm_key(text)
        if key in self.aliases:
            return self.aliases[key]
        compact = key.replace(" ", "")
        for alias, book in self.aliases.items():
            if alias.replace(" ", "") == compact:
                return book
        return None

    def parse_reference(self, query: str) -> tuple[str, int, int, int] | None:
        q = query.strip()
        match = re.search(
            r"\b([1-3]?\s*[A-Za-z][A-Za-z .]*(?:\s+of\s+[A-Za-z .]+)?)\s+"
            r"(\d{1,3})\s*:\s*(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?\b",
            q,
        )
        if not match:
            return None
        book_text, chapter_s, start_s, end_s = match.groups()
        book = self._book_from_text(book_text)
        if not book:
            return None
        chapter = int(chapter_s)
        start = int(start_s)
        end = int(end_s or start_s)
        if end < start:
            start, end = end, start
        return book, chapter, start, end

    def cite(self, query: str) -> dict[str, Any]:
        parsed = self.parse_reference(query)
        if not parsed:
            return {"ok": False, "query": query, "error": "reference_not_found", "verses": []}
        book, chapter, start, end = parsed
        verses = [
            self.by_ref[(book, chapter, verse)]
            for verse in range(start, end + 1)
            if (book, chapter, verse) in self.by_ref
        ]
        expected = end - start + 1
        return {
            "ok": len(verses) == expected,
            "query": query,
            "parsed": {
                "book": book,
                "chapter": chapter,
                "start_verse": start,
                "end_verse": end,
            },
            "verses": verses,
        }

    def search(self, query: str, top_k: int = 3,
               canon_category: str | None = None) -> list[SearchHit]:
        q_terms = terms(query)
        if not q_terms:
            return []
        q_counts = Counter(q_terms)
        phrase = norm_key(query)
        hits: list[SearchHit] = []
        for idx, doc in enumerate(self.docs):
            if canon_category and doc.get("canon_category") != canon_category:
                continue
            counts = self.doc_terms[idx]
            score = 0.0
            for term, q_count in q_counts.items():
                if term in counts:
                    score += (1.0 + math.log(counts[term])) * self.idf.get(term, 1.0) * q_count
            if phrase and phrase in norm_key(doc.get("text", "")):
                score += 50.0
            if doc.get("ref", "").lower() in query.lower():
                score += 100.0
            if score > 0:
                hits.append(SearchHit(doc=doc, score=score))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    def chat(self, message: str, top_k: int = 3) -> dict[str, Any]:
        citation = self.cite(message)
        if citation.get("ok"):
            hits = [SearchHit(doc=doc, score=1.0) for doc in citation["verses"][:top_k]]
            mode = "citation"
        else:
            hits = self.search(message, top_k=top_k)
            mode = "retrieval"
        max_score = max((h.score for h in hits), default=0.0)
        citations = [
            {
                "id": h.doc["id"],
                "ref": h.doc["ref"],
                "text": h.doc["text"],
                "canon_category": h.doc.get("canon_category", ""),
                "confidence": round(h.score / max_score, 4) if max_score else 0.0,
            }
            for h in hits
        ]
        answer = "\n".join(f"{c['ref']} {c['text']}" for c in citations)
        return {
            "mode": mode,
            "answer": answer,
            "citations": citations,
            "retrieval_confidence": citations[0]["confidence"] if citations else 0.0,
            "generation_invoked": False,
        }
