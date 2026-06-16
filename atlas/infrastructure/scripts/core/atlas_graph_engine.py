"""Atlas Graph Engine floor for Atlas Intelligence Core v0.2."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from atlas_models import write_json, write_yaml
from atlas_paths import (
    ATLAS_GRAPH_ENGINE_EXPORTS,
    ATLAS_GRAPH_ENGINE_GRAPHS,
    ATLAS_GRAPH_ENGINE_MANIFEST,
    ATLAS_GRAPH_ENGINE_REPORTS,
    GRAPH_EVIDENCE_DIR,
    GRAPH_SNAPSHOT,
    rel,
)


def _all_files() -> list[Path]:
    proc = subprocess.run(["git", "ls-files"], text=True, capture_output=True, cwd=Path(__file__).resolve().parents[3])
    files = [Path(line.strip()) for line in proc.stdout.splitlines() if line.strip()]
    return files


def _build_nodes() -> tuple[list[dict], list[dict], list[str]]:
    files = _all_files()
    roots = sorted({str(file.parts[0]) for file in files if len(file.parts) > 1})
    nodes: list[dict[str, str | int]] = []
    edges: list[dict[str, str]] = []

    for root in roots:
        root_files = [f for f in files if f.parts and f.parts[0] == root]
        nodes.append(
            {
                "id": root,
                "type": "root",
                "artifact_count": len(root_files),
                "updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
        top = sorted(set(f.parts[1] for f in root_files if len(f.parts) > 1))
        for child in top:
            child_id = f"{root}/{child}"
            nodes.append({"id": child_id, "type": "folder", "artifact_count": len([f for f in root_files if len(f.parts) > 2 and f.parts[1] == child])})
            edges.append({"from": root, "to": child_id, "type": "contains"})

    return nodes, edges, []


def build_graph(snapshot: dict | None = None) -> dict:
    nodes, edges, warnings = _build_nodes()
    summary = {
            "graph_id": f"AGE-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "generated_ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sources": {
            "source_of_truth": "19_truth_state/current.truth.yaml",
            "ingest": snapshot.get("run_id", "missing") if isinstance(snapshot, dict) else "missing",
        },
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
    }
    return summary


def graph_markdown(graph: dict) -> str:
    return "\n".join(
        [
            "# Atlas Graph Engine Snapshot",
            "",
            f"graph_id: `{graph['graph_id']}`",
            f"generated_ts: `{graph['generated_ts']}`",
            f"sources.ingest: `{graph['sources']['ingest']}`",
            f"nodes: {len(graph['nodes'])}",
            f"edges: {len(graph['edges'])}",
            "",
            "## Top-level Nodes",
            *[f"- `{node['id']}` ({node['type']})" for node in graph["nodes"] if node.get("type") == "root"],
            "",
            "## Warnings",
            *([f"- {item}" for item in graph.get("warnings", [])] if graph.get("warnings") else ["- none"]),
            "",
        ]
    )


def write_graph_artifacts(graph: dict, run_id: str, apply_latest: bool = False) -> tuple[list[Path], Path, Path]:
    GRAPH_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ATLAS_GRAPH_ENGINE_GRAPHS.mkdir(parents=True, exist_ok=True)
    ATLAS_GRAPH_ENGINE_EXPORTS.mkdir(parents=True, exist_ok=True)
    ATLAS_GRAPH_ENGINE_REPORTS.mkdir(parents=True, exist_ok=True)

    json_path = GRAPH_EVIDENCE_DIR / f"atlas_graph_{run_id}.json"
    md_path = GRAPH_EVIDENCE_DIR / f"atlas_graph_{run_id}.md"
    report_path = ATLAS_GRAPH_ENGINE_REPORTS / f"atlas_graph_report_{run_id}.md"

    write_json(json_path, graph)
    json_path2 = ATLAS_GRAPH_ENGINE_EXPORTS / f"atlas_graph_{run_id}.json"
    write_json(json_path2, graph)

    snapshot_payload = {
        "graph_id": graph["graph_id"],
        "generated_ts": graph["generated_ts"],
        "source": graph.get("sources", {}),
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(graph.get("edges", [])),
    }
    write_yaml(ATLAS_GRAPH_ENGINE_MANIFEST, {
        "generated": graph["generated_ts"],
        "graph_id": graph["graph_id"],
        "latest": str(json_path2),
        "summary": snapshot_payload,
    })

    report_text = graph_markdown(graph)
    report_path.write_text(report_text)
    md_path.write_text(report_text)

    generated = [json_path, json_path2, md_path, report_path, ATLAS_GRAPH_ENGINE_MANIFEST]
    if apply_latest:
        from shutil import copyfile

        copyfile(json_path, GRAPH_SNAPSHOT)
        latest_markdown = GRAPH_EVIDENCE_DIR / "atlas_graph_latest.md"
        copyfile(md_path, latest_markdown)
        generated.append(GRAPH_SNAPSHOT)
        generated.append(latest_markdown)

    return generated, json_path, report_path
