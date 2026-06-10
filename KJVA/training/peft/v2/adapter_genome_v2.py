"""adapter_genome_v2.py — signed/scoped/hashed adapter genome (Omni-PEFT++ §11.1, §11.2 step 5).

Superset of the v1 AdapterGenomeRecord. Adds content hashing, HMAC signing, scope,
and provenance (parents). Serialization is **non-breaking**: to_yaml_dict() emits a
byte-identical v1 `adapter_genome` block plus a sibling `adapter_genome_v2` block, so
the v1 registry.load() continues to work untouched.

Pure stdlib (hashlib/hmac) — imports without torch/mlx.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Any

# v1 fields that registry.load() reads from the `adapter_genome` block.
V1_FIELDS = ("method", "operator", "family", "rank", "alpha",
             "target_modules", "trainable_params", "base_checkpoint", "evaluation")


@dataclass
class AdapterGenomeV2:
    method: str
    family: str
    rank: int = 0
    alpha: int = 0
    target_modules: list[str] = field(default_factory=list)
    trainable_params: int = 0
    operator: str = ""
    base_checkpoint: str = ""
    evaluation: dict[str, Any] = field(default_factory=dict)
    # v2 additions
    scope: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    signature: str | None = None
    signer: str | None = None
    parents: list[str] = field(default_factory=list)

    # --- v1 interop (lossless on v1 fields) ------------------------------
    @classmethod
    def from_v1(cls, rec: dict) -> "AdapterGenomeV2":
        return cls(**{k: rec[k] for k in V1_FIELDS if k in rec})

    def to_v1(self) -> dict:
        return {
            "method": self.method, "operator": self.operator, "family": self.family,
            "rank": self.rank, "alpha": self.alpha, "target_modules": list(self.target_modules),
            "trainable_params": self.trainable_params, "base_checkpoint": self.base_checkpoint,
            "evaluation": dict(self.evaluation),
        }

    # --- hashing + signing -----------------------------------------------
    def compute_hash(self, ir_bytes: bytes) -> str:
        self.content_hash = hashlib.sha256(ir_bytes).hexdigest()
        return self.content_hash

    def sign(self, key: bytes, signer: str = "omni-peft") -> str:
        msg = (self.content_hash + "|" + self.method + "|" + self.family).encode()
        self.signature = hmac.new(key, msg, hashlib.sha256).hexdigest()
        self.signer = signer
        return self.signature

    def verify(self, key: bytes) -> bool:
        if not self.signature:
            return False
        msg = (self.content_hash + "|" + self.method + "|" + self.family).encode()
        return hmac.compare_digest(self.signature, hmac.new(key, msg, hashlib.sha256).hexdigest())

    # --- serialization (non-breaking dual block) -------------------------
    def to_yaml_dict(self) -> dict:
        return {
            "adapter_genome": self.to_v1(),                 # untouched by registry.load()
            "adapter_genome_v2": {
                "schema_version": "2.0", "scope": dict(self.scope),
                "content_hash": self.content_hash, "signature": self.signature,
                "signer": self.signer, "parents": list(self.parents),
            },
        }
