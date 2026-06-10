"""determinism.py — deterministic adapter route/run records + replay (Omni-PEFT++ §11.2 step 13).

Pure stdlib. A RouteRecord captures (seed, route plan, input hash, env fingerprint)
such that replay(record) re-derives an identical plan from the same seed+inputs. This
gives the DeterminantProbabilityRecord property: identical inputs ⇒ identical route.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Any


def _hash_inputs(inputs: Any) -> str:
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class RouteRecord:
    seed: int
    input_hash: str
    candidates: list[str]
    plan: list[str] = field(default_factory=list)
    env_fingerprint: str = ""

    def to_dict(self) -> dict:
        return {"seed": self.seed, "input_hash": self.input_hash,
                "candidates": list(self.candidates), "plan": list(self.plan),
                "env_fingerprint": self.env_fingerprint}


def _derive_plan(seed: int, input_hash: str, candidates: list[str], top_k: int) -> list[str]:
    # Deterministic: seed the RNG from seed+input_hash, shuffle a copy, take top_k.
    rng = random.Random(f"{seed}:{input_hash}")
    pool = list(candidates)
    rng.shuffle(pool)
    return pool[:top_k]


def record(seed: int, candidates: list[str], inputs: Any, *, top_k: int = 2,
           env_fingerprint: str = "") -> RouteRecord:
    ih = _hash_inputs(inputs)
    plan = _derive_plan(seed, ih, candidates, top_k)
    return RouteRecord(seed=seed, input_hash=ih, candidates=list(candidates),
                       plan=plan, env_fingerprint=env_fingerprint)


def replay(rec: RouteRecord, top_k: int | None = None) -> list[str]:
    k = top_k if top_k is not None else len(rec.plan)
    return _derive_plan(rec.seed, rec.input_hash, rec.candidates, k)


def is_deterministic(rec: RouteRecord) -> bool:
    return replay(rec, top_k=len(rec.plan)) == rec.plan
