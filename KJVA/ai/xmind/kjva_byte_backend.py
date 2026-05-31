"""XMIND host bridge for the current KJVA byte-level weights.

This module makes ``ai/xmind`` the active serving boundary for the KJVA Bible
app without importing MLX.  The freestanding C runtime remains the lower-level
contract, and this host bridge mirrors its requirements:

* byte-token semantics: PAD=0, BOS=1, EOS=2, byte b -> b+3, vocab=259
* safetensors layout validation before serving
* embeddings and RMSNorm weights kept as float32
* projection matrices materialized through XMIND Q4_0 blocks
* negative pre/per-token/post hook return codes halt generation

No training code lives here.  This is a runtime materialization bridge.
"""
from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

PAD_ID = 0
BOS_ID = 1
EOS_ID = 2
BYTE_OFFSET = 3

EXPECTED_CONFIG = {
    "vocab_size": 259,
    "n_layers": 8,
    "n_heads": 6,
    "d_model": 384,
    "d_ffn": 1536,
    "max_seq_len": 1024,
}

_F32_TENSORS = {
    "embed.weight": (259, 384),
    "norm_final.weight": (384,),
}

_PROJECTION_TEMPLATES = {
    "blocks.{i}.attn.q.weight": (384, 384),
    "blocks.{i}.attn.k.weight": (384, 384),
    "blocks.{i}.attn.v.weight": (384, 384),
    "blocks.{i}.attn.o.weight": (384, 384),
    "blocks.{i}.mlp.gate.weight": (1536, 384),
    "blocks.{i}.mlp.up.weight": (1536, 384),
    "blocks.{i}.mlp.down.weight": (384, 1536),
}

_NORM_TEMPLATES = {
    "blocks.{i}.norm1.weight": (384,),
    "blocks.{i}.norm2.weight": (384,),
}


class XmindBackendError(RuntimeError):
    """Raised when the XMIND host bridge cannot serve a request."""


class XmindPolicyHalt(XmindBackendError):
    """Raised when a pre/per-token/post XMIND hook requests a halt."""


def _import_numpy() -> Any:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise XmindBackendError(
            "XMIND host backend requires numpy for active byte-weight serving."
        ) from exc
    return np


def encode_bytes(text: str) -> list[int]:
    return [BOS_ID] + [b + BYTE_OFFSET for b in text.encode("utf-8")]


def decode_bytes(token_ids: list[int]) -> str:
    raw = bytes(
        token_id - BYTE_OFFSET
        for token_id in token_ids
        if token_id not in (PAD_ID, BOS_ID, EOS_ID) and token_id >= BYTE_OFFSET
    )
    return raw.decode("utf-8", errors="replace")


class _SafeTensorIndex:
    """Minimal safetensors reader for float32 runtime weights."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.header: Dict[str, Dict[str, Any]] = {}
        self.data_start = 0
        self._load_header()

    def _load_header(self) -> None:
        with self.path.open("rb") as f:
            raw_len = f.read(8)
            if len(raw_len) != 8:
                raise XmindBackendError("Invalid safetensors file: missing header length")
            header_len = struct.unpack("<Q", raw_len)[0]
            header_bytes = f.read(header_len)
            if len(header_bytes) != header_len:
                raise XmindBackendError("Invalid safetensors file: truncated header")
        header = json.loads(header_bytes.decode("utf-8"))
        header.pop("__metadata__", None)
        self.header = header
        self.data_start = 8 + int(header_len)

    def validate(self) -> None:
        expected: Dict[str, tuple[int, ...]] = dict(_F32_TENSORS)
        for layer in range(EXPECTED_CONFIG["n_layers"]):
            for template, shape in _PROJECTION_TEMPLATES.items():
                expected[template.format(i=layer)] = shape
            for template, shape in _NORM_TEMPLATES.items():
                expected[template.format(i=layer)] = shape

        missing = sorted(set(expected) - set(self.header))
        if missing:
            raise XmindBackendError(f"KJVA safetensors missing keys: {missing[:8]}")

        bad = []
        for name, shape in expected.items():
            meta = self.header[name]
            if meta.get("dtype") != "F32":
                bad.append(f"{name}:dtype={meta.get('dtype')}")
            if tuple(meta.get("shape", ())) != tuple(shape):
                bad.append(f"{name}:shape={meta.get('shape')} expected={shape}")
        if bad:
            raise XmindBackendError(f"KJVA safetensors layout mismatch: {bad[:8]}")

    def load_f32(self, name: str, np: Any) -> Any:
        meta = self.header[name]
        begin, end = meta["data_offsets"]
        shape = tuple(meta["shape"])
        n_items = math.prod(shape)
        if end - begin != n_items * 4:
            raise XmindBackendError(f"Invalid F32 byte length for {name}")
        arr = np.memmap(
            self.path,
            dtype="<f4",
            mode="r",
            offset=self.data_start + begin,
            shape=shape,
        )
        return np.asarray(arr, dtype=np.float32).copy()


@dataclass
class _Q4Matrix:
    """Host representation of XMIND Q4_0 projection blocks."""

    shape: tuple[int, int]
    scales: Any
    packed: Any
    _dequantized: Any = None

    @classmethod
    def from_f32(cls, matrix: Any, np: Any) -> "_Q4Matrix":
        flat = np.asarray(matrix, dtype=np.float32).reshape(-1)
        remainder = flat.size % 32
        if remainder:
            flat = np.pad(flat, (0, 32 - remainder), mode="constant")
        blocks = flat.reshape(-1, 32)
        max_abs = np.max(np.abs(blocks), axis=1)
        scales = np.where(max_abs > 0.0, max_abs / 7.0, 1.0).astype(np.float32)
        q = np.rint(blocks / scales[:, None]).clip(-8, 7).astype(np.int8)
        nibbles = (q + 8).astype(np.uint8)
        packed = (nibbles[:, 0::2] | (nibbles[:, 1::2] << 4)).astype(np.uint8)
        return cls(tuple(matrix.shape), scales, packed)

    def dequantize(self, np: Any) -> Any:
        if self._dequantized is None:
            low = self.packed & 0x0F
            high = self.packed >> 4
            nibbles = np.empty((self.packed.shape[0], 32), dtype=np.uint8)
            nibbles[:, 0::2] = low
            nibbles[:, 1::2] = high
            values = (nibbles.astype(np.int16) - 8).astype(np.float32)
            values *= self.scales[:, None]
            self._dequantized = values.reshape(-1)[: math.prod(self.shape)].reshape(self.shape)
        return self._dequantized

    def matmul_transposed(self, x: Any, np: Any) -> Any:
        return x @ self.dequantize(np).T


class XmindKJVAInference:
    """Active XMIND backend for KJVA byte-level inference."""

    backend_name = "xmind-byte-host"

    def __init__(self, models_dir: Optional[Path] = None) -> None:
        self.models_dir = models_dir or Path(__file__).resolve().parents[2] / "training"
        self.weights_path = self.models_dir / "weights.safetensors"
        self.config_path = self.models_dir / "model_config.json"
        self._cfg: Dict[str, Any] = {}
        self._weights: Dict[str, Any] = {}
        self._loaded = False
        self._last_error = ""
        self._rng = None
        self.pre_inference_hook: Callable[[Dict[str, Any]], int] = lambda _ctx: 0
        self.per_token_hook: Callable[[Dict[str, Any]], int] = lambda _ctx: 0
        self.post_inference_hook: Callable[[Dict[str, Any]], int] = lambda _ctx: 0

    @property
    def last_error(self) -> str:
        return self._last_error

    def status(self) -> Dict[str, Any]:
        return {
            "backend": self.backend_name,
            "ready": self.is_ready(),
            "loaded": self._loaded,
            "weights_path": str(self.weights_path),
            "last_error": self._last_error,
            "byte_tokens": {
                "pad": PAD_ID,
                "bos": BOS_ID,
                "eos": EOS_ID,
                "byte_offset": BYTE_OFFSET,
            },
            "expected_config": dict(EXPECTED_CONFIG),
        }

    def is_ready(self) -> bool:
        try:
            self._validate_files()
            _import_numpy()
            _SafeTensorIndex(self.weights_path).validate()
            self._last_error = ""
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            return False

    def _validate_files(self) -> None:
        if not self.weights_path.exists():
            raise XmindBackendError(
                f"KJVA weights not found at {self.weights_path}. "
                "Place weights.safetensors at KJVA/training/weights.safetensors."
            )
        if not self.config_path.exists():
            raise XmindBackendError(f"KJVA model_config.json not found at {self.config_path}")
        with self.config_path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        mismatches = {
            key: (cfg.get(key), expected)
            for key, expected in EXPECTED_CONFIG.items()
            if cfg.get(key) != expected
        }
        if mismatches:
            raise XmindBackendError(f"KJVA config rejected by XMIND: {mismatches}")
        if cfg.get("tie_embeddings") is not True:
            raise XmindBackendError("KJVA config rejected by XMIND: tie_embeddings must be true")
        self._cfg = cfg

    def _load(self) -> None:
        if self._loaded:
            return
        np = _import_numpy()
        self._validate_files()
        index = _SafeTensorIndex(self.weights_path)
        index.validate()

        self._weights["embed.weight"] = index.load_f32("embed.weight", np)
        self._weights["norm_final.weight"] = index.load_f32("norm_final.weight", np)
        for layer in range(EXPECTED_CONFIG["n_layers"]):
            for template in _NORM_TEMPLATES:
                name = template.format(i=layer)
                self._weights[name] = index.load_f32(name, np)
            for template in _PROJECTION_TEMPLATES:
                name = template.format(i=layer)
                self._weights[name] = _Q4Matrix.from_f32(index.load_f32(name, np), np)

        self._rng = np.random.default_rng()
        self._loaded = True
        self._last_error = ""

    def complete(
        self,
        prompt: str,
        max_new_tokens: int = 200,
        temperature: float = 0.8,
        top_p: float = 0.9,
    ) -> str:
        token_ids = encode_bytes(prompt)
        generated = self.xmind_generate(
            token_ids,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        return decode_bytes(generated)

    def xmind_generate(
        self,
        prompt_tokens: list[int],
        max_new_tokens: int,
        temperature: float,
        top_p: float,
    ) -> list[int]:
        self._load()
        np = _import_numpy()

        pre_rc = self.pre_inference_hook({
            "prompt_len": len(prompt_tokens),
            "max_new_tokens": max_new_tokens,
            "backend": self.backend_name,
        })
        if pre_rc < 0:
            raise XmindPolicyHalt(f"XMIND pre_inference halted with rc={pre_rc}")

        max_ctx = int(self._cfg["max_seq_len"]) - max_new_tokens
        tokens = list(prompt_tokens[-max_ctx:]) if len(prompt_tokens) > max_ctx else list(prompt_tokens)
        generated: list[int] = []
        for step in range(max_new_tokens):
            logits = self._forward(np.asarray(tokens + generated, dtype=np.int64))[-1]
            hook_rc = self.per_token_hook({
                "step": step,
                "current_token": int((tokens + generated)[-1]),
                "logits": logits,
                "vocab_size": EXPECTED_CONFIG["vocab_size"],
                "backend": self.backend_name,
            })
            if hook_rc < 0:
                raise XmindPolicyHalt(f"XMIND per_token halted at step={step} rc={hook_rc}")
            next_token = self._sample(logits, temperature, top_p, np)
            if next_token == EOS_ID:
                break
            generated.append(next_token)

        post_rc = self.post_inference_hook({
            "generated_tokens": len(generated),
            "backend": self.backend_name,
        })
        if post_rc < 0:
            raise XmindPolicyHalt(f"XMIND post_inference halted with rc={post_rc}")
        return generated

    def _linear(self, x: Any, name: str, np: Any) -> Any:
        weight = self._weights[name]
        if isinstance(weight, _Q4Matrix):
            return weight.matmul_transposed(x, np)
        return x @ weight.T

    def _rms_norm(self, x: Any, weight: Any, np: Any) -> Any:
        eps = float(self._cfg.get("rms_eps", 1e-5))
        return x * (1.0 / np.sqrt(np.mean(x * x, axis=-1, keepdims=True) + eps)) * weight

    def _rope(self, x: Any, np: Any) -> Any:
        head_dim = EXPECTED_CONFIG["d_model"] // EXPECTED_CONFIG["n_heads"]
        inv = 1.0 / (
            float(self._cfg.get("rope_base", 10000.0))
            ** (np.arange(0, head_dim, 2, dtype=np.float32) / head_dim)
        )
        pos = np.arange(x.shape[0], dtype=np.float32)
        freqs = np.outer(pos, inv)
        emb = np.concatenate([freqs, freqs], axis=-1)
        cos = np.cos(emb)[:, None, :]
        sin = np.sin(emb)[:, None, :]
        d = x.shape[-1]
        rotated = np.concatenate([-x[..., d // 2 :], x[..., : d // 2]], axis=-1)
        return x * cos + rotated * sin

    def _softmax(self, x: Any, np: Any, axis: int = -1) -> Any:
        x = x - np.max(x, axis=axis, keepdims=True)
        exp = np.exp(x)
        return exp / np.sum(exp, axis=axis, keepdims=True)

    def _forward(self, tokens: Any) -> Any:
        np = _import_numpy()
        if tokens.size == 0:
            raise XmindBackendError("XMIND forward received no tokens")
        if int(tokens.max()) >= EXPECTED_CONFIG["vocab_size"] or int(tokens.min()) < 0:
            raise XmindBackendError("XMIND forward received token outside vocab 0..258")

        x = self._weights["embed.weight"][tokens].astype(np.float32)
        t = x.shape[0]
        d_model = EXPECTED_CONFIG["d_model"]
        n_heads = EXPECTED_CONFIG["n_heads"]
        head_dim = d_model // n_heads
        causal = np.triu(np.full((t, t), -1e9, dtype=np.float32), k=1)

        for layer in range(EXPECTED_CONFIG["n_layers"]):
            prefix = f"blocks.{layer}"
            h = self._rms_norm(x, self._weights[f"{prefix}.norm1.weight"], np)
            q = self._linear(h, f"{prefix}.attn.q.weight", np).reshape(t, n_heads, head_dim)
            k = self._linear(h, f"{prefix}.attn.k.weight", np).reshape(t, n_heads, head_dim)
            v = self._linear(h, f"{prefix}.attn.v.weight", np).reshape(t, n_heads, head_dim)
            q = self._rope(q, np).transpose(1, 0, 2)
            k = self._rope(k, np).transpose(1, 0, 2)
            v = v.transpose(1, 0, 2)
            scores = (q @ np.swapaxes(k, 1, 2)) / math.sqrt(float(head_dim))
            scores = scores + causal[None, :, :]
            attn = self._softmax(scores, np, axis=-1)
            out = (attn @ v).transpose(1, 0, 2).reshape(t, d_model)
            x = x + self._linear(out, f"{prefix}.attn.o.weight", np)

            h2 = self._rms_norm(x, self._weights[f"{prefix}.norm2.weight"], np)
            gate = self._linear(h2, f"{prefix}.mlp.gate.weight", np)
            up = self._linear(h2, f"{prefix}.mlp.up.weight", np)
            hidden = (gate / (1.0 + np.exp(-gate))) * up
            x = x + self._linear(hidden, f"{prefix}.mlp.down.weight", np)

        x = self._rms_norm(x, self._weights["norm_final.weight"], np)
        return x @ self._weights["embed.weight"].T

    def _sample(self, logits: Any, temperature: float, top_p: float, np: Any) -> int:
        if temperature <= 0.0:
            return int(np.argmax(logits))
        logits = logits / float(temperature)
        probs = self._softmax(logits, np, axis=-1)
        order = np.argsort(-probs)
        sorted_probs = probs[order]
        cdf = np.cumsum(sorted_probs)
        keep = (cdf - sorted_probs) < float(top_p)
        filtered = np.where(keep, sorted_probs, 0.0)
        total = float(np.sum(filtered))
        if total <= 0.0:
            return int(order[0])
        filtered = filtered / total
        return int(self._rng.choice(order, p=filtered))


_engine = XmindKJVAInference()


def get_engine() -> XmindKJVAInference:
    return _engine
