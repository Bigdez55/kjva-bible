# Corpus Workspace

Corpus artifacts are generated from canonical local source datasets.

Current tracked corpus:

- `eng_kjv_apocrypha_v1/` - KJV plus Apocrypha corpus, verse records,
  retrieval index, byte-vocab metadata, manifest, and validation report.
- `programs/` - training-program corpus generated from the omni training
  registry.

Do not restore the removed legacy combined or scraped external corpus folders.
Regenerate corpus artifacts with:

```bash
python3 ml-training/scripts/run_retrain.py \
  --recipe Bible_Tokenless_POC/training/kjv_retrain.yaml \
  --stage prepare
```
