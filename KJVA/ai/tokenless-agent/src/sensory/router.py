"""sensory/router.py — deterministic/probabilistic sensory routing (§11.2 step 9).

Maps an EvidenceEnvelope to routing decisions consumed downstream: the memory scope
to retrieve, the sensory scope passed to adapter routing (OmniPEFT.route_adapters),
and a deterministic seed so the same evidence routes identically (determinism §11.2 step 13).
Pure stdlib.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .evidence import EvidenceEnvelope

# Memory scope tiers (broadest → narrowest) chosen by salience.
_SCOPES = ("archival", "semantic", "episodic", "session")


@dataclass
class SensoryRoute:
    memory_scope: str
    sensory_scope: list[str] = field(default_factory=list)
    seed: int = 0
    deterministic: bool = True
    reason: str = ""


class SensoryRouter:
    def __init__(self, salience_episodic: float = 0.3, salience_semantic: float = 0.6):
        self.t_epi = salience_episodic
        self.t_sem = salience_semantic

    def _seed(self, env: EvidenceEnvelope) -> int:
        key = f"{env.session_hash}:{','.join(env.entities)}:{env.modality}"
        return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)

    def route(self, env: EvidenceEnvelope) -> SensoryRoute:
        if env.salience >= self.t_sem:
            scope, why = "semantic", "high salience → semantic recall"
        elif env.salience >= self.t_epi:
            scope, why = "episodic", "mid salience → episodic recall"
        else:
            scope, why = "session", "low salience → session-local"
        # sensory_scope = the dominant non-printable byte channels + modality
        dominant = [c for c, f in sorted(env.byte_profile.items(), key=lambda kv: -kv[1])
                    if c != "ascii_printable" and f > 0.0][:2]
        sensory_scope = [env.modality] + dominant
        return SensoryRoute(memory_scope=scope, sensory_scope=sensory_scope,
                            seed=self._seed(env), deterministic=True, reason=why)
