#!/usr/bin/env python3
"""Extract pseudepigrapha books from The Forgotten Books of Eden (1926, PD).

Source: data/corpus/external/archive_org/forgotten_books_of_eden.txt
(sacred-texts digital edition preserved on archive.org).

Only books NOT already held in cleaner form from wesley.nnu.edu are
extracted: 2 Enoch, Odes of Solomon, 4 Maccabees, Story of Ahikar, and the
twelve Testaments of the Patriarchs.

Verse model: paragraphs starting with a number N are verse N; a verse-number
reset (N <= previous) starts the next chapter. parse_quality="ocr-approx".
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "corpus" / "external" / "archive_org" / "forgotten_books_of_eden.txt"
OUT_DIR = REPO_ROOT / "data" / "corpus_v2" / "versions"

# (book_id, code, header phrase) — bounded by the next entry's body position
BOOKS = [
    ("2-enoch", "2ENO", "SECRETS OF ENOCH"),
    ("odes-of-solomon", "ODES", "ODES OF SOLOMON"),
    ("4-maccabees", "4MA", "FOURTH BOOK OF MACCABEES"),
    ("story-of-ahikar", "AHIK", "STORY OF AHIKAR"),
    ("testament-of-reuben", "TREU", "TESTAMENT OF REUBEN"),
    ("testament-of-simeon", "TSIM", "TESTAMENT OF SIMEON"),
    ("testament-of-levi", "TLEV", "TESTAMENT OF LEVI"),
    ("testament-of-judah", "TJUD", "TESTAMENT OF JUDAH"),
    ("testament-of-issachar", "TISS", "TESTAMENT OF ISSACHAR"),
    ("testament-of-zebulun", "TZEB", "TESTAMENT OF ZEBULUN"),
    ("testament-of-dan", "TDAN", "TESTAMENT OF DAN"),
    ("testament-of-naphtali", "TNAP", "TESTAMENT OF NAPHTALI"),
    ("testament-of-gad", "TGAD", "TESTAMENT OF GAD"),
    ("testament-of-asher", "TASH", "TESTAMENT OF ASHER"),
    ("testament-of-joseph", "TJOS", "TESTAMENT OF JOSEPH"),
    ("testament-of-benjamin", "TBEN", "TESTAMENT OF BENJAMIN"),
]

PAGE_MARK = re.compile(r"\[p\.\s*\d+\]|<page\s+\d+>|\bThe Forgotten Books of Eden.*?sacred-texts\.com\b")
VERSE_HEAD = re.compile(r"^(\d{1,3})\s+(.*)$", re.S)


def body_pos(text_upper: str, phrase: str, after: int = 10000) -> int | None:
    # `after` carries the previous book's position: FBE sections appear in
    # BOOKS order, and earlier in-text mentions (e.g. 4 Maccabees discussing
    # the Testament of Joseph) must not be mistaken for section starts.
    hits = [m.start() for m in re.finditer(re.escape(phrase), text_upper) if m.start() > after]
    return hits[0] if hits else None


def clean_para(p: str) -> str:
    p = PAGE_MARK.sub(" ", p)
    p = p.replace("| ", "I ").replace(" |", " I")
    p = re.sub(r"\s+", " ", p).strip()
    return p


def extract(section: str):
    """Yield (chapter, verse, text) from a section's raw text."""
    paras = [clean_para(p) for p in re.split(r"\n\s*\n", section)]
    paras = [p for p in paras if p and len(p) > 2]
    chapter, last_verse = 1, 0
    started = False
    for p in paras:
        m = VERSE_HEAD.match(p)
        if not m:
            continue  # intro/commentary paragraphs have no leading verse number
        vs, text = int(m.group(1)), m.group(2).strip()
        if not text or len(text) < 3 or vs > 200:
            continue
        if started and vs <= last_verse:
            chapter += 1
        started = True
        last_verse = vs
        yield chapter, vs, text


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = SRC.read_text(encoding="utf-8", errors="replace")
    upper = raw.upper()

    positions = []
    prev = 10000
    for book_id, code, phrase in BOOKS:
        pos = body_pos(upper, phrase, after=prev)
        positions.append((book_id, code, phrase, pos))
        if pos is None:
            print(f"[WARN] section not found: {phrase}")
        else:
            prev = pos

    found = [(b, c, p, pos) for b, c, p, pos in positions if pos is not None]
    found.sort(key=lambda x: x[3])

    for i, (book_id, code, phrase, pos) in enumerate(found):
        end = found[i + 1][3] if i + 1 < len(found) else len(raw)
        bname = book_id.replace("-", " ").title()
        src = {"primary": "archive.org the-forgotten-books-of-eden_202304 (sacred-texts digital edition)",
               "volume": "The Forgotten Books of Eden, Rutherford H. Platt, 1926 (public domain)"}
        recs = []
        for ch, vs, text in extract(raw[pos:end]):
            recs.append({
                "id": f"PSEUD-{book_id}.{code}.{ch}.{vs}",
                "ref": f"{code} {ch}:{vs}",
                "book": code,
                "book_name": bname,
                "chapter": ch,
                "verse": vs,
                "canon_category": "pseudepigrapha",
                "text": text,
                "translation_id": f"PSEUD-{book_id}",
                "translation_name": f"{bname} (Forgotten Books of Eden)",
                "corpus_section": "pseudepigrapha",
                "source": src,
                "parse_quality": "ocr-approx",
            })
        out = OUT_DIR / f"PSEUD-{book_id}.jsonl"
        with out.open("w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        chapters = max((r["chapter"] for r in recs), default=0)
        print(f"{book_id:<26} verses={len(recs):>5} chapters={chapters:>3} -> {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
