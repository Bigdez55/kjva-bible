#!/usr/bin/env python3
"""Ingest an owner-supplied LICENSED translation (e.g. NKJV) into corpus v2.

The NKJV is copyright Thomas Nelson, Inc. (1982) and cannot be scraped or
redistributed. If the owner obtains a licensed digital copy, this script
normalizes it locally into data/corpus_v2/versions/ — the file stays on this
machine and is never committed (the directory pattern is gitignored for
licensed IDs).

Accepted input formats:
  --format json   scrollmapper-style {translation, books:[{name, chapters:[{chapter, verses:[{verse,text}]}]}]}
  --format vpl    verse-per-line text: "GEN 1:1 In the beginning..."

Usage:
  python3 scripts/corpus/ingest_licensed.py --id NKJV --name "New King James Version" \
      --format vpl /path/to/licensed/nkjv.txt
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize_sources import (  # noqa: E402
    OUT_DIR, TRANSLATION_META, VPL_LINE, book_code, clean_text, record,
    write_version,
)
import json  # noqa: E402

LICENSED_IDS = {"NKJV", "KJ21", "MEV", "NKJV-licensed"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--id", required=True, help="translation id, e.g. NKJV")
    ap.add_argument("--name", required=True, help="display name")
    ap.add_argument("--format", choices=["json", "vpl"], required=True)
    args = ap.parse_args()

    if not args.input.exists():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 1

    print(f"NOTICE: ingesting '{args.id}' as LICENSED material. It will be "
          f"normalized locally only; do not commit or redistribute.")

    tid = args.id
    TRANSLATION_META[tid] = (args.name, "kjv_lineage")
    src = {"primary": f"owner-licensed copy: {args.input.name}",
           "license": "owner-held license; local use only; NOT redistributable"}
    out = []
    if args.format == "json":
        data = json.loads(args.input.read_text(encoding="utf-8"))
        for book in data["books"]:
            code = book_code(book["name"])
            if not code:
                print(f"  unknown book skipped: {book['name']}", file=sys.stderr)
                continue
            for ch in book["chapters"]:
                for v in ch["verses"]:
                    text = clean_text(v["text"])
                    if text:
                        out.append(record(tid, args.name, "kjv_lineage", code,
                                          book["name"], ch["chapter"], v["verse"], text, src))
    else:
        for line in args.input.read_text(encoding="utf-8-sig").splitlines():
            m = VPL_LINE.match(line.strip())
            if not m:
                continue
            text = clean_text(m.group(4))
            if text:
                out.append(record(tid, args.name, "kjv_lineage", m.group(1),
                                  m.group(1), int(m.group(2)), int(m.group(3)), text, src))

    write_version(tid, out)
    print(f"wrote {len(out):,} verses -> {OUT_DIR / (tid + '.jsonl')}")
    print("Re-run scripts/corpus/build_corpus_v2.py to rebuild corpus.txt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
