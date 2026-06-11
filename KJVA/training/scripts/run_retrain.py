#!/usr/bin/env python3
"""run_retrain.py — thin retrain delegate for the omni training program.

`omni_training_program.py run [--stage S] [--dry-run]` resolves
``program["delegate_recipe"]`` and shells into this script with the exact
contract:

    run_retrain.py --recipe <path> [--stage <stage>] [--dry-run]

where ``--stage`` ∈ {prepare, train, evaluate, export, publish} (omitted ⇒
``all``). This file is the missing delegate that contract pointed at.

The canonical trainer is the **MLX** stack under ``training/scripts/``.
A runnable ``train`` stage means subprocess'ing into ``scripts/train_byte.py``
(full pretrain) or, for a PEFT recipe, ``scripts/train_peft.py``.

Recipe schema (reuse of the existing ``kjv_omni_program.yaml`` shape — the
only real program file in the repo, so the dry-run is meaningful)::

    framework: mlx
    corpus: {path: corpus/.../corpus.txt}
    base:
      name: byte_v1_20m
      arch: {n_layers, n_heads, d_model, d_ffn, max_seq_len, ...}
    pretraining: {iters, batch, seq_len, seed, warmup, grad_clip,
                  weight_decay, lr_max, lr_min}
    # For a PEFT recipe instead of pretraining:
    peft:  {method: lora, base_checkpoint: ..., rank, alpha, steps, batch,
            seq_len, lr}
    # (or top-level `method: <peft-id>` is also honoured.)

Only flags actually present in the recipe are emitted; the trainer's own
argparse defaults fill the rest. ``--dry-run`` prints the assembled command
and returns 0 without executing — the verify path with no torch installed.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
# Make `omni_training_program` importable even when invoked by absolute path.
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# REPO_ROOT == training/scripts/../.. == "models v7" root.
REPO_ROOT = SCRIPT_DIR.parents[1]
TRAIN_BYTE = SCRIPT_DIR / "train_byte.py"
TRAIN_PEFT = SCRIPT_DIR / "train_peft.py"

# PEFT/alignment method ids that route to train_peft.py instead of train_byte.py.
PEFT_METHODS = {
    "lora", "dora", "ia3", "sft", "dpo", "qlora", "adalora", "loha", "lokr",
    "vera", "boft", "rslora", "pissa", "omni",
}


def _load_yaml_or_json(path: Path) -> dict[str, Any]:
    """Load a recipe. JSON by suffix; otherwise reuse omni's tolerant YAML loader."""
    if path.suffix.lower() == ".json":
        import json

        return json.loads(path.read_text(encoding="utf-8")) or {}
    # Reuse the exact loader omni uses (PyYAML if present, else the simple parser).
    from omni_training_program import load_yaml  # type: ignore

    return load_yaml(path) or {}


def _resolve(value: Any, base: Path = REPO_ROOT) -> Path:
    p = Path(str(value)).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def _get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Nested get: _get(recipe, 'base', 'arch', 'n_layers')."""
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _emit(cmd: list[str], flag: str, value: Any) -> None:
    """Append `flag value` only when value is present (not None / not '')."""
    if value is None:
        return
    if isinstance(value, str) and value == "":
        return
    cmd.extend([flag, str(value)])


def _detect_peft_method(recipe: dict[str, Any]) -> str | None:
    """Return a PEFT method id if this recipe is a PEFT/alignment run, else None."""
    peft = recipe.get("peft")
    if isinstance(peft, dict) and peft.get("method"):
        return str(peft["method"])
    # Top-level `method:` only counts when it names a PEFT method (the omni
    # program YAML carries `omni.method: omni`, handled below).
    m = recipe.get("method")
    if isinstance(m, str) and m.lower() in PEFT_METHODS:
        return m
    omni_method = _get(recipe, "omni", "method")
    if isinstance(omni_method, str) and omni_method.lower() in PEFT_METHODS:
        return omni_method
    return None


def build_pretrain_cmd(py: str, recipe: dict[str, Any]) -> list[str]:
    """Map a pretraining recipe onto a scripts/train_byte.py invocation."""
    cmd = [py, str(TRAIN_BYTE)]
    _emit(cmd, "--run-id", _get(recipe, "base", "name"))

    corpus = _get(recipe, "corpus", "path")
    if corpus:
        _emit(cmd, "--corpus", str(_resolve(corpus)))

    pt = recipe.get("pretraining", {}) if isinstance(recipe.get("pretraining"), dict) else {}
    _emit(cmd, "--iters", pt.get("iters"))
    _emit(cmd, "--batch", pt.get("batch"))
    _emit(cmd, "--seed", pt.get("seed"))
    _emit(cmd, "--warmup", pt.get("warmup"))
    _emit(cmd, "--grad-clip", pt.get("grad_clip"))
    _emit(cmd, "--weight-decay", pt.get("weight_decay"))
    _emit(cmd, "--lr", pt.get("lr_max"))
    _emit(cmd, "--lr-min", pt.get("lr_min"))
    # seq-len: prefer pretraining override, else the arch value.
    _emit(cmd, "--seq-len", pt.get("seq_len") or _get(recipe, "base", "arch", "max_seq_len"))

    _emit(cmd, "--n-layers", _get(recipe, "base", "arch", "n_layers"))
    _emit(cmd, "--d-model", _get(recipe, "base", "arch", "d_model"))
    _emit(cmd, "--n-heads", _get(recipe, "base", "arch", "n_heads"))
    _emit(cmd, "--d-ffn", _get(recipe, "base", "arch", "d_ffn"))
    return cmd


def build_peft_cmd(py: str, recipe: dict[str, Any], method: str) -> list[str]:
    """Map a PEFT recipe onto a scripts/train_peft.py invocation (requires base ckpt)."""
    peft = recipe.get("peft", {}) if isinstance(recipe.get("peft"), dict) else {}
    base_ckpt = (
        peft.get("base_checkpoint")
        or recipe.get("base_checkpoint")
        or _get(recipe, "base", "checkpoint")
    )
    if not base_ckpt:
        raise SystemExit(
            "[run_retrain] PEFT method '%s' requires a base checkpoint; add "
            "`peft.base_checkpoint` (or `base_checkpoint`) to the recipe." % method
        )
    cmd = [py, str(TRAIN_PEFT), "--method", method,
           "--base-checkpoint", str(_resolve(base_ckpt))]
    corpus = peft.get("corpus") or _get(recipe, "corpus", "path")
    if corpus:
        _emit(cmd, "--corpus", str(_resolve(corpus)))
    _emit(cmd, "--output", peft.get("output"))
    _emit(cmd, "--rank", peft.get("rank"))
    _emit(cmd, "--alpha", peft.get("alpha"))
    _emit(cmd, "--steps", peft.get("steps"))
    _emit(cmd, "--batch", peft.get("batch"))
    _emit(cmd, "--seq-len", peft.get("seq_len"))
    _emit(cmd, "--lr", peft.get("lr"))
    _emit(cmd, "--seed", peft.get("seed"))
    return cmd


def run(recipe_path: Path, stage: str, dry_run: bool) -> int:
    if not recipe_path.exists():
        print(f"[run_retrain] recipe not found: {recipe_path}", file=sys.stderr)
        return 2
    recipe = _load_yaml_or_json(recipe_path)
    py = sys.executable

    # Stages other than train are not runnable from a recipe alone (the eval /
    # export trainers need explicit checkpoint/output paths a recipe doesn't
    # carry). Report them honestly as no-ops instead of inventing fragile args.
    if stage in {"prepare", "publish"}:
        print(f"[run_retrain] stage '{stage}' is a no-op for recipe "
              f"{recipe_path.name} (nothing to do).", flush=True)
        return 0
    if stage in {"evaluate", "export"}:
        script = "scripts/eval_byte.py" if stage == "evaluate" else "scripts/export_byte.py"
        print(f"[run_retrain] stage '{stage}' is not driven by the recipe; run "
              f"{script} directly with explicit checkpoint paths.", flush=True)
        return 0

    # stage in {"all", "train"} → drive the canonical MLX trainer.
    method = _detect_peft_method(recipe)
    if method and method.lower() != "omni":
        if not TRAIN_PEFT.exists():
            print(f"[run_retrain] train_peft.py missing at {TRAIN_PEFT}", file=sys.stderr)
            return 2
        cmd = build_peft_cmd(py, recipe, method)
    else:
        # Full pretrain (also the default for `method: omni`, which auto-selects
        # downstream; the base pretrain is the runnable retrain here).
        if not TRAIN_BYTE.exists():
            print(f"[run_retrain] train_byte.py missing at {TRAIN_BYTE}", file=sys.stderr)
            return 2
        cmd = build_pretrain_cmd(py, recipe)

    print("+ " + " ".join(cmd), flush=True)
    if dry_run:
        return 0
    return subprocess.run(cmd, cwd=REPO_ROOT, env=dict(os.environ), check=False).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="omni retrain delegate → MLX trainer")
    ap.add_argument("--recipe", required=True, help="path to a program/recipe YAML or JSON")
    ap.add_argument("--stage", default="all",
                    choices=["all", "prepare", "train", "evaluate", "export", "publish"])
    ap.add_argument("--dry-run", action="store_true",
                    help="print the assembled trainer command and exit 0")
    args = ap.parse_args()
    return run(_resolve(args.recipe), args.stage, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
