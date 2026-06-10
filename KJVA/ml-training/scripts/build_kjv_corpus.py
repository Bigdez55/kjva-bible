#!/usr/bin/env python3
"""Build the KJV + Apocrypha corpus and retrieval artifacts.

The VPL XML file is the canonical verse source. The VPL text file is used as a
cross-check. HTML/browser files provide optional footnotes and Strong's-style
lemma metadata for retrieval, but their markup is not trained directly.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


OLD_TESTAMENT = {
    "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT", "1SA", "2SA",
    "1KI", "2KI", "1CH", "2CH", "EZR", "NEH", "EST", "JOB", "PSA", "PRO",
    "ECC", "SNG", "ISA", "JER", "LAM", "EZK", "DAN", "HOS", "JOL", "AMO",
    "OBA", "JON", "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL",
}
APOCRYPHA = {
    "TOB", "JDT", "ESG", "WIS", "SIR", "BAR", "S3Y", "SUS", "BEL", "1MA",
    "2MA", "1ES", "MAN", "2ES",
}
NEW_TESTAMENT = {
    "MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH",
    "PHP", "COL", "1TH", "2TH", "1TI", "2TI", "TIT", "PHM", "HEB", "JAS",
    "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV",
}
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
TOKENLESS_HOME = Path(os.environ.get("TOKENLESS_HOME", str(REPO_ROOT / "ml-training")))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_for_crosscheck(text: str) -> str:
    text = clean_text(text)
    text = text.replace("[", "").replace("]", "").replace("¶", "")
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def canon_category(book: str) -> str:
    if book in OLD_TESTAMENT:
        return "old_testament"
    if book in APOCRYPHA:
        return "apocrypha"
    if book in NEW_TESTAMENT:
        return "new_testament"
    return "unknown"


def parse_book_names(html_dir: Path) -> dict[str, dict[str, str]]:
    parms = html_dir / "eng-kjv-VernacularParms.xml"
    names: dict[str, dict[str, str]] = defaultdict(dict)
    if not parms.exists():
        return names
    raw = parms.read_text(encoding="utf-8-sig", errors="replace")
    pat = re.compile(
        r'<scriptureBook\s+ubsAbbreviation="([^"]+)"\s+parm="([^"]+)">(.*?)</scriptureBook>'
    )
    for code, parm, value in pat.findall(raw):
        names[code][parm] = clean_text(value)
    return names


def parse_browser_info(browser_dir: Path, ubs_order: list[str]) -> dict[str, dict[str, str]]:
    info_path = browser_dir / "info.json"
    if not info_path.exists():
        return {}
    info = json.loads(info_path.read_text(encoding="utf-8"))
    divisions = info.get("divisions", [])
    names = info.get("divisionNames", [])
    # Browser divisions include the preface first; verse XML starts at Genesis.
    div_books = [d for d in divisions if d != "FR"]
    div_names = names[1:] if names and names[0].lower().startswith("preface") else names
    mapping: dict[str, dict[str, str]] = {}
    for idx, ubs in enumerate(ubs_order):
        if idx < len(div_books):
            mapping[ubs] = {
                "browser_code": div_books[idx],
                "browser_name": div_names[idx] if idx < len(div_names) else "",
            }
    return mapping


def parse_xml_verses(xml_path: Path, book_names: dict[str, dict[str, str]],
                     browser_map: dict[str, dict[str, str]], repo_root: Path) -> list[dict[str, Any]]:
    root = ET.parse(xml_path).getroot()
    verses: list[dict[str, Any]] = []
    book_order: dict[str, int] = {}
    for node in root.findall(".//v"):
        book = node.attrib["b"]
        if book not in book_order:
            book_order[book] = len(book_order) + 1
        chapter = int(node.attrib["c"])
        verse = int(node.attrib["v"])
        text = clean_text("".join(node.itertext()))
        names = book_names.get(book, {})
        browser = browser_map.get(book, {})
        verse_id = f"{book}.{chapter}.{verse}"
        verses.append({
            "id": verse_id,
            "ref": f"{book} {chapter}:{verse}",
            "book": book,
            "book_name": names.get("vernacularAbbreviatedName")
            or names.get("vernacularFullName")
            or browser.get("browser_name")
            or book,
            "book_full_name": names.get("vernacularFullName")
            or browser.get("browser_name")
            or book,
            "browser_code": browser.get("browser_code", ""),
            "chapter": chapter,
            "verse": verse,
            "canon_category": canon_category(book),
            "book_order": book_order[book],
            "text": text,
            "source": {
                "primary": rel(xml_path, repo_root),
            },
        })
    return verses


def parse_vpl_book_order(vpl_path: Path) -> list[str]:
    order: list[str] = []
    seen: set[str] = set()
    pat = re.compile(r"^(\S+)\s+\d+:\d+\s+")
    for line in vpl_path.read_text(encoding="utf-8-sig").splitlines():
        m = pat.match(line)
        if not m:
            continue
        book = m.group(1)
        if book not in seen:
            seen.add(book)
            order.append(book)
    return order


def parse_vpl_text(vpl_path: Path, vpl_to_ubs: dict[str, str] | None = None) -> dict[str, str]:
    out: dict[str, str] = {}
    vpl_to_ubs = vpl_to_ubs or {}
    pat = re.compile(r"^(\S+)\s+(\d+):(\d+)\s+(.*)$")
    for lineno, line in enumerate(vpl_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        m = pat.match(line)
        if not m:
            raise ValueError(f"invalid VPL line {lineno}: {line[:80]}")
        book, chapter, verse, text = m.groups()
        book = vpl_to_ubs.get(book, book)
        out[f"{book}.{int(chapter)}.{int(verse)}"] = clean_text(text)
    return out


def parse_html_footnotes(html_dir: Path) -> dict[tuple[str, int, int], list[str]]:
    footnotes: dict[tuple[str, int, int], list[str]] = defaultdict(list)
    if not html_dir.exists():
        return footnotes
    for path in sorted(html_dir.glob("*.htm")):
        m = re.match(r"^([1-3]?[A-Z]{2,3}|S3Y)(\d{2})\.htm$", path.name)
        if not m:
            continue
        book, chapter_s = m.groups()
        chapter = int(chapter_s)
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
        for block in re.findall(r'<p class="f"[^>]*>.*?</p>', raw, flags=re.S):
            ref_match = re.search(r">(\d+)\.(\d+)<", block)
            if not ref_match:
                continue
            verse = int(ref_match.group(2))
            notes = re.findall(r'<span class="ft">(.*?)</span>', block, flags=re.S)
            for note in notes:
                note_text = clean_text(re.sub(r"<[^>]+>", "", note))
                if note_text:
                    footnotes[(book, chapter, verse)].append(note_text)
    return footnotes


class _StrongParser(HTMLParser):
    def __init__(self, browser_to_ubs: dict[str, str]):
        super().__init__(convert_charrefs=True)
        self.browser_to_ubs = browser_to_ubs
        self.current: tuple[str, int, int] | None = None
        self.span_depth = 0
        self.strongs: dict[tuple[str, int, int], set[str]] = defaultdict(set)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: v or "" for k, v in attrs}
        if tag == "span":
            if self.current is not None:
                self.span_depth += 1
                return
            data_id = attr.get("data-id", "")
            cls = f" {attr.get('class', '')} "
            if " v " not in cls or not data_id:
                return
            m = re.match(r"^([A-Za-z0-9]+)(\d+)_(\d+)$", data_id)
            if not m:
                return
            bcode, chapter_s, verse_s = m.groups()
            book = self.browser_to_ubs.get(bcode)
            if not book:
                return
            self.current = (book, int(chapter_s), int(verse_s))
            self.span_depth = 1
            return
        if tag == "l" and self.current is not None:
            sid = attr.get("s", "")
            if sid:
                self.strongs[self.current].add(sid)

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self.current is not None:
            self.span_depth -= 1
            if self.span_depth <= 0:
                self.current = None
                self.span_depth = 0


def parse_browser_strongs(browser_dir: Path, browser_to_ubs: dict[str, str]
                          ) -> dict[tuple[str, int, int], list[str]]:
    strongs: dict[tuple[str, int, int], set[str]] = defaultdict(set)
    if not browser_dir.exists():
        return {}
    for path in sorted(browser_dir.glob("*.html")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        parser = _StrongParser(browser_to_ubs)
        parser.feed(raw)
        for key, values in parser.strongs.items():
            strongs[key].update(values)
    return {k: sorted(v) for k, v in strongs.items()}


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    xml_path = Path(args.primary_text)
    vpl_path = Path(args.crosscheck_text)
    html_dir = Path(args.html_dir)
    browser_dir = Path(args.browser_dir)

    book_names = parse_book_names(html_dir)
    # Need XML book order before browser mapping.
    root = ET.parse(xml_path).getroot()
    ubs_order: list[str] = []
    for node in root.findall(".//v"):
        b = node.attrib["b"]
        if b not in ubs_order:
            ubs_order.append(b)
    browser_map = parse_browser_info(browser_dir, ubs_order)
    browser_to_ubs = {
        meta["browser_code"]: ubs
        for ubs, meta in browser_map.items()
        if meta.get("browser_code")
    }

    verses = parse_xml_verses(xml_path, book_names, browser_map, repo_root)
    vpl_order = parse_vpl_book_order(vpl_path)
    vpl_to_ubs = {
        vpl_book: ubs_book
        for vpl_book, ubs_book in zip(vpl_order, ubs_order)
    } if len(vpl_order) == len(ubs_order) else {}
    vpl = parse_vpl_text(vpl_path, vpl_to_ubs)
    footnotes = parse_html_footnotes(html_dir)
    strongs = parse_browser_strongs(browser_dir, browser_to_ubs)

    mismatches = []
    for verse in verses:
        text_vpl = vpl.get(verse["id"])
        verse["text_vpl"] = text_vpl
        key = (verse["book"], verse["chapter"], verse["verse"])
        verse["footnotes"] = footnotes.get(key, [])
        verse["strongs"] = strongs.get(key, [])
        if text_vpl is None:
            mismatches.append({"id": verse["id"], "issue": "missing_in_vpl"})
        elif normalize_for_crosscheck(text_vpl) != normalize_for_crosscheck(verse["text"]):
            mismatches.append({
                "id": verse["id"],
                "issue": "text_mismatch",
                "xml": verse["text"],
                "vpl": text_vpl,
            })

    xml_ids = {v["id"] for v in verses}
    for verse_id in sorted(set(vpl) - xml_ids):
        mismatches.append({"id": verse_id, "issue": "extra_in_vpl"})

    verses_path = out_dir / "verses.jsonl"
    with verses_path.open("w", encoding="utf-8") as f:
        for verse in verses:
            f.write(json.dumps(verse, ensure_ascii=False) + "\n")

    by_chapter: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for verse in verses:
        by_chapter[(verse["book"], verse["chapter"])].append(verse)

    corpus_path = out_dir / "corpus.txt"
    with corpus_path.open("w", encoding="utf-8") as f:
        chapters = sorted(
            by_chapter.items(), key=lambda item: (item[1][0]["book_order"], item[0][1])
        )
        for idx, ((book, chapter), chapter_verses) in enumerate(chapters):
            first = chapter_verses[0]
            f.write(
                f"<|source:kjv:{first['canon_category']}:{book}:{chapter}|>\n"
                f"Book: {first['book_full_name']}\n"
                f"Chapter: {chapter}\n"
                f"Canon: {first['canon_category']}\n\n"
            )
            for verse in chapter_verses:
                f.write(f"{verse['ref']} {verse['text_vpl'] or verse['text']}\n")
            f.write("<|endsource|>\n")
            if idx + 1 < len(chapters):
                f.write("\n")

    retrieval = {
        "corpus_id": args.corpus_id,
        "documents": [
            {
                "id": v["id"],
                "ref": v["ref"],
                "book": v["book"],
                "book_name": v["book_name"],
                "chapter": v["chapter"],
                "verse": v["verse"],
                "canon_category": v["canon_category"],
                "text": v["text_vpl"] or v["text"],
                "footnotes": v["footnotes"],
                "strongs": v["strongs"],
                "search_text": " ".join([
                    v["ref"],
                    v["book_name"],
                    v["book_full_name"],
                    v["text_vpl"] or v["text"],
                    " ".join(v["footnotes"]),
                    " ".join(v["strongs"]),
                ]),
            }
            for v in verses
        ],
    }
    retrieval_path = out_dir / "retrieval_index.json"
    write_json(retrieval_path, retrieval)

    byte_vocab_path = out_dir / "byte_vocab.json"
    write_json(byte_vocab_path, {
        "kind": "utf8_byte",
        "pad_id": 0,
        "bos_id": 1,
        "eos_id": 2,
        "byte_offset": 3,
        "vocab_size": 259,
        "byte_id_range": [3, 258],
    })

    counts = Counter(v["canon_category"] for v in verses)
    anchors = {
        "GEN.1.1": "GEN.1.1" in xml_ids,
        "PSA.23.1": "PSA.23.1" in xml_ids,
        "PRO.3.5": "PRO.3.5" in xml_ids,
        "PRO.3.6": "PRO.3.6" in xml_ids,
        "JHN.3.16": "JHN.3.16" in xml_ids,
        "MAT.5.3-12": all(f"MAT.5.{v}" in xml_ids for v in range(3, 13)),
        "apocrypha_any": any(v["canon_category"] == "apocrypha" for v in verses),
    }
    validation = {
        "pass": len(verses) == len(vpl) and not mismatches and all(anchors.values()),
        "xml_verse_count": len(verses),
        "vpl_verse_count": len(vpl),
        "mismatch_count": len(mismatches),
        "mismatches_sample": mismatches[:25],
        "anchors": anchors,
        "counts_by_canon": dict(counts),
        "footnoted_verses": sum(1 for v in verses if v["footnotes"]),
        "strongs_verses": sum(1 for v in verses if v["strongs"]),
    }
    validation_path = out_dir / "validation_report.json"
    write_json(validation_path, validation)

    source_files = [xml_path, vpl_path]
    for opt in [html_dir / "eng-kjv-VernacularParms.xml", browser_dir / "info.json"]:
        if opt.exists():
            source_files.append(opt)
    manifest = {
        "corpus_id": args.corpus_id,
        "created_by": "ml-training/scripts/build_kjv_corpus.py",
        "source_policy": {
            "primary_text": rel(xml_path, repo_root),
            "crosscheck_text": rel(vpl_path, repo_root),
            "metadata_sources": [rel(html_dir, repo_root), rel(browser_dir, repo_root)],
        },
        "stats": {
            "books": len(ubs_order),
            "chapters": len(by_chapter),
            "verses": len(verses),
            "counts_by_canon": dict(counts),
            "corpus_chars": corpus_path.stat().st_size,
        },
        "hashes": {
            "inputs": {rel(p, repo_root): sha256_file(p) for p in source_files},
            "outputs": {
                "verses.jsonl": sha256_file(verses_path),
                "corpus.txt": sha256_file(corpus_path),
                "retrieval_index.json": sha256_file(retrieval_path),
                "byte_vocab.json": sha256_file(byte_vocab_path),
                "validation_report.json": sha256_file(validation_path),
            },
        },
        "artifacts": {
            "verses": "verses.jsonl",
            "corpus": "corpus.txt",
            "retrieval_index": "retrieval_index.json",
            "byte_vocab": "byte_vocab.json",
            "validation_report": "validation_report.json",
        },
        "validation": validation,
        "attestation": (
            "KJV corpus built from provided local eng-kjv_vpl XML/VPL files. "
            "HTML/browser metadata is used only for retrieval enrichment."
        ),
    }
    manifest_path = out_dir / "manifest.json"
    write_json(manifest_path, manifest)

    if args.strict and not validation["pass"]:
        print(json.dumps(validation, indent=2), file=sys.stderr)
        raise SystemExit("KJV corpus validation failed")

    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-id", default="eng_kjv_apocrypha_v1")
    parser.add_argument("--primary-text", default="eng-kjv_vpl/eng-kjv_vpl.xml")
    parser.add_argument("--crosscheck-text", default="eng-kjv_vpl/eng-kjv_vpl.txt")
    parser.add_argument("--html-dir", default="eng-kjv_html")
    parser.add_argument("--browser-dir", default="eng-kjv_browserBible")
    parser.add_argument("--out-dir", default=str(TOKENLESS_HOME / "corpus/eng_kjv_apocrypha_v1"))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    manifest = build_outputs(args)
    print(json.dumps({
        "corpus_id": manifest["corpus_id"],
        "out_dir": str(Path(args.out_dir)),
        "stats": manifest["stats"],
        "validation_pass": manifest["validation"]["pass"],
        "mismatch_count": manifest["validation"]["mismatch_count"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
