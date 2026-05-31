"""Atlas ingest surface for v0.2 intelligence-core bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from atlas_inventory import build_inventory, inventory_markdown
from atlas_models import read_yaml, write_json, write_yaml
from atlas_paths import COMMANDS_DIR, COMMAND_LATEST, CONTEXT_PACKET, GRAPH_EVIDENCE_DIR, INGEST_DIR, INGEST_LATEST, ROOT, iter_canonical_registries, rel


def _read_text_snippet(path: Path, max_len: int = 200) -> str:
    if not path.exists():
        return ""
    return path.read_text(errors="ignore")[:max_len].strip()


def _collect_manifests() -> dict[str, str]:
    return {
        "atlas": _read_text_snippet(ROOT / "atlas.manifest.yaml", 400),
        "project_manifest": _read_text_snippet(ROOT / "platform" / "systems" / "18_registry" / "project.manifest.yaml", 400),
        "apex_version": _read_text_snippet(ROOT / "APEX_VERSION.md", 120),
    }


def _collect_registries() -> list[str]:
    return [rel(p) for p in iter_canonical_registries()]


def _collect_truth() -> dict[str, str]:
    truth_path = "platform/systems/19_truth_state/current.truth.yaml"
    truth = read_yaml(ROOT / truth_path)
    return {
        "path": truth_path,
        "status": truth.get("status", "missing") if isinstance(truth, dict) else "missing",
        "summary": truth.get("summary", "") if isinstance(truth, dict) else "",
    }


@dataclass(frozen=True)
class IngestSnapshot:
    run_id: str
    created_ts: str
    status: str
    inventory: dict
    manifests: dict
    registries: list[str]
    truth: dict

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "created_ts": self.created_ts,
            "status": self.status,
            "source": {
                "manifests": self.manifests,
                "registries": self.registries,
                "truth": self.truth,
            },
            "inventory": self.inventory,
        }


def build_snapshot() -> IngestSnapshot:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_id = now.replace(":", "_").replace("T", "_").replace("Z", "")
    return IngestSnapshot(
        run_id=run_id,
        created_ts=now,
        status="pass",
        inventory=build_inventory(),
        manifests=_collect_manifests(),
        registries=_collect_registries(),
        truth=_collect_truth(),
    )


def build_ingest_report(snapshot: IngestSnapshot) -> str:
    return "\n".join(
        [
            "# Atlas Ingest Snapshot",
            "",
            f"run_id: {snapshot.run_id}",
            f"created_ts: {snapshot.created_ts}",
            f"tracked_files: {snapshot.inventory['atlas_inventory']['tracked_files_total']}",
            f"tracked_roots: {len(snapshot.inventory['atlas_inventory']['tracked_numbered_roots'])}",
            f"registries: {len(snapshot.registries)}",
            "",
            "## Snapshot",
            f"- status: {snapshot.status}",
            "",
            "## Source Manifests",
            *[f"- `{key}`: {value}" for key, value in snapshot.manifests.items()],
            "",
            "## Inventory",
            inventory_markdown(snapshot.inventory),
        ]
    )


def write_ingest_artifacts(snapshot: IngestSnapshot, apply_latest: bool = False) -> tuple[Path, list[Path], Path]:
    INGEST_DIR.mkdir(parents=True, exist_ok=True)
    COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    run_prefix = snapshot.run_id
    snapshot_path = INGEST_DIR / f"atlas_ingest_{run_prefix}.yaml"
    snapshot_json = INGEST_DIR / f"atlas_ingest_{run_prefix}.json"
    report_path = GRAPH_EVIDENCE_DIR / f"atlas_ingest_{run_prefix}.md"
    payload = snapshot.to_dict()
    write_yaml(snapshot_path, payload)
    write_json(snapshot_json, payload)
    report_path.write_text(build_ingest_report(snapshot))

    artifact_paths: list[Path] = [snapshot_path, snapshot_json, report_path]
    if apply_latest:
        INGEST_LATEST.parent.mkdir(parents=True, exist_ok=True)
        tmp = snapshot_path.with_suffix(".tmp")
        tmp.write_text(snapshot_path.read_text())
        INGEST_LATEST.write_text(snapshot_path.read_text())
        tmp.unlink(missing_ok=True)
        # Keep a deterministic command pointer that other commands can consume.
        COMMAND_LATEST.write_text(f"{snapshot_path}\n")
        if snapshot_json.exists():
            artifact_paths.append(COMMAND_LATEST)

    return snapshot_path, artifact_paths, report_path


def latest_snapshot_path() -> Path | None:
    if INGEST_LATEST.exists():
        return INGEST_LATEST
    if not INGEST_DIR.exists():
        return None
    files = sorted(INGEST_DIR.glob("atlas_ingest_*.yaml"))
    return files[-1] if files else None


def load_snapshot(path: Path | None = None) -> dict:
    snapshot_path = path or latest_snapshot_path()
    if not snapshot_path:
        return {}
    data = read_yaml(snapshot_path)
    return data if isinstance(data, dict) else {}
