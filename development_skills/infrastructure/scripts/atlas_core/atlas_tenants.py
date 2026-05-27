"""Multi-tenant repository wiring inventory for the ATLAS POC."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas_models import read_yaml, write_json, write_yaml
from atlas_paths import ROOT, TENANT_EVIDENCE_DIR


SYNC_PACKET_DIR = ROOT / "21_repo_sync" / "sync_packets"
TWIN_DIR = ROOT / "39_repo_twins" / "twins"


def _load_sync_packets() -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    if not SYNC_PACKET_DIR.exists():
        return packets
    for path in sorted(SYNC_PACKET_DIR.glob("SYNC-*.yaml")):
        if ".gitkeep" in path.name:
            continue
        data = read_yaml(path)
        if not data:
            continue
        repo_name = (
            data.get("repo")
            or data.get("name")
            or data.get("repo_name")
            or path.stem.replace("SYNC-", "")
        )
        if str(repo_name).strip() in {"", ".gitkeep"}:
            continue
        packets.append(
            {
                "repo_name": str(repo_name),
                "sync_packet": path.relative_to(ROOT).as_posix(),
                "raw": data,
            }
        )
    return packets


def _twin_status(repo_name: str) -> dict[str, Any]:
    twin_root = TWIN_DIR / repo_name
    manifest = twin_root / "repo_twin.manifest.yaml"
    truth = twin_root / "current.truth.yaml"
    sync_status = twin_root / "sync_status.yaml"
    return {
        "twin_root": twin_root.relative_to(ROOT).as_posix() if twin_root.exists() else None,
        "has_twin": twin_root.exists(),
        "manifest": manifest.relative_to(ROOT).as_posix() if manifest.exists() else None,
        "current_truth": truth.relative_to(ROOT).as_posix() if truth.exists() else None,
        "sync_status": sync_status.relative_to(ROOT).as_posix() if sync_status.exists() else None,
    }


def build_tenant_manifest(tenant_id: str = "desmond-personal-poc") -> dict[str, Any]:
    """Build the first ATLAS tenant manifest from existing repo sync packets and twins."""

    repos: list[dict[str, Any]] = []
    for packet in _load_sync_packets():
        repo_name = packet["repo_name"]
        twin = _twin_status(repo_name)
        repos.append(
            {
                "repo_name": repo_name,
                "repo_key": repo_name.lower().replace(" ", "-"),
                "sync_packet": packet["sync_packet"],
                "twin": twin,
                "connector_state": "wired" if twin["has_twin"] else "sync_packet_only",
                "poc_role": "tenant_repository_corpus",
                "ingestion_targets": [
                    "repo_inventory",
                    "source_truth",
                    "skill_surfaces",
                    "agent_surfaces",
                    "proof_evidence",
                    "graph_relationships",
                    "knowledge_vault_notes",
                ],
            }
        )

    wired = sum(1 for repo in repos if repo["connector_state"] == "wired")
    return {
        "tenant": {
            "tenant_id": tenant_id,
            "display_name": "Desmond ATLAS POC",
            "platform_name": "ATLAS",
            "tenancy_model": "multi_tenant",
            "poc_scope": "Wire all known local/GitHub repo sync packets and repo twins as the first tenant corpus.",
        },
        "repo_connectors": repos,
        "summary": {
            "repo_count": len(repos),
            "wired_repo_twins": wired,
            "sync_packet_only": len(repos) - wired,
            "source_sync_packet_dir": SYNC_PACKET_DIR.relative_to(ROOT).as_posix(),
            "source_twin_dir": TWIN_DIR.relative_to(ROOT).as_posix(),
        },
        "next_buildouts": [
            "Add tenant selector to apps/atlas.",
            "Expose repo connector health from this manifest.",
            "Connect Atlas Graph Engine to tenant-scoped repo nodes.",
            "Connect Atlas Knowledge Vault to tenant-scoped linked notes.",
            "Add auth, roles, and tenant isolation before external users.",
        ],
    }


def tenant_markdown(manifest: dict[str, Any]) -> str:
    tenant = manifest["tenant"]
    summary = manifest["summary"]
    lines = [
        "# ATLAS Tenant Wiring POC",
        "",
        f"- Tenant: `{tenant['tenant_id']}`",
        f"- Display name: {tenant['display_name']}",
        f"- Tenancy model: `{tenant['tenancy_model']}`",
        f"- Repo connectors: {summary['repo_count']}",
        f"- Wired repo twins: {summary['wired_repo_twins']}",
        f"- Sync-packet only: {summary['sync_packet_only']}",
        "",
        "## Repo Connectors",
        "",
        "| Repo | State | Sync Packet | Twin |",
        "| --- | --- | --- | --- |",
    ]
    for repo in manifest["repo_connectors"]:
        twin_root = repo["twin"]["twin_root"] or ""
        lines.append(f"| {repo['repo_name']} | {repo['connector_state']} | `{repo['sync_packet']}` | `{twin_root}` |")
    lines.extend(["", "## Next Buildouts", ""])
    for item in manifest["next_buildouts"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def write_tenant_manifest(manifest: dict[str, Any]) -> list[Path]:
    TENANT_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    json_path = TENANT_EVIDENCE_DIR / "atlas_tenant_poc.json"
    yaml_path = TENANT_EVIDENCE_DIR / "atlas_tenant_poc.yaml"
    md_path = TENANT_EVIDENCE_DIR / "atlas_tenant_poc.md"
    write_json(json_path, manifest)
    write_yaml(yaml_path, manifest)
    md_path.write_text(tenant_markdown(manifest))
    return [json_path, yaml_path, md_path]
