#!/usr/bin/env python3
"""Fetch all corpus v2 sources into data/corpus/external/.

Per SPEC-KJVA-FUNC-0002-multi-version-corpus-expansion. Idempotent: existing
files are skipped unless --force. Every fetched file gets sha256 + size
recorded in data/corpus/external/fetch_manifest.json.

NKJV is NOT fetched: copyright Thomas Nelson 1982. See ingest_licensed.py.
"""
import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL = REPO_ROOT / "data" / "corpus" / "external"
MANIFEST_PATH = EXTERNAL / "fetch_manifest.json"

UA = "kjva-bible-corpus-builder/1.0 (personal research; contact: repo owner)"

SCROLLMAPPER_IDS = [
    "KJV", "KJVA", "KJVPCE", "AKJV", "UKJV", "RNKJV", "MKJV",
    "Webster", "RWebster", "Geneva1599", "Tyndale", "Wycliffe", "JPS",
]
SCROLLMAPPER_URL = (
    "https://raw.githubusercontent.com/scrollmapper/bible_databases/"
    "master/formats/json/{tid}.json"
)

EBIBLE_IDS = ["engwebster", "enggnv", "engDRA", "engjps", "hboWLC"]
EBIBLE_URL = "https://ebible.org/Scriptures/{tid}_vpl.zip"

WESLEY_BASE = (
    "https://wesley.nnu.edu/sermons-essays-books/noncanonical-literature/"
    "noncanonical-literature-ot-pseudepigrapha/{slug}/"
)
# slug -> book id used downstream. Summary-only pages are excluded.
WESLEY_SLUGS = {
    "book-of-enoch": "1-enoch",
    "the-first-book-of-enoch": "1-enoch-alt",
    "2-enoch": "2-enoch",
    "jubilees": "jubilees-alt",
    "the-book-of-jubilees": "jubilees",
    "2-baruch": "2-baruch-alt",
    "the-book-of-the-apocalypse-of-baruch-the-son-of-neriah-or-2-baruch": "2-baruch",
    "3-baruch": "3-baruch-alt",
    "the-greek-apocalypse-of-baruch-or-3-baruch": "3-baruch",
    "4-baruch-paraleipomena-jeremiou": "4-baruch",
    "apocalypse-of-abraham": "apocalypse-of-abraham",
    "testaments-of-the-twelve-patriarchs": "testaments-twelve-patriarchs",
    "testament-of-abraham": "testament-of-abraham",
    "testament-of-job": "testament-of-job",
    "testament-of-solomon": "testament-of-solomon",
    "the-letter-of-aristeas": "letter-of-aristeas",
    "the-life-of-adam-and-eve": "life-of-adam-and-eve",
    "the-books-of-adam-and-eve": "books-of-adam-and-eve",
    "slavanic-life-of-adam-and-eve": "slavonic-adam-and-eve",
    "the-apocalypse-of-moses": "apocalypse-of-moses",
    "the-martyrdom-of-isaiah": "martyrdom-of-isaiah",
    "the-psalms-of-solomon": "psalms-of-solomon",
    "joseph-and-aseneth": "joseph-and-aseneth",
    "pseudo-phocylides": "pseudo-phocylides",
    "word-and-revelation-of-esdras": "word-revelation-esdras",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path, force: bool) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    status = "cached"
    if force or not dest.exists() or dest.stat().st_size == 0:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.write_bytes(resp.read())
        status = "fetched"
    return {
        "url": url,
        "path": str(dest.relative_to(REPO_ROOT)),
        "bytes": dest.stat().st_size,
        "sha256": sha256(dest),
        "status": status,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    manifest = {"generated_by": "scripts/corpus/fetch_sources.py", "entries": [], "errors": []}

    jobs = []
    for tid in SCROLLMAPPER_IDS:
        jobs.append((SCROLLMAPPER_URL.format(tid=tid),
                     EXTERNAL / "scrollmapper" / f"{tid}.json", 0.2))
    for tid in EBIBLE_IDS:
        jobs.append((EBIBLE_URL.format(tid=tid),
                     EXTERNAL / "ebible" / f"{tid}_vpl.zip", 0.5))
    for slug, book_id in WESLEY_SLUGS.items():
        jobs.append((WESLEY_BASE.format(slug=slug),
                     EXTERNAL / "wesley_nnu" / f"{book_id}.html", 1.0))

    for url, dest, delay in jobs:
        try:
            entry = fetch(url, dest, args.force)
            manifest["entries"].append(entry)
            print(f"[{entry['status']}] {entry['path']} ({entry['bytes']:,} bytes)")
            if entry["status"] == "fetched":
                time.sleep(delay)
        except Exception as exc:  # noqa: BLE001 — record and continue; manifest is the report
            manifest["errors"].append({"url": url, "error": str(exc)})
            print(f"[ERROR] {url}: {exc}", file=sys.stderr)

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\nmanifest: {MANIFEST_PATH}")
    print(f"ok={len(manifest['entries'])} errors={len(manifest['errors'])}")
    return 1 if manifest["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
