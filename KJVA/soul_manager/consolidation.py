"""council/runtime/memory/consolidation.py
ACT-R memory consolidation engine for the Council memory subsystem.

Implements:
  - ACT-R base-level activation:  a_i = B_i + sum(t_j^(-d))
  - Consolidation tick (60 s): compute activation, bucket memories
  - Cold bucket migration (activation < 0.3)
  - XBLOB archival (activation < 0.1)
  - Episode pruning via cosine similarity merging (> 0.85)

Backed by SoulManager for HOT/COLD storage and a simulated XBLOB
archive for long-term persistence.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .daemon_client import CouncilDaemonAsyncClient

logger = logging.getLogger("council.consolidation")

# ── ACT-R parameters ─────────────────────────────────────────────────
# Decay parameter d in t^(-d).  ACT-R default is 0.5.
DECAY_RATE: float = 0.5

# Activation thresholds
COLD_THRESHOLD: float = 0.3    # below -> move to COLD bucket
ARCHIVE_THRESHOLD: float = 0.1  # below -> archive to XBLOB

# Base-level learning rate — added once per creation
BASE_LEVEL_CONSTANT: float = 0.0

# Consolidation tick interval (seconds)
TICK_INTERVAL_S: float = 60.0

# Episode pruning: cosine similarity threshold for merging
SIMILARITY_THRESHOLD: float = 0.85

# Maximum memories per agent before forced consolidation
MAX_MEMORIES_PER_AGENT: int = 10_000


# ── Data types ────────────────────────────────────────────────────────

@dataclass
class MemoryRecord:
    """A single memory unit tracked by the consolidation engine.

    Attributes:
        key: Unique identifier (typically sub_path in SoulManager).
        agent: Owning agent name.
        bucket: Current bucket: 'episodic', 'context', 'persistent', 'meta'.
        content: The memory payload (JSON-serialisable).
        access_times: List of Unix timestamps when this memory was accessed.
        created_at: Unix timestamp of creation.
        activation: Cached activation level (recomputed each tick).
        content_hash: SHA-256 of serialised content for dedup/similarity.
        embedding: Optional float vector for cosine similarity.
        merged_from: List of keys this record was merged from.
        archived: True if moved to XBLOB.
    """

    key: str
    agent: str
    bucket: str
    content: Any
    access_times: List[float] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    activation: float = 0.0
    content_hash: str = ""
    embedding: Optional[List[float]] = None
    merged_from: List[str] = field(default_factory=list)
    archived: bool = False

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = self._compute_hash()
        if not self.access_times:
            self.access_times = [self.created_at]

    def _compute_hash(self) -> str:
        raw = json.dumps(self.content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def record_access(self) -> None:
        """Record an access event (updates activation on next tick)."""
        self.access_times.append(time.time())

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "agent": self.agent,
            "bucket": self.bucket,
            "content": self.content,
            "access_times": self.access_times,
            "created_at": self.created_at,
            "activation": self.activation,
            "content_hash": self.content_hash,
            "embedding": self.embedding,
            "merged_from": self.merged_from,
            "archived": self.archived,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryRecord":
        return cls(
            key=d.get("key", ""),
            agent=d.get("agent", ""),
            bucket=d.get("bucket", "episodic"),
            content=d.get("content"),
            access_times=d.get("access_times", []),
            created_at=d.get("created_at", time.time()),
            activation=d.get("activation", 0.0),
            content_hash=d.get("content_hash", ""),
            embedding=d.get("embedding"),
            merged_from=d.get("merged_from", []),
            archived=d.get("archived", False),
        )


# ── Activation computation ────────────────────────────────────────────

def compute_activation(record: MemoryRecord, now: Optional[float] = None) -> float:
    """Compute ACT-R base-level activation for a memory record.

    Activation = B + ln( sum( t_j^(-d) ) )

    where t_j is the time since the j-th access (in seconds, min 1.0),
    d is the decay rate, and B is the base-level constant.

    Returns the computed activation value (also stored on the record).
    """
    if now is None:
        now = time.time()

    if not record.access_times:
        record.activation = BASE_LEVEL_CONSTANT - 10.0  # very low
        return record.activation

    summation = 0.0
    for t_access in record.access_times:
        elapsed = max(1.0, now - t_access)
        summation += elapsed ** (-DECAY_RATE)

    if summation <= 0.0:
        record.activation = BASE_LEVEL_CONSTANT - 10.0
    else:
        record.activation = BASE_LEVEL_CONSTANT + math.log(summation)

    return record.activation


# ── Cosine similarity ─────────────────────────────────────────────────

def _dot(a: List[float], b: List[float]) -> float:
    """Dot product of two vectors."""
    total = 0.0
    for x, y in zip(a, b, strict=False):
        total += x * y
    return total


def _magnitude(v: List[float]) -> float:
    """Euclidean magnitude of a vector."""
    return math.sqrt(_dot(v, v))


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns 0.0 if either vector is zero-length or has zero magnitude.
    """
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    mag_a = _magnitude(a)
    mag_b = _magnitude(b)
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return _dot(a, b) / (mag_a * mag_b)


def _sha256_pseudo_embedding(text: str, dim: int = 64) -> List[float]:
    """Generate a deterministic pseudo-embedding from text content.

    Uses SHA-256 based expansion to produce a fixed-dimension vector.
    The resulting vectors have useful cosine-similarity properties
    for near-identical texts (same hash -> same vector).
    """
    raw = text.encode("utf-8") if isinstance(text, str) else str(text).encode("utf-8")
    embedding: List[float] = []
    block_idx = 0
    while len(embedding) < dim:
        h = hashlib.sha256(raw + block_idx.to_bytes(4, "big")).digest()
        for byte_val in h:
            if len(embedding) >= dim:
                break
            # Map byte to [-1.0, 1.0]
            embedding.append((byte_val / 127.5) - 1.0)
        block_idx += 1
    return embedding[:dim]


def text_to_embedding(text: str, dim: int = 64) -> List[float]:
    """Generate an embedding from text content.

    Uses SHA-256 pseudo-embeddings in the portable Tokenless blueprint.
    Consuming projects can replace this with a local XMIND provider.
    """
    logger.debug("text_to_embedding: using SHA-256 pseudo-embedding (dim=%d)", dim)
    return _sha256_pseudo_embedding(text, dim)


# ── XBLOB archive (simulated) ─────────────────────────────────────────

class XBlobArchive:
    """Simulated XBLOB long-term storage.

    In production this calls xblob_put/xblob_get via ctypes FFI.
    For now, stores archived records in an in-memory dict.
    """

    def __init__(self) -> None:
        self._store: Dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def archive(self, record: MemoryRecord) -> bool:
        """Archive a memory record to XBLOB. Returns True on success."""
        async with self._lock:
            blob_key = f"archive:{record.agent}:{record.key}"
            self._store[blob_key] = record.to_dict()
        logger.debug(
            "Archived memory %s for agent %s to XBLOB",
            record.key, record.agent,
        )
        return True

    async def retrieve(self, agent: str, key: str) -> Optional[MemoryRecord]:
        """Retrieve an archived memory. Returns None if not found."""
        blob_key = f"archive:{agent}:{key}"
        async with self._lock:
            data = self._store.get(blob_key)
        if data is None:
            return None
        return MemoryRecord.from_dict(data)

    async def list_archived(self, agent: str) -> List[str]:
        """List all archived keys for an agent."""
        prefix = f"archive:{agent}:"
        async with self._lock:
            return [
                k[len(prefix):]
                for k in self._store
                if k.startswith(prefix)
            ]

    async def count(self) -> int:
        """Total number of archived records."""
        async with self._lock:
            return len(self._store)


# ── Consolidation Engine ──────────────────────────────────────────────

class ConsolidationEngine:
    """ACT-R memory consolidation engine.

    Runs periodic consolidation ticks that:
      1. Recompute activation for every tracked memory.
      2. Migrate low-activation memories to COLD bucket.
      3. Archive very-low-activation memories to XBLOB.
      4. Prune similar episodic memories via cosine merge.

    Attributes:
        _memories: Agent -> key -> MemoryRecord mapping.
        _soul_client: Optional SoulManagerClient for bucket migration.
        _xblob: XBLOB archive backend.
        _tick_task: Background asyncio.Task for periodic ticks.
        _tick_count: Number of consolidation ticks completed.
    """

    def __init__(
        self,
        soul_client: Optional[Any] = None,
        xblob: Optional[XBlobArchive] = None,
    ) -> None:
        self._memories: Dict[str, Dict[str, MemoryRecord]] = {}
        self._soul_client = soul_client or CouncilDaemonAsyncClient(
            source_agent="soul_manager.consolidation"
        )
        self._xblob = xblob or XBlobArchive()
        self._tick_task: Optional[asyncio.Task[None]] = None
        self._tick_count: int = 0
        self._cold_migrations: int = 0
        self._archives: int = 0
        self._merges: int = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the periodic consolidation tick loop."""
        if self._tick_task is None or self._tick_task.done():
            self._tick_task = asyncio.create_task(
                self._tick_loop(), name="consolidation_tick"
            )
            logger.info("ConsolidationEngine started (interval=%.0fs)", TICK_INTERVAL_S)

    async def stop(self) -> None:
        """Stop the consolidation tick loop."""
        if self._tick_task and not self._tick_task.done():
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
        logger.info(
            "ConsolidationEngine stopped: ticks=%d cold=%d archived=%d merged=%d",
            self._tick_count, self._cold_migrations, self._archives, self._merges,
        )

    # ── Memory registration ──────────────────────────────────────────

    async def track_memory(
        self,
        agent: str,
        key: str,
        bucket: str,
        content: Any,
        embedding: Optional[List[float]] = None,
    ) -> MemoryRecord:
        """Register a new memory for consolidation tracking.

        If the memory already exists, record an access event instead.
        """
        async with self._lock:
            agent_memories = self._memories.setdefault(agent, {})
            if key in agent_memories:
                existing = agent_memories[key]
                existing.record_access()
                return existing

            record = MemoryRecord(
                key=key,
                agent=agent,
                bucket=bucket,
                content=content,
                embedding=embedding,
            )
            # Auto-generate embedding if not provided
            if record.embedding is None:
                content_str = json.dumps(content, sort_keys=True)
                record.embedding = text_to_embedding(content_str)

            agent_memories[key] = record
        return record

    async def record_access(self, agent: str, key: str) -> bool:
        """Record an access event for a tracked memory. Returns True if found."""
        async with self._lock:
            agent_memories = self._memories.get(agent, {})
            record = agent_memories.get(key)
            if record is None:
                return False
            record.record_access()
        return True

    async def get_activation(self, agent: str, key: str) -> Optional[float]:
        """Get the current activation level of a memory."""
        async with self._lock:
            agent_memories = self._memories.get(agent, {})
            record = agent_memories.get(key)
        if record is None:
            return None
        return compute_activation(record)

    # ── Consolidation tick ───────────────────────────────────────────

    async def consolidation_tick(self) -> Dict[str, int]:
        """Run one consolidation cycle.

        Returns a summary dict: {recomputed, cold, archived, merged}.
        """
        now = time.time()
        recomputed = 0
        cold_moved = 0
        archived = 0
        merged = 0

        async with self._lock:
            agents = list(self._memories.keys())

        for agent in agents:
            async with self._lock:
                agent_memories = self._memories.get(agent, {})
                keys = list(agent_memories.keys())

            # Phase 1: Recompute activation for all memories
            to_cold: List[str] = []
            to_archive: List[str] = []

            for key in keys:
                async with self._lock:
                    record = agent_memories.get(key)
                if record is None or record.archived:
                    continue

                activation = compute_activation(record, now)
                recomputed += 1

                if activation < ARCHIVE_THRESHOLD:
                    to_archive.append(key)
                elif activation < COLD_THRESHOLD:
                    to_cold.append(key)

            # Phase 2: Migrate to COLD bucket
            for key in to_cold:
                async with self._lock:
                    record = agent_memories.get(key)
                if record is None:
                    continue

                old_bucket = record.bucket
                if old_bucket == "persistent":
                    # Never migrate persistent memories to cold
                    continue

                record.bucket = "meta"  # COLD == meta bucket
                await self._migrate_bucket(agent, key, old_bucket, "meta")
                cold_moved += 1

            # Phase 3: Archive to XBLOB
            for key in to_archive:
                async with self._lock:
                    record = agent_memories.get(key)
                if record is None:
                    continue

                if record.bucket == "persistent":
                    continue  # Never archive persistent

                await self._xblob.archive(record)
                record.archived = True
                archived += 1

                # Remove from SoulManager (if connected)
                await self._delete_from_soul(agent, record.bucket, key)

            # Phase 4: Episode pruning (merge similar episodic memories)
            merged += await self._prune_similar_episodes(agent)

        self._tick_count += 1
        self._cold_migrations += cold_moved
        self._archives += archived
        self._merges += merged

        summary = {
            "recomputed": recomputed,
            "cold": cold_moved,
            "archived": archived,
            "merged": merged,
        }
        logger.info(
            "Consolidation tick #%d: recomputed=%d cold=%d archived=%d merged=%d",
            self._tick_count, recomputed, cold_moved, archived, merged,
        )
        return summary

    async def _prune_similar_episodes(self, agent: str) -> int:
        """Merge episodic memories with cosine similarity > threshold.

        When two episodes are similar enough, their access histories
        are combined and the newer content replaces the older.
        Returns the number of merges performed.
        """
        merge_count = 0
        async with self._lock:
            agent_memories = self._memories.get(agent, {})
            episodic = [
                (k, r) for k, r in agent_memories.items()
                if r.bucket == "episodic"
                and not r.archived
                and r.embedding is not None
            ]

        if len(episodic) < 2:
            return 0

        merged_keys: set = set()
        merge_pairs: List[Tuple[str, str]] = []

        for i in range(len(episodic)):
            if episodic[i][0] in merged_keys:
                continue
            for j in range(i + 1, len(episodic)):
                if episodic[j][0] in merged_keys:
                    continue

                key_a, rec_a = episodic[i]
                key_b, rec_b = episodic[j]

                if rec_a.embedding is None or rec_b.embedding is None:
                    continue

                sim = cosine_similarity(rec_a.embedding, rec_b.embedding)
                if sim > SIMILARITY_THRESHOLD:
                    merge_pairs.append((key_a, key_b))
                    merged_keys.add(key_b)

        for keep_key, merge_key in merge_pairs:
            async with self._lock:
                keep_rec = agent_memories.get(keep_key)
                merge_rec = agent_memories.get(merge_key)

                if keep_rec is None or merge_rec is None:
                    continue

                # Combine access histories
                keep_rec.access_times.extend(merge_rec.access_times)
                keep_rec.access_times.sort()

                # Track merge provenance
                keep_rec.merged_from.append(merge_key)
                keep_rec.merged_from.extend(merge_rec.merged_from)

                # Use newer content if merge_rec is newer
                if merge_rec.created_at > keep_rec.created_at:
                    keep_rec.content = merge_rec.content
                    keep_rec.content_hash = merge_rec.content_hash

                # Remove merged record
                del agent_memories[merge_key]

            merge_count += 1

        return merge_count

    # ── SoulManager integration ──────────────────────────────────────

    async def _migrate_bucket(
        self,
        agent: str,
        key: str,
        old_bucket: str,
        new_bucket: str,
    ) -> None:
        """Move a memory from one SoulManager bucket to another."""
        if self._soul_client is None:
            return
        try:
            # Read from old bucket
            value = await self._soul_client.get(old_bucket, key, namespace=agent)
            if value is not None:
                # Write to new bucket
                await self._soul_client.put(new_bucket, key, value, namespace=agent)
                # Delete from old bucket -- best-effort
                # SoulManagerClient doesn't expose delete, so we
                # overwrite with None marker
                await self._soul_client.put(
                    old_bucket,
                    key,
                    {"_deleted": True, "_migrated_to": new_bucket},
                    namespace=agent,
                )
        except Exception as exc:
            logger.warning("Bucket migration failed for %s:%s: %s", agent, key, exc)

    async def _delete_from_soul(self, agent: str, bucket: str, key: str) -> None:
        """Remove a memory from SoulManager after archival."""
        if self._soul_client is None:
            return
        try:
            await self._soul_client.put(
                bucket,
                key,
                {"_archived": True, "_archived_at": time.time()},
                namespace=agent,
            )
        except Exception as exc:
            logger.warning("Delete from soul failed for %s:%s:%s: %s", agent, bucket, key, exc)

    # ── Background loop ───────────────────────────────────────────────

    async def _tick_loop(self) -> None:
        """Run consolidation_tick every TICK_INTERVAL_S seconds."""
        while True:
            await asyncio.sleep(TICK_INTERVAL_S)
            try:
                await self.consolidation_tick()
            except Exception as exc:
                logger.error("Consolidation tick failed: %s", exc, exc_info=True)

    # ── Stats & diagnostics ──────────────────────────────────────────

    async def stats(self) -> Dict[str, Any]:
        """Return consolidation engine statistics."""
        async with self._lock:
            total_memories = sum(
                len(mems) for mems in self._memories.values()
            )
            agent_count = len(self._memories)
            archived_count = sum(
                1
                for mems in self._memories.values()
                for r in mems.values()
                if r.archived
            )
        xblob_count = await self._xblob.count()
        return {
            "tick_count": self._tick_count,
            "total_memories": total_memories,
            "agent_count": agent_count,
            "archived_in_tracker": archived_count,
            "xblob_archived": xblob_count,
            "cold_migrations": self._cold_migrations,
            "total_archives": self._archives,
            "total_merges": self._merges,
            "decay_rate": DECAY_RATE,
            "cold_threshold": COLD_THRESHOLD,
            "archive_threshold": ARCHIVE_THRESHOLD,
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "tick_interval_s": TICK_INTERVAL_S,
        }

    async def get_agent_memories(
        self,
        agent: str,
        include_archived: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return all tracked memories for an agent as dicts."""
        async with self._lock:
            agent_memories = self._memories.get(agent, {})
            result = []
            for record in agent_memories.values():
                if not include_archived and record.archived:
                    continue
                result.append(record.to_dict())
        return result

    async def get_activation_report(self, agent: str) -> List[Dict[str, Any]]:
        """Return activation levels for all memories of an agent, sorted desc."""
        now = time.time()
        report: List[Dict[str, Any]] = []
        async with self._lock:
            agent_memories = self._memories.get(agent, {})
            for key, record in agent_memories.items():
                if record.archived:
                    continue
                activation = compute_activation(record, now)
                report.append({
                    "key": key,
                    "bucket": record.bucket,
                    "activation": round(activation, 4),
                    "access_count": len(record.access_times),
                    "last_access": record.access_times[-1] if record.access_times else 0,
                    "age_s": round(now - record.created_at, 1),
                })
        report.sort(key=lambda r: r["activation"], reverse=True)
        return report
