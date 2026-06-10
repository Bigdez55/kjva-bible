#!/usr/bin/env python3
"""
convert_to_gguf.py — Convert a validated TokenlessLM export bundle to GGUF format

GGUF (Generic Universal File Format) is the binary format used by llama.cpp,
Ollama, and LM Studio for local edge inference.

This converter handles the custom TokenlessLM architecture (decoder-only
transformer with RMSNorm + SwiGLU + RoPE). GGUF files are written with the
full metadata header so llama.cpp can load them without a separate config.

Supported quantization modes:
  f32   — full precision (largest, most accurate)
  f16   — half precision (default, good balance)
  q8_0  — 8-bit quantization (2x smaller, negligible quality loss)
  q4_0  — 4-bit quantization (4x smaller, small quality loss)
  q4_1  — 4-bit with delta (slightly larger than q4_0, higher quality)

Usage:
  python convert_to_gguf.py --input exports/kjv_tokenless_v1_active --output gguf/kjv_tokenless.gguf
  python convert_to_gguf.py --input exports/kjv_byte_v1_20m --output gguf/kjv_byte.gguf --dtype q8_0
  python convert_to_gguf.py --input exports/kjv_bpe_v1_20m --output gguf/kjv_bpe.gguf --dtype q4_0 --dry-run

Output:
  gguf/<name>.gguf         — the GGUF binary
  gguf/<name>.gguf.json    — sidecar metadata (human-readable)

References:
  GGUF spec: https://github.com/ggerganov/ggml/blob/master/docs/gguf.md
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
ML_TRAINING = SCRIPT_DIR.parent

# ---------------------------------------------------------------------------
# GGUF constants (from ggml spec)
# ---------------------------------------------------------------------------

GGUF_MAGIC = b"GGUF"
GGUF_VERSION = 3

class GGUFValueType(IntEnum):
    UINT8   = 0
    INT8    = 1
    UINT16  = 2
    INT16   = 3
    UINT32  = 4
    INT32   = 5
    FLOAT32 = 6
    BOOL    = 7
    STRING  = 8
    ARRAY   = 9
    UINT64  = 10
    INT64   = 11
    FLOAT64 = 12

class GGMLType(IntEnum):
    F32   = 0
    F16   = 1
    Q4_0  = 2
    Q4_1  = 3
    Q8_0  = 8
    Q8_1  = 9

DTYPE_MAP = {
    "f32":  GGMLType.F32,
    "f16":  GGMLType.F16,
    "q8_0": GGMLType.Q8_0,
    "q4_0": GGMLType.Q4_0,
    "q4_1": GGMLType.Q4_1,
}


# ---------------------------------------------------------------------------
# Quantization helpers
# ---------------------------------------------------------------------------

def quantize_q8_0(tensor: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Q8_0: 8-bit asymmetric quantization. Returns (quants, scales)."""
    flat = tensor.reshape(-1, 32)   # blocks of 32
    absmax = np.max(np.abs(flat), axis=1, keepdims=True)
    absmax = np.where(absmax == 0, 1.0, absmax)
    scales = absmax.astype(np.float16)
    quants = np.round(flat / absmax * 127).clip(-127, 127).astype(np.int8)
    return quants, scales


def quantize_q4_0(tensor: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Q4_0: 4-bit quantization, packed 2 values per byte."""
    flat = tensor.reshape(-1, 32)
    absmax = np.max(np.abs(flat), axis=1, keepdims=True)
    absmax = np.where(absmax == 0, 1.0, absmax)
    scales = absmax.astype(np.float16)
    # Quantize to [-7, 7]
    quants_f = np.round(flat / absmax * 7).clip(-7, 7).astype(np.int8) + 8  # shift to [1, 15]
    # Pack two 4-bit values per byte
    quants_packed = (quants_f[:, ::2] & 0xF) | ((quants_f[:, 1::2] & 0xF) << 4)
    return quants_packed.astype(np.uint8), scales


def to_numpy_dtype(dtype_str: str, tensor: np.ndarray) -> np.ndarray:
    """Convert tensor to target dtype (f32/f16 only; q8/q4 handled separately)."""
    if dtype_str == "f32":
        return tensor.astype(np.float32)
    if dtype_str == "f16":
        return tensor.astype(np.float16)
    return tensor.astype(np.float32)   # base for quantized (quantizer handles packing)


# ---------------------------------------------------------------------------
# GGUF binary writer
# ---------------------------------------------------------------------------

class GGUFWriter:
    """Writes a GGUF binary file incrementally."""

    def __init__(self, path: Path, architecture: str = "tokenless_lm"):
        self.path = path
        self.architecture = architecture
        self._metadata: list[tuple[str, Any, GGUFValueType]] = []
        self._tensors: list[tuple[str, np.ndarray, GGMLType]] = []

    def add_string(self, key: str, value: str):
        self._metadata.append((key, value, GGUFValueType.STRING))

    def add_uint32(self, key: str, value: int):
        self._metadata.append((key, int(value), GGUFValueType.UINT32))

    def add_uint64(self, key: str, value: int):
        self._metadata.append((key, int(value), GGUFValueType.UINT64))

    def add_float32(self, key: str, value: float):
        self._metadata.append((key, float(value), GGUFValueType.FLOAT32))

    def add_bool(self, key: str, value: bool):
        self._metadata.append((key, bool(value), GGUFValueType.BOOL))

    def add_array_uint32(self, key: str, values: list[int]):
        self._metadata.append((key, [int(v) for v in values], GGUFValueType.ARRAY))

    def add_tensor(self, name: str, data: np.ndarray, ggml_type: GGMLType = GGMLType.F32,
                   original_shape: "list[int] | None" = None):
        shape = original_shape if original_shape is not None else list(data.shape)
        self._tensors.append((name, shape, data, ggml_type))

    def _encode_string(self, s: str) -> bytes:
        encoded = s.encode("utf-8")
        return struct.pack("<Q", len(encoded)) + encoded

    def _encode_value(self, value: Any, vtype: GGUFValueType) -> bytes:
        if vtype == GGUFValueType.STRING:
            return self._encode_string(str(value))
        if vtype == GGUFValueType.UINT32:
            return struct.pack("<I", int(value))
        if vtype == GGUFValueType.UINT64:
            return struct.pack("<Q", int(value))
        if vtype == GGUFValueType.INT32:
            return struct.pack("<i", int(value))
        if vtype == GGUFValueType.FLOAT32:
            return struct.pack("<f", float(value))
        if vtype == GGUFValueType.BOOL:
            return struct.pack("<B", int(bool(value)))
        if vtype == GGUFValueType.ARRAY:
            items = value
            item_type = GGUFValueType.UINT32
            out = struct.pack("<I", int(item_type))
            out += struct.pack("<Q", len(items))
            for item in items:
                out += self._encode_value(item, item_type)
            return out
        raise ValueError(f"Unsupported value type: {vtype}")

    def write(self) -> int:
        """Write the GGUF file. Returns total bytes written."""
        with self.path.open("wb") as f:
            # Header
            f.write(GGUF_MAGIC)
            f.write(struct.pack("<I", GGUF_VERSION))
            f.write(struct.pack("<Q", len(self._tensors)))
            f.write(struct.pack("<Q", len(self._metadata)))

            # Metadata key-value pairs
            for key, value, vtype in self._metadata:
                f.write(self._encode_string(key))
                f.write(struct.pack("<I", int(vtype)))
                f.write(self._encode_value(value, vtype))

            # Tensor info (name, n_dims, dims, type, offset)
            # First pass: compute offsets using stored original shape and quantized data size
            offset = 0
            tensor_infos = []
            for name, original_shape, data, ggml_type in self._tensors:
                info = (name, original_shape, ggml_type, offset)
                tensor_infos.append(info)
                offset += data.nbytes

            for name, dims, ggml_type, toffset in tensor_infos:
                f.write(self._encode_string(name))
                f.write(struct.pack("<I", len(dims)))
                for d in dims:
                    f.write(struct.pack("<Q", d))
                f.write(struct.pack("<I", int(ggml_type)))
                f.write(struct.pack("<Q", toffset))

            # Alignment padding (GGUF spec requires 32-byte alignment before tensor data)
            current_pos = f.tell()
            alignment = 32
            padding = (alignment - (current_pos % alignment)) % alignment
            f.write(b"\x00" * padding)

            # Tensor data
            for name, original_shape, data, ggml_type in self._tensors:
                f.write(data.tobytes())

            return f.tell()


# ---------------------------------------------------------------------------
# Model loader
# ---------------------------------------------------------------------------

def load_export_bundle(bundle_dir: Path) -> tuple[dict, dict[str, np.ndarray]]:
    """
    Load config and weights from an export bundle directory.
    Supports both direct .npz and manifest-referenced files.
    """
    # Try to load config
    config: dict = {}
    for config_name in ("config.json", "model_config.json", "manifest.json"):
        cfg_path = bundle_dir / config_name
        if cfg_path.exists():
            raw = json.loads(cfg_path.read_text())
            # Flatten nested manifest into flat config
            config = raw.get("model_config", raw.get("config", raw))
            break

    # Default config if not found (TokenlessLM defaults)
    defaults = {
        "vocab_size": 16000,
        "n_layers": 6,
        "n_heads": 6,
        "d_model": 384,
        "d_ffn": 1536,
        "max_seq_len": 512,
        "rope_base": 10000.0,
        "tie_embeddings": True,
        "rms_eps": 1e-5,
    }
    for k, v in defaults.items():
        config.setdefault(k, v)

    # Load weights
    weights: dict[str, np.ndarray] = {}
    for weights_name in ("weights.npz", "model.npz", "checkpoint.npz"):
        wpath = bundle_dir / weights_name
        if wpath.exists():
            weights = dict(np.load(str(wpath)))
            break

    if not weights:
        # Try any .npz in the directory
        npz_files = list(bundle_dir.glob("*.npz"))
        if npz_files:
            weights = dict(np.load(str(npz_files[0])))

    return config, weights


def map_weights_to_gguf(
    weights: dict[str, np.ndarray],
    config: dict,
    dtype_str: str,
) -> list[tuple[str, np.ndarray, GGMLType]]:
    """
    Map TokenlessLM weight keys to GGUF tensor names.

    TokenlessLM uses these key patterns (from mlx):
      embed.weight                        → token_embd.weight
      blocks.N.norm1.weight               → blk.N.attn_norm.weight
      blocks.N.attn.q.weight              → blk.N.attn_q.weight
      blocks.N.attn.k.weight              → blk.N.attn_k.weight
      blocks.N.attn.v.weight              → blk.N.attn_v.weight
      blocks.N.attn.o.weight              → blk.N.attn_output.weight
      blocks.N.norm2.weight               → blk.N.ffn_norm.weight
      blocks.N.mlp.gate.weight            → blk.N.ffn_gate.weight
      blocks.N.mlp.up.weight              → blk.N.ffn_up.weight
      blocks.N.mlp.down.weight            → blk.N.ffn_down.weight
      norm_final.weight                   → output_norm.weight
    """
    ggml_type_default = DTYPE_MAP.get(dtype_str, GGMLType.F32)

    mapping = {
        "embed.weight": "token_emb.weight",
        "norm_final.weight": "output_norm.weight",
    }
    n_layers = config.get("n_layers", 6)
    for i in range(n_layers):
        prefix = f"blocks.{i}"
        blk = f"blk.{i}"
        mapping.update({
            f"{prefix}.norm1.weight":     f"{blk}.attn_norm.weight",
            f"{prefix}.attn.q.weight":    f"{blk}.attn_q.weight",
            f"{prefix}.attn.k.weight":    f"{blk}.attn_k.weight",
            f"{prefix}.attn.v.weight":    f"{blk}.attn_v.weight",
            f"{prefix}.attn.o.weight":    f"{blk}.attn_output.weight",
            f"{prefix}.norm2.weight":     f"{blk}.ffn_norm.weight",
            f"{prefix}.mlp.gate.weight":  f"{blk}.ffn_gate.weight",
            f"{prefix}.mlp.up.weight":    f"{blk}.ffn_up.weight",
            f"{prefix}.mlp.down.weight":  f"{blk}.ffn_down.weight",
        })

    tensors = []
    unmapped = []

    for src_key, data in weights.items():
        gguf_name = mapping.get(src_key)
        if gguf_name is None:
            unmapped.append(src_key)
            continue

        arr = data.astype(np.float32)
        original_shape = list(arr.shape)

        # 1-D tensors (RMSNorm scales) and the embedding/output-norm tables must remain
        # F32 — the xmind loader reads them via the GGML_TYPE_F32 branch and leaves
        # those slots NULL for any other type (weights_loader.c lines 290-298, 320-322,
        # 413-416, 606-610).  Only attention/FFN weight matrices (2-D, not embedding/norm)
        # are eligible for quantization.
        _F32_NAMES = frozenset(("token_emb.weight", "output_norm.weight"))
        force_f32 = arr.ndim != 2 or gguf_name in _F32_NAMES
        ggml_type = GGMLType.F32 if force_f32 else ggml_type_default

        if force_f32 or dtype_str == "f32":
            pass  # keep as float32
        elif dtype_str == "f16":
            arr = arr.astype(np.float16)
        elif dtype_str == "q4_0":
            arr_flat = arr.flatten()
            pad = (32 - arr_flat.size % 32) % 32
            if pad:
                arr_flat = np.pad(arr_flat, (0, pad))
            quants_packed, scales = quantize_q4_0(arr_flat)
            # Q4_0 block layout: [2-byte f16 scale][16-byte packed nibbles] = 18 bytes/block
            n_blocks = quants_packed.shape[0]
            scales_bytes = scales.astype(np.float16).view(np.uint8).reshape(n_blocks, 2)
            arr = np.concatenate([scales_bytes, quants_packed], axis=1).reshape(-1)
        elif dtype_str == "q8_0":
            arr_flat = arr.flatten()
            pad = (32 - arr_flat.size % 32) % 32
            if pad:
                arr_flat = np.pad(arr_flat, (0, pad))
            quants, scales = quantize_q8_0(arr_flat)
            # Q8_0 block layout: [2-byte f16 scale][32-byte int8 quants] = 34 bytes/block
            n_blocks = quants.shape[0]
            scales_bytes = scales.astype(np.float16).view(np.uint8).reshape(n_blocks, 2)
            quants_bytes = quants.view(np.uint8)
            arr = np.concatenate([scales_bytes, quants_bytes], axis=1).reshape(-1)

        tensors.append((gguf_name, arr, ggml_type, original_shape))

    if unmapped:
        print(f"  [WARN] {len(unmapped)} unmapped keys: {unmapped[:5]}")

    return tensors


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------

def convert(args: argparse.Namespace) -> int:
    bundle_dir = Path(args.input).expanduser()
    if not bundle_dir.is_absolute():
        bundle_dir = ML_TRAINING / bundle_dir

    if not bundle_dir.exists():
        print(f"[ERROR] Bundle not found: {bundle_dir}", file=sys.stderr)
        return 2

    output_path = Path(args.output).expanduser()
    if not output_path.is_absolute():
        output_path = ML_TRAINING / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    dtype = args.dtype.lower()
    if dtype not in DTYPE_MAP:
        print(f"[ERROR] Unknown dtype '{dtype}'. Choose: {list(DTYPE_MAP.keys())}", file=sys.stderr)
        return 2

    print(f"[INFO] Bundle   : {bundle_dir}")
    print(f"[INFO] Output   : {output_path}")
    print(f"[INFO] Dtype    : {dtype}")

    # Load bundle
    config, weights = load_export_bundle(bundle_dir)
    print(f"[INFO] Config   : vocab={config['vocab_size']}  layers={config['n_layers']}  "
          f"d_model={config['d_model']}  heads={config['n_heads']}")
    print(f"[INFO] Weights  : {len(weights)} tensors loaded")

    if not weights:
        print("[WARN] No weights found in bundle. Output GGUF will have metadata only.")

    if args.dry_run:
        print("[DRY RUN] No file written.")
        return 0

    # Build GGUF
    writer = GGUFWriter(output_path, architecture="tokenless_lm")

    # Required GGUF metadata (llama.cpp / Ollama compatible keys)
    writer.add_string("general.architecture", "tokenless_lm")
    writer.add_string("general.name", bundle_dir.name)
    writer.add_uint32("general.file_type", int(DTYPE_MAP[dtype]))
    writer.add_string("general.description",
                      "TokenlessLM — custom decoder-only transformer trained on KJV+Apocrypha corpus")

    # Model hyperparameters (llama.cpp style keys)
    writer.add_uint32("tokenless_lm.context_length",  int(config["max_seq_len"]))
    writer.add_uint32("tokenless_lm.embedding_length", int(config["d_model"]))
    writer.add_uint32("tokenless_lm.block_count",     int(config["n_layers"]))
    writer.add_uint32("tokenless_lm.feed_forward_length", int(config["d_ffn"]))
    writer.add_uint32("tokenless_lm.attention.head_count", int(config["n_heads"]))
    writer.add_uint32("tokenless_lm.attention.head_count_kv", int(config["n_heads"]))
    writer.add_float32("tokenless_lm.attention.layer_norm_rms_epsilon", float(config["rms_eps"]))
    writer.add_float32("tokenless_lm.rope.freq_base", float(config.get("rope_base", 10000.0)))
    writer.add_uint32("tokenless_lm.vocab_size", int(config["vocab_size"]))

    # Tokenizer metadata
    writer.add_string("tokenizer.model", "byte_level")
    writer.add_string("tokenizer.description",
                      "UTF-8 byte-level tokenizer. Token ID = byte value + 3 (ids 3..258; 0/1/2 = pad/bos/eos).")

    # Tensors
    tensor_records = map_weights_to_gguf(weights, config, dtype)
    total_params = 0
    for name, arr, ggml_type, original_shape in tensor_records:
        writer.add_tensor(name, arr, ggml_type, original_shape)
        total_params += int(np.prod(original_shape))
        print(f"  + {name:<45}  {original_shape}  {arr.dtype}")

    print(f"\n[INFO] Writing GGUF  ({len(tensor_records)} tensors, ~{total_params:,} params)...")
    bytes_written = writer.write()

    # Sidecar JSON
    sidecar = {
        "source_bundle": str(bundle_dir),
        "gguf_path": str(output_path),
        "dtype": dtype,
        "config": config,
        "tensor_count": len(tensor_records),
        "total_params": total_params,
        "file_size_mb": round(bytes_written / (1024 * 1024), 2),
    }
    sidecar_path = output_path.with_suffix(".gguf.json")
    sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")

    print(f"[SUCCESS] {output_path.name}  ({bytes_written / (1024*1024):.1f} MB)")
    print(f"[INFO] Sidecar: {sidecar_path.name}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Convert a TokenlessLM export bundle to GGUF format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--input", required=True,
                   help="Path to export bundle directory (e.g. exports/kjv_byte_v1_20m)")
    p.add_argument("--output", required=True,
                   help="Output .gguf file path (e.g. gguf/kjv_tokenless.gguf)")
    p.add_argument("--dtype", default="f16",
                   choices=list(DTYPE_MAP.keys()),
                   help="Target dtype / quantization (default: f16)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print plan without writing output")
    return convert(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
