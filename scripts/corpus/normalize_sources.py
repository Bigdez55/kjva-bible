#!/usr/bin/env python3
"""Normalize fetched corpus v2 sources into unified verse records.

Per SPEC-KJVA-FUNC-0002. Reads data/corpus/external/, writes
data/corpus_v2/versions/<translation_id>.jsonl — one JSON record per verse:

  {id, ref, book, book_name, chapter, verse, canon_category, text,
   translation_id, translation_name, corpus_section, source, parse_quality}
"""
import io
import json
import re
import unicodedata
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL = REPO_ROOT / "data" / "corpus" / "external"
OUT_DIR = REPO_ROOT / "data" / "corpus_v2" / "versions"

# --- canon classification (same codes as eng_kjv_apocrypha_v1) -------------
OLD_TESTAMENT = {
    "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT", "1SA", "2SA",
    "1KI", "2KI", "1CH", "2CH", "EZR", "NEH", "EST", "JOB", "PSA", "PRO",
    "ECC", "SNG", "ISA", "JER", "LAM", "EZK", "DAN", "HOS", "JOL", "AMO",
    "OBA", "JON", "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL",
}
TORAH = {"GEN", "EXO", "LEV", "NUM", "DEU"}
APOCRYPHA = {
    "TOB", "JDT", "ESG", "WIS", "SIR", "BAR", "S3Y", "SUS", "BEL",
    "1MA", "2MA", "1ES", "MAN", "2ES", "LJE", "3MA", "4MA", "PS2",
}
NEW_TESTAMENT = {
    "MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH",
    "PHP", "COL", "1TH", "2TH", "1TI", "2TI", "TIT", "PHM", "HEB", "JAS",
    "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV",
}

# Book display-name -> USFM-style code. Keys are normalized (lowercased,
# roman numerals collapsed to arabic, articles stripped).
BOOK_CODES = {
    "genesis": "GEN", "exodus": "EXO", "leviticus": "LEV", "numbers": "NUM",
    "deuteronomy": "DEU", "joshua": "JOS", "judges": "JDG", "ruth": "RUT",
    "1 samuel": "1SA", "2 samuel": "2SA", "1 kings": "1KI", "2 kings": "2KI",
    "1 chronicles": "1CH", "2 chronicles": "2CH", "ezra": "EZR",
    "nehemiah": "NEH", "esther": "EST", "job": "JOB", "psalms": "PSA",
    "psalm": "PSA", "proverbs": "PRO", "ecclesiastes": "ECC",
    "song of solomon": "SNG", "song of songs": "SNG", "canticles": "SNG",
    "isaiah": "ISA", "jeremiah": "JER", "lamentations": "LAM",
    "ezekiel": "EZK", "daniel": "DAN", "hosea": "HOS", "joel": "JOL",
    "amos": "AMO", "obadiah": "OBA", "jonah": "JON", "micah": "MIC",
    "nahum": "NAM", "habakkuk": "HAB", "zephaniah": "ZEP", "haggai": "HAG",
    "zechariah": "ZEC", "malachi": "MAL",
    # apocrypha
    "1 esdras": "1ES", "2 esdras": "2ES", "tobit": "TOB", "judith": "JDT",
    "additions to esther": "ESG", "esther (greek)": "ESG",
    "greek esther": "ESG", "rest of esther": "ESG",
    "wisdom": "WIS", "wisdom of solomon": "WIS",
    "sirach": "SIR", "ecclesiasticus": "SIR",
    "baruch": "BAR", "letter of jeremiah": "LJE", "epistle of jeremiah": "LJE",
    "prayer of azariah": "S3Y", "song of three children": "S3Y",
    "song of the three holy children": "S3Y",
    "susanna": "SUS", "bel and dragon": "BEL", "bel and the dragon": "BEL",
    "prayer of manasses": "MAN", "prayer of manasseh": "MAN",
    "1 maccabees": "1MA", "2 maccabees": "2MA",
    "3 maccabees": "3MA", "4 maccabees": "4MA", "psalm 151": "PS2",
    # new testament
    "matthew": "MAT", "mark": "MRK", "luke": "LUK", "john": "JHN",
    "acts": "ACT", "acts of apostles": "ACT", "acts of the apostles": "ACT",
    "romans": "ROM", "1 corinthians": "1CO", "2 corinthians": "2CO",
    "galatians": "GAL", "ephesians": "EPH", "philippians": "PHP",
    "colossians": "COL", "1 thessalonians": "1TH", "2 thessalonians": "2TH",
    "1 timothy": "1TI", "2 timothy": "2TI", "titus": "TIT",
    "philemon": "PHM", "hebrews": "HEB", "james": "JAS",
    "1 peter": "1PE", "2 peter": "2PE", "1 john": "1JN", "2 john": "2JN",
    "3 john": "3JN", "jude": "JUD",
    "revelation": "REV", "revelation of john": "REV", "apocalypse": "REV",
    "revelation of st. john divine": "REV",
}

ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}

TRANSLATION_META = {
    # translation_id: (display name, corpus_section)
    "KJV": ("King James Version 1769", "kjv_lineage"),
    "KJVA": ("King James Version with Apocrypha", "kjv_lineage"),
    "KJVPCE": ("KJV Pure Cambridge Edition", "kjv_lineage"),
    "AKJV": ("American King James Version", "kjv_lineage"),
    "UKJV": ("Updated King James Version", "kjv_lineage"),
    "RNKJV": ("Restored Name King James Version", "kjv_lineage"),
    "MKJV": ("Modern King James Version", "kjv_lineage"),
    "Webster": ("Webster Bible 1833", "kjv_lineage"),
    "RWebster": ("Revised Webster 1995", "kjv_lineage"),
    "Geneva1599": ("Geneva Bible 1599", "kjv_lineage"),
    "Tyndale": ("Tyndale Bible 1525/1530", "kjv_lineage"),
    "Wycliffe": ("Wycliffe Bible c.1395", "kjv_lineage"),
    "JPS": ("JPS 1917 Tanakh", "tanakh"),
    "engwebster": ("Webster 1833 (eBible witness)", "kjv_lineage"),
    "enggnv": ("Geneva 1599 (eBible witness)", "kjv_lineage"),
    "engDRA": ("Douay-Rheims American 1899", "apocrypha"),
    "engjps": ("JPS 1917 (eBible witness)", "tanakh"),
    "hboWLC": ("Westminster Leningrad Codex (Hebrew)", "hebrew"),
}


def norm_book_name(name: str) -> str:
    n = name.strip().lower()
    n = re.sub(r"^the\s+", "", n)
    n = re.sub(r"\s+", " ", n)
    parts = n.split(" ")
    if parts and parts[0] in ROMAN:
        parts[0] = ROMAN[parts[0]]
    n = " ".join(parts)
    return n


def book_code(name: str) -> str | None:
    return BOOK_CODES.get(norm_book_name(name))


def canon_category(code: str, translation_id: str) -> str:
    if translation_id in ("JPS", "engjps", "hboWLC"):
        return "torah" if code in TORAH else "old_testament"
    if code in OLD_TESTAMENT:
        return "old_testament"
    if code in APOCRYPHA:
        return "apocrypha"
    if code in NEW_TESTAMENT:
        return "new_testament"
    return "other"


def clean_text(t: str) -> str:
    t = unicodedata.normalize("NFC", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def record(tid, tname, section, code, bname, ch, vs, text, src, quality="exact"):
    return {
        "id": f"{tid}.{code}.{ch}.{vs}",
        "ref": f"{code} {ch}:{vs}",
        "book": code,
        "book_name": bname,
        "chapter": ch,
        "verse": vs,
        "canon_category": canon_category(code, tid) if section != "pseudepigrapha" else "pseudepigrapha",
        "text": text,
        "translation_id": tid,
        "translation_name": tname,
        "corpus_section": section,
        "source": src,
        "parse_quality": quality,
    }


# --- scrollmapper JSON ------------------------------------------------------
def normalize_scrollmapper(path: Path):
    tid = path.stem
    tname, section = TRANSLATION_META[tid]
    data = json.loads(path.read_text(encoding="utf-8"))
    src = {"primary": f"scrollmapper/bible_databases formats/json/{tid}.json"}
    out, unknown = [], set()
    for book in data["books"]:
        code = book_code(book["name"])
        if not code:
            unknown.add(book["name"])
            continue
        for ch in book["chapters"]:
            for v in ch["verses"]:
                text = clean_text(v["text"])
                if not text:
                    continue
                out.append(record(tid, tname, section, code, book["name"],
                                  ch["chapter"], v["verse"], text, src))
    return out, unknown


# --- ebible VPL zip ---------------------------------------------------------
VPL_LINE = re.compile(r"^([1-3A-Z][A-Z0-9]{2})\s+(\d+):(\d+)\s+(.*)$")


def normalize_ebible(path: Path):
    tid = path.stem.replace("_vpl", "")
    tname, section = TRANSLATION_META[tid]
    src = {"primary": f"ebible.org/Scriptures/{path.name}"}
    out, unknown = [], set()
    with zipfile.ZipFile(path) as zf:
        txt_names = [n for n in zf.namelist() if n.endswith(".txt") and "vpl" in n.lower()]
        if not txt_names:
            txt_names = [n for n in zf.namelist() if n.endswith(".txt")]
        for name in txt_names:
            with zf.open(name) as f:
                for raw in io.TextIOWrapper(f, encoding="utf-8-sig"):
                    m = VPL_LINE.match(raw.strip())
                    if not m:
                        continue
                    code, ch, vs, text = m.group(1), int(m.group(2)), int(m.group(3)), clean_text(m.group(4))
                    if not text:
                        continue
                    out.append(record(tid, tname, section, code, code,
                                      ch, vs, text, src))
    return out, unknown


# --- Wesley NNU pseudepigrapha HTML ----------------------------------------
CHAPTER_MARKERS = [
    re.compile(r"\[\s*chapter\s+([0-9ivxlc]+)\s*\]", re.I),
    re.compile(r"\bchapter\s+([0-9ivxlc]+)\b", re.I),
]
# Charles-era layout puts the verse number inline, sometimes mid-clause and
# before a lowercase continuation ("...Garden 24 of Eden. And...").
# Split on any space-delimited 1-3 digit number; junk hits are filtered by
# the short-text guard and the 250-verse cap downstream.
VERSE_SPLIT = re.compile(r"(?<=\s)(\d{1,3})(?=\s)")


def roman_to_int(s: str) -> int | None:
    s = s.strip().lower()
    if s.isdigit():
        return int(s)
    vals = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
    if not s or any(c not in vals for c in s):
        return None
    total, prev = 0, 0
    for c in reversed(s):
        v = vals[c]
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total


def html_to_text(html: str) -> str:
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<(br|/p|/div|/h[1-6]|/li)[^>]*>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    for ent, repl in [("&amp;", "&"), ("&quot;", '"'), ("&#8217;", "'"), ("&#8216;", "'"),
                      ("&#8220;", '"'), ("&#8221;", '"'), ("&nbsp;", " "), ("&#8211;", "-"),
                      ("&#8212;", "-"), ("&lt;", "<"), ("&gt;", ">")]:
        html = html.replace(ent, repl)
    return html


def extract_main(text: str) -> str:
    # Wesley pages: try to trim the attribution header and footer, but never
    # trim away the bulk of the page — site navigation carries no
    # verse-number patterns, so over-inclusion is harmless while
    # over-trimming loses scripture (this truncated 2 Baruch to 1.8KB).
    start = 0
    m = re.search(r"R\.?\s*H\.?\s*Charles|Clarendon Press|Oxford", text)
    if m and m.end() < len(text) * 0.5:
        start = m.end()
    end = len(text)
    m = re.search(r"Copyright\s*©|All rights reserved", text[start:], re.I)
    if m and m.start() > (end - start) * 0.5:
        end = start + m.start()
    return text[start:end]


def normalize_wesley(path: Path, book_id: str):
    tid = "PSEUD"
    code = re.sub(r"[^A-Z0-9]", "", book_id.upper())[:8] or "UNK"
    bname = book_id.replace("-", " ").title()
    src = {"primary": f"wesley.nnu.edu noncanonical-literature ({book_id})",
           "translation": "R.H. Charles era, public domain"}
    text = html_to_text(path.read_text(encoding="utf-8", errors="replace"))
    body = extract_main(re.sub(r"[ \t]+", " ", text))

    # split into chapters
    chapters: list[tuple[int, str]] = []
    marker = CHAPTER_MARKERS[0]
    pieces = marker.split(body)
    if len(pieces) >= 3:
        it = iter(pieces[1:])
        for num, chunk in zip(it, it):
            n = roman_to_int(num)
            if n:
                chapters.append((n, chunk))
    if not chapters:
        chapters = [(1, body)]
        quality = "single-block"
    else:
        quality = "chapter-parsed"

    out = []
    explicit_chapters = quality == "chapter-parsed"
    ch_counter = 0
    for ch_num, chunk in chapters:
        chunk = chunk.strip()
        if not chunk:
            continue
        # pad so a chunk-leading verse number still satisfies the lookbehind
        parts = VERSE_SPLIT.split(" " + chunk + " ")
        # parts: [pre, num, seg, num, seg, ...]
        verses: list[tuple[int, str]] = []
        if len(parts) >= 3:
            it = iter(parts[1:])
            for num, seg in zip(it, it):
                seg = clean_text(seg)
                if seg and len(seg) > 2:
                    verses.append((int(num), seg))
        if len(verses) < 5 and len(chunk) > 5000:
            # prose translation without verse numbers (e.g. Word and
            # Revelation of Esdras): fall back to paragraph-per-verse
            paras = [clean_text(p) for p in chunk.split("\n")]
            # cycle 1..100 so the verse-reset logic opens a new chapter and
            # numbers stay under the 250 cap
            verses = [(i % 100 + 1, p) for i, p in enumerate(p for p in paras if len(p) >= 30)]
            quality = "paragraph-fallback"
        elif not verses:
            seg = clean_text(chunk)
            if seg:
                verses = [(1, seg)]
        # within a chunk, a verse-number reset means a new chapter
        # (single-block pages have no explicit chapter markers at all)
        ch_counter = ch_num if explicit_chapters else ch_counter + 1
        last_vs = 0
        seen: set[tuple[int, int]] = set()
        for vs, vtext in verses:
            if vs == 0 or vs > 250:
                continue
            if vs <= last_vs and not explicit_chapters:
                ch_counter += 1
            elif vs <= last_vs:
                continue  # explicit chapters: out-of-order number is noise
            last_vs = vs
            if (ch_counter, vs) in seen:
                continue
            seen.add((ch_counter, vs))
            out.append(record("PSEUD-" + code, bname + " (R.H. Charles)",
                              "pseudepigrapha", code, bname, ch_counter, vs,
                              vtext, src, quality))
    return out, set()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = []

    # scrollmapper
    for path in sorted((EXTERNAL / "scrollmapper").glob("*.json")):
        recs, unknown = normalize_scrollmapper(path)
        write_version(path.stem, recs)
        summary.append((path.stem, len(recs), sorted(unknown)))

    # ebible
    for path in sorted((EXTERNAL / "ebible").glob("*_vpl.zip")):
        tid = path.stem.replace("_vpl", "")
        recs, unknown = normalize_ebible(path)
        write_version(tid, recs)
        summary.append((tid, len(recs), sorted(unknown)))

    # wesley pseudepigrapha — prefer the larger of alt/main duplicates.
    # Pages under ~13KB are navigation shells with no text body; skip them.
    wesley_files = {}
    for path in sorted((EXTERNAL / "wesley_nnu").glob("*.html")):
        base = path.stem.removesuffix("-alt")
        cur = wesley_files.get(base)
        if cur is None or path.stat().st_size > cur.stat().st_size:
            wesley_files[base] = path
    wesley_files = {b: p for b, p in wesley_files.items() if p.stat().st_size >= 13000}
    for base, path in sorted(wesley_files.items()):
        recs, _ = normalize_wesley(path, base)
        write_version(f"PSEUD-{base}", recs)
        summary.append((f"PSEUD-{base}", len(recs), []))

    print(f"{'translation':<32}{'verses':>8}  unknown_books")
    for tid, n, unknown in summary:
        print(f"{tid:<32}{n:>8}  {unknown if unknown else ''}")
    return 0


def write_version(tid: str, recs: list[dict]) -> None:
    out = OUT_DIR / f"{tid}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
