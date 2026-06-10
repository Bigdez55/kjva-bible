#!/usr/bin/env python3
"""
train_tokenizer.py - Train a byte-fallback BPE tokenizer from scratch on a
configured Tokenless corpus. NO pretrained vocabulary. NO external tokenizer.

Uses sentencepiece's training harness (pure algorithm, zero pretrained data).
Output: $TOKENLESS_HOME/tokenizer/kjv_bpe_v1_20m.model + .vocab
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
TOKENLESS_HOME = Path(os.environ.get("TOKENLESS_HOME", str(REPO_ROOT / "ml-training")))
DEFAULT_CORPUS = TOKENLESS_HOME / "corpus" / "eng_kjv_apocrypha_v1" / "corpus.txt"
OUT_DIR = TOKENLESS_HOME / "tokenizer"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--vocab-size", type=int, default=16000)
    parser.add_argument("--model-type", default="bpe", choices=["bpe", "unigram"])
    parser.add_argument("--prefix", default="kjv_bpe_v1_20m")
    args = parser.parse_args()

    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        print(f"ERROR: corpus not found at {corpus_path}. Run build_kjv_corpus.py first.",
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
            "<|source|>", "<|source:kjv|>", "<|endsource|>",
            "<|old_testament|>", "<|apocrypha|>", "<|new_testament|>",
        ],
        split_by_whitespace=True,
        treat_whitespace_as_suffix=False,
        allow_whitespace_only_pieces=True,
    )

    # Quick sanity check
    sp = spm.SentencePieceProcessor(model_file=str(model_prefix) + ".model")
    sample_text = "In the beginning was the Word, and the Word was with God."
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
