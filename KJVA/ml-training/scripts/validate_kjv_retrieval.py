#!/usr/bin/env python3
"""Validate citation and retrieval gates for the KJV bundle."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from kjv_retrieval import KJVRetriever  # noqa


DIRECT_CASES = [
    ("GEN 1:1", ["GEN.1.1"]),
    ("Psalm 23:1", ["PSA.23.1"]),
    ("Proverbs 3:5-6", ["PRO.3.5", "PRO.3.6"]),
    ("John 3:16", ["JHN.3.16"]),
    ("Matthew 5:3-12", [f"MAT.5.{i}" for i in range(3, 13)]),
    ("Tobit 1:1", ["TOB.1.1"]),
]


NATURAL_CASES = [
    ("in the beginning god created the heaven and the earth", "GEN.1.1"),
    ("the lord is my shepherd i shall not want", "PSA.23.1"),
    ("trust in the lord with all thine heart lean not unto thine own understanding", "PRO.3.5"),
    ("god so loved the world that he gave his only begotten son", "JHN.3.16"),
    ("blessed are the poor in spirit for theirs is the kingdom of heaven", "MAT.5.3"),
    ("our father which art in heaven hallowed be thy name", "MAT.6.9"),
    ("for by grace are ye saved through faith", "EPH.2.8"),
    ("faith is the substance of things hoped for the evidence of things not seen", "HEB.11.1"),
    ("charity suffereth long and is kind charity envieth not", "1CO.13.4"),
    ("i am alpha and omega the beginning and the ending", "REV.1.8"),
]


APOCRYPHA_CASES = [
    ("the book of the words of tobit son of tobiel", "TOB.1.1"),
    ("love righteousness ye that be judges of the earth", "WIS.1.1"),
    ("all wisdom cometh from the lord and is with him for ever", "SIR.1.1"),
    ("alexander son of philip the macedonian smitten darius", "1MA.1.1"),
    ("for god made not death neither hath he pleasure in the destruction of the living", "WIS.1.13"),
    ("the fear of the lord is honour and glory and gladness", "SIR.1.11"),
    ("i tobit have walked all the days of my life in the ways of truth and justice", "TOB.1.3"),
    ("there came out of them a wicked root antiochus surnamed epiphanes", "1MA.1.10"),
    ("the ear of jealousy heareth all things and the noise of murmurings is not hid", "WIS.1.10"),
    ("the fear of the lord maketh a merry heart", "SIR.1.12"),
]


def rate(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    return sum(1 for row in results if row["pass"]) / len(results)


def collect_absolute_paths(value: Any, path: str = "$") -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            hits.extend(collect_absolute_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            hits.extend(collect_absolute_paths(child, f"{path}[{idx}]"))
    elif isinstance(value, str) and value.startswith("/"):
        hits.append({"json_path": path, "value": value})
    return hits


def validate_manifest(corpus_dir: Path) -> dict[str, Any]:
    manifest_path = corpus_dir / "manifest.json"
    if not manifest_path.exists():
        return {"pass": False, "error": "missing_manifest"}
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    absolute_paths = collect_absolute_paths(data)
    return {
        "pass": not absolute_paths,
        "absolute_source_paths": absolute_paths,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--natural-top3-min", type=float, default=0.90)
    parser.add_argument("--apocrypha-top3-min", type=float, default=0.90)
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir)
    retriever = KJVRetriever(corpus_dir)

    direct_results = []
    for query, expected_ids in DIRECT_CASES:
        got = retriever.cite(query)
        got_ids = [v["id"] for v in got.get("verses", [])]
        direct_results.append({
            "query": query,
            "expected_ids": expected_ids,
            "got_ids": got_ids,
            "pass": got.get("ok") and got_ids == expected_ids,
        })

    natural_results = []
    for query, expected_id in NATURAL_CASES:
        hits = retriever.search(query, top_k=3)
        got_ids = [hit.doc["id"] for hit in hits]
        natural_results.append({
            "query": query,
            "expected_id": expected_id,
            "got_ids": got_ids,
            "pass": expected_id in got_ids,
        })

    apocrypha_results = []
    for query, expected_id in APOCRYPHA_CASES:
        hits = retriever.search(query, top_k=3, canon_category="apocrypha")
        got_ids = [hit.doc["id"] for hit in hits]
        apocrypha_results.append({
            "query": query,
            "expected_id": expected_id,
            "got_ids": got_ids,
            "pass": expected_id in got_ids,
        })

    manifest_gate = validate_manifest(corpus_dir)
    direct_rate = rate(direct_results)
    natural_rate = rate(natural_results)
    apocrypha_rate = rate(apocrypha_results)
    report = {
        "retrieval_docs": retriever.retrieval_docs,
        "corpus_id": retriever.corpus_id,
        "direct_citation": {
            "rate": direct_rate,
            "required": 1.0,
            "pass": direct_rate == 1.0,
            "cases": direct_results,
        },
        "natural_language_retrieval": {
            "top3_rate": natural_rate,
            "required": args.natural_top3_min,
            "pass": natural_rate >= args.natural_top3_min,
            "cases": natural_results,
        },
        "apocrypha_retrieval": {
            "top3_rate": apocrypha_rate,
            "required": args.apocrypha_top3_min,
            "pass": apocrypha_rate >= args.apocrypha_top3_min,
            "cases": apocrypha_results,
        },
        "manifest_hygiene": manifest_gate,
    }
    report["pass"] = (
        report["direct_citation"]["pass"]
        and report["natural_language_retrieval"]["pass"]
        and report["apocrypha_retrieval"]["pass"]
        and manifest_gate["pass"]
    )

    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
