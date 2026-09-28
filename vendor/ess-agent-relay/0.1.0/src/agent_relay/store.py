"""Transactional event store, explicit connection lifetime, tokens and replay.

The local OS account holding owner.key is trusted. Hash chains detect accidental
corruption; they do not authenticate a history against an administrator who can
rewrite the database and the key. No provider token is stored in an event.
"""
from __future__ import annotations
from contextlib import contextmanager
from importlib.resources import files
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import time
from typing import Any, Callable, Iterator
from .codec import canonical, digest, object_digest, decode_blob, encode_blob, ident, strict_loads
from .errors import RelayError, require

SCHEMA = 1
ZERO = "0" * 64


def wal_fixed(version: tuple[int, ...] | None = None) -> bool:
    v = version or sqlite3.sqlite_version_info
    return v >= (3, 51, 3) or (v[:2] == (3, 50) and v >= (3, 50, 7)) or (v[:2] == (3, 44) and v >= (3, 44, 6))


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_write(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    fsync_dir(path.parent)


class Transaction:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.changes: dict[tuple[str, str], dict[str, Any]] = {}
        self.new_blobs: list[str] = []

    def get(self, kind: str, id: str, optional: bool = False) -> dict | None:
        row = self.conn.execute("SELECT rev,workflow,data FROM objects WHERE kind=? AND id=?", (kind, id)).fetchone()
        if row is None:
            if optional:
                return None
            raise RelayError("NOT_FOUND", f"{kind}:{id}")
        return {"id": id, "rev": row[0], "workflow": row[1], **json.loads(row[2])}

    def scan(self, kind: str, workflow: str | None = None) -> list[dict]:
        if workflow is None:
            rows = self.conn.execute("SELECT id,rev,workflow,data FROM objects WHERE kind=? ORDER BY rowid", (kind,))
        else:
            rows = self.conn.execute("SELECT id,rev,workflow,data FROM objects WHERE kind=? AND workflow=? ORDER BY rowid", (kind, workflow))
        return [{"id": r[0], "rev": r[1], "workflow": r[2], **json.loads(r[3])} for r in rows]

    def unresolved_actions(self, workflow: str | None = None) -> list[dict]:
        sql = "SELECT id,rev,workflow,data FROM objects WHERE kind='action' AND json_extract(data,'$.outcome')='UNKNOWN' AND json_extract(data,'$.dispatch')!='CANCELED_BEFORE_SEND'"
        params = ()
        if workflow is not None:
            sql += " AND workflow=?"
            params = (workflow,)
        return [{"id":r[0],"rev":r[1],"workflow":r[2],**json.loads(r[3])} for r in self.conn.execute(sql,params)]

    def active_leases(self, now: float) -> list[dict]:
        sql = "SELECT id,rev,workflow,data FROM objects WHERE kind='lease' AND CAST(json_extract(data,'$.expires') AS REAL)>?"
        return [{"id":r[0],"rev":r[1],"workflow":r[2],**json.loads(r[3])} for r in self.conn.execute(sql,(now,))]

    def recent(self, kind: str, workflow: str, limit: int=16) -> list[dict]:
        rows=self.conn.execute("SELECT id,rev,workflow,data FROM objects WHERE kind=? AND workflow=? ORDER BY rowid DESC LIMIT ?",(kind,workflow,limit))
        return list(reversed([{"id":r[0],"rev":r[1],"workflow":r[2],**json.loads(r[3])} for r in rows]))

    def put(self, kind: str, id: str, workflow: str, data: dict, expected: int | None = None) -> dict:
        current = self.get(kind, id, True)
        rev = current["rev"] if current else 0
        if expected is not None:
            require(rev == expected, "STALE_REVISION", f"{kind}:{id}: expected {expected}, current {rev}")
        body = {k: v for k, v in data.items() if k not in ("id", "rev", "workflow")}
        newrev = rev + 1
        self.conn.execute("INSERT INTO objects VALUES(?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET workflow=excluded.workflow,rev=excluded.rev,data=excluded.data",
                          (kind, id, workflow, newrev, canonical(body).decode()))
        key = (kind, id)
        before = self.changes[key]["before"] if key in self.changes else rev
        self.changes[key] = {"kind": kind, "id": id, "workflow": workflow,
                             "before": before, "rev": newrev, "data": body}
        return {"id": id, "rev": newrev, "workflow": workflow, **body}

    def blob(self, raw: bytes) -> str:
        key = digest(raw)
        if self.conn.execute("SELECT 1 FROM blobs WHERE hash=?", (key,)).fetchone() is None:
            codec, payload = encode_blob(raw)
            total = int(self.conn.execute("SELECT value FROM meta WHERE key='blob_bytes'").fetchone()[0])
            limit = int(self.conn.execute("SELECT value FROM meta WHERE key='blob_quota'").fetchone()[0])
            require(total + len(payload) <= limit, "STORE_QUOTA", "blob quota reached; do not silently delete retained evidence")
            self.conn.execute("INSERT INTO blobs VALUES(?,?,?,?)", (key, codec, len(raw), payload))
            self.conn.execute("UPDATE meta SET value=? WHERE key='blob_bytes'", (str(total + len(payload)),))
            self.new_blobs.append(key)
        return key

    def read_blob(self, key: str) -> bytes:
        row = self.conn.execute("SELECT codec,data,size FROM blobs WHERE hash=?", (key,)).fetchone()
        require(row is not None, "MISSING_BLOB", key)
        return decode_blob(row[0], row[1], row[2], key)


class Store:
    def __init__(self, home: str | Path, clock: Callable[[], float] = time.time):
        rawhome = Path(home).expanduser().absolute()
        require(not rawhome.is_symlink(), "UNSAFE_HOME", "home cannot be a symlink")
        self.home = rawhome.resolve()
        self.db = self.home / "relay.sqlite3"
        self.clock = clock
        require(self.db.is_file() and not self.db.is_symlink(), "NOT_INITIALIZED", f"run relayctl --home {self.home} init")
        self._check_private()
        self.key = (self.home / "owner.key").read_text().strip()
        self.config = strict_loads((self.home / "store.json").read_bytes())
        require(self.config.get("schema") == SCHEMA, "SCHEMA_VERSION", "unsupported store metadata")

    def _check_private(self):
        for path in (self.home, self.db, self.home / "owner.key", self.home / "store.json"):
            s = path.lstat()
            require(not stat.S_ISLNK(s.st_mode) and s.st_uid == os.geteuid()
                    and not (stat.S_IMODE(s.st_mode) & 0o077),
                    "INSECURE_PERMISSIONS", f"owner-only access required: {path}")

    @classmethod
    def initialize(cls, home: str | Path, journal: str = "auto", blob_quota: int = 1024**3) -> "Store":
        home = Path(home).expanduser().absolute()
        require(not home.exists(), "ALREADY_EXISTS", "initialization never overwrites a directory or existing relay")
        require(sqlite3.sqlite_version_info >= (3, 37, 0), "SQLITE_VERSION", "SQLite 3.37+ required for STRICT tables")
        require(journal in ("auto", "wal", "delete"), "JOURNAL_MODE", journal)
        selected = "wal" if (journal == "wal" or journal == "auto" and wal_fixed()) else "delete"
        require(selected != "wal" or wal_fixed(), "SQLITE_WAL_UNPATCHED", "WAL requires a documented fixed SQLite; use --journal delete or a patched Python build")
        require(type(blob_quota) is int and blob_quota > 0, "INVALID_FIELD", "invalid quota")
        home.mkdir(parents=True, mode=0o700)
        os.chmod(home, 0o700)
        private_write(home / "owner.key", (secrets.token_urlsafe(48) + "\n").encode())
        config = {"schema": SCHEMA, "journal": selected, "authority_id": secrets.token_hex(16),
                  "profile": "single-host-trusted-workers", "created_at": time.time()}
        private_write(home / "store.json", canonical(config))
        private_write(home / "relay.sqlite3", b"")
        conn = sqlite3.connect(home / "relay.sqlite3", isolation_level=None)
        try:
            conn.execute(f"PRAGMA journal_mode={selected}")
            conn.execute(f"PRAGMA synchronous={'FULL' if selected == 'wal' else 'EXTRA'}")
            if os.uname().sysname == "Darwin":
                conn.execute("PRAGMA fullfsync=ON")
                conn.execute("PRAGMA checkpoint_fullfsync=ON")
            conn.executescript(files("agent_relay").joinpath("schema.sql").read_text())
            values = {"schema": "1", "head": ZERO, "last_wall": "0", "blob_bytes": "0",
                      "blob_quota": str(blob_quota), "mode": "ACTIVE", "generation": secrets.token_hex(16),
                      "last_scrub": "0", "journal_bytes": "0", "journal_quota": str(256*1024*1024)}
            conn.executemany("INSERT INTO meta VALUES(?,?)", values.items())
        finally:
            conn.close()
        fsync_dir(home)
        return cls(home)

    @contextmanager
    def connection(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        self._check_private()
        require(self.config["journal"] != "wal" or wal_fixed(), "SQLITE_WAL_UNPATCHED", "linked SQLite changed to an unpatched build")
        conn = sqlite3.connect(f"{self.db.as_uri()}?mode=rw", uri=True, isolation_level=None, timeout=10)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=10000")
            conn.execute(f"PRAGMA synchronous={'FULL' if self.config['journal'] == 'wal' else 'EXTRA'}")
            conn.execute("PRAGMA trusted_schema=OFF")
            if os.uname().sysname == "Darwin":
                conn.execute("PRAGMA fullfsync=ON")
                conn.execute("PRAGMA checkpoint_fullfsync=ON")
            require(conn.execute("PRAGMA journal_mode").fetchone()[0] == self.config["journal"], "STORE_CONFIG", "journal mode changed")
            require(conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA, "SCHEMA_VERSION", "unsupported database schema; do not write")
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            conn.commit()
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    def worker_token(self, grant: dict, generation: str) -> str:
        value = f"rly1.{generation}.{grant['id']}"
        sig = hmac.new(self.key.encode(), value.encode(), hashlib.sha256).hexdigest()
        return value + "." + sig

    def authenticate(self, tx: Transaction, token: str, now: float) -> dict:
        require(type(token) is str, "AUTH", "missing credential")
        if hmac.compare_digest(token, self.key):
            return {"id": "owner", "role": "owner", "workflow": "*"}
        parts = token.split(".")
        require(len(parts) == 4 and parts[0] == "rly1", "AUTH", "invalid credential")
        generation = tx.conn.execute("SELECT value FROM meta WHERE key='generation'").fetchone()[0]
        require(parts[1] == generation, "AUTH_GENERATION", "credential belongs to another authority generation")
        grant = tx.get("grant", parts[2], True)
        require(grant is not None and not grant["revoked"] and grant["expires"] > now,
                "AUTH", "credential is revoked, expired, or unknown")
        require(hmac.compare_digest(token, self.worker_token(grant, generation)), "AUTH", "invalid signature")
        return {"id": grant["id"], "role": "worker", "workflow": grant["workflow"]}

    def command(self, token: str, command_id: str, op: str, payload: dict,
                apply: Callable[[Transaction, dict, float], dict]) -> dict:
        ident(command_id, "command_id")
        require(type(payload) is dict, "INVALID_FIELD", "payload must be an object")
        request_hash = object_digest({"op": op, "payload": payload})
        with self.connection(True) as conn:
            tx = Transaction(conn)
            now = self.clock()
            actor = self.authenticate(tx, token, now)
            last = float(conn.execute("SELECT value FROM meta WHERE key='last_wall'").fetchone()[0])
            require(now + 1 >= last, "CLOCK_ROLLBACK", "wall clock moved backwards; inspect before resuming writes")
            old = conn.execute("SELECT request_hash,response FROM commands WHERE actor=? AND id=?", (actor["id"], command_id)).fetchone()
            if old:
                require(old[0] == request_hash, "IDEMPOTENCY_CONFLICT", "command ID reused with a different payload")
                return json.loads(old[1])
            mode = conn.execute("SELECT value FROM meta WHERE key='mode'").fetchone()[0]
            allowed_recovery = {"restore.resume", "action.receipt", "action.resolve", "grant.revoke"}
            require(mode == "ACTIVE" or op in allowed_recovery, "RECOVERY_ONLY", "authority is held for operator reconciliation")
            result = apply(tx, actor, max(now, last))
            previous = conn.execute("SELECT value FROM meta WHERE key='head'").fetchone()[0]
            seq = conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM events").fetchone()[0]
            response = {**result, "event_seq": seq}
            body = {"schema": SCHEMA, "seq": seq, "at": now, "actor": actor["id"],
                    "command_id": command_id, "op": op, "request_hash": request_hash,
                    "changes": list(tx.changes.values()), "blobs": tx.new_blobs, "response": response}
            encoded = canonical(body)
            used = int(conn.execute("SELECT value FROM meta WHERE key='journal_bytes'").fetchone()[0])
            quota = int(conn.execute("SELECT value FROM meta WHERE key='journal_quota'").fetchone()[0])
            recovery_ops = {"action.receipt","action.resolve","workflow.cancel","workflow.settle_cancel",
                            "attempt.release","grant.revoke","restore.resume","_process.observed","_process.output","_verify.finish"}
            ceiling = quota + (64*1024*1024 if op in recovery_ops else 0)
            require(used + len(encoded) <= ceiling, "JOURNAL_QUOTA", "logical journal budget reached; new work is held; preserve history and perform controlled archival/rotation")
            conn.execute("UPDATE meta SET value=? WHERE key='journal_bytes'", (str(used+len(encoded)),))
            chain = digest(bytes.fromhex(previous) + encoded)
            conn.execute("INSERT INTO events VALUES(?,?,?,?)", (seq, previous, chain, encoded.decode()))
            conn.execute("INSERT INTO commands VALUES(?,?,?,?,?)", (actor["id"], command_id, request_hash, canonical(response).decode(), seq))
            conn.execute("UPDATE meta SET value=? WHERE key='head'", (chain,))
            conn.execute("UPDATE meta SET value=? WHERE key='last_wall'", (str(max(now, last)),))
            return response

    def read(self, token: str, fn: Callable[[Transaction, dict], Any]) -> Any:
        with self.connection() as conn:
            tx = Transaction(conn)
            actor = self.authenticate(tx, token, self.clock())
            return fn(tx, actor)

    def doctor(self, scrub: bool = False) -> dict:
        with self.connection() as conn:
            out = {"schema": conn.execute("PRAGMA user_version").fetchone()[0],
                   "sqlite": sqlite3.sqlite_version,
                   "sqlite_source_id": conn.execute("SELECT sqlite_source_id()").fetchone()[0],
                   "wal_fix_version_recognized": wal_fixed(),
                   "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
                   "synchronous": conn.execute("PRAGMA synchronous").fetchone()[0],
                   "foreign_keys": conn.execute("PRAGMA foreign_keys").fetchone()[0],
                   "mode": conn.execute("SELECT value FROM meta WHERE key='mode'").fetchone()[0],
                   "events": conn.execute("SELECT count(*) FROM events").fetchone()[0],
                   "blobs": conn.execute("SELECT count(*) FROM blobs").fetchone()[0],
                   "objects": conn.execute("SELECT count(*) FROM objects").fetchone()[0],
                   "blob_stored_bytes": int(conn.execute("SELECT value FROM meta WHERE key='blob_bytes'").fetchone()[0]),
                   "journal_logical_bytes": int(conn.execute("SELECT value FROM meta WHERE key='journal_bytes'").fetchone()[0]),
                   "journal_quota_bytes": int(conn.execute("SELECT value FROM meta WHERE key='journal_quota'").fetchone()[0]),
                   "scrub_scheduling": "full scrub is explicit; schedule periodic relayctl doctor --scrub",
                   "chain_head": conn.execute("SELECT value FROM meta WHERE key='head'").fetchone()[0]}
            if scrub:
                require(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLITE_INTEGRITY", "integrity_check failed")
                require(not conn.execute("PRAGMA foreign_key_check").fetchall(), "SQLITE_INTEGRITY", "foreign key violation")
                projections, commands = self._replay(conn)
                actual = {(k, id): (w, rev, json.loads(d)) for k, id, w, rev, d in conn.execute("SELECT kind,id,workflow,rev,data FROM objects")}
                require(projections == actual, "PROJECTION_DRIFT", "projection differs from immutable journal")
                for key, codec, size, data in conn.execute("SELECT hash,codec,size,data FROM blobs"):
                    decode_blob(codec, data, size, key)
                actual_commands = [(a, id, rh, json.loads(res), es) for a,id,rh,res,es in conn.execute("SELECT actor,id,request_hash,response,event_seq FROM commands ORDER BY event_seq")]
                require(commands == actual_commands, "COMMAND_DRIFT", "command receipts differ from history")
                out["full_scrub"] = "PASS"
        out["database_bytes"] = self.db.stat().st_size
        wal = Path(str(self.db) + "-wal")
        out["wal_bytes"] = wal.stat().st_size if wal.exists() else 0
        return out

    def _replay(self, conn):
        previous, seq = ZERO, 0
        projections, commands = {}, []
        for n, prev, hashval, raw in conn.execute("SELECT seq,previous,hash,body FROM events ORDER BY seq"):
            seq += 1
            require(n == seq and prev == previous and digest(bytes.fromhex(prev) + raw.encode()) == hashval,
                    "CHAIN_CORRUPT", f"event {n}")
            body = strict_loads(raw)
            require(body["schema"] == SCHEMA and body["seq"] == n and canonical(body).decode() == raw,
                    "EVENT_SCHEMA", f"unsupported or noncanonical event {n}")
            for c in body["changes"]:
                key = (c["kind"], c["id"])
                oldrev = projections[key][1] if key in projections else 0
                require(oldrev == c["before"] and c["rev"] > oldrev, "REPLAY_REVISION", f"event {n}")
                projections[key] = (c["workflow"], c["rev"], c["data"])
            for b in body["blobs"]:
                require(conn.execute("SELECT 1 FROM blobs WHERE hash=?", (b,)).fetchone() is not None, "MISSING_BLOB", b)
            commands.append((body["actor"], body["command_id"], body["request_hash"], body["response"], n))
            previous = hashval
        require(previous == conn.execute("SELECT value FROM meta WHERE key='head'").fetchone()[0], "CHAIN_CORRUPT", "head mismatch")
        return projections, commands

    def rebuild(self) -> dict:
        """Operator-only offline operation. Replays facts, never dispatches effects."""
        with self.connection(True) as conn:
            projections, commands = self._replay(conn)
            conn.execute("DELETE FROM objects")
            conn.execute("DELETE FROM commands")
            conn.executemany("INSERT INTO objects VALUES(?,?,?,?,?)", [(k,id,w,rev,canonical(d).decode()) for (k,id),(w,rev,d) in projections.items()])
            conn.executemany("INSERT INTO commands VALUES(?,?,?,?,?)", [(a,id,rh,canonical(r).decode(),seq) for a,id,rh,r,seq in commands])
        return {"objects_rebuilt": len(projections), "effects_dispatched": 0}

    def backup(self, destination: str | Path) -> dict:
        destination = Path(destination).expanduser().absolute()
        require(not destination.exists(), "ALREADY_EXISTS", "backup target exists")
        destination.mkdir(parents=True, mode=0o700)
        os.chmod(destination, 0o700)
        target = destination / "relay.sqlite3"
        private_write(target, b"")
        # SQLite's backup API copies committed WAL contents too; copying the DB file alone would not.
        with self.connection() as src:
            dst = sqlite3.connect(target)
            try:
                src.backup(dst)
            finally:
                dst.close()
        with target.open("rb") as f:
            os.fsync(f.fileno())
        manifest = {"schema": SCHEMA, "database_sha256": digest(target.read_bytes()),
                    "source_authority": self.config["authority_id"], "source_journal": self.config["journal"],
                    "created_at": self.clock(), "secret_keys_included": False,
                    "trust": "local integrity only; unsigned export"}
        private_write(destination / "backup.json", canonical(manifest))
        return manifest

    @classmethod
    def restore(cls, backup: str | Path, home: str | Path) -> "Store":
        backup = Path(backup)
        m = strict_loads((backup / "backup.json").read_bytes())
        require(digest((backup / "relay.sqlite3").read_bytes()) == m["database_sha256"], "BACKUP_HASH", "backup mismatch")
        # Creates a separate authority/key. Never replaces a running or historical store.
        new = cls.initialize(home, "auto")
        src = sqlite3.connect(f"{(backup / 'relay.sqlite3').resolve().as_uri()}?mode=ro", uri=True)
        dst = sqlite3.connect(new.db, isolation_level=None)
        try:
            src.backup(dst)
            dst.execute(f"PRAGMA journal_mode={new.config['journal']}")
            dst.execute("UPDATE meta SET value='RECOVERY_ONLY' WHERE key='mode'")
            dst.execute("UPDATE meta SET value=? WHERE key='generation'", (secrets.token_hex(16),))
        finally:
            src.close()
            dst.close()
        new.doctor(scrub=True)
        private_write(new.home / "RESTORE_REQUIRES_RECONCILIATION.json", canonical(m))
        return new

    @contextmanager
    def service_lock(self):
        """Exactly one daemon or offline maintenance owner per local home."""
        path = self.home / "service.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as e:
                raise RelayError("SERVICE_RUNNING", "stop the existing service before maintenance/start") from e
            yield
        finally:
            os.close(fd)
