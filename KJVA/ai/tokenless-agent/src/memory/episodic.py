"""ai/tokenless-agent/src/memory/episodic.py
EpisodicMemory — event store with FNV-1a embedding hashing, recency retrieval,
keyword search, and LRU-style eviction when capacity is exceeded.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tokenless.memory.episodic")

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_EPISODES: int = 1000
_EVICT_FRACTION: float = 0.10      # evict oldest 10% when full
_SECONDS_PER_DAY: float = 86400.0

# FNV-1a 32-bit parameters
_FNV_OFFSET: int = 2166136261
_FNV_PRIME: int = 16777619
_FNV_MASK: int = 0xFFFFFFFF


def _fnv1a_32(text: str) -> int:
    """FNV-1a 32-bit hash. Matches XMIND BPE hash table algorithm."""
    h = _FNV_OFFSET
    for byte in text.encode("utf-8", errors="replace"):
        h ^= byte
        h = (h * _FNV_PRIME) & _FNV_MASK
    return h


def _embedding_hash(description: str, entities: List[str]) -> str:
    """Derive a compact embedding proxy hash from episode content."""
    combined = description + "|".join(sorted(entities))
    return format(_fnv1a_32(combined), "08x")


# ── Episode dataclass ─────────────────────────────────────────────────────────

@dataclass
class Episode:
    """
    A discrete episodic memory entry.

    Fields
    ------
    event_id       : unique identifier (auto-generated from FNV hash + timestamp)
    timestamp      : wall-clock time of recording (time.monotonic() domain)
    event_type     : free-form category string (e.g. "tool_call", "user_query")
    description    : human-readable summary of the event
    entities       : named entities extracted from the event
    embedding_hash : FNV-1a proxy for fast similarity filtering
    payload        : arbitrary structured data for replay/debugging
    """
    event_id: str
    timestamp: float
    event_type: str
    description: str
    entities: List[str] = field(default_factory=list)
    embedding_hash: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    def age_seconds(self) -> float:
        return time.monotonic() - self.timestamp

    def age_days(self) -> float:
        return self.age_seconds() / _SECONDS_PER_DAY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "description": self.description,
            "entities": self.entities,
            "embedding_hash": self.embedding_hash,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Episode":
        return cls(
            event_id=d["event_id"],
            timestamp=d["timestamp"],
            event_type=d["event_type"],
            description=d["description"],
            entities=d.get("entities", []),
            embedding_hash=d.get("embedding_hash", ""),
            payload=d.get("payload", {}),
        )


# ── EpisodicMemory ────────────────────────────────────────────────────────────

class EpisodicMemory:
    """
    Append-only episodic store with keyword search and temporal decay eviction.

    Design decisions
    ----------------
    - Storage: ordered list (chronological) for O(1) append and O(n) recall.
      At MAX_EPISODES=1000, linear search is acceptable (<1 ms on modern HW).
    - Eviction: oldest 10% evicted when capacity exceeded (not LRU by access —
      episodic events are intrinsically temporal, so age is the right signal).
    - Search: keyword overlap between query tokens and (description + entities).
      No vector embedding required — keeps this layer free of ML dependencies.
    - Hashing: FNV-1a 32-bit to mirror the BPE hash table in XMIND tokenizer.c.
    """

    def __init__(self) -> None:
        self._episodes: List[Episode] = []

    # ── Record ────────────────────────────────────────────────────────────────

    def record(
        self,
        event_type: str,
        description: str,
        entities: Optional[List[str]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Episode:
        """
        Record a new episodic event and return the Episode object.
        Triggers eviction if MAX_EPISODES is reached before inserting.
        """
        if len(self._episodes) >= MAX_EPISODES:
            self._evict()

        ents = entities or []
        emb_hash = _embedding_hash(description, ents)
        ts = time.monotonic()
        # Unique event_id: hash of (ts_int + description_hash)
        raw_id = f"{int(ts * 1000)}:{emb_hash}"
        event_id = format(_fnv1a_32(raw_id), "08x")

        ep = Episode(
            event_id=event_id,
            timestamp=ts,
            event_type=event_type,
            description=description,
            entities=ents,
            embedding_hash=emb_hash,
            payload=payload or {},
        )
        self._episodes.append(ep)
        logger.debug(
            "EpisodicMemory: recorded %s id=%s total=%d",
            event_type, event_id, len(self._episodes),
        )
        return ep

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str, max_results: int = 10) -> List[Episode]:
        """
        Keyword search over description and entities.
        Scores each episode by token overlap with the query (Jaccard-style).
        Returns up to max_results results, sorted by score descending.
        """
        if not query.strip():
            return []
        query_tokens = set(query.lower().split())
        scored: List[tuple[float, Episode]] = []
        for ep in self._episodes:
            ep_tokens = set(
                (ep.description + " " + " ".join(ep.entities)).lower().split()
            )
            if not ep_tokens:
                continue
            intersection = len(query_tokens & ep_tokens)
            union = len(query_tokens | ep_tokens)
            score = intersection / union if union > 0 else 0.0
            if score > 0:
                scored.append((score, ep))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:max_results]]

    # ── Recent ────────────────────────────────────────────────────────────────

    def recent(self, n: int = 10) -> List[Episode]:
        """Return the n most-recently recorded episodes."""
        return list(reversed(self._episodes[-n:])) if self._episodes else []

    # ── Forgetting ────────────────────────────────────────────────────────────

    def forget_old(self, days: float = 30.0) -> int:
        """
        Remove episodes older than `days` days.
        Returns the number of episodes removed.
        """
        threshold = days * _SECONDS_PER_DAY
        before = len(self._episodes)
        self._episodes = [
            ep for ep in self._episodes if ep.age_seconds() < threshold
        ]
        removed = before - len(self._episodes)
        if removed:
            logger.info("EpisodicMemory: forgot %d episodes older than %.1f days", removed, days)
        return removed

    # ── Eviction ─────────────────────────────────────────────────────────────

    def _evict(self) -> None:
        """Evict the oldest _EVICT_FRACTION of episodes."""
        n_evict = max(1, int(len(self._episodes) * _EVICT_FRACTION))
        self._episodes = self._episodes[n_evict:]
        logger.info("EpisodicMemory: evicted %d oldest episodes (cap=%d)", n_evict, MAX_EPISODES)

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def count(self) -> int:
        return len(self._episodes)

    def all_event_types(self) -> List[str]:
        seen: set = set()
        types: List[str] = []
        for ep in self._episodes:
            if ep.event_type not in seen:
                seen.add(ep.event_type)
                types.append(ep.event_type)
        return types

    def get_by_id(self, event_id: str) -> Optional[Episode]:
        for ep in reversed(self._episodes):
            if ep.event_id == event_id:
                return ep
        return None

    def __repr__(self) -> str:
        return f"EpisodicMemory(count={len(self._episodes)}, cap={MAX_EPISODES})"
