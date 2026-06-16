#!/usr/bin/env python3
"""Build the corpus v2 training text + manifest + validation report.

Per SPEC-KJVA-FUNC-0002. Reads data/corpus_v2/versions/*.jsonl, validates
against the spec gates, and writes:

  data/corpus_v2/corpus.txt              source-tagged training text
  data/corpus_v2/manifest.json           provenance + stats + validation flag
  data/corpus_v2/validation_report.json  per-gate results

corpus.txt block format follows eng_kjv_apocrypha_v1:

  <|source:<translation_id>:<canon_category>:<BOOK>:<chapter>|>
  Translation: <name>
  Book: <book name>
  Chapter: <n>
  Canon: <canon_category>

  <REF> <text>
  ...
"""
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSIONS = REPO_ROOT / "data" / "corpus_v2" / "versions"
OUT_DIR = REPO_ROOT / "data" / "corpus_v2"
FETCH_MANIFEST = REPO_ROOT / "data" / "corpus" / "external" / "fetch_manifest.json"

# expected counts: (min, max) verses; None = no gate (partial canons, parsed HTML)
EXPECTED = {
    "KJV": (30480, 31800), "KJVA": (36000, 37600), "KJVPCE": (30480, 31800),
    "AKJV": (30480, 31800), "UKJV": (30480, 31800), "RNKJV": (30480, 31800),
    "MKJV": (30480, 31800), "Webster": (30480, 31800), "RWebster": (30480, 31800),
    "Geneva1599": (30480, 31800), "JPS": (22500, 24500),
    "engjps": (22500, 24500), "hboWLC": (22500, 24500),
    "engwebster": (30480, 31800), "enggnv": (30480, 31800),
    "engDRA": (34000, 36500),
    "Tyndale": None, "Wycliffe": None,
}

ANCHORS = {  # translation_id -> list of (book, chapter, verse, must_contain_lower)
    "KJV": [("GEN", 1, 1, "in the beginning"), ("PSA", 23, 1, "shepherd"), ("JHN", 3, 16, "only begotten")],
    "KJVA": [("GEN", 1, 1, "in the beginning"), ("TOB", 1, 1, None), ("JHN", 3, 16, "only begotten")],
    "KJVPCE": [("GEN", 1, 1, "in the beginning"), ("JHN", 3, 16, "only begotten")],
    "JPS": [("GEN", 1, 1, "in the beginning"), ("DEU", 6, 4, "hear")],
    "hboWLC": [("GEN", 1, 1, None), ("DEU", 6, 4, None)],
    "engDRA": [("TOB", 1, 1, None), ("WIS", 1, 1, None)],
    "PSEUD-1-enoch": [("1ENOCH", 1, 1, None)],
}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    files = sorted(VERSIONS.glob("*.jsonl"))
    gates = []
    stats = {}
    all_lines = []

    for path in files:
        tid = path.stem
        recs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        ids = set()
        empties = dupes = 0
        by_book_ch = defaultdict(list)
        for r in recs:
            if not r["text"].strip():
                empties += 1
            if r["id"] in ids:
                dupes += 1
            ids.add(r["id"])
            by_book_ch[(r["book"], r["chapter"])].append(r)

        stats[tid] = {
            "verses": len(recs),
            "books": len({r["book"] for r in recs}),
            "chars": sum(len(r["text"]) for r in recs),
            "sections": sorted({r["corpus_section"] for r in recs}),
            "sha256": sha256_file(path),
        }
        gates.append({"gate": f"{tid}: no empty texts", "pass": empties == 0, "detail": empties})
        gates.append({"gate": f"{tid}: no duplicate ids", "pass": dupes == 0, "detail": dupes})

        exp = EXPECTED.get(tid)
        if tid.startswith("PSEUD-"):
            gates.append({"gate": f"{tid}: nonempty pseudepigrapha book", "pass": len(recs) > 0, "detail": len(recs)})
        elif exp:
            ok = exp[0] <= len(recs) <= exp[1]
            gates.append({"gate": f"{tid}: verse count in [{exp[0]},{exp[1]}]", "pass": ok, "detail": len(recs)})

        for (book, ch, vs, frag) in ANCHORS.get(tid, []):
            hit = next((r for r in recs if r["book"].startswith(book[:3]) and r["chapter"] == ch and r["verse"] == vs), None)
            ok = hit is not None and (frag is None or frag in hit["text"].lower())
            gates.append({"gate": f"{tid}: anchor {book} {ch}:{vs}", "pass": ok,
                          "detail": (hit["text"][:60] if hit else "MISSING")})

        # emit corpus blocks (one per chapter)
        if recs:
            meta0 = recs[0]
            for (book, ch), vlist in sorted(by_book_ch.items()):
                vlist.sort(key=lambda r: r["verse"])
                r0 = vlist[0]
                lines = [
                    f"<|source:{tid}:{r0['canon_category']}:{book}:{ch}|>",
                    f"Translation: {meta0['translation_name']}",
                    f"Book: {r0['book_name']}",
                    f"Chapter: {ch}",
                    f"Canon: {r0['canon_category']}",
                    "",
                ]
                lines.extend(f"{tid} {r['ref']} {r['text']}" for r in vlist)
                lines.append("")
                all_lines.append("\n".join(lines))

    # Deterministic shuffle of chapter blocks: without it the corpus is
    # ordered by translation file name and the trailing 2% (the trainer's
    # validation split) would be a single translation — the val_ppl gate
    # would measure only Hebrew WLC instead of the full mix.
    random.Random(42).shuffle(all_lines)

    corpus_path = OUT_DIR / "corpus.txt"
    corpus_path.write_text("\n".join(all_lines) + "\n", encoding="utf-8")

    all_pass = all(g["pass"] for g in gates)
    report = {"gates": gates, "pass": all_pass,
              "failed": [g for g in gates if not g["pass"]]}
    (OUT_DIR / "validation_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "corpus_id": "sacred_multi_v2",
        "spec": "SPEC-KJVA-FUNC-0002-multi-version-corpus-expansion",
        "translations": stats,
        "totals": {
            "translations": len(files),
            "verses": sum(s["verses"] for s in stats.values()),
            "chars": sum(s["chars"] for s in stats.values()),
            "corpus_txt_bytes": corpus_path.stat().st_size,
            "corpus_txt_sha256": sha256_file(corpus_path),
        },
        "fetch_manifest": str(FETCH_MANIFEST.relative_to(REPO_ROOT)) if FETCH_MANIFEST.exists() else None,
        "excluded": {"NKJV": "copyright Thomas Nelson 1982 — see SOURCES.md; use ingest_licensed.py with an owner-licensed copy"},
        "validation": {"pass": all_pass, "gates": len(gates),
                       "failed": len(report["failed"])},
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"translations={len(files)} verses={manifest['totals']['verses']:,} "
          f"chars={manifest['totals']['chars']:,}")
    print(f"corpus.txt: {manifest['totals']['corpus_txt_bytes']:,} bytes")
    print(f"validation: pass={all_pass} ({len(report['failed'])}/{len(gates)} gates failed)")
    for g in report["failed"]:
        print(f"  FAIL {g['gate']}: {g['detail']}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
