#!/usr/bin/env python3
"""Manual gated KJV Tokenless retraining orchestrator."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def simple_yaml_load(path: Path) -> dict[str, Any]:
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    lines: list[tuple[int, str]] = []
    for raw in raw_lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        content = raw.split("#", 1)[0].rstrip()
        if content:
            lines.append((len(raw) - len(raw.lstrip(" ")), content.strip()))

    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    for idx, (indent, content) in enumerate(lines):
        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if content.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"list item without list parent at line {idx + 1}: {content}")
            parent.append(parse_scalar(content[2:]))
            continue
        if ":" not in content:
            raise ValueError(f"invalid YAML line {idx + 1}: {content}")
        key, value = content.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            if not isinstance(parent, dict):
                raise ValueError(f"mapping item without mapping parent at line {idx + 1}")
            parent[key] = parse_scalar(value)
            continue
        next_is_list = False
        for next_indent, next_content in lines[idx + 1:]:
            if next_indent <= indent:
                break
            next_is_list = next_content.startswith("- ")
            break
        container: Any = [] if next_is_list else {}
        if not isinstance(parent, dict):
            raise ValueError(f"mapping item without mapping parent at line {idx + 1}")
        parent[key] = container
        stack.append((indent, container))
    return root


def load_recipe(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data or {}
    except Exception:
        return simple_yaml_load(path)


def tokenless_home(recipe: dict[str, Any]) -> Path:
    configured = (
        recipe.get("tokenless_home")
        or recipe.get("paths", {}).get("tokenless_home")
        or os.environ.get("TOKENLESS_HOME")
        or str(REPO_ROOT / "ml-training")
    )
    path = Path(str(configured)).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def recipe_python(recipe: dict[str, Any]) -> str:
    configured = recipe.get("python_bin") or recipe.get("paths", {}).get("python_bin")
    if not configured:
        return sys.executable
    path = Path(str(configured)).expanduser()
    return str(path if path.is_absolute() else REPO_ROOT / path)


def repo_path(value: str) -> str:
    p = Path(value).expanduser()
    if p.is_absolute():
        return str(p)
    return str((REPO_ROOT / p).resolve())


def run_command(cmd: list[str], env: dict[str, str], dry_run: bool) -> None:
    printable = " ".join(cmd)
    print(f"+ {printable}", flush=True)
    if dry_run:
        return
    subprocess.run(cmd, cwd=REPO_ROOT, env=env, check=True)


def model_args(config: dict[str, Any], seq_key: str = "max_seq_len") -> list[str]:
    return [
        "--n-layers", str(config["n_layers"]),
        "--d-model", str(config["d_model"]),
        "--n-heads", str(config["n_heads"]),
        "--d-ffn", str(config["d_ffn"]),
        "--seq-len", str(config[seq_key]),
    ]


def training_args(config: dict[str, Any]) -> list[str]:
    args = [
        "--iters", str(config.get("iters", 5000)),
        "--batch", str(config.get("batch", 8)),
        "--lr", str(config.get("lr", 3e-4)),
        "--lr-min", str(config.get("lr_min", 3e-5)),
        "--warmup", str(config.get("warmup", 200)),
        "--weight-decay", str(config.get("weight_decay", 0.1)),
        "--grad-clip", str(config.get("grad_clip", 1.0)),
        "--log-every", str(config.get("log_every", 10)),
        "--eval-every", str(config.get("eval_every", 200)),
        "--eval-batches", str(config.get("eval_batches", 10)),
        "--save-every", str(config.get("save_every", 500)),
        "--seed", str(config.get("seed", 42)),
    ]
    return args


def read_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def symlink_active(target: Path, active: Path, dry_run: bool) -> None:
    tmp = active.with_name(active.name + ".tmp")
    print(f"+ publish active -> {target}")
    if dry_run:
        return
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    tmp.symlink_to(target, target_is_directory=True)
    os.replace(tmp, active)


def publish_selection(recipe: dict[str, Any], home: Path, dry_run: bool) -> dict[str, Any]:
    run_group = recipe.get("run_group", "kjv_tokenless_v1")
    byte_id = recipe.get("byte_model", {}).get("run_id", "kjv_byte_v1_20m")
    bpe_id = recipe.get("bpe_model", {}).get("run_id", "kjv_bpe_v1_20m")
    gates = recipe.get("gates", {})
    byte_eval = read_report(home / "eval" / run_group / f"{byte_id}.eval.json")
    bpe_eval = read_report(home / "eval" / run_group / f"{bpe_id}.eval.json")
    retrieval = read_report(home / "eval" / run_group / "retrieval_validation.json")
    byte_ppl = byte_eval.get("val_ppl")
    bpe_ppl = bpe_eval.get("val_ppl")
    ratio_limit = float(gates.get("byte_ppl_ratio_max", 1.25))
    retrieval_pass = bool(retrieval.get("pass"))
    byte_ratio_ok = (
        byte_ppl is not None and bpe_ppl is not None and float(byte_ppl) <= ratio_limit * float(bpe_ppl)
    )
    byte_default = retrieval_pass and byte_ratio_ok
    selected = byte_id if byte_default else bpe_id
    publish_allowed = retrieval_pass and (byte_default or bpe_ppl is not None)
    status = {
        "run_group": run_group,
        "byte_model": byte_id,
        "bpe_model": bpe_id,
        "byte_val_ppl": byte_ppl,
        "bpe_val_ppl": bpe_ppl,
        "byte_ppl_ratio_limit": ratio_limit,
        "byte_within_ratio": byte_ratio_ok,
        "retrieval_pass": retrieval_pass,
        "selected_default": selected if publish_allowed else None,
        "publish_allowed": publish_allowed,
        "rule": (
            "Publish byte if retrieval gates pass and byte validation perplexity is "
            "within 25% of BPE; otherwise publish BPE only when gates pass."
        ),
    }
    out_path = home / "eval" / run_group / "selection_report.json"
    print(json.dumps(status, indent=2))
    if not dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    if publish_allowed:
        symlink_active(home / "exports" / selected, home / "exports" / f"{run_group}_active", dry_run)
    else:
        print("Active export unchanged: validation gates are incomplete or failed.")
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", required=True)
    parser.add_argument("--stage", default="all",
                        choices=["all", "prepare", "train", "evaluate", "export", "publish"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    recipe_path = Path(args.recipe).expanduser()
    if not recipe_path.is_absolute():
        recipe_path = (REPO_ROOT / recipe_path).resolve()
    recipe = load_recipe(recipe_path)
    home = tokenless_home(recipe)
    env = dict(os.environ)
    env["TOKENLESS_HOME"] = str(home)
    py = recipe_python(recipe)

    run_group = recipe.get("run_group", "kjv_tokenless_v1")
    corpus_id = recipe.get("corpus_id", "eng_kjv_apocrypha_v1")
    corpus_dir = home / "corpus" / corpus_id
    eval_dir = home / "eval" / run_group
    byte_cfg = recipe.get("byte_model", {})
    bpe_cfg = recipe.get("bpe_model", {})
    train_cfg = recipe.get("training", {})
    gates = recipe.get("gates", {})
    byte_id = byte_cfg.get("run_id", "kjv_byte_v1_20m")
    bpe_id = bpe_cfg.get("run_id", "kjv_bpe_v1_20m")
    tokenizer_prefix = bpe_cfg.get("tokenizer_prefix", bpe_id)
    tokenizer_model = home / "tokenizer" / f"{tokenizer_prefix}.model"
    tokenizer_vocab = home / "tokenizer" / f"{tokenizer_prefix}.vocab"

    if not args.dry_run:
        eval_dir.mkdir(parents=True, exist_ok=True)

    def stage_enabled(name: str) -> bool:
        return args.stage == "all" or args.stage == name

    if stage_enabled("prepare"):
        run_command([
            py, str(SCRIPT_DIR / "build_kjv_corpus.py"),
            "--corpus-id", corpus_id,
            "--primary-text", repo_path(recipe.get("primary_text", "eng-kjv_vpl/eng-kjv_vpl.xml")),
            "--crosscheck-text", repo_path(recipe.get("crosscheck_text", "eng-kjv_vpl/eng-kjv_vpl.txt")),
            "--html-dir", repo_path("eng-kjv_html"),
            "--browser-dir", repo_path("eng-kjv_browserBible"),
            "--out-dir", str(corpus_dir),
            "--repo-root", str(REPO_ROOT),
            "--strict",
        ], env, args.dry_run)
        run_command([
            py, str(SCRIPT_DIR / "validate_kjv_retrieval.py"),
            "--corpus-dir", str(corpus_dir),
            "--out", str(eval_dir / "retrieval_validation.json"),
            "--natural-top3-min", str(gates.get("natural_top3_min", 0.90)),
            "--apocrypha-top3-min", str(gates.get("apocrypha_top3_min", 0.90)),
        ], env, args.dry_run)

    if stage_enabled("train"):
        run_command([
            py, str(SCRIPT_DIR / "train_tokenizer.py"),
            "--corpus", str(corpus_dir / "corpus.txt"),
            "--vocab-size", str(bpe_cfg.get("vocab_size", 16000)),
            "--model-type", "bpe",
            "--prefix", tokenizer_prefix,
        ], env, args.dry_run)
        run_command([
            py, str(SCRIPT_DIR / "train.py"),
            "--run-id", bpe_id,
            "--corpus", str(corpus_dir / "corpus.txt"),
            "--tokenizer", str(tokenizer_model),
            "--token-cache", str(corpus_dir / "tokens_bpe_uint32.npy"),
            *model_args(bpe_cfg),
            *training_args(train_cfg),
        ], env, args.dry_run)
        run_command([
            py, str(SCRIPT_DIR / "train_byte.py"),
            "--run-id", byte_id,
            "--corpus", str(corpus_dir / "corpus.txt"),
            "--token-cache", str(corpus_dir / "tokens_byte_uint16.npy"),
            *model_args(byte_cfg),
            *training_args(train_cfg),
        ], env, args.dry_run)

    if stage_enabled("evaluate"):
        run_command([
            py, str(SCRIPT_DIR / "eval_final.py"),
            "--run-dir", str(home / "runs" / bpe_id),
            "--tokenizer", str(tokenizer_model),
            "--token-cache", str(corpus_dir / "tokens_bpe_uint32.npy"),
            "--out", str(eval_dir / f"{bpe_id}.eval.json"),
        ], env, args.dry_run)
        run_command([
            py, str(SCRIPT_DIR / "eval_byte.py"),
            "--run-dir", str(home / "runs" / byte_id),
            "--token-cache", str(corpus_dir / "tokens_byte_uint16.npy"),
            "--out", str(eval_dir / f"{byte_id}.eval.json"),
        ], env, args.dry_run)
        run_command([
            py, str(SCRIPT_DIR / "validate_kjv_retrieval.py"),
            "--corpus-dir", str(corpus_dir),
            "--out", str(eval_dir / "retrieval_validation.json"),
            "--natural-top3-min", str(gates.get("natural_top3_min", 0.90)),
            "--apocrypha-top3-min", str(gates.get("apocrypha_top3_min", 0.90)),
        ], env, args.dry_run)

    if stage_enabled("export"):
        run_command([
            py, str(SCRIPT_DIR / "export.py"),
            "--run-dir", str(home / "runs" / bpe_id),
            "--out-dir", str(home / "exports" / bpe_id),
            "--tokenizer-model", str(tokenizer_model),
            "--tokenizer-vocab", str(tokenizer_vocab),
            "--model-id", bpe_id,
            "--corpus-dir", str(corpus_dir),
            "--corpus-manifest", str(corpus_dir / "manifest.json"),
            "--training-recipe", str(recipe_path),
            "--validation-report", str(eval_dir / "retrieval_validation.json"),
            "--copy-runtime",
        ], env, args.dry_run)
        run_command([
            py, str(SCRIPT_DIR / "export_byte.py"),
            "--run-dir", str(home / "runs" / byte_id),
            "--out-dir", str(home / "exports" / byte_id),
            "--model-id", byte_id,
            "--corpus-dir", str(corpus_dir),
            "--training-recipe", str(recipe_path),
            "--validation-report", str(eval_dir / "retrieval_validation.json"),
        ], env, args.dry_run)

    if args.stage == "publish":
        publish_selection(recipe, home, args.dry_run)

    if args.stage == "all":
        publish_selection(recipe, home, args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
