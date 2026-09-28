"""Offline, staged schema-1 (agent-relay 0.1.0) -> schema-2 migration.

Original event and blob bytes are retained. The original authority is fenced
before a new store is published; the new store remains RECOVERY_ONLY. Rollback
before activation retires the target before releasing the original to recovery.
Rollback after activation is refused instead of discarding newer effects.

No automatic discovery of earlier standalone/other-brand relay databases.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import sqlite3
import time
from .codec import canonical, digest, strict_loads, text
from .errors import RelayError, require
from .network import private_file
from .store import SCHEMA, Store, fsync_dir, private_write, wal_fixed

MARKER = "MIGRATION_FENCE.json"
MANIFEST = "MIGRATION_FROM_V1.json"


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    temp = path.with_name("." + path.name + "." + secrets.token_hex(8))
    private_write(temp, canonical(value))
    try:
        os.replace(temp, path)
        fsync_dir(path.parent)
    finally:
        temp.unlink(missing_ok=True)


def checked_source(home: Path) -> tuple[Path, dict]:
    home = home.expanduser().absolute()
    require(home.is_dir() and not home.is_symlink(), "MIGRATION_SOURCE", "source must be a real existing private store")
    st=home.stat()
    require(st.st_uid == os.geteuid() and not (stat.S_IMODE(st.st_mode) & 0o077), "MIGRATION_SOURCE", "source directory must be owner-only")
    for name in ("owner.key", "store.json", "relay.sqlite3"):
        private_file(home / name)
    config = strict_loads((home / "store.json").read_bytes())
    require(config.get("schema") == 1 and config.get("profile") == "single-host-trusted-workers",
            "MIGRATION_UNSUPPORTED", "only the supplied 0.1.0 schema-1 store is supported; no heuristic import")
    require(config.get("journal") in ("wal", "delete"), "MIGRATION_SOURCE", "invalid journal mode")
    require(config["journal"] != "wal" or wal_fixed(), "SQLITE_WAL_UNPATCHED", "use a patched linked SQLite before opening a WAL source")
    return home.resolve(), config


@contextmanager
def home_lock(home: Path):
    fd = os.open(home / "service.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RelayError("SERVICE_RUNNING", "stop the relevant service before migration/rollback") from exc
        yield
    finally:
        os.close(fd)


@contextmanager
def legacy_connection(home: Path, config: dict, write=False):
    conn = sqlite3.connect(f"{(home / 'relay.sqlite3').as_uri()}?mode={'rw' if write else 'ro'}", uri=True, isolation_level=None)
    try:
        require(conn.execute("PRAGMA user_version").fetchone()[0] == 1, "MIGRATION_UNSUPPORTED", "legacy schema mismatch")
        require(conn.execute("PRAGMA journal_mode").fetchone()[0] == config["journal"], "STORE_CONFIG", "source journal mode differs")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA trusted_schema=OFF")
        if write:
            conn.execute(f"PRAGMA synchronous={'FULL' if config['journal']=='wal' else 'EXTRA'}")
            if os.uname().sysname == "Darwin":
                conn.execute("PRAGMA fullfsync=ON")
            conn.execute("BEGIN IMMEDIATE")
        else:
            conn.execute("BEGIN")
        yield conn
        conn.commit()
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def history_fingerprint(conn, prefix: int | None = None) -> dict:
    h = hashlib.sha256()
    rows = conn.execute("SELECT seq,previous,hash,body FROM events WHERE seq<=? ORDER BY seq", (prefix if prefix is not None else 2**63-1,))
    count = 0
    head = "0" * 64
    for seq, previous, chain, raw in rows:
        # Includes exact historical UTF-8 event bytes, not a reserialized replacement.
        b = raw.encode("utf-8")
        h.update(seq.to_bytes(8, "big") + bytes.fromhex(previous) + bytes.fromhex(chain) + len(b).to_bytes(8, "big") + b)
        head = chain
        count += 1
    return {"events": count, "head": head, "exact_event_bytes_sha256": h.hexdigest()}


def validate_legacy(conn) -> dict:
    from .codec import decode_blob
    require(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "MIGRATION_CORRUPT", "SQLite integrity failed")
    require(not conn.execute("PRAGMA foreign_key_check").fetchall(), "MIGRATION_CORRUPT", "foreign key failure")
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    require(names == {"meta", "events", "objects", "commands", "blobs"}, "MIGRATION_UNSUPPORTED", "unexpected source table layout")
    # Replay checks original hash chain, blob references, command receipts and projections.
    projections, commands = Store._replay(None, conn)
    actual = {(k, i): (w, r, json.loads(d)) for k, i, w, r, d in conn.execute("SELECT kind,id,workflow,rev,data FROM objects")}
    require(projections == actual, "PROJECTION_DRIFT", "source projections differ from its journal")
    actual_commands = [(a, i, h, json.loads(r), n) for a, i, h, r, n in conn.execute("SELECT actor,id,request_hash,response,event_seq FROM commands ORDER BY event_seq")]
    require(commands == actual_commands, "COMMAND_DRIFT", "source command receipts differ")
    blobs = hashlib.sha256()
    count = 0
    for key, codec, size, data in conn.execute("SELECT hash,codec,size,data FROM blobs ORDER BY hash"):
        decode_blob(codec, data, size, key)
        blobs.update(canonical({"hash": key, "codec": codec, "size": size, "stored_sha256": digest(data)}))
        count += 1
    return {**history_fingerprint(conn), "objects": len(actual), "blob_count": count,
            "exact_stored_blobs_sha256": blobs.hexdigest()}


def plan(source: Path, destination: Path) -> dict:
    source, config = checked_source(source)
    destination = destination.expanduser().resolve(strict=False)
    require(not destination.exists(), "ALREADY_EXISTS", "destination must be new")
    require(not destination.is_relative_to(source), "MIGRATION_PATH", "destination must be outside the source store")
    with home_lock(source), legacy_connection(source, config) as conn:
        fingerprint = validate_legacy(conn)
        mode = conn.execute("SELECT value FROM meta WHERE key='mode'").fetchone()[0]
    return {"migration": "schema1-to-schema2", "source": str(source), "destination": str(destination),
            "source_schema": 1, "target_schema": SCHEMA, "source_mode": mode, "source_authority": config["authority_id"],
            "source_fingerprint": fingerprint, "effects_dispatched": 0, "destination_state": "RECOVERY_ONLY",
            "rollback": "only before activation and before any new target command beyond migration record"}


def prepare(source: Path, destination: Path, *, fault=None) -> dict:
    source, config = checked_source(source)
    destination = destination.expanduser().resolve(strict=False)
    require(not destination.exists(), "ALREADY_EXISTS", "destination must be new")
    require(not destination.is_relative_to(source), "MIGRATION_PATH", "destination must be outside source")
    destination.parent.mkdir(parents=True, exist_ok=True)
    def checkpoint(step):
        if fault is not None:
            fault(step)  # injectable test harness; no environment-triggered production crash hook
    with home_lock(source):
        require(not (source / MARKER).exists(), "MIGRATION_PENDING", "an earlier migration has a fence record; inspect/rollback rather than starting another")
        with legacy_connection(source, config) as conn:
            fingerprint = validate_legacy(conn)
            mode = conn.execute("SELECT value FROM meta WHERE key='mode'").fetchone()[0]
            require(mode in {"ACTIVE", "RECOVERY_ONLY"}, "MIGRATION_HELD", "source already held")
        mid = "migration-" + secrets.token_hex(12)
        stage = destination.with_name("." + destination.name + "." + mid)
        marker = {"version": 1, "id": mid, "source": str(source), "destination": str(destination),
                  "stage": str(stage), "source_authority": config["authority_id"], "source_fingerprint": fingerprint,
                  "original_mode": mode, "phase": "FENCING", "created_at": time.time()}
        atomic_json(source / MARKER, marker)
        checkpoint("before_fence")
        with legacy_connection(source, config, True) as conn:
            conn.execute("UPDATE meta SET value='MIGRATION_HOLD' WHERE key='mode'")
            conn.execute("UPDATE meta SET value=? WHERE key='generation'", (secrets.token_hex(16),))
        marker["phase"] = "FENCED"
        atomic_json(source / MARKER, marker)
        checkpoint("after_fence")
        new = Store.initialize(stage, "auto")
        # Make even the unpublished temporary target fail closed before copy.
        with new.connection(True) as conn:
            conn.execute("UPDATE meta SET value='RECOVERY_ONLY' WHERE key='mode'")
        marker["phase"] = "COPYING"
        atomic_json(source / MARKER, marker)
        with legacy_connection(source, config) as src:
            dst = sqlite3.connect(new.db, isolation_level=None)
            try:
                src.backup(dst)
                dst.execute(f"PRAGMA journal_mode={new.config['journal']}")
                dst.execute("PRAGMA synchronous=EXTRA" if new.config["journal"] == "delete" else "PRAGMA synchronous=FULL")
                dst.execute("BEGIN IMMEDIATE")
                dst.execute(f"PRAGMA user_version={SCHEMA}")
                dst.execute("UPDATE meta SET value=? WHERE key='schema'", (str(SCHEMA),))
                dst.execute("UPDATE meta SET value='RECOVERY_ONLY' WHERE key='mode'")
                dst.execute("UPDATE meta SET value=? WHERE key='generation'", (secrets.token_hex(16),))
                dst.commit()
            finally:
                dst.close()
        checkpoint("after_copy")
        new.doctor(scrub=True)
        with new.connection() as conn:
            require(history_fingerprint(conn) == {k: fingerprint[k] for k in ("events", "head", "exact_event_bytes_sha256")},
                    "MIGRATION_HASH", "historical event bytes changed")
        record = {"source_authority": config["authority_id"], "source_schema": 1, "target_schema": SCHEMA,
                  "source_fingerprint": fingerprint, "source_home": str(source), "target_home": str(destination),
                  "created_at": time.time(), "effects_dispatched": 0, "historical_evidence_upgraded": False}
        result = new.command(new.key, mid, "_migration.record", record,
                             lambda tx, actor, now: {"migration": tx.put("migration", mid, "*", record, 0)})
        marker.update(phase="PREPARED", target_authority=new.config["authority_id"], target_initial_head=new.doctor()["chain_head"],
                      target_initial_event_count=result["event_seq"])
        private_write(stage / MANIFEST, canonical(marker))
        new.doctor(scrub=True)
        fsync_dir(stage)
        checkpoint("before_publish")
        require(not destination.exists(), "ALREADY_EXISTS", "destination appeared during migration")
        os.rename(stage, destination)
        fsync_dir(destination.parent)
        atomic_json(source / MARKER, marker)
        checkpoint("after_publish")
        return {"prepared": True, "source_fenced": True, "target_mode": "RECOVERY_ONLY", "manifest": marker,
                "next": "run acceptance evaluation; reconcile historical actions; explicitly activate, or rollback before activation"}


def rollback(source: Path, destination: Path) -> dict:
    source, config = checked_source(source)
    destination = destination.expanduser().resolve(strict=False)
    with home_lock(source):
        require((source / MARKER).is_file(), "MIGRATION_MISSING", "no migration fence record")
        marker = strict_loads((source / MARKER).read_bytes())
        require(marker["destination"] == str(destination), "MIGRATION_TARGET", "destination differs from original decision")
        require(marker["phase"] != "ACTIVATED", "ROLLBACK_UNSAFE", "target activated; use forward recovery, never discard newer effects")
        with legacy_connection(source, config) as conn:
            require(history_fingerprint(conn) == {k: marker["source_fingerprint"][k] for k in ("events", "head", "exact_event_bytes_sha256")},
                    "SOURCE_DIVERGED", "source changed after migration began; retain both histories")
        target_path = destination if destination.exists() else Path(marker["stage"])
        if target_path.exists():
            with home_lock(target_path):
                # A crash during copy may leave schema 1; it still must be retired before source release.
                conn = sqlite3.connect(target_path / "relay.sqlite3", isolation_level=None)
                try:
                    current_mode = conn.execute("SELECT value FROM meta WHERE key='mode'").fetchone()[0]
                    require(current_mode in {"RECOVERY_ONLY", "MIGRATION_HOLD", "RETIRED"}, "ROLLBACK_UNSAFE", "target is active")
                    # Even a crash before the source marker is finalized must not
                    # discard a later receipt/command appended to the staged target.
                    initial=marker.get("target_initial_head")
                    if initial is None:
                        prefix=marker["source_fingerprint"]["events"]
                        require(history_fingerprint(conn,prefix) == {k:marker["source_fingerprint"][k] for k in ("events","head","exact_event_bytes_sha256")},
                                "ROLLBACK_UNSAFE", "target history is not the copied source")
                        tail=conn.execute("SELECT body FROM events WHERE seq>? ORDER BY seq",(prefix,)).fetchall()
                        require(len(tail)<=1, "ROLLBACK_UNSAFE", "target has later commands")
                        if tail:
                            body=strict_loads(tail[0][0])
                            require(body.get("op")=="_migration.record" and body.get("command_id")==marker["id"],
                                    "ROLLBACK_UNSAFE", "target suffix is not its migration record")
                    if "target_initial_head" in marker:
                        head = conn.execute("SELECT value FROM meta WHERE key='head'").fetchone()[0]
                        require(head == marker["target_initial_head"], "ROLLBACK_UNSAFE", "target has subsequent commands; preserve and reconcile both histories")
                    conn.execute("PRAGMA synchronous=EXTRA")
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("UPDATE meta SET value='RETIRED' WHERE key='mode'")
                    conn.execute("UPDATE meta SET value=? WHERE key='generation'", (secrets.token_hex(16),))
                    conn.commit()
                finally:
                    conn.close()
                atomic_json(target_path / "RETIRED_BY_ROLLBACK.json", {"migration": marker["id"], "at": time.time()})
        # Never restore a pre-migration lease generation or automatically dispatch old work.
        with legacy_connection(source, config, True) as conn:
            conn.execute("UPDATE meta SET value='RECOVERY_ONLY' WHERE key='mode'")
            conn.execute("UPDATE meta SET value=? WHERE key='generation'", (secrets.token_hex(16),))
        marker["phase"] = "ROLLED_BACK"
        marker["rolled_back_at"] = time.time()
        atomic_json(source / MARKER, marker)
        return {"rolled_back": True, "source_mode": "RECOVERY_ONLY", "target_mode": "RETIRED" if target_path.exists() else "NOT_PUBLISHED",
                "old_worker_credentials_valid": False, "effects_dispatched": 0,
                "next": "use the archived 0.1.0 runtime; inspect/reconcile; owner must explicitly restore.resume"}


def activate(source: Path, destination: Path, evaluation: dict, reconciliation_report: str) -> dict:
    """Called after certification.evaluate, never from an unauthenticated worker."""
    from .certification import runtime_identity
    from .controller import Controller
    require(evaluation.get("ready") is True and evaluation.get("runtime_sha256") == runtime_identity()[0],
            "ACCEPTANCE_HELD", "current candidate needs evaluated gates and reviewed exceptions")
    source, config = checked_source(source)
    destination = destination.expanduser().resolve(strict=False)
    with home_lock(source), home_lock(destination):
        marker = strict_loads((source / MARKER).read_bytes())
        manifest = strict_loads((destination / MANIFEST).read_bytes())
        require(marker["id"] == manifest["id"] and marker["destination"] == str(destination)
                and marker["phase"] in {"PREPARED", "COPYING"}, "MIGRATION_STATE", "not a prepared matching migration")
        with legacy_connection(source, config) as conn:
            require(conn.execute("SELECT value FROM meta WHERE key='mode'").fetchone()[0] == "MIGRATION_HOLD", "SOURCE_NOT_FENCED", "original authority was reopened")
            require(history_fingerprint(conn)["head"] == marker["source_fingerprint"]["head"], "SOURCE_DIVERGED", "original source changed")
        new = Store(destination)
        require(new.doctor(scrub=True)["mode"] == "RECOVERY_ONLY", "MIGRATION_STATE", "destination is not held")
        report = text(reconciliation_report, "reconciliation_report")
        result = Controller(new).command(new.key, "activate-" + marker["id"], "restore.resume", {
            "original_authority_fenced": True,
            "reconciliation_report": report + "\nGate evaluation SHA-256: " + digest(canonical(evaluation)),
        })
        # If interrupted after commit, retry activation is not automatic; head is newer,
        # rollback is denied by mode, and the original stays held.
        marker["phase"] = "ACTIVATED"
        marker["activated_at"] = time.time()
        marker["gate_evaluation_sha256"] = digest(canonical(evaluation))
        atomic_json(destination / MANIFEST, marker)
        atomic_json(source / MARKER, marker)
        return {**result, "source_mode": "MIGRATION_HOLD", "rollback_after_activation": "REFUSED_PRESERVE_NEWER_EFFECTS"}
