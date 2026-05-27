"""Tenant-scoped repo event ingestion for ATLAS POC."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas_models import write_json, write_yaml
from atlas_paths import REPO_EVENTS_DIR


REQUIRED = ("tenant_id", "repo_name", "event_type")


def build_repo_event(
    *,
    tenant_id: str,
    repo_name: str,
    event_type: str,
    commit_sha: str | None = None,
    branch: str | None = None,
    summary: str | None = None,
    changed_files: list[str] | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    event = {
        "event_id": f"{tenant_id}:{repo_name}:{event_type}:{datetime.now(timezone.utc).isoformat()}",
        "received_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tenant_id": tenant_id,
        "repo_name": repo_name,
        "event_type": event_type,
        "commit_sha": commit_sha,
        "branch": branch,
        "summary": summary or "",
        "changed_files": changed_files or [],
        "evidence": evidence or [],
        "propagation_targets": [
            "Atlas Graph Engine",
            "Atlas Knowledge Vault",
            "Proof Matrix",
            "Context Compiler",
        ],
        "status": "accepted",
    }
    missing = [key for key in REQUIRED if not event.get(key)]
    if missing:
        raise ValueError(f"missing required repo event fields: {', '.join(missing)}")
    return event


def write_repo_event(event: dict[str, Any]) -> list[Path]:
    REPO_EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    ledger = REPO_EVENTS_DIR / "repo_events.jsonl"
    latest_json = REPO_EVENTS_DIR / "repo_event_latest.json"
    latest_yaml = REPO_EVENTS_DIR / "repo_event_latest.yaml"
    with ledger.open("a") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    write_json(latest_json, event)
    write_yaml(latest_yaml, event)
    return [ledger, latest_json, latest_yaml]
