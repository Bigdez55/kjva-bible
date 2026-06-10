#!/usr/bin/env python3
"""safetensors_to_gguf.py — convert raw safetensors + config + vocab into a
GGUF file that loads through XMIND's tokenless_lm interpreter (slot 1).

Sibling to convert_to_gguf.py. Used when the source weights are stored as
raw safetensors (e.g. the kjva-bible KJVA base) rather than as an exported
TokenlessLM bundle (config.json + weights.npz).

Reuses GGUFWriter / GGMLType / DTYPE_MAP from convert_to_gguf.py.

Tensor naming convention written here matches what
ai/xmind/src/interp_tokenless.c expects (per UNIFIED_MASTER_TECH_PACK.md
Part II §25.2):
  embed.weight              -> token_emb.weight
  norm_final.weight         -> output_norm.weight
  blocks.N.attn.q.weight    -> blk.N.attn_q.weight
  blocks.N.attn.k.weight    -> blk.N.attn_k.weight
  blocks.N.attn.v.weight    -> blk.N.attn_v.weight
  blocks.N.attn.o.weight    -> blk.N.attn_output.weight
  blocks.N.norm1.weight     -> blk.N.attn_norm.weight
  blocks.N.mlp.gate.weight  -> blk.N.ffn_gate.weight
  blocks.N.mlp.up.weight    -> blk.N.ffn_up.weight
  blocks.N.mlp.down.weight  -> blk.N.ffn_down.weight
  blocks.N.norm2.weight     -> blk.N.ffn_norm.weight
(tied embeddings — no output.weight.)

Usage:
  python3 safetensors_to_gguf.py \\
      --weights ../../../kjva-bible/KJVA/training/weights.safetensors \\
      --config  ../../../kjva-bible/KJVA/training/model_config.json \\
      --vocab   ../../../kjva-bible/KJVA/training/byte_vocab.json \\
      --output  gguf/model.gguf \\
      --dtype   f32
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from convert_to_gguf import GGUFWriter, GGMLType, DTYPE_MAP, quantize_q4_0


# XMIND model struct (ai/xmind/include/xmind.h §9) stores attention and FFN
# weight matrices as Q4_0 block pointers — there are no F32 slots for them.
# Norms + embedding stay F32. These are the role names that must be Q4_0
# in the GGUF for the loader's wl_allocate_from_plan to wire them up.
Q4_ROLES_GGUF_NAMES = (
    "attn_q.weight", "attn_k.weight", "attn_v.weight", "attn_output.weight",
    "ffn_gate.weight", "ffn_down.weight", "ffn_up.weight",
)


class _Q4ShapedBytes(np.ndarray):
    """uint8 ndarray that keeps a logical tensor shape for GGUF metadata
    but emits raw block-packed Q4_0 bytes when serialized via tobytes().

    Used by the writer hook patched onto GGUFWriter (see _patch_writer).
    """
    def __new__(cls, input_array):
        return np.asarray(input_array).view(cls)

    def __array_finalize__(self, obj):
        if obj is None:
            return
        self._q4_raw_bytes = getattr(obj, "_q4_raw_bytes", None)


# Patch GGUFWriter to honor _Q4ShapedBytes._q4_raw_bytes when serializing
# tensor data. Original write() loops the tensor list and calls data.tobytes().
# For Q4_0 tensors with our sidecar bytes, we emit those instead.
_original_write = GGUFWriter.write


def _patched_write(self) -> int:
    import struct as _struct
    GGUF_MAGIC = b"GGUF"
    GGUF_VERSION = 3

    with self.path.open("wb") as f:
        f.write(GGUF_MAGIC)
        f.write(_struct.pack("<I", GGUF_VERSION))
        f.write(_struct.pack("<Q", len(self._tensors)))
        f.write(_struct.pack("<Q", len(self._metadata)))

        for key, value, vtype in self._metadata:
            f.write(self._encode_string(key))
            f.write(_struct.pack("<I", int(vtype)))
            f.write(self._encode_value(value, vtype))

        # First pass: compute offsets (using REAL byte size, not data.nbytes
        # which reflects the uint8 carrier shape for Q4_0 tensors).
        offset = 0
        tensor_infos = []
        for name, data, ggml_type in self._tensors:
            dims = list(data.shape)
            raw_bytes = getattr(data, "_q4_raw_bytes", None)
            if raw_bytes is not None:
                nbytes = len(raw_bytes)
            else:
                nbytes = data.nbytes
            tensor_infos.append((name, dims, ggml_type, offset, nbytes))
            offset += nbytes

        for name, dims, ggml_type, toffset, _nb in tensor_infos:
            f.write(self._encode_string(name))
            f.write(_struct.pack("<I", len(dims)))
            for d in dims:
                f.write(_struct.pack("<Q", d))
            f.write(_struct.pack("<I", int(ggml_type)))
            f.write(_struct.pack("<Q", toffset))

        # 32-byte alignment before tensor data
        current_pos = f.tell()
        alignment = 32
        padding = (alignment - (current_pos % alignment)) % alignment
        f.write(b"\x00" * padding)

        for name, data, ggml_type in self._tensors:
            raw_bytes = getattr(data, "_q4_raw_bytes", None)
            if raw_bytes is not None:
                f.write(raw_bytes)
            else:
                f.write(data.tobytes())

        return f.tell()


GGUFWriter.write = _patched_write  # type: ignore[assignment]


def load_safetensors(path: Path) -> dict[str, np.ndarray]:
    """Minimal safetensors loader — no external dependency required."""
    with path.open("rb") as f:
        header_len = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(header_len).decode("utf-8"))
        data_start = 8 + header_len

        np_dtype_map = {
            "F32":  np.float32,
            "F16":  np.float16,
            "BF16": np.uint16,
            "I32":  np.int32,
            "I64":  np.int64,
            "U8":   np.uint8,
            "I8":   np.int8,
        }

        tensors: dict[str, np.ndarray] = {}
        for name, meta in header.items():
            if name == "__metadata__":
                continue
            dtype = meta["dtype"]
            shape = meta["shape"]
            offset_start, offset_end = meta["data_offsets"]
            f.seek(data_start + offset_start)
            raw = f.read(offset_end - offset_start)
            np_dtype = np_dtype_map[dtype]
            arr = np.frombuffer(raw, dtype=np_dtype).reshape(shape).copy()
            if dtype == "BF16":
                # BF16 is the high 16 bits of an IEEE-754 F32 word.
                # Promote to F32 by shifting into the upper half of a uint32
                # and reinterpreting the bit pattern.
                arr = (arr.astype(np.uint32) << 16).view(np.float32)
            tensors[name] = arr
        return tensors


def build_name_mapping(n_layers: int) -> dict[str, str]:
    """mlx-style safetensors keys -> GGUF tensor names expected by
    ai/xmind/src/interp_tokenless.c map_tensor()."""
    mapping = {
        "embed.weight":      "token_emb.weight",
        "norm_final.weight": "output_norm.weight",
    }
    for i in range(n_layers):
        src = f"blocks.{i}"
        dst = f"blk.{i}"
        mapping.update({
            f"{src}.norm1.weight":    f"{dst}.attn_norm.weight",
            f"{src}.attn.q.weight":   f"{dst}.attn_q.weight",
            f"{src}.attn.k.weight":   f"{dst}.attn_k.weight",
            f"{src}.attn.v.weight":   f"{dst}.attn_v.weight",
            f"{src}.attn.o.weight":   f"{dst}.attn_output.weight",
            f"{src}.norm2.weight":    f"{dst}.ffn_norm.weight",
            f"{src}.mlp.gate.weight": f"{dst}.ffn_gate.weight",
            f"{src}.mlp.up.weight":   f"{dst}.ffn_up.weight",
            f"{src}.mlp.down.weight": f"{dst}.ffn_down.weight",
        })
    return mapping


def permute_rope_qk(arr: np.ndarray, gguf_name: str,
                    n_heads: int, n_kv_heads: int) -> np.ndarray:
    """Reorder attn_q / attn_k output rows so the GGML interleaved-RoPE kernel
    (xmind_rope: pairs (2i, 2i+1)) reproduces the trainer's ROTATE-HALF RoPE
    (pt/model.py: pairs (i, i+head_dim/2)).

    This is the standard llama.cpp HF->GGUF permute. WITHOUT it, the XMIND C
    engine rotates the wrong dimension pairs and silently corrupts attention
    (proven: pt argmax '.', xmind argmax 'a', logit MAE 1.68). See docs/INFERENCE_CORRECTNESS_NOTE.md.
    The matching un-permute lives in pt/eval_clean_ppl.py's GGUF reverse-loader.
    """
    if gguf_name.endswith("attn_q.weight"):
        nh = n_heads
    elif gguf_name.endswith("attn_k.weight"):
        nh = n_kv_heads
    else:
        return arr
    out, in_ = arr.shape                                  # [n_head*head_dim, d_model]
    head_dim = out // nh
    return (arr.reshape(nh, 2, head_dim // 2, in_)
               .swapaxes(1, 2)
               .reshape(out, in_))


def to_target_dtype(arr: np.ndarray, dtype: str,
                     gguf_name: str = "") -> tuple[np.ndarray, GGMLType]:
    """Pick the storage dtype for a tensor.

    The XMIND model struct holds attention and FFN matrices ONLY in
    Q4_0-blocked form (ai/xmind/include/xmind.h §9). Norms and the token
    embedding live in F32. So:
      - role is one of Q4_ROLES_GGUF_NAMES → always Q4_0 (regardless of CLI dtype)
      - otherwise → CLI dtype (f32 or f16; quantized CLI choices fall back to f32)
    The Q4_0 path quantizes via convert_to_gguf.quantize_q4_0 and serializes
    the (quants_packed || scales_fp16) layout that XMIND's loader expects
    via the GGUF Q4_0 block format.
    """
    is_q4_role = any(gguf_name.endswith(r) for r in Q4_ROLES_GGUF_NAMES)
    if is_q4_role:
        # Quantize into Q4_0 blocks (32 elements per block).
        # GGUF Q4_0 layout (per block, 18 bytes):
        #   [fp16 scale (2 bytes) | 16 bytes of packed quants (32 × 4-bit)]
        # GGUF tensor SHAPE must remain the original logical shape so the
        # XMIND loader's wl_allocate_from_plan can compute
        # n_blocks = n_elements / 32 correctly (weights_loader.c §S7).
        flat = arr.astype(np.float32).reshape(-1)
        if flat.size % 32 != 0:
            raise ValueError(
                f"Q4_0 needs element count divisible by 32; got {flat.size} for {gguf_name}")
        quants_packed, scales = quantize_q4_0(flat)
        n_blocks = scales.shape[0]
        packed = np.empty((n_blocks, 18), dtype=np.uint8)
        packed[:, 0:2]  = scales.view(np.uint8).reshape(n_blocks, 2)
        packed[:, 2:18] = quants_packed.reshape(n_blocks, 16)
        # Build a uint8 ndarray with the LOGICAL shape (for GGUF metadata)
        # and attach the raw packed bytes via a sidecar attribute that the
        # writer hook (_emit_q4_bytes) reads to emit the right payload.
        shaped = _Q4ShapedBytes(np.zeros(arr.shape, dtype=np.uint8))
        shaped._q4_raw_bytes = packed.tobytes()
        return shaped, GGMLType.Q4_0
    if dtype == "f32":
        return arr.astype(np.float32), GGMLType.F32
    if dtype == "f16":
        return arr.astype(np.float16), GGMLType.F16
    return arr.astype(np.float32), GGMLType.F32


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--weights", required=True, type=Path)
    p.add_argument("--config",  required=True, type=Path)
    p.add_argument("--vocab",   required=True, type=Path)
    p.add_argument("--output",  required=True, type=Path)
    p.add_argument("--dtype",   default="f32", choices=list(DTYPE_MAP.keys()))
    p.add_argument("--name",    default=None,
                   help="model identity stamped into general.name (default: weights stem). "
                        "This is how a NEUTRAL base becomes a NAMED domain model at derive time.")
    p.add_argument("--domain",  default=None,
                   help="optional domain tag stamped into general.domain (e.g. healthcare, transit)")
    args = p.parse_args()

    for required in (args.weights, args.config, args.vocab):
        if not required.exists():
            print(f"[ERROR] not found: {required}", file=sys.stderr)
            return 2

    print(f"[INFO] weights : {args.weights}")
    print(f"[INFO] config  : {args.config}")
    print(f"[INFO] vocab   : {args.vocab}")
    print(f"[INFO] output  : {args.output}")
    print(f"[INFO] dtype   : {args.dtype}")

    weights = load_safetensors(args.weights)
    cfg = json.loads(args.config.read_text())
    vocab = json.loads(args.vocab.read_text())

    # Reconcile config keys (kjva-bible uses {n_layers,n_heads,d_model,d_ffn,
    # max_seq_len,rope_base,tie_embeddings,rms_eps,vocab_size}).
    cfg.setdefault("vocab_size",  vocab.get("vocab_size", 259))
    cfg.setdefault("max_seq_len", 1024)
    cfg.setdefault("rms_eps",     1e-5)
    cfg.setdefault("d_ffn",       cfg.get("ffn_dim", 1536))
    cfg.setdefault("d_model",     cfg.get("hidden_dim", 384))
    cfg.setdefault("n_heads",     6)
    cfg.setdefault("n_layers",    8)
    cfg.setdefault("rope_base",   10000.0)
    cfg.setdefault("tie_embeddings", True)

    print(f"[INFO] config  : vocab={cfg['vocab_size']} layers={cfg['n_layers']} "
          f"heads={cfg['n_heads']} d_model={cfg['d_model']} d_ffn={cfg['d_ffn']} "
          f"ctx={cfg['max_seq_len']} rope={cfg['rope_base']}")
    print(f"[INFO] vocab   : kind={vocab.get('kind')} byte_offset={vocab.get('byte_offset')} "
          f"PAD={vocab.get('pad_id')} BOS={vocab.get('bos_id')} EOS={vocab.get('eos_id')}")
    print(f"[INFO] tensors : {len(weights)} loaded from safetensors")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    writer = GGUFWriter(args.output, architecture="tokenless_lm")

    # General metadata
    model_name = args.name if args.name else args.weights.stem
    writer.add_string("general.architecture", "tokenless_lm")
    writer.add_string("general.name",         model_name)
    if args.domain:
        writer.add_string("general.domain",   args.domain)
    writer.add_uint32("general.file_type",    int(DTYPE_MAP[args.dtype]))
    writer.add_string("general.description",
                      "TokenlessLM byte-level decoder-only transformer "
                      "(UNIFIED_MASTER_TECH_PACK.md Part II §25.2)")

    # Model hyperparameters — keys consumed by interp_tokenless.c
    writer.add_uint32("tokenless_lm.context_length",       int(cfg["max_seq_len"]))
    writer.add_uint32("tokenless_lm.embedding_length",     int(cfg["d_model"]))
    writer.add_uint32("tokenless_lm.block_count",          int(cfg["n_layers"]))
    writer.add_uint32("tokenless_lm.feed_forward_length",  int(cfg["d_ffn"]))
    writer.add_uint32("tokenless_lm.attention.head_count", int(cfg["n_heads"]))
    writer.add_uint32("tokenless_lm.attention.head_count_kv",
                      int(cfg.get("n_kv_heads", cfg["n_heads"])))
    writer.add_float32("tokenless_lm.attention.layer_norm_rms_epsilon",
                       float(cfg["rms_eps"]))
    writer.add_float32("tokenless_lm.rope.freq_base", float(cfg["rope_base"]))
    writer.add_uint32("tokenless_lm.vocab_size", int(cfg["vocab_size"]))

    # Tokenizer metadata (per master spec — token = byte + 3, vocab 259)
    writer.add_string("tokenizer.model", "byte_level")
    writer.add_string("tokenizer.description",
                      "UTF-8 byte-level (token = byte + 3, vocab 259, "
                      "PAD=0 BOS=1 EOS=2 per UNIFIED_MASTER_TECH_PACK.md Part II §25.6)")
    writer.add_uint32("tokenizer.ggml.bos_token_id", int(vocab.get("bos_id", 1)))
    writer.add_uint32("tokenizer.ggml.eos_token_id", int(vocab.get("eos_id", 2)))

    # Tensors
    name_map = build_name_mapping(int(cfg["n_layers"]))
    mapped: list[tuple[str, np.ndarray, GGMLType]] = []
    unmapped: list[str] = []
    total_params = 0
    for src_key, arr in weights.items():
        gguf_name = name_map.get(src_key)
        if gguf_name is None:
            unmapped.append(src_key)
            continue
        # inference-correctness fix: weights stay CANONICAL (no llama-style q/k permute). The XMIND
        # engine uses the tokenless rotate-half RoPE convention directly (matches
        # training/pt/model.py). XMIND is tokenless-only — it does NOT conform to
        # the llama interleaved convention.
        out_arr, ggml_type = to_target_dtype(arr, args.dtype, gguf_name)
        mapped.append((gguf_name, out_arr, ggml_type))
        # Track logical params (pre-quantization element count from the
        # source tensor) so the report matches the architectural param count.
        total_params += int(np.prod(arr.shape))

    if unmapped:
        print(f"[WARN] {len(unmapped)} unmapped tensor(s): {unmapped[:5]}")

    for name, arr, ggml_type in mapped:
        writer.add_tensor(name, arr, ggml_type)
        print(f"  + {name:<35} {str(list(arr.shape)):<14} {arr.dtype}")

    print(f"\n[INFO] writing {args.output} ({len(mapped)} tensors, "
          f"~{total_params:,} params)...")
    bytes_written = writer.write()

    # Sidecar JSON
    sidecar = {
        "model_name":      model_name,
        "domain":          args.domain,
        "source_weights":  str(args.weights),
        "source_config":   str(args.config),
        "source_vocab":    str(args.vocab),
        "gguf_path":       str(args.output),
        "dtype":           args.dtype,
        "config":          cfg,
        "vocab":           vocab,
        "tensor_count":    len(mapped),
        "total_params":    total_params,
        "file_size_mb":    round(bytes_written / (1024 * 1024), 2),
        "interpreter_slot": 1,
        "interpreter_family": "tokenless_lm",
        "ref": "UNIFIED_MASTER_TECH_PACK.md Part II §25.2/§25.6",
    }
    sidecar_path = args.output.with_suffix(".gguf.json")
    sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")

    print(f"[SUCCESS] {args.output.name} "
          f"({bytes_written / (1024*1024):.1f} MB, {len(mapped)} tensors)")
    print(f"[INFO] sidecar: {sidecar_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
