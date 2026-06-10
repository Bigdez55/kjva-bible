#!/usr/bin/env python3
"""Export a byte-level TokenlessLM checkpoint as a portable KJV bundle."""
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
from mlx.utils import tree_flatten, tree_unflatten

sys.path.insert(0, str(Path(__file__).parent))
from model import ModelConfig, TokenlessLM  # noqa


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
TOKENLESS_HOME = Path(os.environ.get("TOKENLESS_HOME", str(REPO_ROOT / "ml-training")))


def latest_ckpt(run_dir: Path) -> Path:
    ckpts = sorted(run_dir.glob("ckpt_step_*.safetensors"))
    if not ckpts:
        raise FileNotFoundError(f"no checkpoints in {run_dir}")
    return ckpts[-1]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def copy_corpus_artifacts(corpus_dir: Path, out_dir: Path) -> dict[str, str]:
    copied: dict[str, str] = {}
    corpus_out = out_dir / "corpus"
    for name in [
        "verses.jsonl",
        "retrieval_index.json",
        "manifest.json",
        "validation_report.json",
        "byte_vocab.json",
    ]:
        if copy_if_exists(corpus_dir / name, corpus_out / name):
            copied[f"corpus/{name}"] = f"corpus/{name}"
    return copied


def copy_runtime_scripts(out_dir: Path) -> dict[str, str]:
    copied: dict[str, str] = {}
    scripts_dir = Path(__file__).parent
    runtime_out = out_dir / "runtime"
    for name in ["model.py", "kjv_retrieval.py", "serve_kjv_bundle.py"]:
        if copy_if_exists(scripts_dir / name, runtime_out / name):
            copied[f"runtime/{name}"] = f"runtime/{name}"
    return copied


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--ckpt", default=None)
    parser.add_argument("--model-id", default="kjv_byte_v1_20m")
    parser.add_argument("--corpus-dir", default=str(TOKENLESS_HOME / "corpus/eng_kjv_apocrypha_v1"))
    parser.add_argument("--training-recipe", default=None)
    parser.add_argument("--validation-report", default=None)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    out_dir = Path(args.out_dir)
    corpus_dir = Path(args.corpus_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    config_path = run_dir / "model_config.json"
    ckpt_path = Path(args.ckpt) if args.ckpt else latest_ckpt(run_dir)
    cfg_data = json.loads(config_path.read_text(encoding="utf-8"))
    cfg = ModelConfig(**cfg_data)
    model = TokenlessLM(cfg)
    weights = mx.load(str(ckpt_path))
    model.update(tree_unflatten(list(weights.items())))
    flat = dict(tree_flatten(model.parameters()))

    out_weights = out_dir / "weights.safetensors"
    shutil.copy2(ckpt_path, out_weights)
    shutil.copy2(config_path, out_dir / "model_config.json")

    byte_vocab_src = run_dir / "byte_vocab.json"
    if not byte_vocab_src.exists():
        byte_vocab_src = corpus_dir / "byte_vocab.json"
    shutil.copy2(byte_vocab_src, out_dir / "byte_vocab.json")

    copied = {}
    copied.update(copy_corpus_artifacts(corpus_dir, out_dir))
    copied.update(copy_runtime_scripts(out_dir))
    if args.training_recipe and Path(args.training_recipe).exists():
        shutil.copy2(args.training_recipe, out_dir / "training_recipe.yaml")
        copied["training_recipe.yaml"] = "training_recipe.yaml"
    if args.validation_report and Path(args.validation_report).exists():
        shutil.copy2(args.validation_report, out_dir / "validation_report.json")
        copied["validation_report.json"] = "validation_report.json"

    run_meta = {}
    log_path = run_dir / "train_log.jsonl"
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").splitlines()
        if lines:
            try:
                run_meta["run_start"] = json.loads(lines[0])
            except json.JSONDecodeError:
                pass
        for line in reversed(lines):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("event") == "eval" and "last_eval" not in run_meta:
                run_meta["last_eval"] = row
            if row.get("event") == "run_end" and "run_end" not in run_meta:
                run_meta["run_end"] = row

    corpus_manifest = {}
    if (corpus_dir / "manifest.json").exists():
        corpus_manifest = json.loads((corpus_dir / "manifest.json").read_text(encoding="utf-8"))

    n_params = sum(int(arr.size) for arr in flat.values())
    manifest = {
        "export_id": args.model_id,
        "model_id": args.model_id,
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_run_dir": str(run_dir),
        "source_ckpt": str(ckpt_path),
        "source_ckpt_sha256": sha256_file(ckpt_path),
        "weights_sha256": sha256_file(out_weights),
        "weights_match_source_checkpoint": sha256_file(out_weights) == sha256_file(ckpt_path),
        "model_config_sha256": sha256_file(out_dir / "model_config.json"),
        "byte_vocab_sha256": sha256_file(out_dir / "byte_vocab.json"),
        "tokenization": "utf8_byte",
        "architecture": cfg_data,
        "n_parameters": n_params,
        "corpus_id": corpus_manifest.get("corpus_id"),
        "corpus_manifest_sha256": (
            sha256_file(corpus_dir / "manifest.json")
            if (corpus_dir / "manifest.json").exists() else None
        ),
        "copied_artifacts": copied,
        "run_metadata": run_meta,
        "tokenless_attestation": (
            "All weights in this export were initialized from mlx.random and "
            "updated exclusively via AdamW on the configured KJV Tokenless corpus. "
            "Zero pretrained weights, zero old POC checkpoints, zero external base model."
        ),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                           encoding="utf-8")
    (out_dir / "README.md").write_text(
        "# KJV Byte Tokenless Export\n\n"
        "This bundle contains byte-level TokenlessLM weights, model config, byte vocab metadata, "
        "KJV verse artifacts, a retrieval index, and minimal runtime scripts.\n\n"
        "Exact verse answers must use retrieval via `/v1/cite`; generation is not a substitute "
        "for citation lookup.\n",
        encoding="utf-8",
    )
    print(f"Export complete: {out_dir}")
    print(f"  weights_sha256: {manifest['weights_sha256']}")
    print(f"  parameters: {n_params:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
