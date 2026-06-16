#!/usr/bin/env python3
"""ATLAS Audit Export — nightly NDJSON exporter for the immutable audit chain.

Reads unexported rows from `audit_events`, writes them as NDJSON, and (optionally)
uploads to S3. Tracks the last-exported row id in a small state file so subsequent
runs are incremental.

Pre-export discipline:
    BEFORE writing any rows out, the script verifies the audit chain by re-
    computing every row's `row_hash` and confirming every `prev_hash` matches
    the previous row's `row_hash`. If verification fails, the export aborts
    with a non-zero exit code. This is the tripwire described in
    `apps/frontend/shell/docs/audit-retention-policy.md` section 5.

Cron usage (daily 03:00 local):
    0 3 * * * /usr/bin/env python3 /path/to/infrastructure/scripts/core/audit_export.py

Environment:
    ATLAS_SQLITE_PATH                Desktop SQLite path (required for export).
    ATLAS_AUDIT_EXPORT_STATE_DIR     Directory holding `last_exported_id.txt`
                                     (default: <sqlite_dir>/.audit_export_state).
    ATLAS_AUDIT_EXPORT_OUT_DIR       Local NDJSON output dir (default:
                                     <sqlite_dir>/audit-exports).
    ATLAS_AUDIT_S3_BUCKET            If set, upload NDJSON to s3://${bucket}/audit/...
                                     If unset, run in dry-run-export mode (file
                                     written locally; "would export" logged).
    ATLAS_AUDIT_S3_PREFIX            Optional key prefix under the bucket
                                     (default: "audit").

Exit codes:
    0  success (rows exported, or no new rows since last run)
    1  config / file IO error
    2  chain verification failed (TAMPER EVIDENCE — investigate immediately)
    3  S3 upload error

Owner: system-signal-engine
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

GENESIS_EVENT_ID = "GENESIS"
SCHEMA_ORDER = [
    "id",
    "tenant_id",
    "event_id",
    "actor",
    "event_type",
    "resource_type",
    "resource_id",
    "outcome",
    "ip_hash",
    "payload",
    "prev_hash",
    "row_hash",
    "recorded_at",
]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(obj: dict) -> str:
    """Match the TypeScript canonical-JSON serializer: keys sorted alphabetically."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def log(level: str, event: str, **fields: object) -> None:
    """Structured NDJSON log to stdout — matches the pino conventions in the TS app."""
    record = {
        "level": level,
        "time": int(datetime.now(tz=timezone.utc).timestamp() * 1000),
        "service": "atlas-audit-export",
        "event": event,
        **fields,
    }
    print(json.dumps(record, ensure_ascii=False), flush=True)


def resolve_db_path() -> Path:
    raw = os.environ.get("ATLAS_SQLITE_PATH", "").strip()
    if not raw:
        # Fall back to the canonical desktop default used by the TS client.
        home = Path.home()
        raw = str(home / "Library" / "Application Support" / "ATLAS" / "atlas.db")
    p = Path(raw)
    if not p.exists():
        log("error", "audit_export.db.missing", path=str(p))
        sys.exit(1)
    return p


def resolve_state_dir(db_path: Path) -> Path:
    override = os.environ.get("ATLAS_AUDIT_EXPORT_STATE_DIR", "").strip()
    if override:
        d = Path(override)
    else:
        d = db_path.parent / ".audit_export_state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_out_dir(db_path: Path) -> Path:
    override = os.environ.get("ATLAS_AUDIT_EXPORT_OUT_DIR", "").strip()
    if override:
        d = Path(override)
    else:
        d = db_path.parent / "audit-exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_high_watermark(state_dir: Path) -> str | None:
    f = state_dir / "last_exported_id.txt"
    if not f.exists():
        return None
    text = f.read_text(encoding="utf-8").strip()
    return text or None


def save_high_watermark(state_dir: Path, last_id: str) -> None:
    f = state_dir / "last_exported_id.txt"
    f.write_text(last_id + "\n", encoding="utf-8")


def open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # READ-ONLY discipline: we never UPDATE or DELETE audit_events from this script.
    # Even though sqlite3 doesn't enforce a read-only mode at the connection level
    # for an already-open file, we simply do not issue any DML against audit_events.
    return conn


def fetch_all_rows(conn: sqlite3.Connection) -> list[dict]:
    """Pull the whole audit_events table for chain verification + export decision."""
    cursor = conn.execute(
        "SELECT id, tenant_id, event_id, actor, event_type, resource_type, "
        "resource_id, outcome, ip_hash, payload, prev_hash, row_hash, recorded_at "
        "FROM audit_events "
        "ORDER BY recorded_at ASC, id ASC"
    )
    return [dict(row) for row in cursor.fetchall()]


def verify_chain(rows: list[dict]) -> tuple[bool, str | None, str | None]:
    """Mirror of `verifyChain()` in src/lib/audit/audit-verifier.ts.

    Returns (valid, broken_at_id, reason).
    """
    if not rows:
        return False, None, "audit_events table is empty (no genesis row seeded)"

    genesis = rows[0]
    expected_genesis_hash = sha256(GENESIS_EVENT_ID)

    if genesis["event_id"] != GENESIS_EVENT_ID:
        return (
            False,
            genesis["id"],
            f"expected first row event_id={GENESIS_EVENT_ID!r}, got {genesis['event_id']!r}",
        )
    if genesis["prev_hash"] is not None:
        return (
            False,
            genesis["id"],
            f"genesis prev_hash must be NULL, got {genesis['prev_hash']!r}",
        )
    if genesis["row_hash"] != expected_genesis_hash:
        return (
            False,
            genesis["id"],
            f"genesis row_hash={genesis['row_hash']!r} does not equal SHA256('GENESIS')={expected_genesis_hash!r}",
        )

    prev_hash = genesis["row_hash"]
    for i, row in enumerate(rows[1:], start=1):
        if row["prev_hash"] != prev_hash:
            return (
                False,
                row["id"],
                f"row.prev_hash={row['prev_hash']!r} does not equal previous row.row_hash={prev_hash!r}",
            )
        row_for_hash = {k: row[k] for k in SCHEMA_ORDER if k != "row_hash"}
        expected = sha256(canonical_json(row_for_hash))
        if row["row_hash"] != expected:
            return (
                False,
                row["id"],
                f"row.row_hash={row['row_hash']!r} does not equal SHA256(canonical_json(row))={expected!r}",
            )
        prev_hash = row["row_hash"]
    return True, None, None


def select_unexported(rows: list[dict], last_id: str | None) -> list[dict]:
    """Return rows that haven't been exported yet.

    We're conservative: rows are ordered by (recorded_at ASC, id ASC) in the
    verifier; we walk that same ordering and take everything strictly AFTER the
    last_id (if it appears) or everything (if last_id is None or unknown).
    """
    if last_id is None:
        return rows
    seen = False
    out: list[dict] = []
    for row in rows:
        if not seen:
            if row["id"] == last_id:
                seen = True
            continue
        out.append(row)
    if not seen:
        # last_id not found — return everything to be safe (it may have been pruned).
        log("warn", "audit_export.high_watermark.missing", last_id=last_id)
        return rows
    return out


def write_ndjson(rows: Iterable[dict], path: Path) -> int:
    count = 0
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def upload_to_s3(local_path: Path, bucket: str, key: str) -> None:
    try:
        import boto3  # type: ignore
    except ImportError as e:
        log("error", "audit_export.s3.boto3_missing", error=str(e))
        sys.exit(3)
    client = boto3.client("s3")
    try:
        client.upload_file(str(local_path), bucket, key)
        log("info", "audit_export.s3.uploaded", bucket=bucket, key=key)
    except Exception as e:  # noqa: BLE001
        log("error", "audit_export.s3.upload_failed", bucket=bucket, key=key, error=str(e))
        sys.exit(3)


def main() -> int:
    db_path = resolve_db_path()
    state_dir = resolve_state_dir(db_path)
    out_dir = resolve_out_dir(db_path)

    conn = open_db(db_path)
    try:
        all_rows = fetch_all_rows(conn)
    finally:
        conn.close()

    log("info", "audit_export.start", total_rows=len(all_rows), db=str(db_path))

    valid, broken_at, reason = verify_chain(all_rows)
    if not valid:
        log(
            "fatal",
            "audit_export.chain.invalid",
            broken_at=broken_at,
            reason=reason,
        )
        return 2

    log("info", "audit_export.chain.valid", rows_checked=len(all_rows))

    last_id = load_high_watermark(state_dir)
    log("info", "audit_export.watermark.read", last_id=last_id)

    new_rows = select_unexported(all_rows, last_id)
    if not new_rows:
        log("info", "audit_export.no_new_rows", last_id=last_id)
        return 0

    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"atlas-audit-{ts}.ndjson.gz"
    local_path = out_dir / filename

    written = write_ndjson(new_rows, local_path)
    log("info", "audit_export.local_written", path=str(local_path), rows=written)

    bucket = os.environ.get("ATLAS_AUDIT_S3_BUCKET", "").strip()
    if bucket:
        prefix = os.environ.get("ATLAS_AUDIT_S3_PREFIX", "audit").strip().strip("/")
        key = f"{prefix}/dt={today}/{filename}"
        upload_to_s3(local_path, bucket, key)
    else:
        log(
            "info",
            "audit_export.s3.skipped",
            would_export=written,
            reason="ATLAS_AUDIT_S3_BUCKET not set",
            local_path=str(local_path),
        )

    # Advance the high watermark to the newest row's id.
    save_high_watermark(state_dir, new_rows[-1]["id"])
    log("info", "audit_export.watermark.saved", last_id=new_rows[-1]["id"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
