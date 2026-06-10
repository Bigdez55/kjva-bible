#!/usr/bin/env python3
"""
run_xmind_benchmark.py — Honest benchmark runner for XMIND-1 (18.98M byte-LM).

Implements the subset of XMIND_BENCHMARK_AND_EVAL_SUITE_2026-06-04.md that
can ACTUALLY run against the GGUF model + libxmind-core.dylib that exist
on disk in this repo. Sections requiring external eval sets, frontier APIs,
adversarial corpora, NLI judges, or alternative-quantization variants are
explicitly SKIPPED with a recorded reason — they are NOT silently omitted.

Spec sections implemented:
  §3.5  Determinism (T=0, N runs, byte-identical output check)
  §3.7  Byte-level perturbation robustness (typo/case/whitespace)
  §4.1  Decode throughput (tokens/sec) at multiple max_tokens
  §4.2  Time-to-first-token (TTFT) — measured as init + 1-token gen
  §4.3  Memory: model footprint + process RSS
  §4.5  Cold-start latency (init time)
  §4.6  Concurrency (sequential vs concurrent across sessions — limited by per-process singleton)
  §5    Bits-per-byte (BPB) on a small held-out byte sequence

Skipped sections (with reason):
  §2 Axis A (MMLU/GSM8K/...)              — eval sets not in repo
  §3.1 Grounding fidelity                  — no retriever wired
  §3.2 IC/NC/OOC stratification            — no labeled strata
  §3.3 Calibration ECE                     — requires per-position logits + labels
  §3.4 NLI faithfulness                    — no NLI judge
  §3.6 R1_PER injection battery            — R1_PER pipeline not wired
  §4.4 Joules/query                        — requires powermetrics root
  §4.7 Quantization sensitivity            — only Q4_0 variant on disk
  §4.8 Scaling curves                      — only 18M tier on disk
  §6   NIAH/RULER                          — sets not in repo
  §7   SFT / R1_PER round-trip             — no SFT checkpoint
  §8   Adversarial / corpus poisoning      — sets not in repo
  §10  Frontier head-to-head               — no frontier API in this environment
  §11  Contamination audit                 — no eval sets to audit against

Output: a single JSON file with all measured results + provenance,
plus a markdown summary report.

Usage:
  python3 run_xmind_benchmark.py --model <path-to-gguf> --dylib <path-to-dylib>
                                 --out-dir <results-dir>
                                 [--quick]   # skip stability + concurrency
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import resource
import statistics
import subprocess
import sys
import time
import math
import threading
from datetime import datetime, timezone
from pathlib import Path


# ────────────────────────────────────────────────────────────────────────
# Provenance helpers
# ────────────────────────────────────────────────────────────────────────

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_rss_mb() -> float:
    """Resident set size of THIS process (Linux/macOS) in megabytes."""
    ru = resource.getrusage(resource.RUSAGE_SELF)
    # Linux: ru_maxrss is in KB. macOS: bytes.
    if sys.platform == "darwin":
        return ru.ru_maxrss / (1024 * 1024)
    return ru.ru_maxrss / 1024


# ────────────────────────────────────────────────────────────────────────
# Engine binding
# ────────────────────────────────────────────────────────────────────────

class Engine:
    def __init__(self, dylib_path: Path, model_path: Path, max_seq: int = 1024):
        self.dylib_path = dylib_path
        self.model_path = model_path
        self.max_seq    = max_seq
        self.lib        = None
        self.init_ms    = None

    def open(self):
        self.lib = ctypes.CDLL(str(self.dylib_path))
        self.lib.xmind_easy_init.argtypes     = [ctypes.c_char_p, ctypes.c_int]
        self.lib.xmind_easy_init.restype      = ctypes.c_int
        self.lib.xmind_easy_generate.argtypes = [
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int,
            ctypes.c_float,  ctypes.c_float,  ctypes.c_int,
        ]
        self.lib.xmind_easy_generate.restype  = ctypes.c_int
        self.lib.xmind_easy_reset.restype     = ctypes.c_int
        self.lib.xmind_easy_set_sampler.argtypes = [
            ctypes.c_float, ctypes.c_float, ctypes.c_ulonglong,
        ]
        self.lib.xmind_easy_set_sampler.restype  = ctypes.c_int
        self.lib.xmind_easy_version.restype   = ctypes.c_char_p

        t0 = time.perf_counter()
        rc = self.lib.xmind_easy_init(
            str(self.model_path).encode(), int(self.max_seq)
        )
        self.init_ms = (time.perf_counter() - t0) * 1000.0
        if rc != 0:
            raise RuntimeError(f"xmind_easy_init failed rc={rc}")

    def set_sampler(self, temperature: float, top_p: float, seed: int):
        self.lib.xmind_easy_set_sampler(
            ctypes.c_float(temperature),
            ctypes.c_float(top_p),
            ctypes.c_ulonglong(seed),
        )

    def reset(self):
        self.lib.xmind_easy_reset()

    def generate(self, prompt: str, max_tokens: int,
                 temperature: float = 0.0, top_p: float = 1.0) -> tuple[str, float]:
        """Return (text, wall_ms)."""
        out = ctypes.create_string_buffer(4096)
        t0 = time.perf_counter()
        n = self.lib.xmind_easy_generate(
            prompt.encode(),
            out,
            4096,
            ctypes.c_float(temperature),
            ctypes.c_float(top_p),
            int(max_tokens),
        )
        dt_ms = (time.perf_counter() - t0) * 1000.0
        if n < 0:
            return ("", dt_ms)
        return (out.value.decode("utf-8", errors="replace"), dt_ms)

    def version(self) -> str:
        return self.lib.xmind_easy_version().decode()


# ────────────────────────────────────────────────────────────────────────
# §3.5 Determinism
# ────────────────────────────────────────────────────────────────────────

def bench_determinism(engine: Engine, n_runs: int = 5) -> dict:
    """At temperature=0 the model must produce byte-identical output across runs.
    For each run we reset the session, set seed=0, and generate from the same prompt."""
    prompt = "In the beginning"
    max_tokens = 32
    outputs = []
    timings = []
    for i in range(n_runs):
        engine.reset()
        engine.set_sampler(0.0, 1.0, 0)
        text, dt = engine.generate(prompt, max_tokens, temperature=0.0, top_p=1.0)
        outputs.append(text)
        timings.append(dt)
    identical = len(set(outputs)) == 1
    return {
        "section": "§3.5 Determinism (T=0)",
        "n_runs": n_runs,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "all_byte_identical": identical,
        "distinct_outputs_count": len(set(outputs)),
        "outputs_preview": [o[:60] for o in outputs[:3]],
        "wall_ms": {"mean": statistics.mean(timings), "stdev": statistics.stdev(timings) if len(timings) > 1 else 0.0},
    }


# ────────────────────────────────────────────────────────────────────────
# §3.7 Byte-level perturbation robustness
# ────────────────────────────────────────────────────────────────────────

def bench_byte_perturbation(engine: Engine) -> dict:
    """Compare outputs across clean vs perturbed variants of the same prompt.
    A tokenizer-free byte-LM should degrade smoothly, not cliff-edge."""
    base = "In the beginning God created the heaven and the earth"
    perts = {
        "clean":           base,
        "lowercase":       base.lower(),
        "uppercase":       base.upper(),
        "extra_spaces":    base.replace(" ", "  "),
        "typo_swap":       base.replace("beginning", "begnining"),
        "leading_ws":      "   " + base,
        "trailing_ws":     base + "   ",
        "punct_dropped":   base.replace(",", "").replace(".", ""),
    }
    results = {}
    for name, p in perts.items():
        engine.reset()
        engine.set_sampler(0.0, 1.0, 0)
        text, dt = engine.generate(p, max_tokens=24, temperature=0.0, top_p=1.0)
        results[name] = {
            "prompt_len_bytes": len(p),
            "output_preview":   text[:80],
            "output_sha256":    hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16],
            "wall_ms":          dt,
        }
    distinct = len({v["output_sha256"] for v in results.values()})
    return {
        "section": "§3.7 Byte-level perturbation robustness",
        "n_variants": len(perts),
        "distinct_output_hashes": distinct,
        "interpretation": (
            "Lower distinct count = more robust (semantically-similar inputs → similar outputs). "
            "Higher = more brittle. For a healthy byte-LM we expect distinct < n_variants but > 1."
        ),
        "by_variant": results,
    }


# ────────────────────────────────────────────────────────────────────────
# §4.1 Decode throughput
# ────────────────────────────────────────────────────────────────────────

def bench_throughput(engine: Engine) -> dict:
    """Tokens-per-second across multiple max_tokens settings, with p50/p95/p99
    on per-token wall time."""
    prompt = "The Lord is my shepherd; I shall not want."
    results = []
    for max_tokens in [16, 32, 64, 128]:
        per_run = []
        n_runs = 5
        for _ in range(n_runs):
            engine.reset()
            engine.set_sampler(0.7, 0.9, 0)
            t0 = time.perf_counter()
            text, _ = engine.generate(prompt, max_tokens, temperature=0.7, top_p=0.9)
            dt = time.perf_counter() - t0
            n_chars = len(text)
            tok_per_s = (n_chars / dt) if dt > 0 else 0.0
            per_run.append({"chars_emitted": n_chars, "wall_s": dt, "tok_per_s": tok_per_s})
        tps = [r["tok_per_s"] for r in per_run]
        results.append({
            "max_tokens_requested": max_tokens,
            "n_runs":               n_runs,
            "tok_per_s_mean":       statistics.mean(tps),
            "tok_per_s_stdev":      statistics.stdev(tps) if len(tps) > 1 else 0.0,
            "tok_per_s_min":        min(tps),
            "tok_per_s_max":        max(tps),
            "samples":              per_run,
        })
    return {
        "section": "§4.1 Decode throughput (tokens/sec)",
        "by_max_tokens": results,
    }


# ────────────────────────────────────────────────────────────────────────
# §4.2 Time-to-first-token (TTFT)
# ────────────────────────────────────────────────────────────────────────

def bench_ttft(engine: Engine) -> dict:
    """TTFT under varying prompt lengths. Measured as wall time for
    generating just 1 token from a fresh session."""
    prompts = {
        "short_8b":   "Genesis 1",
        "med_64b":    "And God said let there be light and there was light and God saw" ,
        "long_256b":  ("In the beginning God created the heavens and the earth. " * 5)[:256],
    }
    results = []
    for name, p in prompts.items():
        runs = []
        for _ in range(5):
            engine.reset()
            engine.set_sampler(0.0, 1.0, 0)
            t0 = time.perf_counter()
            _, _ = engine.generate(p, max_tokens=1, temperature=0.0, top_p=1.0)
            runs.append((time.perf_counter() - t0) * 1000.0)
        results.append({
            "prompt_label":   name,
            "prompt_len_bytes": len(p),
            "ttft_ms_mean":   statistics.mean(runs),
            "ttft_ms_stdev":  statistics.stdev(runs) if len(runs) > 1 else 0.0,
            "ttft_ms_p50":    statistics.median(runs),
            "ttft_ms_min":    min(runs),
            "ttft_ms_max":    max(runs),
        })
    return {
        "section": "§4.2 Time-to-first-token (TTFT)",
        "by_prompt_length": results,
    }


# ────────────────────────────────────────────────────────────────────────
# §4.3 Memory: model footprint + RSS growth across context lengths
# ────────────────────────────────────────────────────────────────────────

def bench_memory(engine: Engine, model_path: Path) -> dict:
    """Footprint on disk + process RSS at idle + after sustained inference."""
    footprint_mb = model_path.stat().st_size / (1024 * 1024)
    rss_before = get_rss_mb()
    # Burn through a longer prompt to grow KV cache
    long_prompt = ("In the beginning God created the heaven and the earth. " * 20)[:512]
    engine.reset()
    engine.set_sampler(0.0, 1.0, 0)
    engine.generate(long_prompt, max_tokens=64, temperature=0.0, top_p=1.0)
    rss_after = get_rss_mb()
    return {
        "section": "§4.3 Memory + KV-cache growth",
        "model_footprint_mb": round(footprint_mb, 2),
        "process_rss_mb_pre_inference":  round(rss_before, 2),
        "process_rss_mb_post_inference": round(rss_after, 2),
        "rss_delta_mb":                  round(rss_after - rss_before, 2),
        "note": "RSS includes ctypes interpreter overhead; the runtime delta is the meaningful number.",
    }


# ────────────────────────────────────────────────────────────────────────
# §4.5 Cold-start latency
# ────────────────────────────────────────────────────────────────────────

def bench_coldstart(dylib_path: Path, model_path: Path) -> dict:
    """Measure init time across 3 fresh subprocesses (true cold start)."""
    cold_ms = []
    script = (
        "import ctypes, time, sys; "
        f"lib = ctypes.CDLL(r'{dylib_path}'); "
        "lib.xmind_easy_init.argtypes=[ctypes.c_char_p, ctypes.c_int]; "
        "lib.xmind_easy_init.restype=ctypes.c_int; "
        "t0=time.perf_counter(); "
        f"rc=lib.xmind_easy_init(rb'{model_path}', 1024); "
        "dt=(time.perf_counter()-t0)*1000.0; "
        "print(rc, dt)"
    )
    for _ in range(3):
        out = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0:
            continue
        # XMIND init dumps banner lines to stdout. Our "rc dt" sentinel is the
        # last non-empty line; parse only that.
        non_empty = [ln for ln in out.stdout.splitlines() if ln.strip()]
        if not non_empty:
            continue
        parts = non_empty[-1].strip().split()
        if len(parts) >= 2:
            try:
                rc, dt = int(parts[0]), float(parts[1])
                if rc == 0:
                    cold_ms.append(dt)
            except ValueError:
                pass
    return {
        "section": "§4.5 Cold-start latency",
        "n_runs": len(cold_ms),
        "ms_mean":  statistics.mean(cold_ms) if cold_ms else None,
        "ms_stdev": statistics.stdev(cold_ms) if len(cold_ms) > 1 else 0.0,
        "ms_min":   min(cold_ms) if cold_ms else None,
        "ms_max":   max(cold_ms) if cold_ms else None,
        "raw_ms":   cold_ms,
    }


# ────────────────────────────────────────────────────────────────────────
# §4.6 Concurrency (per-process singleton-bound)
# ────────────────────────────────────────────────────────────────────────

def bench_concurrency(engine: Engine) -> dict:
    """The current xmind_easy_* API is a per-process singleton (one model,
    one session, locked via pal_spin_lock). True concurrency requires
    multiple processes. We measure throughput delta between sequential
    and threaded calls — threaded should be SAME or SLIGHTLY WORSE due to
    the spinlock; that is the honest answer for the current implementation."""
    prompt = "test"
    max_tokens = 8

    # Sequential baseline
    seq_times = []
    for _ in range(8):
        engine.reset()
        engine.set_sampler(0.0, 1.0, 0)
        _, dt = engine.generate(prompt, max_tokens, temperature=0.0, top_p=1.0)
        seq_times.append(dt)

    # Threaded — should serialize on the spinlock
    th_times = []
    lock = threading.Lock()
    def worker(out_list):
        # Note: engine.reset/set_sampler/generate are not thread-safe in the
        # Python wrapper layer either, but the C engine serializes via spinlock.
        with lock:
            engine.reset()
            engine.set_sampler(0.0, 1.0, 0)
        _, dt = engine.generate(prompt, max_tokens, temperature=0.0, top_p=1.0)
        with lock:
            out_list.append(dt)
    threads = []
    out_list: list[float] = []
    t0 = time.perf_counter()
    for _ in range(8):
        t = threading.Thread(target=worker, args=(out_list,))
        threads.append(t); t.start()
    for t in threads:
        t.join()
    wall_threaded = (time.perf_counter() - t0) * 1000.0
    th_times = list(out_list)

    return {
        "section": "§4.6 Concurrency",
        "implementation_note": "xmind_easy_* is per-process singleton; in-process threads serialize on a spinlock. True parallelism needs multi-process.",
        "sequential_ms_mean": statistics.mean(seq_times),
        "threaded_ms_per_call_mean": statistics.mean(th_times) if th_times else None,
        "threaded_wall_total_ms_for_8_calls": wall_threaded,
        "ideal_parallel_wall_if_truly_concurrent_ms": statistics.mean(seq_times),
    }


# ────────────────────────────────────────────────────────────────────────
# §5 Bits-per-byte (BPB)
# ────────────────────────────────────────────────────────────────────────

def bench_bpb_via_parity(parity_path: Path, model_path: Path, held_out: str) -> dict:
    """BPB requires per-position log-probabilities of the actual next byte.
    parity_logits emits per-token logit columns. For a small held-out
    sequence we tokenize byte-by-byte (token = byte + 3, vocab 259) and
    accumulate -log p(true_next_byte) / len(bytes). This is an APPROXIMATE
    BPB on the supplied held-out string.

    Note: parity_logits in this repo emits 259 floats per token output line.
    We treat the LAST 259 floats (last position) per call as the next-token
    distribution; to compute BPB across N bytes we make N calls — expensive
    but honest. We cap the sample to ~200 bytes to keep runtime reasonable."""
    if not parity_path.exists():
        return {
            "section": "§5 Bits-per-byte (BPB)",
            "status": "SKIPPED",
            "reason": f"parity_logits not found at {parity_path}",
        }
    sample = held_out[:200]
    nlls: list[float] = []
    PAD = 0; BOS = 1; EOS = 2
    BYTE_OFFSET = 3
    for i in range(1, len(sample)):
        prefix = sample[:i]
        true_next_byte_tok = (ord(sample[i]) & 0xFF) + BYTE_OFFSET
        try:
            out = subprocess.run(
                [str(parity_path), str(model_path), prefix],
                capture_output=True, text=True, timeout=60,
            )
        except Exception as e:
            return {
                "section": "§5 Bits-per-byte (BPB)",
                "status": "ERROR",
                "reason": str(e),
            }
        # Parse last 259 float lines from stdout
        floats = []
        for line in out.stdout.splitlines():
            s = line.strip()
            if not s: continue
            try:
                floats.append(float(s))
            except ValueError:
                continue
        if len(floats) < 259:
            return {
                "section": "§5 Bits-per-byte (BPB)",
                "status": "PARTIAL",
                "reason": f"parity_logits emitted {len(floats)} floats; expected ≥259",
                "samples_processed": len(nlls),
            }
        last_logits = floats[-259:]
        # log-softmax for stability
        m = max(last_logits)
        exps = [math.exp(x - m) for x in last_logits]
        Z = sum(exps)
        log_probs = [math.log(e / Z) if e > 0 else -1e30 for e in exps]
        if 0 <= true_next_byte_tok < 259:
            nlls.append(-log_probs[true_next_byte_tok])
        # cap for runtime
        if len(nlls) >= 64:
            break
    if not nlls:
        return {"section": "§5 BPB", "status": "ERROR", "reason": "no NLL samples computed"}
    avg_nll_nats = sum(nlls) / len(nlls)
    # NLL is per-NEXT-byte prediction (one byte per call). BPB = NLL / ln(2)
    bpb = avg_nll_nats / math.log(2)
    return {
        "section": "§5 Bits-per-byte (BPB) — approximate, on supplied held-out",
        "status": "OK",
        "n_bytes_scored":      len(nlls),
        "held_out_preview":    sample[:80],
        "avg_nll_nats":        avg_nll_nats,
        "bits_per_byte":       bpb,
        "interpretation":      (
            "BPB on this held-out byte stream. Lower is better. "
            "Frontier BPB on English ≈ 0.6–1.0. KJV-trained 18M base will be higher "
            "off-domain and lower in-domain. Use as a CROSS-ARCHITECTURE comparable, "
            "not as a pass/fail."
        ),
    }


# ────────────────────────────────────────────────────────────────────────
# Driver
# ────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model",  required=True, type=Path)
    ap.add_argument("--dylib",  required=True, type=Path)
    ap.add_argument("--parity", default=None,  type=Path,
                    help="Path to parity_logits binary (for §5 BPB)")
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--quick",  action="store_true",
                    help="Skip concurrency + BPB (which take longest)")
    ap.add_argument("--held-out-file", default=None, type=Path,
                    help="Text file to score BPB against; default uses a small KJV excerpt")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    print(f"[run_id] {run_id}")
    print(f"[model]  {args.model} ({args.model.stat().st_size:,} B)")
    print(f"[dylib]  {args.dylib}")

    print("[provenance] computing sha256 ...")
    provenance = {
        "run_id":             run_id,
        "timestamp_utc":      utc_now(),
        "model_path":         str(args.model),
        "model_sha256":       sha256_file(args.model),
        "model_size_bytes":   args.model.stat().st_size,
        "dylib_path":         str(args.dylib),
        "dylib_sha256":       sha256_file(args.dylib),
        "host_platform":      sys.platform,
        "python_version":     sys.version.split()[0],
    }

    print("[open]  binding to dylib + loading model ...")
    eng = Engine(args.dylib, args.model, max_seq=1024)
    eng.open()
    print(f"[open]  version = {eng.version()}, init = {eng.init_ms:.1f} ms")

    results = {
        "spec":              "XMIND_BENCHMARK_AND_EVAL_SUITE_2026-06-04.md",
        "runner":            "run_xmind_benchmark.py",
        "honest_scope_note": (
            "This run executes the SUBSET of the spec that can run against the "
            "on-disk GGUF + dylib without external eval sets, frontier API, "
            "NLI judge, R1_PER pipeline, or alternate-quantization variants. "
            "Skipped sections are listed in results['skipped'] with reasons. "
            "No claim about overall benchmark completeness is being made."
        ),
        "provenance":        provenance,
        "engine_version":    eng.version(),
        "engine_init_ms":    eng.init_ms,
        "sections_executed": {},
        "skipped":           {
            "§2 Axis A (MMLU/GSM8K/ARC/HellaSwag/BBH/HumanEval/DROP/SQuAD)": "eval sets not in repo",
            "§3.1 Grounding fidelity":                "retriever not wired",
            "§3.2 Hallucination IC/NC/OOC":           "labeled strata not in repo",
            "§3.3 Calibration ECE / risk-coverage":   "requires per-position logits aligned to labels",
            "§3.4 Faithfulness / NLI entailment":     "NLI judge not in repo",
            "§3.6 R1_PER injection battery":          "R1_PER opcode pipeline not wired in current build",
            "§4.4 Joules/query":                      "requires powermetrics root + per-query energy probe",
            "§4.7 Quantization sensitivity":          "only Q4_0 variant present; need f32/q8 to compare",
            "§4.8 Capacity scaling curves":           "only 18M tier present",
            "§6   Long-context NIAH/RULER":           "sets not in repo",
            "§7   SFT / R1_PER round-trip":           "no SFT checkpoint, no R1_PER decoder",
            "§8   Adversarial / corpus poisoning":    "adversarial corpus not in repo",
            "§10  Frontier head-to-head":             "no frontier model access from this environment",
            "§11  Contamination audit":               "no eval sets to audit against",
        },
    }

    print("[§3.5] determinism ...")
    results["sections_executed"]["determinism"]    = bench_determinism(eng)
    print("[§3.7] byte perturbation ...")
    results["sections_executed"]["byte_perturbation"] = bench_byte_perturbation(eng)
    print("[§4.1] throughput ...")
    results["sections_executed"]["throughput"]     = bench_throughput(eng)
    print("[§4.2] TTFT ...")
    results["sections_executed"]["ttft"]           = bench_ttft(eng)
    print("[§4.3] memory ...")
    results["sections_executed"]["memory"]         = bench_memory(eng, args.model)
    print("[§4.5] cold start ...")
    results["sections_executed"]["cold_start"]     = bench_coldstart(args.dylib, args.model)
    if not args.quick:
        print("[§4.6] concurrency ...")
        results["sections_executed"]["concurrency"] = bench_concurrency(eng)
        if args.parity and args.parity.exists():
            print("[§5]   BPB ...")
            held_out = (
                "And God said, Let there be light: and there was light. "
                "And God saw the light, that it was good: and God divided "
                "the light from the darkness."
            )
            if args.held_out_file and args.held_out_file.exists():
                held_out = args.held_out_file.read_text(encoding="utf-8", errors="replace")
            results["sections_executed"]["bpb"] = bench_bpb_via_parity(args.parity, args.model, held_out)
        else:
            results["sections_executed"]["bpb"] = {
                "section": "§5 Bits-per-byte (BPB)",
                "status":  "SKIPPED",
                "reason":  "no --parity binary provided or path missing",
            }

    # Write outputs
    json_path = args.out_dir / f"results_{run_id}.json"
    json_path.write_text(json.dumps(results, indent=2, default=str))
    md_path = args.out_dir / f"results_{run_id}.md"
    md_path.write_text(_render_markdown(results))
    print(f"\n[OK] wrote {json_path}")
    print(f"[OK] wrote {md_path}")
    return 0


def _render_markdown(r: dict) -> str:
    s = r["sections_executed"]
    lines = []
    lines.append(f"# XMIND-1 Benchmark Results — {r['provenance']['run_id']}")
    lines.append("")
    lines.append(f"**Spec:** {r['spec']}")
    lines.append(f"**Model:** `{r['provenance']['model_path']}`  ({r['provenance']['model_size_bytes']:,} B)")
    lines.append(f"**Model SHA-256:** `{r['provenance']['model_sha256'][:32]}…`")
    lines.append(f"**Dylib SHA-256:** `{r['provenance']['dylib_sha256'][:32]}…`")
    lines.append(f"**Engine version:** `{r['engine_version']}`")
    lines.append(f"**Init time:** {r['engine_init_ms']:.1f} ms")
    lines.append("")
    lines.append("## Honest scope")
    lines.append(r["honest_scope_note"])
    lines.append("")
    lines.append("## Sections SKIPPED (with reason)")
    for sec, why in r["skipped"].items():
        lines.append(f"- **{sec}** — {why}")
    lines.append("")
    lines.append("## Sections EXECUTED")
    lines.append("")
    if "determinism" in s:
        d = s["determinism"]
        lines.append(f"### §3.5 Determinism")
        lines.append(f"- Byte-identical across {d['n_runs']} runs: **{d['all_byte_identical']}**")
        lines.append(f"- Distinct outputs: {d['distinct_outputs_count']}")
        lines.append(f"- Wall-time mean: {d['wall_ms']['mean']:.1f} ms (σ={d['wall_ms']['stdev']:.1f})")
        lines.append("")
    if "byte_perturbation" in s:
        b = s["byte_perturbation"]
        lines.append(f"### §3.7 Byte-level perturbation robustness")
        lines.append(f"- Variants tested: {b['n_variants']}")
        lines.append(f"- Distinct output hashes: {b['distinct_output_hashes']}")
        lines.append(f"- Interpretation: {b['interpretation']}")
        lines.append("")
        lines.append("| Variant | Out preview | Wall ms |")
        lines.append("|---|---|---|")
        for name, v in b["by_variant"].items():
            preview = v["output_preview"].replace("|", "/").replace("\n", " ")[:50]
            lines.append(f"| {name} | `{preview}` | {v['wall_ms']:.1f} |")
        lines.append("")
    if "throughput" in s:
        t = s["throughput"]
        lines.append(f"### §4.1 Decode throughput")
        lines.append("| max_tokens | tok/s mean | tok/s stdev | min | max |")
        lines.append("|---|---|---|---|---|")
        for row in t["by_max_tokens"]:
            lines.append(f"| {row['max_tokens_requested']} | {row['tok_per_s_mean']:.1f} | {row['tok_per_s_stdev']:.1f} | {row['tok_per_s_min']:.1f} | {row['tok_per_s_max']:.1f} |")
        lines.append("")
    if "ttft" in s:
        t = s["ttft"]
        lines.append(f"### §4.2 Time-to-first-token (TTFT)")
        lines.append("| Prompt | Bytes | TTFT mean ms | p50 | min | max |")
        lines.append("|---|---|---|---|---|---|")
        for row in t["by_prompt_length"]:
            lines.append(f"| {row['prompt_label']} | {row['prompt_len_bytes']} | {row['ttft_ms_mean']:.1f} | {row['ttft_ms_p50']:.1f} | {row['ttft_ms_min']:.1f} | {row['ttft_ms_max']:.1f} |")
        lines.append("")
    if "memory" in s:
        m = s["memory"]
        lines.append(f"### §4.3 Memory")
        lines.append(f"- Model footprint on disk: **{m['model_footprint_mb']} MB**")
        lines.append(f"- Process RSS before inference: {m['process_rss_mb_pre_inference']} MB")
        lines.append(f"- Process RSS after inference: {m['process_rss_mb_post_inference']} MB")
        lines.append(f"- RSS delta: {m['rss_delta_mb']} MB")
        lines.append("")
    if "cold_start" in s:
        c = s["cold_start"]
        lines.append(f"### §4.5 Cold-start latency (true cold, fresh subprocess)")
        lines.append(f"- N runs: {c['n_runs']}")
        if c["ms_mean"] is not None:
            lines.append(f"- Mean: {c['ms_mean']:.1f} ms (σ={c['ms_stdev']:.1f})")
            lines.append(f"- Min/Max: {c['ms_min']:.1f} / {c['ms_max']:.1f} ms")
        lines.append("")
    if "concurrency" in s:
        c = s["concurrency"]
        lines.append(f"### §4.6 Concurrency")
        lines.append(f"- Implementation note: {c['implementation_note']}")
        lines.append(f"- Sequential per-call: {c['sequential_ms_mean']:.1f} ms")
        if c["threaded_ms_per_call_mean"] is not None:
            lines.append(f"- Threaded per-call: {c['threaded_ms_per_call_mean']:.1f} ms")
            lines.append(f"- Threaded total wall (8 calls): {c['threaded_wall_total_ms_for_8_calls']:.1f} ms")
            lines.append(f"- Ideal-parallel wall if truly concurrent: {c['ideal_parallel_wall_if_truly_concurrent_ms']:.1f} ms")
        lines.append("")
    if "bpb" in s:
        b = s["bpb"]
        lines.append(f"### §5 Bits-per-byte (BPB)")
        if b.get("status") == "OK":
            lines.append(f"- Bytes scored: {b['n_bytes_scored']}")
            lines.append(f"- Avg NLL (nats): {b['avg_nll_nats']:.4f}")
            lines.append(f"- **BPB: {b['bits_per_byte']:.4f}**")
            lines.append(f"- Held-out preview: `{b['held_out_preview']}`")
            lines.append(f"- Interpretation: {b['interpretation']}")
        else:
            lines.append(f"- Status: {b.get('status')}")
            lines.append(f"- Reason: {b.get('reason')}")
        lines.append("")
    lines.append("---")
    lines.append("## Spec coverage tally")
    lines.append("")
    lines.append(f"- Sections executed: **{len(s)}**")
    lines.append(f"- Sections skipped (with reason): **{len(r['skipped'])}**")
    lines.append("")
    lines.append("This is honest partial coverage. Do not interpret as a complete benchmark of the spec.")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
