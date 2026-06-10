#!/usr/bin/env python3
"""
train_tokenizer.py - Train a byte-fallback BPE tokenizer from scratch on a
configured Tokenless corpus. NO pretrained vocabulary. NO external tokenizer.

Uses sentencepiece's training harness (pure algorithm, zero pretrained data).
Output: $TOKENLESS_HOME/tokenizer/bpe_v1_20m.model + .vocab
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import sentencepiece as spm

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
TOKENLESS_HOME = Path(os.environ.get("TOKENLESS_HOME", str(SCRIPT_DIR.parent)))
DEFAULT_CORPUS = TOKENLESS_HOME / "corpus" / "domain_corpus_v1" / "corpus.txt"
OUT_DIR = TOKENLESS_HOME / "tokenizer"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--vocab-size", type=int, default=16000)
    parser.add_argument("--model-type", default="bpe", choices=["bpe", "unigram"])
    parser.add_argument("--prefix", default="bpe_v1_20m")
    args = parser.parse_args()

    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        print(f"ERROR: corpus not found at {corpus_path}. "
              f"Build the domain corpus first (consuming project responsibility).",
              file=sys.stderr)
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model_prefix = OUT_DIR / args.prefix

    print(f"Training {args.model_type.upper()} tokenizer: vocab={args.vocab_size}, "
          f"corpus={corpus_path}")

    spm.SentencePieceTrainer.train(
        input=str(corpus_path),
        model_prefix=str(model_prefix),
        vocab_size=args.vocab_size,
        model_type=args.model_type,
        character_coverage=1.0,
        pad_id=0, unk_id=1, bos_id=2, eos_id=3,
        pad_piece="<pad>", unk_piece="<unk>",
        bos_piece="<s>",   eos_piece="</s>",
        input_sentence_size=2_000_000,
        shuffle_input_sentence=True,
        normalization_rule_name="identity",   # preserve Greek/Hebrew/Unicode
        max_sentence_length=32768,
        num_threads=8,
        byte_fallback=True,                    # guarantee unknown-byte coverage
        user_defined_symbols=[
            # Consuming projects extend this list with their own source/section
            # markers. The two below are generic; the rest are domain-specific.
            "<|source|>", "<|endsource|>",
        ],
        split_by_whitespace=True,
        treat_whitespace_as_suffix=False,
        allow_whitespace_only_pieces=True,
    )

    # Quick sanity check
    sp = spm.SentencePieceProcessor(model_file=str(model_prefix) + ".model")
    sample_text = "The quick brown fox jumps over the lazy dog."
    ids = sp.encode(sample_text)
    decoded = sp.decode(ids)
    print(f"Sample encode: {len(ids)} tokens")
    print(f"  text:     {sample_text!r}")
    print(f"  ids[:20]: {ids[:20]}")
    print(f"  decoded:  {decoded!r}")
    print(f"Actual vocab size: {sp.vocab_size()}")

    info = {
        "prefix": str(model_prefix),
        "vocab_size": sp.vocab_size(),
        "model_type": args.model_type,
        "corpus_file": str(corpus_path),
        "special_tokens": {
            "pad_id": 0, "unk_id": 1, "bos_id": 2, "eos_id": 3,
        },
    }
    (OUT_DIR / f"{args.prefix}.info.json").write_text(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
