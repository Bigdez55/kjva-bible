#!/usr/bin/env python3
"""merge_omni_to_safetensors.py — Bake OMNI-PEFT LoRA deltas into base safetensors.

Semi-merged deployment: ONLY LoRA weight deltas are baked into the safetensors.
IA3, BitFit, and PrefixTuning are NOT baked — they require the MLX runtime path
(see serve_adapted_model.py) because they are jointly optimized with each other.

CRITICAL: IA3 and BitFit are jointly optimized during training. Folding IA3 alone
(without BitFit) causes BPB regression (~1.39 vs 1.19). Folding both (IA3+BitFit)
into the weight matrix is also incorrect since BitFit is additive-to-activation,
not multiplicative-to-weight. LoRA is the only operator that cleanly folds into
the frozen weight as an additive delta: W_merged = W_frozen + (B @ A) * (alpha/rank).

What IS baked:
  LoRA:  W += (B @ A) * (alpha / rank)   — safe weight-space additive delta

What is SKIPPED and why:
  IA3         — jointly optimized with BitFit; stripping BitFit causes regression
  BitFit      — additive bias on activations, not compatible with static GGUF weight merge
  PrefixTuning — K/V augmentation at attention runtime; not a weight-space delta

For full-composite inference (all 4 operators active), use:
  python3 training/scripts/serve_adapted_model.py  (MLX hot-swap path)

For GGUF deployment with LoRA-only merge:
  python3 merge_omni_to_safetensors.py \\
      --base-weights  training/runs/byte_clean_v2/ckpt_step_003000.safetensors \\
      --adapters      training/runs/omni_scribe_pareto/omni_adapter_weights.npz \\
      --output        training/exports/kjva_lora_merged.safetensors

  python3 safetensors_to_gguf.py \\
      --weights training/exports/kjva_lora_merged.safetensors \\
      --config  training/runs/byte_clean_v2/model_config.json \\
      --vocab   training/runs/byte_clean_v2/byte_vocab.json \\
      --output  training/gguf/kjva_lora_merged.gguf --dtype q4_0

To also extract residuals (IA3+BitFit+Prefix) as a separate NPZ for the MLX path:
  python3 merge_omni_to_safetensors.py ... --residuals-output training/exports/kjva_residuals.npz
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import mlx.core as mx
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))


# Map from adapter key prefix to safetensors weight key.
# Adapter: op_layerN_attn_{q|k|v|o} → base: blocks.N.attn.{q|k|v|o}.weight
_SLOT_MAP = {
    "attn_q": "attn.q.weight",
    "attn_k": "attn.k.weight",
    "attn_v": "attn.v.weight",
    "attn_o": "attn.o.weight",
}


def _parse_adapter_key(key: str):
    """Parse 'op_layerN_attn_X.component' into (layer_idx, slot, component)."""
    # key format: op_layer{N}_{slot}.{component}
    # e.g. op_layer2_attn_q.weight_op.A
    if not key.startswith("op_layer"):
        return None
    rest = key[len("op_layer"):]
    dot = rest.index(".")
    prefix = rest[:dot]       # e.g. "2_attn_q"
    component = rest[dot+1:]  # e.g. "weight_op.A"
    parts = prefix.split("_", 1)
    layer_idx = int(parts[0])
    slot = parts[1]  # e.g. "attn_q"
    return layer_idx, slot, component


def apply_adapter(weights: dict[str, np.ndarray], npz_path: str,
                  alpha: float, rank: int, verbose: bool = True) -> dict[str, np.ndarray]:
    """Apply LoRA-ONLY from one OMNI-PEFT NPZ adapter into a mutable weights dict.

    ONLY LoRA deltas are folded in: W_merged = W_frozen + (B @ A) * (alpha/rank).
    IA3, BitFit, and PrefixTuning are intentionally skipped — these operators are
    jointly optimized and cannot be cleanly separated for static weight baking.
    Use serve_adapted_model.py for full-composite inference.
    """
    npz = np.load(npz_path)
    lora_scale = alpha / rank

    # Group tensors by (layer_idx, slot)
    slots: dict[tuple, dict] = {}
    for key in npz.files:
        parsed = _parse_adapter_key(key)
        if parsed is None:
            continue
        layer_idx, slot, component = parsed
        k = (layer_idx, slot)
        if k not in slots:
            slots[k] = {}
        slots[k][component] = npz[key]

    applied_lora = 0
    skipped_ia3 = skipped_bitfit = skipped_prefix = 0

    for (layer_idx, slot), comps in sorted(slots.items()):
        if slot not in _SLOT_MAP:
            continue
        base_key = f"blocks.{layer_idx}.{_SLOT_MAP[slot]}"
        if base_key not in weights:
            if verbose:
                print(f"  [skip] {base_key} not found in base weights")
            continue

        W = weights[base_key].astype(np.float32)  # (out, in)

        # LoRA only: W += (B @ A) * scale
        if "weight_op.A" in comps and "weight_op.B" in comps:
            A = comps["weight_op.A"].astype(np.float32)  # (rank, in)
            B = comps["weight_op.B"].astype(np.float32)  # (out, rank)
            delta = (B @ A) * lora_scale
            W = W + delta
            applied_lora += 1
            weights[base_key] = W

        if "ia3_scale" in comps:
            skipped_ia3 += 1
        if "bitfit_bias" in comps:
            skipped_bitfit += 1
        if verbose:
            print(f"  [{layer_idx}] {slot}: lora_baked={('weight_op.A' in comps)}")

    for k in npz.files:
        if k.startswith("prefix_tuning"):
            skipped_prefix += 1
            break

    if verbose:
        print(f"  baked: lora={applied_lora}  "
              f"skipped (need MLX path): ia3={skipped_ia3}, "
              f"bitfit={skipped_bitfit}, prefix_tuning={skipped_prefix > 0}")

    return weights


def extract_residuals(npz_path: str, output_path: str, verbose: bool = True) -> dict:
    """Extract IA3 + BitFit + PrefixTuning tensors into a residuals NPZ.

    These operators cannot be baked into GGUF weights. They are extracted
    here for use with the MLX runtime path (serve_adapted_model.py).
    """
    npz = np.load(npz_path)
    residuals: dict[str, np.ndarray] = {}

    for key in npz.files:
        parsed = _parse_adapter_key(key)
        if parsed is not None:
            _, _, component = parsed
            if component in ("ia3_scale", "bitfit_bias"):
                residuals[key] = npz[key]
        elif key.startswith("prefix_tuning"):
            residuals[key] = npz[key]

    if residuals:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(output_path, **residuals)
        if verbose:
            print(f"  residuals: {len(residuals)} tensors → {output_path}")
    else:
        if verbose:
            print("  no residuals found (no ia3/bitfit/prefix keys)")

    return {"residual_count": len(residuals), "path": output_path}


def load_safetensors_as_numpy(path: str) -> dict[str, np.ndarray]:
    w = mx.load(path)
    return {k: np.array(v, dtype=np.float32) for k, v in w.items()}


def save_safetensors(weights: dict[str, np.ndarray], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    mx_weights = {k: mx.array(v) for k, v in weights.items()}
    mx.save_safetensors(path, mx_weights)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bake LoRA-only from OMNI-PEFT adapters into base safetensors (semi-merged).")
    parser.add_argument("--base-weights", required=True)
    parser.add_argument("--adapters", nargs="+", required=True,
                        help="Adapter NPZ files (applied left-to-right)")
    parser.add_argument("--alpha", type=float, default=16.0)
    parser.add_argument("--rank", type=int, default=8)
    parser.add_argument("--output", required=True)
    parser.add_argument("--residuals-output", default=None,
                        help="Optional: extract IA3+BitFit+Prefix into a residuals NPZ "
                             "for the MLX runtime path (serve_adapted_model.py)")
    args = parser.parse_args()

    print(f"[merge] Loading base weights: {args.base_weights}")
    weights = load_safetensors_as_numpy(args.base_weights)
    print(f"[merge] {len(weights)} tensors loaded")
    print(f"[merge] Mode: LoRA-only bake (IA3/BitFit/Prefix skipped — jointly optimized)")

    for i, adapter_path in enumerate(args.adapters, 1):
        print(f"\n[merge] Applying adapter {i}/{len(args.adapters)}: {adapter_path}")
        apply_adapter(weights, adapter_path, alpha=args.alpha, rank=args.rank)

    print(f"\n[merge] Saving LoRA-merged weights: {args.output}")
    save_safetensors(weights, args.output)
    sha = sha256_file(args.output)
    size_mb = Path(args.output).stat().st_size / (1 << 20)
    print(f"[merge] Done: {size_mb:.1f} MB  sha256={sha[:16]}...")

    # Optionally extract residuals
    residuals_result = {}
    if args.residuals_output:
        print(f"\n[merge] Extracting residuals (IA3+BitFit+Prefix) → {args.residuals_output}")
        for adapter_path in args.adapters:
            residuals_result = extract_residuals(adapter_path, args.residuals_output)

    # Write sidecar manifest
    manifest = {
        "base_weights": args.base_weights,
        "adapters_applied": args.adapters,
        "alpha": args.alpha,
        "rank": args.rank,
        "merged_output": args.output,
        "merged_sha256": sha,
        "size_mb": round(size_mb, 2),
        "baked_operators": ["lora"],
        "skipped_operators": ["ia3", "bitfit", "prefix_tuning"],
        "residuals_npz": args.residuals_output,
        "note": (
            "LoRA-only bake (semi-merged deployment). "
            "IA3/BitFit skipped: jointly optimized — stripping BitFit orphans IA3, causing BPB regression. "
            "PrefixTuning skipped: K/V augmentation not supported in static GGUF. "
            "For full 4-operator inference use training/scripts/serve_adapted_model.py (MLX hot-swap)."
        ),
    }
    manifest_path = args.output + ".merge_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"[merge] Manifest: {manifest_path}")
    print(f"[merge] NOTE: For full OMNI-PEFT composite, use serve_adapted_model.py instead.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
