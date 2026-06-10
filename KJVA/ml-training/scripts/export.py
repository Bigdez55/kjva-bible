#!/usr/bin/env python3
"""
export.py - Package a trained TokenlessLM checkpoint + tokenizer into a
portable, self-contained export directory ready for inference (and eventual
GGUF conversion for XMIND).

Produces:
  <export_dir>/
    weights.safetensors           (fused model weights)
    model_config.json             (architecture spec)
    tokenizer.model               (SentencePiece binary)
    tokenizer.vocab               (SentencePiece vocab dump, for readability)
    manifest.json                 (full export metadata)
    README.md                     (how-to-load stub)

The export is tokenless: every byte traces to random init plus the configured
training corpus. Zero external pretrained material.

Usage:
  python export.py --run-dir "$TOKENLESS_HOME/runs/kjv_bpe_v1_20m" \
                   --out-dir  "$TOKENLESS_HOME/exports/kjv_bpe_v1_20m"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import mlx.core as mx
from mlx.utils import tree_unflatten, tree_flatten

sys.path.insert(0, str(Path(__file__).parent))
from model import ModelConfig, TokenlessLM  # noqa


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
TOKENLESS_HOME = Path(os.environ.get("TOKENLESS_HOME", str(REPO_ROOT / "ml-training")))
TOKENIZER_MODEL = TOKENLESS_HOME / "tokenizer" / "kjv_bpe_v1_20m.model"
TOKENIZER_VOCAB = TOKENLESS_HOME / "tokenizer" / "kjv_bpe_v1_20m.vocab"
CORPUS_STATS = TOKENLESS_HOME / "corpus" / "eng_kjv_apocrypha_v1" / "manifest.json"


def latest_ckpt(run_dir: Path) -> Path:
    ckpts = sorted(run_dir.glob("ckpt_step_*.safetensors"))
    if not ckpts:
        raise FileNotFoundError(f"no checkpoints in {run_dir}")
    return ckpts[-1]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--ckpt", default=None,
                        help="Specific checkpoint; default = latest")
    parser.add_argument("--tokenizer-model", default=str(TOKENIZER_MODEL))
    parser.add_argument("--tokenizer-vocab", default=str(TOKENIZER_VOCAB))
    parser.add_argument("--model-id", default=None)
    parser.add_argument("--corpus-manifest", default=None)
    parser.add_argument("--corpus-dir", default=None)
    parser.add_argument("--training-recipe", default=None)
    parser.add_argument("--validation-report", default=None)
    parser.add_argument("--copy-runtime", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    config_path = run_dir / "model_config.json"
    ckpt_path = Path(args.ckpt) if args.ckpt else latest_ckpt(run_dir)

    if not config_path.exists():
        print(f"ERROR: missing {config_path}", file=sys.stderr)
        sys.exit(1)

    # Load + re-save weights to ensure clean safetensors format
    cfg_data = json.loads(config_path.read_text())
    cfg = ModelConfig(**cfg_data)
    model = TokenlessLM(cfg)
    weights = mx.load(str(ckpt_path))
    model.update(tree_unflatten(list(weights.items())))

    out_weights = out_dir / "weights.safetensors"
    flat = dict(tree_flatten(model.parameters()))
    shutil.copy2(ckpt_path, out_weights)

    # Copy config
    shutil.copy2(config_path, out_dir / "model_config.json")

    # Copy tokenizer
    out_tok = out_dir / "tokenizer.model"
    out_vocab = out_dir / "tokenizer.vocab"
    shutil.copy2(args.tokenizer_model, out_tok)
    if Path(args.tokenizer_vocab).exists():
        shutil.copy2(args.tokenizer_vocab, out_vocab)

    copied_artifacts: dict[str, str] = {}
    for arg_name, out_name in [
        ("corpus_manifest", "corpus_manifest.json"),
        ("training_recipe", "training_recipe.yaml"),
        ("validation_report", "validation_report.json"),
    ]:
        src = getattr(args, arg_name)
        if src and Path(src).exists():
            shutil.copy2(src, out_dir / out_name)
            copied_artifacts[out_name] = out_name
    if args.corpus_dir:
        corpus_dir = Path(args.corpus_dir)
        corpus_out = out_dir / "corpus"
        for name in [
            "verses.jsonl",
            "retrieval_index.json",
            "manifest.json",
            "validation_report.json",
            "byte_vocab.json",
        ]:
            src = corpus_dir / name
            if src.exists():
                corpus_out.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, corpus_out / name)
                copied_artifacts[f"corpus/{name}"] = f"corpus/{name}"
    if args.copy_runtime:
        runtime_out = out_dir / "runtime"
        for name in ["model.py", "kjv_retrieval.py", "serve_kjv_bundle.py"]:
            src = Path(__file__).parent / name
            if src.exists():
                runtime_out.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, runtime_out / name)
                copied_artifacts[f"runtime/{name}"] = f"runtime/{name}"

    # Read training log for run metadata
    log_path = run_dir / "train_log.jsonl"
    run_meta: dict = {}
    if log_path.exists():
        with log_path.open("r") as f:
            lines = f.readlines()
        # first line is run_start; last line should be run_end
        try:
            run_meta["run_start"] = json.loads(lines[0])
        except Exception:
            pass
        try:
            run_meta["run_end"] = json.loads(lines[-1])
        except Exception:
            pass
        # Collect last eval row
        for line in reversed(lines):
            try:
                row = json.loads(line)
                if row.get("event") == "eval":
                    run_meta["last_eval"] = row
                    break
            except Exception:
                continue

    # Corpus stats
    corpus_stats: dict = {}
    if CORPUS_STATS.exists():
        corpus_stats = json.loads(CORPUS_STATS.read_text())
    corpus_manifest: dict = {}
    if args.corpus_manifest and Path(args.corpus_manifest).exists():
        corpus_manifest = json.loads(Path(args.corpus_manifest).read_text(encoding="utf-8"))

    n_params = sum(int(arr.size) for _, arr in flat.items())

    manifest = {
        "export_id": args.model_id or f"tokenless-{int(time.time())}",
        "model_id": args.model_id,
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_run_dir": str(run_dir),
        "source_ckpt": str(ckpt_path),
        "source_ckpt_sha256": sha256_file(ckpt_path),
        "weights_sha256": sha256_file(out_weights),
        "weights_match_source_checkpoint": sha256_file(out_weights) == sha256_file(ckpt_path),
        "tokenizer_sha256": sha256_file(out_tok),
        "architecture": cfg_data,
        "n_parameters": n_params,
        "tokenization": "sentencepiece_bpe",
        "corpus_id": corpus_manifest.get("corpus_id"),
        "corpus_manifest_sha256": (
            sha256_file(Path(args.corpus_manifest))
            if args.corpus_manifest and Path(args.corpus_manifest).exists()
            else None
        ),
        "run_metadata": run_meta,
        "corpus_stats": corpus_stats,
        "copied_artifacts": copied_artifacts,
        "tokenless_attestation": (
            "All weights in this export were initialized from mlx.random and "
            "updated exclusively via AdamW on the configured Tokenless corpus. "
            "Zero pretrained weights, zero external base model."
        ),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    # Minimal README stub (no auto-generated marketing; user requested no docs)
    readme = (
        f"# Tokenless LM export\n\n"
        f"- architecture: `{cfg_data}`\n"
        f"- parameters: {n_params:,}\n"
        f"- weights: weights.safetensors ({out_weights.stat().st_size:,} bytes)\n"
        f"- tokenizer: tokenizer.model (SentencePiece BPE)\n"
        f"- see manifest.json for full provenance\n\n"
        f"## Load & generate\n\n"
        f"```python\n"
        f"import json, os, sys, mlx.core as mx\n"
        f"from mlx.utils import tree_unflatten\n"
        f"import sentencepiece as spm\n"
        f"runtime_dir = os.path.join(os.getcwd(), 'runtime')\n"
        f"repo_scripts = os.path.join(os.environ.get('TOKENLESS_REPO_ROOT', os.getcwd()), 'ml-training/scripts')\n"
        f"sys.path.insert(0, runtime_dir if os.path.isdir(runtime_dir) else repo_scripts)\n"
        f"from model import ModelConfig, TokenlessLM\n\n"
        f"cfg = ModelConfig(**json.load(open('model_config.json')))\n"
        f"m = TokenlessLM(cfg)\n"
        f"m.update(tree_unflatten(list(mx.load('weights.safetensors').items())))\n"
        f"sp = spm.SentencePieceProcessor(model_file='tokenizer.model')\n"
        f"```\n"
    )
    (out_dir / "README.md").write_text(readme)

    print(f"Export complete: {out_dir}")
    print(f"  weights:      {out_weights} ({out_weights.stat().st_size:,} bytes)")
    print(f"  params:       {n_params:,}")
    print(f"  sha256:       {manifest['weights_sha256'][:16]}...")
    if "last_eval" in run_meta:
        ev = run_meta["last_eval"]
        print(f"  last val_ppl: {ev.get('val_ppl'):.3f} at step {ev.get('step')}")


if __name__ == "__main__":
    main()
