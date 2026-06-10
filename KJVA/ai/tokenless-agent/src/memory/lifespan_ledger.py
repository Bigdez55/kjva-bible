"""memory/lifespan_ledger.py — atom lifespan + decay + eviction (§11.1 Add, §11.2 step 11).

Tracks every ExperienceAtom's lifespan: registers atoms, decays their strength over
time, and evicts those below a strength floor (bounded memory). Deterministic given an
injected clock. Pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .experience_atom import ExperienceAtom


@dataclass
class LifespanLedger:
    capacity: int = 4096
    strength_floor: float = 0.05
    half_life: float = 86400.0
    atoms: dict[str, ExperienceAtom] = field(default_factory=dict)

    def register(self, atom: ExperienceAtom) -> str:
        self.atoms[atom.atom_id] = atom
        self._enforce_capacity()
        return atom.atom_id

    def decay_all(self, now: float) -> int:
        """Decay every atom; evict those below the floor. Returns #evicted."""
        evict = []
        for aid, atom in self.atoms.items():
            if atom.decay(now, self.half_life) < self.strength_floor:
                evict.append(aid)
        for aid in evict:
            del self.atoms[aid]
        return len(evict)

    def _enforce_capacity(self) -> None:
        if len(self.atoms) <= self.capacity:
            return
        # evict weakest first
        ranked = sorted(self.atoms.values(), key=lambda a: a.strength)
        for atom in ranked[: len(self.atoms) - self.capacity]:
            del self.atoms[atom.atom_id]

    def alive(self) -> list[ExperienceAtom]:
        return list(self.atoms.values())

    def stats(self) -> dict:
        n = len(self.atoms)
        avg = sum(a.strength for a in self.atoms.values()) / n if n else 0.0
        return {"count": n, "capacity": self.capacity, "avg_strength": round(avg, 4)}
