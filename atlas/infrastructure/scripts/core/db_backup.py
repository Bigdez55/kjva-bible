#!/usr/bin/env python3
"""ATLAS Durable Storage — daily backup driver (desktop SQLite + hosted Neon).

Desktop mode:
    Shells out to the SQLite CLI `.backup` command, which produces a
    point-in-time consistent copy even while the source is open under WAL.
    Falls back to `sqlite3` Python module if the CLI is not installed.

Hosted mode:
    Neon provides continuous PITR + branching as a managed feature. The script
    emits a structured note to STDOUT (no-op on Neon's behalf) so a cron caller
    can log evidence that backup responsibility is correctly delegated.

Cron usage (daily 02:00 local):
    0 2 * * * /usr/bin/env python3 /path/to/infrastructure/scripts/core/db_backup.py

Environment:
    ATLAS_RUNTIME           "desktop" (default) | "hosted"
    ATLAS_SQLITE_PATH       Override of the source DB path (desktop only).
    ATLAS_BACKUP_DIR        Override of the backup target dir (desktop only).
    ATLAS_BACKUP_RETENTION  Integer count of snapshots to keep (default: 7).

Exit codes:
    0  success (backup written, or hosted no-op acknowledged)
    1  config error (missing path, runtime not recognized)
    2  backup execution error

Owner: data-infrastructure-lead
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _utc_stamp() -> str:
    """Filesystem-safe UTC timestamp for backup filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _resolve_runtime() -> str:
    raw = (os.environ.get("ATLAS_RUNTIME") or "desktop").strip().lower()
    if raw not in {"desktop", "hosted"}:
        return "desktop"
    return raw


def _default_desktop_db_path() -> Path:
    override = os.environ.get("ATLAS_SQLITE_PATH")
    if override:
        return Path(override).expanduser()
    # Mirror of apps/frontend/shell/src/lib/db/client.ts default.
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "ATLAS"
        / "atlas.db"
    )


def _default_backup_dir() -> Path:
    override = os.environ.get("ATLAS_BACKUP_DIR")
    if override:
        return Path(override).expanduser()
    return _default_desktop_db_path().parent / "backups"


def _retention_count() -> int:
    raw = os.environ.get("ATLAS_BACKUP_RETENTION", "7")
    try:
        return max(1, int(raw))
    except ValueError:
        return 7


# ---------------------------------------------------------------------------
# desktop path
# ---------------------------------------------------------------------------


def _backup_with_cli(src: Path, dest: Path) -> None:
    """Use the `sqlite3` CLI `.backup` command for online consistent backup."""
    # `sqlite3 SRC ".backup DEST"` opens SRC read-only and copies pages safely
    # even with concurrent writers (WAL-aware).
    subprocess.run(
        ["sqlite3", str(src), f".backup '{dest}'"],
        check=True,
        capture_output=True,
        text=True,
    )


def _backup_with_python(src: Path, dest: Path) -> None:
    """Fallback to the sqlite3 stdlib backup API when the CLI is absent."""
    # `Connection.backup()` is online and WAL-safe; identical semantics.
    src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        dest_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()


def _prune_old(backup_dir: Path, keep: int) -> list[str]:
    """Retain the newest `keep` snapshots. Returns paths that were removed."""
    snapshots = sorted(
        backup_dir.glob("atlas-*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed: list[str] = []
    for old in snapshots[keep:]:
        try:
            old.unlink()
            removed.append(str(old))
        except OSError:
            # Don't fail the backup over a leftover file we can't delete.
            pass
    return removed


def run_desktop_backup() -> dict:
    src = _default_desktop_db_path()
    if not src.exists():
        return {
            "status": "skipped",
            "runtime": "desktop",
            "reason": f"Source DB does not exist yet at {src}. Backup is a no-op until first migration writes the file.",
            "source": str(src),
        }

    backup_dir = _default_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    dest = backup_dir / f"atlas-{_utc_stamp()}.db"

    if shutil.which("sqlite3"):
        try:
            _backup_with_cli(src, dest)
            method = "cli"
        except subprocess.CalledProcessError as err:
            return {
                "status": "error",
                "runtime": "desktop",
                "reason": f"sqlite3 CLI backup failed: {err.stderr.strip() or err}",
                "source": str(src),
                "dest": str(dest),
            }
    else:
        try:
            _backup_with_python(src, dest)
            method = "stdlib"
        except sqlite3.Error as err:
            return {
                "status": "error",
                "runtime": "desktop",
                "reason": f"sqlite3 stdlib backup failed: {err}",
                "source": str(src),
                "dest": str(dest),
            }

    removed = _prune_old(backup_dir, _retention_count())

    return {
        "status": "ok",
        "runtime": "desktop",
        "method": method,
        "source": str(src),
        "dest": str(dest),
        "size_bytes": dest.stat().st_size,
        "retention_kept": _retention_count(),
        "pruned": removed,
    }


# ---------------------------------------------------------------------------
# hosted path
# ---------------------------------------------------------------------------


def run_hosted_backup() -> dict:
    """Neon handles backup natively — log evidence and exit cleanly."""
    return {
        "status": "delegated",
        "runtime": "hosted",
        "provider": "neon",
        "note": (
            "Neon provides continuous branching and point-in-time restore. "
            "No custom backup action is required from this script. "
            "Operators should verify retention policy on the Neon project."
        ),
        "next_action": "use Neon PITR",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="ATLAS durable-storage daily backup driver.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON result document instead of human text.",
    )
    args = parser.parse_args(argv)

    runtime = _resolve_runtime()
    if runtime == "desktop":
        result = run_desktop_backup()
    else:
        result = run_hosted_backup()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        status = result.get("status", "unknown")
        if status == "ok":
            print(
                f"ATLAS backup OK ({result['runtime']}/{result.get('method', 'n/a')}): "
                f"{result['dest']} ({result['size_bytes']} bytes); "
                f"pruned {len(result['pruned'])}"
            )
        elif status == "delegated":
            print(f"ATLAS backup delegated to {result['provider']} — {result['next_action']}")
        elif status == "skipped":
            print(f"ATLAS backup skipped: {result['reason']}")
        else:
            print(f"ATLAS backup ERROR: {result.get('reason', 'unknown failure')}", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
