# ADR 0002: Byte-level tokenizer and 18M parameter scale

## Status

Accepted (retroactive — captures the model architecture choice visible in backend/model.py and KJVA training metadata)

## Context

KJVA serves KJV scripture, which uses early-modern English with extensive proper nouns (Hebrew/Greek transliterations) and a small but fixed corpus (~36,822 verses + Apocrypha). A subword tokenizer (BPE/Unigram) would require a training pass on this narrow domain and would handle the long tail of Hebrew names poorly. The author also wanted to keep model size small enough to train + ship without GPU dependencies.

## Decision

Use a byte-level tokenizer with vocab=259 (256 bytes + 3 special tokens) and an 18M-parameter transformer: 8 layers, d_model=384, 6 attention heads. Validation perplexity = 3.21. Weights distributed as a single 72 MB safetensors file.

## Options considered

1. **Byte-level (chosen)** — vocab=259, no tokenizer training, perfectly handles any Unicode input including proper nouns.
2. **Custom BPE trained on KJV** — Smaller context lengths in tokens, but requires tokenizer artifact alongside weights; brittle to OOV outside corpus.
3. **GPT-2 BPE (off-the-shelf)** — Works out of the box, but trained on modern web text; biases against early-modern KJV English ("thou", "thee", "behold").
4. **SentencePiece unigram** — Similar issues to BPE; extra dependency.

## Why this decision wins

A 36,822-verse corpus is small enough that the additional sequence length cost of byte-level (~4x vs subword) is irrelevant in practice — most verses fit in well under 512 bytes. Byte-level eliminates the tokenizer-versioning problem entirely (no tokenizer.json shipping alongside weights) and handles every Hebrew/Greek proper noun without OOV behavior. 18M params is the smallest scale that achieved sub-4 validation perplexity in training experiments.

## Tradeoffs

- **Benefit:** Zero tokenizer state to ship/version. Perfect Unicode handling.
- **Benefit:** Small enough (72 MB) to mount as a single file at runtime.
- **Cost:** ~4x longer sequence lengths than a subword tokenizer; context window is byte-measured.
- **Cost:** 18M params cannot match a larger LM on open-ended generation; this is mitigated by retrieval-first completion (ADR-0003).
- **Reversibility:** Low for the trained weights themselves — switching tokenizers requires full retraining. The retrieval layer (ADR-0003) is independent and provides graceful degradation if the model is ever retired.

## Affected components

- `backend/model.py` — `TokenlessLM`, vocab=259
- `backend/inference.py` — byte-level encode/decode, sampling
- `KJVA/training/weights.safetensors` — frozen weights, 18M params
- training pipeline (out of tree, in Tokenless-Models repo)

## Rollback path

If model quality is inadequate: retain retrieval layer (ADR-0003) and demote AI fallback to disabled-by-default. Train a replacement model upstream and swap weights without changing the inference API contract.
