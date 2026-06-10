#!/usr/bin/env python3
"""
benchmark_byte.py — Comprehensive stress test and benchmark for byte-level TokenlessLM.

Tests:
  1. Full-corpus sliding-window perplexity (all validation tokens)
  2. Per-canon perplexity breakdown  (OT / Apocrypha / NT)
  3. Per-book perplexity for the 10 highest-verse-count books
  4. Inference throughput (tokens/sec at varying batch sizes)
  5. Long-context stress (128 / 256 / 512 / 768 / 1024 context lengths)
  6. KJV generation probes (30 prompts: canonical verses, theology, names)
  7. Stability run (50 consecutive greedy generations — checks for crashes/NaN)
  8. Latency distribution (100 single-token forward passes — p50/p95/p99)

Usage:
  python benchmark_byte.py --run-dir ml-training/runs/kjv_byte_v1_20m
  python benchmark_byte.py --run-dir ml-training/runs/kjv_byte_v1_20m --ckpt <path>
  python benchmark_byte.py --run-dir ... --out eval/kjv_byte_v1_20m/benchmark.json
  python benchmark_byte.py --run-dir ... --quick   # skip stability + latency dist
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_unflatten

SCRIPT_DIR = Path(__file__).resolve().parent
ML_TRAINING = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
from model import ModelConfig, TokenlessLM  # noqa

TOKENLESS_HOME = Path(os.environ.get("TOKENLESS_HOME", str(ML_TRAINING)))
DEFAULT_CACHE = TOKENLESS_HOME / "corpus" / "eng_kjv_apocrypha_v1" / "tokens_byte_uint16.npy"
VERSES_JSONL  = TOKENLESS_HOME / "corpus" / "eng_kjv_apocrypha_v1" / "verses.jsonl"
CORPUS_TXT    = TOKENLESS_HOME / "corpus" / "eng_kjv_apocrypha_v1" / "corpus.txt"

# ─────────────────────────────────────────────────────────────────────────────
# KJV Generation Prompts
# ─────────────────────────────────────────────────────────────────────────────

GENERATION_PROMPTS = [
    # Canonical openers
    {"id": "gen_1_1",    "prompt": "In the beginning God created the heaven and the earth.",    "category": "canonical"},
    {"id": "jhn_3_16",   "prompt": "For God so loved the world, that he gave his only begotten Son,", "category": "canonical"},
    {"id": "psa_23_1",   "prompt": "The LORD is my shepherd;",                                  "category": "canonical"},
    {"id": "psa_119_1",  "prompt": "Blessed are the undefiled in the way,",                     "category": "canonical"},
    {"id": "pro_3_5",    "prompt": "Trust in the LORD with all thine heart;",                   "category": "canonical"},
    {"id": "isa_53_1",   "prompt": "Who hath believed our report? and to whom is the arm of the LORD revealed?", "category": "canonical"},
    {"id": "rom_8_28",   "prompt": "And we know that all things work together for good",        "category": "canonical"},
    {"id": "mat_5_3",    "prompt": "Blessed are the poor in spirit:",                           "category": "canonical"},
    {"id": "rev_1_1",    "prompt": "The Revelation of Jesus Christ, which God gave unto him,",  "category": "canonical"},
    {"id": "exo_20_1",   "prompt": "And God spake all these words, saying,",                    "category": "canonical"},
    # Theological / doctrinal
    {"id": "theo_grace", "prompt": "For by grace are ye saved through faith;",                  "category": "theology"},
    {"id": "theo_love",  "prompt": "And now abideth faith, hope, charity, these three;",        "category": "theology"},
    {"id": "theo_law",   "prompt": "Thou shalt love the LORD thy God with all thy heart,",      "category": "theology"},
    {"id": "theo_sin",   "prompt": "For all have sinned, and come short of the glory of God;",  "category": "theology"},
    {"id": "theo_faith", "prompt": "Now faith is the substance of things hoped for,",           "category": "theology"},
    # Names / genealogy
    {"id": "names_adam", "prompt": "And Adam knew Eve his wife;",                               "category": "names"},
    {"id": "names_abr",  "prompt": "Now the LORD had said unto Abram, Get thee out of thy country,", "category": "names"},
    {"id": "names_moses","prompt": "And Moses said unto God, Who am I, that I should go unto Pharaoh,", "category": "names"},
    {"id": "names_david","prompt": "And David said to Saul, Let no man's heart fail because of him;", "category": "names"},
    # Chapter/book openers
    {"id": "open_ruth",  "prompt": "Now it came to pass in the days when the judges ruled,",   "category": "opener"},
    {"id": "open_job",   "prompt": "There was a man in the land of Uz, whose name was Job;",   "category": "opener"},
    {"id": "open_acts",  "prompt": "The former treatise have I made, O Theophilus, of all that Jesus began both to do and teach,", "category": "opener"},
    # Apocrypha
    {"id": "apoc_tob",   "prompt": "The book of the words of Tobit,",                          "category": "apocrypha"},
    {"id": "apoc_wis",   "prompt": "Love righteousness, ye that be judges of the earth:",      "category": "apocrypha"},
    # Short / stress
    {"id": "short_lord", "prompt": "LORD",                                                      "category": "short"},
    {"id": "short_god",  "prompt": "God",                                                       "category": "short"},
    {"id": "short_and",  "prompt": "And",                                                       "category": "short"},
    # Verse continuation
    {"id": "vc_psa_22",  "prompt": "My God, my God, why hast thou forsaken me?",               "category": "verse_continuation"},
    {"id": "vc_luk_2",   "prompt": "And she brought forth her firstborn son,",                 "category": "verse_continuation"},
    {"id": "vc_jhn_1",   "prompt": "In the beginning was the Word, and the Word was with God,","category": "verse_continuation"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def latest_ckpt(run_dir: Path) -> Path:
    ckpts = sorted(run_dir.glob("ckpt_step_*.safetensors"))
    if not ckpts:
        raise FileNotFoundError(f"No checkpoints in {run_dir}")
    return ckpts[-1]


def load_model(run_dir: Path, ckpt_path: Path) -> TokenlessLM:
    cfg = ModelConfig(**json.loads((run_dir / "model_config.json").read_text()))
    model = TokenlessLM(cfg)
    weights = mx.load(str(ckpt_path))
    model.update(tree_unflatten(list(weights.items())))
    mx.eval(model.parameters())
    return model


def encode_bytes(text: str) -> list[int]:
    return [1] + [b + 3 for b in text.encode("utf-8")]


def decode_bytes(ids: list[int]) -> str:
    raw = bytes(max(0, min(255, i - 3)) for i in ids if 3 <= i <= 258)
    return raw.decode("utf-8", errors="replace")


def sample_token(logits: mx.array, temperature: float = 0.8, top_k: int = 40) -> int:
    if temperature <= 0.0:
        return int(mx.argmax(logits).item())
    scaled = logits / temperature
    if top_k > 0:
        top_vals = mx.topk(scaled, min(top_k, logits.shape[-1]))
        threshold = mx.min(top_vals)
        scaled = mx.where(scaled >= threshold, scaled,
                          mx.full(scaled.shape, -1e9, dtype=scaled.dtype))
    probs = mx.softmax(scaled, axis=-1)
    return int(mx.random.categorical(mx.log(probs + 1e-9)).item())


def generate_text(model: TokenlessLM, prompt: str, max_new: int = 120,
                  temperature: float = 0.8, top_k: int = 40) -> tuple[str, int, float]:
    ids = encode_bytes(prompt)
    tokens = mx.array(ids, dtype=mx.int32)[None, :]
    out_ids: list[int] = []
    t0 = time.perf_counter()
    for _ in range(max_new):
        if tokens.shape[1] > model.cfg.max_seq_len:
            tokens = tokens[:, -model.cfg.max_seq_len:]
        logits = model(tokens)[0, -1, :]
        mx.eval(logits)
        next_id = sample_token(logits, temperature, top_k)
        if next_id == 2:
            break
        out_ids.append(next_id)
        tokens = mx.concatenate([tokens, mx.array([[next_id]])], axis=1)
    elapsed = time.perf_counter() - t0
    return decode_bytes(out_ids), len(out_ids), elapsed


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark sections
# ─────────────────────────────────────────────────────────────────────────────

def bench_perplexity_stream(model: TokenlessLM, tokens: np.ndarray,
                             seq_len: int, label: str) -> dict[str, Any]:
    total_nll = 0.0
    total_toks = 0
    n_chunks = (len(tokens) - 1) // seq_len
    if n_chunks == 0:
        return {"label": label, "ppl": None, "tokens": 0, "note": "too short"}
    t0 = time.perf_counter()
    for i in range(n_chunks):
        s = i * seq_len
        chunk = tokens[s: s + seq_len + 1].astype(np.int32)
        if len(chunk) < seq_len + 1:
            break
        x = mx.array(chunk[:-1])[None, :]
        y = mx.array(chunk[1:])[None, :]
        logits = model(x)
        log_probs = logits - mx.logsumexp(logits, axis=-1, keepdims=True)
        nll = -mx.take_along_axis(log_probs, y[..., None], axis=-1).squeeze(-1).sum()
        mx.eval(nll)
        total_nll += float(nll.item())
        total_toks += y.size
    elapsed = time.perf_counter() - t0
    ppl = math.exp(total_nll / max(1, total_toks))
    return {
        "label": label,
        "ppl": round(ppl, 4),
        "tokens_scored": total_toks,
        "chunks": n_chunks,
        "elapsed_s": round(elapsed, 2),
    }


def bench_full_ppl(model: TokenlessLM, all_tokens: np.ndarray) -> dict[str, Any]:
    print("  [1/8] Full-corpus perplexity...", file=sys.stderr)
    n_valid = max(8192, int(len(all_tokens) * 0.02))
    valid = np.asarray(all_tokens[-n_valid:])
    return bench_perplexity_stream(model, valid, model.cfg.max_seq_len, "full_valid")


def bench_canon_ppl(model: TokenlessLM) -> list[dict[str, Any]]:
    print("  [2/8] Per-canon perplexity...", file=sys.stderr)
    if not VERSES_JSONL.exists():
        return []

    canon_texts: dict[str, list[str]] = defaultdict(list)
    with VERSES_JSONL.open() as f:
        for line in f:
            v = json.loads(line)
            canon_texts[v["canon_category"]].append(v["text"])

    results = []
    for canon, texts in canon_texts.items():
        joined = "\n".join(texts)
        raw = joined.encode("utf-8")
        toks = np.frombuffer(raw, dtype=np.uint8).astype(np.uint16) + 3
        r = bench_perplexity_stream(model, toks, 512, canon)
        results.append(r)
        print(f"    {canon}: ppl={r['ppl']}", file=sys.stderr)
    return results


def bench_book_ppl(model: TokenlessLM, top_n: int = 10) -> list[dict[str, Any]]:
    print("  [3/8] Per-book perplexity (top books by verse count)...", file=sys.stderr)
    if not VERSES_JSONL.exists():
        return []

    book_texts: dict[str, list[str]] = defaultdict(list)
    with VERSES_JSONL.open() as f:
        for line in f:
            v = json.loads(line)
            book_texts[v["book"]].append(v["text"])

    by_size = sorted(book_texts.items(), key=lambda x: len(x[1]), reverse=True)[:top_n]
    results = []
    for book, texts in by_size:
        joined = "\n".join(texts)
        raw = joined.encode("utf-8")
        toks = np.frombuffer(raw, dtype=np.uint8).astype(np.uint16) + 3
        r = bench_perplexity_stream(model, toks, 512, book)
        results.append(r)
    return results


def bench_throughput(model: TokenlessLM) -> list[dict[str, Any]]:
    print("  [4/8] Inference throughput...", file=sys.stderr)
    results = []
    seq_lens = [64, 128, 256, 512, 1024]
    batch_sizes = [1, 4]
    for bs in batch_sizes:
        for sl in seq_lens:
            if bs * sl > 8192:
                continue
            x = mx.zeros((bs, sl), dtype=mx.int32)
            # warm up
            _ = model(x)
            mx.eval(_)
            # timed runs
            runs = 5
            t0 = time.perf_counter()
            for _ in range(runs):
                out = model(x)
                mx.eval(out)
            elapsed = time.perf_counter() - t0
            toks_per_sec = (bs * sl * runs) / elapsed
            results.append({
                "batch": bs,
                "seq_len": sl,
                "toks_per_sec": round(toks_per_sec, 1),
                "ms_per_batch": round(elapsed / runs * 1000, 2),
            })
            print(f"    bs={bs} sl={sl}: {toks_per_sec:.0f} tok/s", file=sys.stderr)
    return results


def bench_long_context(model: TokenlessLM) -> list[dict[str, Any]]:
    print("  [5/8] Long-context stress...", file=sys.stderr)
    if not CORPUS_TXT.exists():
        return []
    corpus = CORPUS_TXT.read_text(encoding="utf-8")
    results = []
    for ctx_len in [128, 256, 512, 768, 1024]:
        # Take a real slice of the corpus
        raw = corpus[:ctx_len * 4].encode("utf-8")[:ctx_len]
        ids = [1] + [b + 3 for b in raw][:ctx_len - 1]
        x = mx.array(ids, dtype=mx.int32)[None, :]
        t0 = time.perf_counter()
        logits = model(x)
        mx.eval(logits)
        elapsed = time.perf_counter() - t0
        # Check no NaN/Inf in output
        has_nan = bool(mx.any(mx.isnan(logits)).item())
        has_inf = bool(mx.any(mx.isinf(logits)).item())
        results.append({
            "context_len": ctx_len,
            "actual_tokens": len(ids),
            "elapsed_ms": round(elapsed * 1000, 2),
            "has_nan": has_nan,
            "has_inf": has_inf,
            "pass": not has_nan and not has_inf,
        })
        status = "PASS" if not has_nan and not has_inf else "FAIL"
        print(f"    ctx={ctx_len}: {elapsed*1000:.1f}ms  [{status}]", file=sys.stderr)
    return results


def bench_generation_probes(model: TokenlessLM) -> list[dict[str, Any]]:
    print("  [6/8] Generation probes...", file=sys.stderr)
    results = []
    for p in GENERATION_PROMPTS:
        text, n_toks, elapsed = generate_text(model, p["prompt"], max_new=100,
                                               temperature=0.8, top_k=40)
        results.append({
            "id": p["id"],
            "category": p["category"],
            "prompt": p["prompt"],
            "generation": text,
            "new_tokens": n_toks,
            "elapsed_s": round(elapsed, 3),
            "tok_per_s": round(n_toks / elapsed, 1) if elapsed > 0 else 0,
        })
        snippet = text[:60].replace("\n", " ")
        print(f"    [{p['id']}] → {snippet!r}", file=sys.stderr)
    return results


def bench_stability(model: TokenlessLM, n: int = 50) -> dict[str, Any]:
    print(f"  [7/8] Stability run ({n} consecutive generations)...", file=sys.stderr)
    prompts = [p["prompt"] for p in GENERATION_PROMPTS]
    failures = []
    nan_count = 0
    t0 = time.perf_counter()
    for i in range(n):
        prompt = prompts[i % len(prompts)]
        try:
            ids = encode_bytes(prompt)
            tokens = mx.array(ids, dtype=mx.int32)[None, :]
            for _ in range(20):
                logits = model(tokens)[0, -1, :]
                mx.eval(logits)
                if bool(mx.any(mx.isnan(logits)).item()):
                    nan_count += 1
                    break
                next_id = sample_token(logits, temperature=0.9, top_k=50)
                tokens = mx.concatenate([tokens, mx.array([[next_id]])], axis=1)
        except Exception as e:
            failures.append({"run": i, "error": str(e)})
    elapsed = time.perf_counter() - t0
    return {
        "runs": n,
        "failures": len(failures),
        "nan_events": nan_count,
        "pass": len(failures) == 0 and nan_count == 0,
        "elapsed_s": round(elapsed, 2),
        "failure_details": failures[:5],
    }


def bench_latency_dist(model: TokenlessLM, n: int = 100) -> dict[str, Any]:
    print(f"  [8/8] Latency distribution ({n} single-token forward passes)...", file=sys.stderr)
    latencies = []
    x = mx.zeros((1, 64), dtype=mx.int32)
    # warm up
    for _ in range(3):
        out = model(x)
        mx.eval(out)
    for _ in range(n):
        t0 = time.perf_counter()
        out = model(x)
        mx.eval(out)
        latencies.append((time.perf_counter() - t0) * 1000)
    latencies.sort()
    return {
        "n": n,
        "p50_ms":  round(latencies[int(n * 0.50)], 2),
        "p90_ms":  round(latencies[int(n * 0.90)], 2),
        "p95_ms":  round(latencies[int(n * 0.95)], 2),
        "p99_ms":  round(latencies[int(n * 0.99)], 2),
        "min_ms":  round(latencies[0], 2),
        "max_ms":  round(latencies[-1], 2),
        "mean_ms": round(sum(latencies) / n, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark byte-level TokenlessLM")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--ckpt", default=None, help="Specific checkpoint path")
    parser.add_argument("--token-cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--out", default=None, help="Write JSON report to file")
    parser.add_argument("--quick", action="store_true",
                        help="Skip stability run and latency distribution")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    mx.random.seed(args.seed)
    run_dir = Path(args.run_dir)
    ckpt_path = Path(args.ckpt) if args.ckpt else latest_ckpt(run_dir)

    print(f"\n{'='*64}", file=sys.stderr)
    print(f"  TokenlessLM Benchmark", file=sys.stderr)
    print(f"  checkpoint : {ckpt_path.name}", file=sys.stderr)
    print(f"  run_dir    : {run_dir}", file=sys.stderr)
    print(f"{'='*64}\n", file=sys.stderr)

    t_load = time.perf_counter()
    model = load_model(run_dir, ckpt_path)
    load_time = time.perf_counter() - t_load
    print(f"  Model loaded in {load_time:.2f}s", file=sys.stderr)

    all_tokens = np.load(args.token_cache, mmap_mode="r")

    report: dict[str, Any] = {
        "checkpoint": str(ckpt_path),
        "checkpoint_name": ckpt_path.name,
        "run_dir": str(run_dir),
        "model_config": json.loads((run_dir / "model_config.json").read_text()),
        "tokenization": "utf8_byte",
        "benchmarked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "load_time_s": round(load_time, 3),
        "results": {},
    }

    report["results"]["full_perplexity"] = bench_full_ppl(model, all_tokens)
    report["results"]["canon_perplexity"] = bench_canon_ppl(model)
    report["results"]["book_perplexity"]  = bench_book_ppl(model)
    report["results"]["throughput"]       = bench_throughput(model)
    report["results"]["long_context"]     = bench_long_context(model)
    report["results"]["generation_probes"] = bench_generation_probes(model)

    if not args.quick:
        report["results"]["stability"]      = bench_stability(model)
        report["results"]["latency_dist"]   = bench_latency_dist(model)

    # ── Summary ──────────────────────────────────────────────────────────────
    fp  = report["results"]["full_perplexity"]
    lc  = report["results"]["long_context"]
    st  = report["results"].get("stability", {})
    lat = report["results"].get("latency_dist", {})
    lc_pass = all(r["pass"] for r in lc) if lc else True
    st_pass = st.get("pass", True)

    summary = {
        "full_val_ppl":     fp.get("ppl"),
        "long_context_pass": lc_pass,
        "stability_pass":   st_pass,
        "p50_latency_ms":   lat.get("p50_ms"),
        "overall": "PASS" if (lc_pass and st_pass) else "FAIL",
    }
    report["summary"] = summary

    print(f"\n{'='*64}", file=sys.stderr)
    print(f"  SUMMARY", file=sys.stderr)
    print(f"  full val ppl      : {summary['full_val_ppl']}", file=sys.stderr)
    print(f"  long context      : {'PASS' if lc_pass else 'FAIL'}", file=sys.stderr)
    print(f"  stability (50 gen): {'PASS' if st_pass else 'FAIL'}", file=sys.stderr)
    if lat:
        print(f"  p50 latency       : {lat.get('p50_ms')} ms", file=sys.stderr)
    print(f"  OVERALL           : {summary['overall']}", file=sys.stderr)
    print(f"{'='*64}\n", file=sys.stderr)

    out_text = json.dumps(report, indent=2, ensure_ascii=False)
    print(out_text)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out_text + "\n", encoding="utf-8")
        print(f"Report written to {out_path}", file=sys.stderr)

    return 0 if summary["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
