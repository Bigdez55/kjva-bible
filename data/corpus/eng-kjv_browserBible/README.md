# eng-kjv_browserBible — KJV + Apocrypha Browser Bible HTML

Per-chapter HTML files for the King James Version + Apocrypha in
BibleGateway-compatible browser format, sourced from the eBible.org
Browser Bible distribution.

## Contents

~1,490 HTML files named `<BOOK_CODE><CHAPTER>.html` (e.g. `GEN1.html`,
`AC1.html` for Acts chapter 1). Each file contains a single chapter with
verse markup, cross-reference anchors, and heading tags.

Book codes follow the standard OSIS abbreviations. Apocrypha books use
OSIS Deuterocanonical codes (e.g. `AC` = 1 Esdras in some distributions).

## Role in ml-training Pipeline

Used as a **metadata crosscheck source** alongside `eng-kjv_html/`. The
benchmark script `benchmark_byte.py` can parse chapter/verse structure from
these files for per-book perplexity evaluation.

Not used directly in training — `eng-kjv_vpl/eng-kjv_vpl.txt` is the
authoritative corpus source.

## Do Not Modify

These are read-only reference files. Do not edit, reformat, or delete
individual chapter files. If a chapter appears malformed, compare against
`eng-kjv_html/` and `eng-kjv_vpl/eng-kjv_vpl.xml`.
