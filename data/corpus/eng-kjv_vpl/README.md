# eng-kjv_vpl — KJV + Apocrypha Verse-Per-Line Source

Canonical source files for the King James Version + Apocrypha corpus in
Verse-Per-Line (VPL) format, produced by the HAIOLA Bible tool.

## Contents

| File | Description |
|---|---|
| `eng-kjv_vpl.txt` | 36,822 verses, plain UTF-8 VPL (used as primary corpus) |
| `eng-kjv_vpl.xml` | OSIS XML encoding of the same 36,822 verses (crosscheck) |
| `eng-kjv_vpl.sql` | SQLite dump of verse table |
| `eng-kjv_about.htm` | HAIOLA metadata page |
| `haiola.css` | Stylesheet for HAIOLA HTML output |
| `signature.txt.asc` | PGP signature for authenticity verification |

## Corpus Statistics

- **Total verses:** 36,822
- **OT books:** 39 (23,145 verses)
- **Apocrypha books:** 18 (5,720 verses)
- **NT books:** 27 (7,957 verses)
- **Encoding:** UTF-8

## Role in ml-training Pipeline

`eng-kjv_vpl.txt` is the primary input to the byte tokenizer:

```bash
python3 ml-training/scripts/train_byte.py \
  --corpus eng-kjv_vpl/eng-kjv_vpl.txt \
  --run-id kjv_byte_v1_20m
```

The processed corpus is cached as:
`ml-training/corpus/eng_kjv_apocrypha_v1/tokens_byte_uint16.npy`

`eng-kjv_vpl.xml` is loaded by `ml-training/scripts/benchmark_byte.py` for
per-canon and per-book perplexity breakdowns.

## Do Not Modify

These files are upstream source material. Any corpus preprocessing should
produce derivative files under `ml-training/corpus/` — never modify the
VPL source files directly.
