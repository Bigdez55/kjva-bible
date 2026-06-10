"""memory/recall_trail.py — Jog My Memory Protocol (§11.1 Add, §11.2 step 12).

Given a cue, builds a relevance-ranked trail of ExperienceAtoms: entity overlap ×
atom strength × salience. The trail is bounded (top-k) and records why each atom was
recalled, so the §12 pipeline can surface provenance. Touching recalled atoms
reinforces them. Pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .experience_atom import ExperienceAtom
from sensory.evidence import _extract_entities   # absolute (src on path; memory is top-level)


@dataclass
class RecallHit:
    atom_id: str
    score: float
    matched_entities: list[str] = field(default_factory=list)


@dataclass
class RecallTrail:
    cue_entities: list[str]
    hits: list[RecallHit] = field(default_factory=list)
    # ADR-0002 §7.3 RecallTrail minimum fields (the bounded-cascade termination evidence):
    trail_id: str = ""
    cue_hash: str = ""
    expansion_depth: int = 0
    visited_memory_ids: list[str] = field(default_factory=list)
    recovered_entities: list[str] = field(default_factory=list)
    recovered_time_windows: list[str] = field(default_factory=list)
    recovered_sensory_anchors: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    stop_reason: str = ""

    def atom_ids(self) -> list[str]:
        return [h.atom_id for h in self.hits]


def _score(cue_ents: set[str], atom: ExperienceAtom) -> tuple[float, list[str]]:
    aents = {e.lower() for e in atom.cue_entities}
    matched = sorted(cue_ents & aents)
    if not matched and cue_ents:
        overlap = 0.0
    else:
        overlap = len(matched) / max(1, len(cue_ents))
    return overlap * atom.strength * (0.5 + 0.5 * atom.salience), matched


def jog_my_memory(cue: str, atoms: list[ExperienceAtom], *, top_k: int = 7,
                  now: float | None = None, min_score: float = 1e-6) -> RecallTrail:
    cue_ents = {e.lower() for e in _extract_entities(cue)}
    scored = []
    for a in atoms:
        s, matched = _score(cue_ents, a)
        if s > min_score:
            scored.append((s, a, matched))
    scored.sort(key=lambda t: -t[0])
    trail = RecallTrail(cue_entities=sorted(cue_ents))
    recovered: set[str] = set()
    for s, a, matched in scored[:top_k]:
        if now is not None:
            a.touch(now)                       # recall reinforces
        trail.hits.append(RecallHit(atom_id=a.atom_id, score=round(s, 4), matched_entities=matched))
        recovered.update(matched)
    # §7.3 termination evidence — the bounded single-pass cascade over the live ledger.
    import hashlib as _hl
    trail.cue_hash = "sha256:" + _hl.sha256(cue.encode("utf-8")).hexdigest()[:32]
    trail.trail_id = "rt:" + trail.cue_hash[7:23] + ":" + str(int((now or 0) * 1000))
    trail.expansion_depth = 1                  # single bounded pass (no recursive expansion this turn)
    trail.visited_memory_ids = trail.atom_ids()
    trail.recovered_entities = sorted(recovered)
    trail.confidence_after = round(max((h.score for h in trail.hits), default=0.0), 4)
    trail.stop_reason = "top_k_reached" if len(scored) > top_k else "candidates_exhausted"
    return trail
