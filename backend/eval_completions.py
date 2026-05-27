#!/usr/bin/env python3
"""
eval_completions.py — Benchmark KJVA completion quality against ground truth.

Usage:
  cd backend
  python eval_completions.py [--n 100] [--seed 42] [--skip-model]

Measures three conditions:
  A  retrieval_first  — lookup_ref / search_prefix (exact, no model)
  B  raw_model        — model completion, no augmentation
  C  rag_model        — corpus-format augmented model completion

Metrics per condition:
  hit_rate   — fraction of prompts that produced a non-empty completion
  prefix_sim — SequenceMatcher ratio of completion vs ground truth suffix
  char_f1    — character-level F1 (precision × recall harmonic mean)
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

# Make backend imports work when running from backend/ dir
sys.path.insert(0, str(Path(__file__).parent))

from corpus import get_index, _norm
from inference import get_engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _char_f1(pred: str, truth: str) -> float:
    pred_chars = list(pred.lower())
    truth_chars = list(truth.lower())
    if not pred_chars or not truth_chars:
        return 0.0
    common = sum((min(pred_chars.count(c), truth_chars.count(c)) for c in set(pred_chars)))
    prec = common / len(pred_chars)
    rec = common / len(truth_chars)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def _split_verse(text: str, split_frac: float = 0.45) -> tuple[str, str]:
    """Split verse text at ~split_frac word boundary. Returns (prompt, ground_truth_suffix)."""
    words = text.split()
    cut = max(3, int(len(words) * split_frac))
    return " ".join(words[:cut]), " ".join(words[cut:])


# ---------------------------------------------------------------------------
# Eval conditions
# ---------------------------------------------------------------------------

def eval_retrieval_first(index, prompt: str, truth: str) -> dict:
    ref_match = index.lookup_ref(prompt.strip())
    if ref_match:
        return {"hit": True, "completion": ref_match["text"], "method": "ref_match"}

    text_match = index.search_prefix(prompt)
    if text_match:
        verse_text = text_match["text"]
        prompt_clean = prompt.strip().rstrip(".,;:!? ")
        m = re.search(re.escape(prompt_clean), verse_text, re.IGNORECASE)
        completion = verse_text[m.end():].lstrip() if m else verse_text
        return {"hit": True, "completion": completion, "method": "prefix_match"}

    return {"hit": False, "completion": "", "method": "miss"}


def eval_raw_model(engine, prompt: str, max_new_tokens: int = 120) -> dict:
    try:
        completion = engine.complete(prompt, max_new_tokens=max_new_tokens, temperature=0.0)
        return {"hit": bool(completion.strip()), "completion": completion, "method": "raw_model"}
    except Exception as e:
        return {"hit": False, "completion": "", "method": f"error:{e}"}


def eval_rag_model(engine, index, prompt: str, max_new_tokens: int = 120) -> dict:
    candidates = index.search_text(prompt, limit=3)
    if candidates:
        augmented = index.build_corpus_context(candidates[0], prompt)
    else:
        augmented = prompt
    try:
        completion = engine.complete(augmented, max_new_tokens=max_new_tokens, temperature=0.0)
        return {"hit": bool(completion.strip()), "completion": completion, "method": "rag_model"}
    except Exception as e:
        return {"hit": False, "completion": "", "method": f"error:{e}"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100, help="Number of verses to sample")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-model", action="store_true", help="Skip model conditions (fast, tests retrieval only)")
    parser.add_argument("--split-frac", type=float, default=0.45, help="Fraction of verse to use as prompt")
    args = parser.parse_args()

    print("Loading verse index...")
    index = get_index()
    index.load()
    all_verses = list(index._by_ref.values())
    print(f"  {len(all_verses):,} verses loaded")

    # Filter: only verses with enough words to split meaningfully
    long_enough = [v for v in all_verses if len(v["text"].split()) >= 8]
    random.seed(args.seed)
    sample = random.sample(long_enough, min(args.n, len(long_enough)))
    print(f"  Sampled {len(sample)} verses (min 8 words, seed={args.seed})")

    engine = None
    if not args.skip_model:
        engine = get_engine()
        if not engine.is_ready():
            print("\nWARN: Model weights not found. Running retrieval-only eval.")
            args.skip_model = True
        else:
            print("  Loading model weights...")
            engine._load()
            print("  Model ready.")

    # Accumulators
    stats = {
        "A_retrieval": {"hits": 0, "sim": 0.0, "f1": 0.0},
        "B_raw":       {"hits": 0, "sim": 0.0, "f1": 0.0},
        "C_rag":       {"hits": 0, "sim": 0.0, "f1": 0.0},
    }
    total = len(sample)

    print(f"\nRunning eval on {total} verses...")
    for i, verse in enumerate(sample, 1):
        if i % 10 == 0:
            print(f"  {i}/{total}...", end="\r", flush=True)

        prompt, truth = _split_verse(verse["text"], args.split_frac)
        if not truth:
            total -= 1
            continue

        # Condition A
        res_a = eval_retrieval_first(index, prompt, truth)
        if res_a["hit"]:
            stats["A_retrieval"]["hits"] += 1
            stats["A_retrieval"]["sim"] += _sim(res_a["completion"], truth)
            stats["A_retrieval"]["f1"] += _char_f1(res_a["completion"], truth)

        if not args.skip_model:
            # Condition B
            res_b = eval_raw_model(engine, prompt)
            if res_b["hit"]:
                stats["B_raw"]["hits"] += 1
                stats["B_raw"]["sim"] += _sim(res_b["completion"], truth)
                stats["B_raw"]["f1"] += _char_f1(res_b["completion"], truth)

            # Condition C
            res_c = eval_rag_model(engine, index, prompt)
            if res_c["hit"]:
                stats["C_rag"]["hits"] += 1
                stats["C_rag"]["sim"] += _sim(res_c["completion"], truth)
                stats["C_rag"]["f1"] += _char_f1(res_c["completion"], truth)

    print(f"\n{'='*60}")
    print(f"KJVA Completion Eval  n={total}  split={args.split_frac:.0%}")
    print(f"{'='*60}")
    print(f"{'Condition':<20} {'Hit%':>6} {'SequenceMatch':>14} {'Char-F1':>8}")
    print(f"{'-'*60}")
    for key, label in [
        ("A_retrieval", "A retrieval-first"),
        ("B_raw",       "B raw model"),
        ("C_rag",       "C rag-augmented"),
    ]:
        s = stats[key]
        hit_pct = 100.0 * s["hits"] / total
        avg_sim = s["sim"] / s["hits"] if s["hits"] else 0.0
        avg_f1 = s["f1"] / s["hits"] if s["hits"] else 0.0
        if key != "A_retrieval" and args.skip_model:
            print(f"  {label:<18} {'(skipped)':>6}")
        else:
            print(f"  {label:<18} {hit_pct:>5.1f}%  {avg_sim:>13.3f}  {avg_f1:>7.3f}")
    print(f"{'='*60}")
    print()
    print("Notes:")
    print("  Hit%         — fraction of prompts returning non-empty completion")
    print("  SequenceMatch — difflib ratio vs ground truth suffix (higher=better)")
    print("  Char-F1      — character-level F1 vs ground truth suffix (higher=better)")
    print()
    print("Expected: A should have near-100% hit rate with high similarity scores.")
    print("         C should outscore B on both metrics.")


if __name__ == "__main__":
    main()
