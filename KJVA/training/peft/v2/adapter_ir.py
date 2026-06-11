"""adapter_ir.py — canonical AdapterIR for the Omni-PEFT++ v2 layer (§11.1).

Framework-neutral: numpy payloads + stdlib only, so it imports and tests without
torch or mlx. Conversion to/from a live framework happens at explicit boundaries
(to_torch / from_torch / to_mlx / from_mlx — lazy import). This is the canonical,
hashable container that adapter_algebra, adapter_genome_v2, and determinism operate on.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np

SCHEMA_VERSION = "2.0"


@dataclass
class AdapterIR:
    family: str
    method: str
    target_module: str               # e.g. "attn.q" (relative to a block)
    layer_idx: int
    tensors: dict[str, np.ndarray] = field(default_factory=dict)
    hparams: dict[str, Any] = field(default_factory=dict)
    dtype: str = "float32"
    schema_version: str = SCHEMA_VERSION

    # --- construction -----------------------------------------------------
    @classmethod
    def from_named_arrays(cls, family: str, method: str, target_module: str,
                          layer_idx: int, arrays: dict[str, np.ndarray],
                          hparams: dict | None = None) -> "AdapterIR":
        return cls(family=family, method=method, target_module=target_module,
                   layer_idx=layer_idx,
                   tensors={k: np.asarray(v, dtype=np.float32) for k, v in arrays.items()},
                   hparams=dict(hparams or {}))

    # --- structure ops ----------------------------------------------------
    def flatten(self) -> list[tuple[str, np.ndarray]]:
        return [(k, self.tensors[k]) for k in sorted(self.tensors)]

    @classmethod
    def unflatten(cls, meta: dict, flat: list[tuple[str, np.ndarray]]) -> "AdapterIR":
        return cls(family=meta["family"], method=meta["method"],
                   target_module=meta["target_module"], layer_idx=meta["layer_idx"],
                   tensors={k: np.asarray(v) for k, v in flat},
                   hparams=dict(meta.get("hparams", {})), dtype=meta.get("dtype", "float32"),
                   schema_version=meta.get("schema_version", SCHEMA_VERSION))

    def meta(self) -> dict:
        return {"family": self.family, "method": self.method,
                "target_module": self.target_module, "layer_idx": self.layer_idx,
                "hparams": self.hparams, "dtype": self.dtype,
                "schema_version": self.schema_version}

    def param_count(self) -> int:
        return int(sum(int(a.size) for a in self.tensors.values()))

    def canonical_bytes(self) -> bytes:
        """Deterministic byte serialization (meta + sorted tensors) for hashing."""
        h = hashlib.sha256()
        m = self.meta()
        h.update(json.dumps(m, sort_keys=True, default=str).encode("utf-8"))
        for name, arr in self.flatten():
            h.update(name.encode("utf-8"))
            h.update(np.ascontiguousarray(arr, dtype=np.float32).tobytes())
        return h.digest()

    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def copy(self) -> "AdapterIR":
        return AdapterIR.unflatten(self.meta(), [(k, v.copy()) for k, v in self.flatten()])

    # --- framework boundary (lazy) ---------------------------------------
    def to_torch(self) -> dict:
        import torch  # lazy
        return {k: torch.from_numpy(np.asarray(v, dtype=np.float32)) for k, v in self.tensors.items()}

    @classmethod
    def from_torch(cls, family: str, method: str, target_module: str, layer_idx: int,
                   tensors: dict, hparams: dict | None = None) -> "AdapterIR":
        return cls.from_named_arrays(
            family, method, target_module, layer_idx,
            {k: v.detach().cpu().numpy() for k, v in tensors.items()}, hparams)

    def to_mlx(self) -> dict:
        import mlx.core as mx  # lazy
        return {k: mx.array(v) for k, v in self.tensors.items()}

    @classmethod
    def from_mlx(cls, family: str, method: str, target_module: str, layer_idx: int,
                 tensors: dict, hparams: dict | None = None) -> "AdapterIR":
        return cls.from_named_arrays(
            family, method, target_module, layer_idx,
            {k: np.asarray(v) for k, v in tensors.items()}, hparams)


def compatible(a: AdapterIR, b: AdapterIR) -> bool:
    """Two IRs are algebra-compatible iff same target/family and matching tensor shapes."""
    if a.target_module != b.target_module or a.family != b.family:
        return False
    if set(a.tensors) != set(b.tensors):
        return False
    return all(a.tensors[k].shape == b.tensors[k].shape for k in a.tensors)
