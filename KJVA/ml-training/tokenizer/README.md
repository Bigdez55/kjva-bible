# Tokenizer Workspace

The BPE baseline tokenizer is generated here from the local KJV corpus.

Expected generated files:

- `kjv_bpe_v1_20m.model`
- `kjv_bpe_v1_20m.vocab`

Generate with:

```bash
python3 ml-training/scripts/run_retrain.py \
  --recipe Bible_Tokenless_POC/training/kjv_retrain.yaml \
  --stage train
```

Tokenizer binaries and vocab dumps are ignored by Git. The byte-level model does
not use a tokenizer and instead uses `corpus/eng_kjv_apocrypha_v1/byte_vocab.json`.
