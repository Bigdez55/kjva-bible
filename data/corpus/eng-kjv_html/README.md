# eng-kjv_html — KJV + Apocrypha Chapter-Level HTML

Per-chapter HTML files for the King James Version + Apocrypha in a compact
chapter-per-file format. Companion to `eng-kjv_browserBible/`.

## Contents

~1,470 HTML files named `<BOOK_CODE>.htm` (index) and `<BOOK_CODE><NN>.htm`
(individual chapters), e.g. `1CH.htm` (1 Chronicles index), `1CH01.htm`
(chapter 1). These follow the `.htm` extension convention (vs `.html` in
`eng-kjv_browserBible/`).

## Role in ml-training Pipeline

Used as a **secondary metadata crosscheck source**. The benchmark script
`benchmark_byte.py` references these for per-chapter verse counts and book
structure validation.

Not used directly in training — `eng-kjv_vpl/eng-kjv_vpl.txt` is the
authoritative corpus source.

## Do Not Modify

Read-only reference files. Do not edit or reformat. Compare against
`eng-kjv_browserBible/` and `eng-kjv_vpl/` if discrepancies are found.
