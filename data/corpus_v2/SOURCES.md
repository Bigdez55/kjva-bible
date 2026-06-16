# Corpus v2 Sources & Licensing

Per `SPEC-KJVA-FUNC-0002-multi-version-corpus-expansion` / `SLICE-0002-corpus-expansion-v2`.
Built 2026-06-10. Rebuild: `python3 scripts/corpus/fetch_sources.py && python3 scripts/corpus/normalize_sources.py && python3 scripts/corpus/extract_fbe.py && python3 scripts/corpus/build_corpus_v2.py`

All raw files carry sha256 hashes in `data/corpus/external/fetch_manifest.json`.
Final stats and per-version hashes: `data/corpus_v2/manifest.json` (45 translations,
535,433 verses, 70.75M chars; validation 148/148 gates PASS).

## KJV lineage (scrollmapper/bible_databases, public domain / freely redistributable)

| ID | Version | Verses |
|---|---|---|
| KJV | King James Version 1769 | 31,102 |
| KJVA | KJV with Apocrypha (80 books) | 36,819 |
| KJVPCE | KJV Pure Cambridge Edition | 31,098 |
| AKJV | American King James Version | 31,102 |
| UKJV | Updated King James Version | 31,102 |
| RNKJV | Restored Name King James Version | 31,102 |
| MKJV | Modern King James Version (Green) — freely redistributable per source repo; flag retained | 31,102 |
| Webster | Webster Bible 1833 | 31,102 |
| RWebster | Revised Webster 1995 | 31,102 |
| Geneva1599 | Geneva Bible 1599 (KJV predecessor) | 31,064 |
| Tyndale | Tyndale 1525/1530 (partial canon) | 7,888 |
| Wycliffe | Wycliffe c.1395 | 36,207 |

eBible.org crosscheck witnesses (public domain): engwebster (31,102), enggnv (31,090),
engDRA — Douay-Rheims American 1899 with full deuterocanon (35,811).

## Torah / Tanakh (public domain)

- **JPS** — Jewish Publication Society 1917 Tanakh (scrollmapper): 23,194 verses
- **engjps** — JPS 1917 (eBible witness): 23,145 verses
- **hboWLC** — Westminster Leningrad Codex, Hebrew: 23,213 verses

## Apocrypha

KJVA carries the full 14-book KJV Apocrypha (~5,700 verses); engDRA adds the
Douay-Rheims deuterocanon as a second witness. (Corpus v1 `data/verses.jsonl`
already held KJV Apocrypha; v2 adds the cross-version witnesses.)

## Pseudepigrapha (public domain translations)

From **wesley.nnu.edu** (R.H. Charles-era translations): 1 Enoch (845), Jubilees
(1,176), 2 Baruch (663), 3 Baruch (124), Testament of Job (319), Letter of
Aristeas (237), Psalms of Solomon (327), Books of Adam and Eve (148), Slavonic
Adam and Eve (31), Apocalypse of Moses (156), Word & Revelation of Esdras (~140).

From **The Forgotten Books of Eden** (Platt 1926, PD; archive.org sacred-texts
digital edition): 2 Enoch / Secrets of Enoch (243), Odes of Solomon (1,012),
4 Maccabees (332), Story of Ahikar (341), Testaments of the Twelve Patriarchs
(12 books, ~1,000 verses total).

Parse quality is flagged per record (`parse_quality`: exact | chapter-parsed |
single-block | paragraph-fallback | ocr-approx).

### Future acquisitions (not yet sourced in clean PD form)
Apocalypse of Abraham, Testament of Abraham, Testament of Solomon, Martyrdom /
Ascension of Isaiah, 4 Baruch, Joseph and Aseneth, Sibylline Oracles, 3 Enoch.
(Wesley pages for these are navigation shells; archive.org scans were
OCR-unusable. Candidates: G.H. Box translations 1918-19 via better archive.org
items, or Wayback captures of sacred-texts.)

## NKJV — BLOCKED (copyright)

The **New King James Version is copyright © 1982 Thomas Nelson, Inc.**
(HarperCollins Christian Publishing). It cannot be scraped, downloaded, or
redistributed, and is therefore **excluded from this corpus**.

Path to include it:
1. Obtain a licensed digital copy (license inquiry:
   https://www.harpercollinschristian.com/permissions/).
2. Run `python3 scripts/corpus/ingest_licensed.py --id NKJV --name "New King James Version" --format vpl /path/to/licensed/nkjv.txt`
3. The normalized file stays local-only (gitignored); rebuild with
   `build_corpus_v2.py`.

The same path applies to KJ21, MEV, and any other copyrighted KJV-lineage
modernization.
