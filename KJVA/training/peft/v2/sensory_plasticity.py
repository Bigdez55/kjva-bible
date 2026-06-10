"""sensory_plasticity.py — sensory/byte-stream plasticity map (Omni-PEFT++ §11.2 step 9).

Pure numpy. For a byte-level model, "sensory channels" are byte classes (control,
printable-ascii, utf8-continuation, high). Profiles a corpus byte histogram into
normalized plasticity priors used to bias which channels adapt most.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

CHANNELS = ("control", "ascii_printable", "utf8_lead", "utf8_cont", "high")


def _channel_of(b: int) -> str:
    if b < 32 or b == 127:
        return "control"
    if 32 <= b < 127:
        return "ascii_printable"
    if 0xC0 <= b <= 0xF4:
        return "utf8_lead"
    if 0x80 <= b < 0xC0:
        return "utf8_cont"
    return "high"


@dataclass
class SensoryPlasticityMap:
    priors: dict[str, float] = field(default_factory=dict)

    @classmethod
    def profile(cls, byte_histogram: dict[int, int] | np.ndarray) -> "SensoryPlasticityMap":
        counts = {c: 0.0 for c in CHANNELS}
        if isinstance(byte_histogram, np.ndarray):
            it = enumerate(byte_histogram.tolist())
        else:
            it = byte_histogram.items()
        for b, n in it:
            counts[_channel_of(int(b))] += float(n)
        total = sum(counts.values()) or 1.0
        return cls(priors={c: counts[c] / total for c in CHANNELS})

    @classmethod
    def from_corpus_bytes(cls, raw: bytes) -> "SensoryPlasticityMap":
        hist = np.bincount(np.frombuffer(raw, dtype=np.uint8), minlength=256)
        return cls.profile(hist)

    def normalized(self) -> dict[str, float]:
        s = sum(self.priors.values()) or 1.0
        return {k: v / s for k, v in self.priors.items()}
