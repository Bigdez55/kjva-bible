"""memory/experience_atom.py — atomic experience unit (§11.1 Add, §11.2 step 11).

An ExperienceAtom is the smallest persisted memory: a (cue → response) pair with
salience, provenance lineage, and a decayable strength. Atoms compose into recall
trails (recall_trail.py) and are aged by the lifespan ledger (lifespan_ledger.py).

PII policy (§4.4): raw cue text is hashed for the id; only entity tokens + the
response are retained verbatim by callers that choose to.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict


def _atom_id(cue: str, response: str, ts: float) -> str:
    return hashlib.sha256(f"{cue}\x00{response}\x00{ts}".encode("utf-8")).hexdigest()[:16]


@dataclass
class ExperienceAtom:
    cue_entities: list[str]
    response: str
    salience: float = 0.5
    created_at: float = 0.0
    last_access: float = 0.0
    access_count: int = 0
    strength: float = 1.0                  # decayable [0,1]
    lineage: list[str] = field(default_factory=list)   # parent atom ids / source tags (lineage_ref)
    atom_id: str = ""
    # ADR-0001 §8.2 provenance/lineage fields (exact-source pointer + correction lineage):
    source_hashes: list[str] = field(default_factory=list)        # sha256 of the stored content
    contradiction_links: list[str] = field(default_factory=list)  # atom ids this contradicts
    correction_history: list[str] = field(default_factory=list)   # prior corrected versions
    privacy_class: str = "private"          # public|internal|private|sealed
    retention_mode: str = "session"         # session|episodic|semantic|archival

    @classmethod
    def create(cls, cue: str, response: str, *, salience: float = 0.5,
               now: float = 0.0, lineage: list[str] | None = None) -> "ExperienceAtom":
        from sensory.evidence import _extract_entities  # reuse the entity heuristic (src on path)
        ents = _extract_entities(cue)
        aid = _atom_id(cue, response, now)
        # §8.2 source_hash: exact-source pointer to the stored content (never raw content).
        src = "sha256:" + hashlib.sha256(response.encode("utf-8")).hexdigest()
        return cls(cue_entities=ents, response=response, salience=salience,
                   created_at=now, last_access=now, access_count=0, strength=1.0,
                   lineage=list(lineage or []), atom_id=aid, source_hashes=[src],
                   retention_mode=("episodic" if salience >= 0.7 else "session"))

    def touch(self, now: float) -> None:
        self.last_access = now
        self.access_count += 1
        # access reinforces strength (capped)
        self.strength = min(1.0, self.strength + 0.1)

    def decay(self, now: float, half_life: float = 86400.0) -> float:
        """Exponential strength decay by elapsed time since last access."""
        import math
        dt = max(0.0, now - self.last_access)
        self.strength = self.strength * math.pow(0.5, dt / half_life)
        return self.strength

    def to_dict(self) -> dict:
        return asdict(self)
