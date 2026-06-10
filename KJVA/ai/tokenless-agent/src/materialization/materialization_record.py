"""materialization/materialization_record.py — the materialization-plane contract.

Defines :class:`MaterializationRecord` (ADR-0001 §11.2). Materialization is mandatory
(§11): it is the record of *when abstract cognition becomes runtime state* — a model
artifact loaded, an adapter activated, a recall reconstructed, an action authorized, a
response finalized, a writeback committed. Without it the architecture is abstract
(§11 preamble), and the §11.3 rules ("No writeback commits without materialization
record", "No model artifact loads without hash verification", ...) are unenforceable.

Field set is the FULL ADR-0001 §11.2 JSON block. Frozen, every field defaulted,
collections via ``field(default_factory=...)`` per ADR-0002 §6.3 record style.
``materialization_type`` / ``status`` / ``privacy_class`` / ``retention_mode`` defaults
are chosen from the ADR enumerations to make a zero-arg record valid and honest about
its lifecycle ("planned", not "committed").
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MaterializationRecord:
    """Record of abstract cognition becoming runtime state (ADR-0001 §11.2)."""

    materialization_id: str = ""
    # adapter|memory|sensory|simulation|action|response|provenance|
    # model_artifact|weight_tensor|deployment  (§11.1 / §11.2)
    materialization_type: str = ""
    source_refs: list[str] = field(default_factory=list)
    source_hashes: list[str] = field(default_factory=list)
    input_records: list[str] = field(default_factory=list)
    transforms: list[Any] = field(default_factory=list)
    runtime_location: str = ""
    owning_role: str = ""
    authority_scope: list[str] = field(default_factory=list)
    # public|internal|private|sealed
    privacy_class: str = "private"
    confidence: float = 0.0
    created_at: str = ""
    # ephemeral|session|episodic|semantic|archival|discard
    retention_mode: str = "ephemeral"
    lineage_refs: list[str] = field(default_factory=list)
    proof_refs: list[str] = field(default_factory=list)
    rollback_refs: list[str] = field(default_factory=list)
    # planned|active|committed|rolled_back|revoked|archived
    status: str = "planned"

    def to_dict(self) -> dict:
        return asdict(self)

    # ------------------------------------------------------------------
    # ADR-0002 §8.3 minimum-field NAME aliases.
    #
    # §8.3 fixes a *minimum* field-name contract for the materialization
    # plane that differs lexically from the ADR-0001 §11.2 shape stored in
    # the frozen fields above. Rather than fork the record (which would
    # break every existing constructor call and ``to_dict()`` consumer),
    # the §8.3 names are exposed as read-only ``@property`` aliases that
    # project onto the existing fields, plus ``to_dict_v2()`` which emits
    # the §8.3 key set. These properties are *unannotated descriptors*, so
    # ``@dataclass`` ignores them — frozen-ness, ``__init__`` and
    # ``asdict()``/``to_dict()`` (§11.2 names) are all untouched.
    #
    # NOTE: ``status`` is deliberately NOT re-exposed as a property — it is
    # already a frozen field with the §8.3 name; adding a property of the
    # same name would shadow the field and break ``__init__``.
    # ------------------------------------------------------------------

    @property
    def record_id(self) -> str:
        """§8.3 record_id ← §11.2 materialization_id."""
        return self.materialization_id

    @property
    def artifact_kind(self) -> str:
        """§8.3 artifact_kind ← §11.2 materialization_type."""
        return self.materialization_type

    @property
    def source_hash(self) -> str:
        """§8.3 source_hash (single) ← first of §11.2 source_hashes, else ""."""
        return self.source_hashes[0] if self.source_hashes else ""

    @property
    def target_runtime(self) -> str:
        """§8.3 target_runtime ← §11.2 runtime_location."""
        return self.runtime_location

    @property
    def materialized_at_ns(self) -> int:
        """§8.3 materialized_at_ns (int epoch-ns) ← §11.2 created_at (ISO str).

        §8.3 types this as ``int``; §11.2 stores an ISO-8601 string. To stay
        type-honest we always return an ``int``: parse ``created_at`` to epoch
        nanoseconds when possible, else ``0``. (We do not build a bulletproof
        parser — a best-effort ISO parse is sufficient and documented.)
        """
        ts = self.created_at
        if not ts:
            return 0
        try:
            iso = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
            dt = datetime.fromisoformat(iso)
            return int(dt.timestamp() * 1_000_000_000)
        except Exception:
            return 0

    @property
    def memory_region(self) -> str:
        """§8.3 memory_region — no §11.2 source; best-effort "" (nullable in spec)."""
        return ""

    @property
    def adapter_ids(self) -> list[str]:
        """§8.3 adapter_ids — best-effort.

        §11.2 has no dedicated adapter-id field; ``transforms`` is ``list[Any]``
        with no fixed schema. We fall back to ``source_hashes`` (the closest
        identifier-bearing field for an adapter materialization), str-coerced.
        """
        return [str(h) for h in self.source_hashes]

    @property
    def tensor_roles(self) -> list[str]:
        """§8.3 tensor_roles — best-effort from §11.2 transforms.

        ``transforms`` is ``list[Any]`` with no declared schema, so we cannot
        extract structured roles; we str-coerce each transform entry. Empty
        ``transforms`` yields ``[]`` (the §8.3 default for a non-tensor record).
        """
        return [str(t) for t in self.transforms]

    @property
    def evidence_ids(self) -> list[str]:
        """§8.3 evidence_ids ← §11.2 input_records (the upstream record refs)."""
        return [str(r) for r in self.input_records]

    @property
    def context_hash(self) -> str:
        """§8.3 context_hash — no §11.2 source; best-effort "" (nullable in spec)."""
        return ""

    @property
    def rollback_pointer(self) -> str:
        """§8.3 rollback_pointer (single) ← first of §11.2 rollback_refs, else ""."""
        return self.rollback_refs[0] if self.rollback_refs else ""

    def to_dict_v2(self) -> dict:
        """Emit the ADR-0002 §8.3 minimum-field key set.

        Distinct from ``to_dict()`` (which emits the §11.2 names via
        ``asdict()``); this never mutates the §11.2 output.
        """
        return {
            "record_id": self.record_id,
            "artifact_kind": self.artifact_kind,
            "source_hash": self.source_hash,
            "target_runtime": self.target_runtime,
            "materialized_at_ns": self.materialized_at_ns,
            "memory_region": self.memory_region,
            "adapter_ids": self.adapter_ids,
            "tensor_roles": self.tensor_roles,
            "evidence_ids": self.evidence_ids,
            "context_hash": self.context_hash,
            "status": self.status,
            "rollback_pointer": self.rollback_pointer,
        }


if __name__ == "__main__":
    rec = MaterializationRecord(
        materialization_id="mat-1",
        materialization_type="response",
        source_refs=["draft:abc"],
        source_hashes=["sha256:deadbeef"],
        owning_role="responder",
        privacy_class="internal",
        confidence=0.91,
        created_at="2026-06-01T00:00:00Z",
        retention_mode="session",
        status="committed",
    )
    d = rec.to_dict()
    assert d["materialization_type"] == "response"
    assert d["status"] == "committed"
    assert MaterializationRecord().status == "planned"
    try:
        rec.status = "revoked"  # type: ignore[misc]
        raise SystemExit("FAIL: record is not frozen")
    except SystemExit:
        raise
    except Exception:
        pass

    # --- ADR-0002 §8.3 alias coverage (populated record) ---
    v2 = rec.to_dict_v2()
    expected_v2_keys = {
        "record_id", "artifact_kind", "source_hash", "target_runtime",
        "materialized_at_ns", "memory_region", "adapter_ids", "tensor_roles",
        "evidence_ids", "context_hash", "status", "rollback_pointer",
    }
    assert set(v2.keys()) == expected_v2_keys, set(v2.keys()) ^ expected_v2_keys
    assert v2["record_id"] == "mat-1"
    assert v2["artifact_kind"] == "response"
    assert v2["source_hash"] == "sha256:deadbeef"
    assert v2["status"] == "committed"
    assert isinstance(v2["materialized_at_ns"], int) and v2["materialized_at_ns"] > 0
    # §11.2 output is unchanged by §8.3 additions
    assert "materialization_id" in d and "record_id" not in d

    # --- bare record: empty-list aliases must NOT raise (the break case) ---
    bare = MaterializationRecord()
    bv2 = bare.to_dict_v2()
    assert set(bv2.keys()) == expected_v2_keys
    assert bv2["source_hash"] == ""
    assert bv2["rollback_pointer"] == ""
    assert bv2["materialized_at_ns"] == 0
    assert bv2["adapter_ids"] == [] and bv2["tensor_roles"] == []
    assert bv2["status"] == "planned"

    print("MaterializationRecord OK:", d)
    print("§8.3 to_dict_v2 OK:", v2)
    print("§8.3 bare-record OK:", bv2)
