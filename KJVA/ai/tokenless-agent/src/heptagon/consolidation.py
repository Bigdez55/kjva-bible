"""ai/tokenless-agent/src/heptagon/consolidation.py
ACT-R decay consolidation for the Heptagon Layer 6 (Calibration) memory engine.

Implements:
  - ACT-R base-level activation: a_i = B + ln(Σ t_j^(-d))
  - Consolidation tick every 60 s (tick())
  - Pruning of low-activation memories (prune_low_activation)
  - Episode deduplication via Jaccard similarity (merge_similar)

Mirrors the implementation in council/runtime/memory/consolidation.py but
scoped to the Tokenless AI layer (no async, no SoulManager dependency).
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("tokenless.heptagon.consolidation")

# ── ACT-R Parameters ──────────────────────────────────────────────────────────
DECAY_RATE: float = 0.5            # d in t_j^(-d) — ACT-R default
BASE_LEVEL_CONSTANT: float = 0.0   # B — baseline activation offset
PRUNE_THRESHOLD: float = 0.1       # activations below this are pruned
MERGE_SIMILARITY: float = 0.85     # Jaccard threshold for episode merging
TICK_INTERVAL_S: float = 60.0      # consolidation tick interval

# ── Memory entry ──────────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    """
    A single memory item tracked by the consolidator.

    access_times: list of monotonic timestamps when the memory was accessed.
    created_at  : initial creation timestamp.
    content     : the raw text content (used for similarity matching).
    tags        : optional set of topic tags for fast filtering.
    activation  : computed ACT-R activation (updated by tick()).
    """
    entry_id: str
    content: str
    created_at: float = field(default_factory=time.monotonic)
    access_times: List[float] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)
    activation: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        """Record an access, updating the access_times list."""
        self.access_times.append(time.monotonic())

    def age_seconds(self) -> float:
        return time.monotonic() - self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "content": self.content,
            "created_at": self.created_at,
            "access_times": self.access_times,
            "tags": list(self.tags),
            "activation": self.activation,
            "metadata": self.metadata,
        }


# ── MemoryConsolidator ────────────────────────────────────────────────────────

class MemoryConsolidator:
    """
    ACT-R decay consolidation engine for Tokenless AI episodic memory.

    Activation formula (Anderson et al. 2004):
        a_i = B + ln( Σ_{j=1}^{n} t_j^{-d} )

    where:
        B = BASE_LEVEL_CONSTANT
        t_j = elapsed time (seconds) since the j-th retrieval
        d = DECAY_RATE (0.5 standard)
        n = number of prior retrievals (access_times)

    Memories with a_i < PRUNE_THRESHOLD are removed on tick().
    Episodes with Jaccard similarity ≥ MERGE_SIMILARITY are merged (dedup).
    """

    def __init__(
        self,
        prune_threshold: float = PRUNE_THRESHOLD,
        merge_threshold: float = MERGE_SIMILARITY,
        tick_interval: float = TICK_INTERVAL_S,
        on_prune: Optional[Callable[[MemoryEntry], None]] = None,
    ) -> None:
        self._memories: Dict[str, MemoryEntry] = {}
        self._prune_threshold = prune_threshold
        self._merge_threshold = merge_threshold
        self._tick_interval = tick_interval
        self._last_tick: float = time.monotonic()
        self._on_prune = on_prune
        self._tick_count: int = 0

    # ── Store / retrieve ──────────────────────────────────────────────────────

    def store(
        self,
        entry_id: str,
        content: str,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Add or update a memory entry. Returns the entry."""
        existing = self._memories.get(entry_id)
        if existing is not None:
            existing.touch()
            logger.debug("MemoryConsolidator: touched existing entry %s", entry_id)
            return existing
        entry = MemoryEntry(
            entry_id=entry_id,
            content=content,
            tags=tags or set(),
            metadata=metadata or {},
        )
        entry.touch()   # count creation as first access
        self._memories[entry_id] = entry
        logger.debug("MemoryConsolidator: stored entry %s (total=%d)", entry_id, len(self._memories))
        return entry

    def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        """Retrieve and touch a memory entry, returning it or None."""
        entry = self._memories.get(entry_id)
        if entry is not None:
            entry.touch()
        return entry

    # ── ACT-R activation ──────────────────────────────────────────────────────

    def compute_activation(self, entry: MemoryEntry) -> float:
        """
        Compute ACT-R base-level activation.

        a_i = B + ln( Σ t_j^{-d} )

        t_j is time elapsed since the j-th retrieval (in seconds, floored at 1e-3
        to avoid ln(0) when access was just now).
        Returns BASE_LEVEL_CONSTANT if there are no access events.
        """
        if not entry.access_times:
            return BASE_LEVEL_CONSTANT
        now = time.monotonic()
        total = 0.0
        for t_access in entry.access_times:
            elapsed = max(1e-3, now - t_access)
            total += elapsed ** (-DECAY_RATE)
        if total <= 0.0:
            return BASE_LEVEL_CONSTANT
        return BASE_LEVEL_CONSTANT + math.log(total)

    def _update_activations(self) -> None:
        """Recompute activation for all memories in-place."""
        for entry in self._memories.values():
            entry.activation = self.compute_activation(entry)

    # ── Consolidation tick ────────────────────────────────────────────────────

    def tick(self) -> Dict[str, Any]:
        """
        Run one consolidation cycle.

        Steps:
          1. Update all activations.
          2. Prune entries below prune_threshold.
          3. Merge near-duplicate episodes.

        Returns a summary dict for observability.
        """
        self._tick_count += 1
        self._last_tick = time.monotonic()
        self._update_activations()

        pruned = self.prune_low_activation(self._prune_threshold)
        merged = self.merge_similar(self._merge_threshold)

        summary = {
            "tick": self._tick_count,
            "remaining": len(self._memories),
            "pruned": pruned,
            "merged": merged,
        }
        logger.info(
            "MemoryConsolidator tick #%d: remaining=%d pruned=%d merged=%d",
            self._tick_count, len(self._memories), pruned, merged,
        )
        return summary

    def maybe_tick(self) -> Optional[Dict[str, Any]]:
        """Run a tick if tick_interval has elapsed since the last tick."""
        if time.monotonic() - self._last_tick >= self._tick_interval:
            return self.tick()
        return None

    # ── Pruning ───────────────────────────────────────────────────────────────

    def prune_low_activation(self, threshold: float = PRUNE_THRESHOLD) -> int:
        """
        Remove all entries with activation < threshold.
        Fires on_prune callback for each removed entry.
        Returns count of pruned entries.
        """
        to_prune = [
            eid for eid, entry in self._memories.items()
            if entry.activation < threshold
        ]
        for eid in to_prune:
            entry = self._memories.pop(eid)
            if self._on_prune is not None:
                try:
                    self._on_prune(entry)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("on_prune callback failed: %s", exc)
        if to_prune:
            logger.debug(
                "MemoryConsolidator: pruned %d entries (threshold=%.3f)",
                len(to_prune), threshold,
            )
        return len(to_prune)

    # ── Merge / dedup ─────────────────────────────────────────────────────────

    def merge_similar(self, threshold: float = MERGE_SIMILARITY) -> int:
        """
        Detect and merge near-duplicate episodes using Jaccard similarity
        on word-token sets derived from entry.content.

        The older entry is kept; the newer is removed (its access_times are
        merged into the surviving entry to preserve retrieval history).
        Returns the count of merged (removed) entries.
        """
        entries = list(self._memories.values())
        merged_ids: Set[str] = set()
        merge_count = 0

        for i in range(len(entries)):
            if entries[i].entry_id in merged_ids:
                continue
            tokens_i = _tokenize_for_similarity(entries[i].content)
            for j in range(i + 1, len(entries)):
                if entries[j].entry_id in merged_ids:
                    continue
                tokens_j = _tokenize_for_similarity(entries[j].content)
                sim = _jaccard(tokens_i, tokens_j)
                if sim >= threshold:
                    # Keep older entry (smaller created_at)
                    keep = entries[i] if entries[i].created_at <= entries[j].created_at else entries[j]
                    drop = entries[j] if keep is entries[i] else entries[i]
                    keep.access_times.extend(drop.access_times)
                    keep.tags.update(drop.tags)
                    merged_ids.add(drop.entry_id)
                    merge_count += 1
                    logger.debug(
                        "MemoryConsolidator: merged %s into %s (sim=%.3f)",
                        drop.entry_id, keep.entry_id, sim,
                    )

        for eid in merged_ids:
            self._memories.pop(eid, None)

        return merge_count

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def count(self) -> int:
        return len(self._memories)

    def tick_count(self) -> int:
        return self._tick_count

    def top_activations(self, n: int = 10) -> List[Tuple[str, float]]:
        """Return the top-n entries by activation score."""
        pairs = [(eid, e.activation) for eid, e in self._memories.items()]
        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs[:n]

    def all_entries(self) -> List[MemoryEntry]:
        return list(self._memories.values())

    def __repr__(self) -> str:
        return (
            f"MemoryConsolidator(entries={len(self._memories)}, "
            f"ticks={self._tick_count}, "
            f"prune_threshold={self._prune_threshold})"
        )


# ── Similarity helpers ────────────────────────────────────────────────────────

def _tokenize_for_similarity(text: str) -> Set[str]:
    """Word-level tokenisation for Jaccard similarity."""
    return set(text.lower().split())


def _jaccard(a: Set[str], b: Set[str]) -> float:
    """Jaccard similarity coefficient."""
    if not a and not b:
        return 1.0
    union = len(a | b)
    if union == 0:
        return 0.0
    return len(a & b) / union
