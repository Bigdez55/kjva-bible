"""Atlas Knowledge Vault export floor for Atlas Intelligence Core v0.2."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from atlas_models import read_yaml, write_yaml
from atlas_paths import ATLAS_KNOWLEDGE_VAULT_MANIFEST, ATLAS_KNOWLEDGE_VAULT_NOTES, ATLAS_KNOWLEDGE_VAULT_REPORTS


def _repo_path(value: str) -> Path:
    return Path(__file__).resolve().parents[3] / value


def _note(path: str, title: str, body: str, created_ts: str) -> str:
    lines = [
        "---",
        f"title: {title}",
        "type: atlas",
        f"created: {created_ts}",
        "aliases: [Atlas, Intelligence Core]",
        "---",
        "",
        f"# {title}",
        "",
        body,
        "",
        f"source: `23_evidence/{path}`",
        "",
    ]
    return "\n".join(lines)


def build_vault_payload(graph: dict | None = None, status: dict | None = None) -> dict:
    created_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    graph_id = graph.get("graph_id", "missing") if isinstance(graph, dict) else "missing"
    truth_status = status.get("atlas_status", {}).get("repository_lineage", "missing") if isinstance(status, dict) else "missing"
    return {
        "vault_id": f"AKV-{created_ts.replace(':', '_').replace('+00:00', '')}",
        "created_ts": created_ts,
        "graph_ref": graph_id,
        "lineage": truth_status,
        "notes": [
            {
                "id": "status",
                "title": "Atlas Status",
                "filename": "000_Atlas_Status.md",
                "body": "## Atlas status snapshot\n\nSee linked status artifacts and validation gates.",
            },
            {
                "id": "graph",
                "title": "Atlas Graph",
                "filename": "100_Atlas_Graph.md",
                "body": f"## Graph Snapshot\n\n`graph_id: {graph_id}`",
            },
            {
                "id": "proof",
                "title": "Atlas Proof Path",
                "filename": "200_Atlas_Proof.md",
                "body": "## Proof Evidence\n\nGenerated from `36_proof_matrix`, `20_drift_detection`, and gate outputs.",
            },
        ],
    }


def build_vault_notes(payload: dict) -> list[tuple[str, str]]:
    created_ts = payload.get("created_ts", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    return [
        (note["filename"], _note(note["filename"], note["title"], note["body"], created_ts))
        for note in payload.get("notes", [])
    ]


def write_vault(payload: dict, run_id: str, apply_latest: bool = False) -> tuple[list[Path], Path]:
    ATLAS_KNOWLEDGE_VAULT_NOTES.mkdir(parents=True, exist_ok=True)
    ATLAS_KNOWLEDGE_VAULT_REPORTS.mkdir(parents=True, exist_ok=True)

    note_dir = ATLAS_KNOWLEDGE_VAULT_NOTES / run_id
    note_dir.mkdir(parents=True, exist_ok=True)
    note_paths: list[Path] = []

    for filename, content in build_vault_notes(payload):
        path = note_dir / filename
        path.write_text(content)
        note_paths.append(path)

    summary = {
        "vault_id": payload.get("vault_id", "missing"),
        "created_ts": payload.get("created_ts", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
        "graph_ref": payload.get("graph_ref", "missing"),
        "note_count": len(note_paths),
        "notes": [str(p.relative_to(Path(__file__).resolve().parents[3])) for p in note_paths],
    }

    report_path = ATLAS_KNOWLEDGE_VAULT_REPORTS / f"atlas_knowledge_vault_{run_id}.md"
    report_lines = [
        "# Atlas Knowledge Vault Export",
        "",
        f"vault_id: {summary['vault_id']}",
        f"created_ts: {summary['created_ts']}",
        f"graph_ref: {summary['graph_ref']}",
        f"notes: {summary['note_count']}",
        "",
        "## Notes",
    ]
    for p in summary["notes"]:
        report_lines.append(f"- `{p}`")
    report_lines.append("")
    report_path.write_text("\n".join(report_lines))

    write_yaml(ATLAS_KNOWLEDGE_VAULT_MANIFEST, {
        "generated": summary["created_ts"],
        "vault_id": summary["vault_id"],
        "note_dir": str(note_dir),
        "report": str(report_path),
        "notes": summary["notes"],
    })

    if apply_latest:
        latest_manifest = ATLAS_KNOWLEDGE_VAULT_REPORTS / "atlas_knowledge_vault_latest.md"
        latest_manifest.write_text(report_path.read_text())

    return note_paths + [report_path, ATLAS_KNOWLEDGE_VAULT_MANIFEST], report_path


def payload_from_files(graph_payload: dict | None = None, status_path: str = "23_evidence/platform/status/atlas_status.json") -> dict:
    graph = graph_payload if isinstance(graph_payload, dict) else {}
    status = read_yaml(_repo_path(status_path))
    return build_vault_payload(graph=graph, status=status if isinstance(status, dict) else {})
