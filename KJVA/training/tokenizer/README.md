# Tokenizer Workspace

The BPE baseline tokenizer is generated here from the configured training
corpus. The byte-level model does NOT use this tokenizer — it operates on UTF-8
bytes via `corpus/<corpus-id>/byte_vocab.json` instead. This directory exists
for the BPE path only.

Expected generated files (under the default `--prefix bpe_v1_20m`):

- `bpe_v1_20m.model`
- `bpe_v1_20m.vocab`

Generate with:

```bash
python3 training/scripts/train_tokenizer.py \
  --corpus training/corpus/<your-corpus-id>/corpus.txt \
  --prefix bpe_v1_20m
```

Tokenizer binaries and vocab dumps are ignored by Git.
