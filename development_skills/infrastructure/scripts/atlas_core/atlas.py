#!/usr/bin/env python3
"""SUPER C Atlas Intelligence Core v0.2 CLI surface."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from atlas_context import build_context_packet, write_context_packet
from atlas_gates import run_safe_gates
from atlas_graph_engine import build_graph, graph_markdown, write_graph_artifacts
from atlas_ingest import build_snapshot, latest_snapshot_path, load_snapshot, write_ingest_artifacts
from atlas_inventory import build_inventory, inventory_markdown, write_inventory
from atlas_models import read_yaml
from atlas_knowledge_vault import payload_from_files, write_vault
from atlas_paths import (
    COMMAND_LATEST,
    CONTEXT_PACKET,
    FLOW_DIR,
    FLOW_LATEST,
    GATE_LOG_DIR,
    GRAPH_SNAPSHOT,
    INGEST_LATEST,
    ATLAS_GRAPH_ENGINE_MANIFEST,
    ATLAS_KNOWLEDGE_VAULT_MANIFEST,
    ROOT,
    ensure_output_dirs,
    rel,
)
from atlas_reports import generate_intelligence_report, load_gate_payload
from atlas_repo_events import build_repo_event, write_repo_event
from atlas_status import build_status, status_markdown, write_status
from atlas_tenants import build_tenant_manifest, tenant_markdown, write_tenant_manifest


def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_id() -> str:
    return now_ts().replace(":", "_").replace("T", "_").replace("Z", "")


def response_model(
    command: str,
    status: str,
    run_id_value: str,
    changed_files: list[Path] | None = None,
    evidence: list[str] | None = None,
    next_actions: list[str] | None = None,
    errors: list[str] | None = None,
    start_ts: str | None = None,
    end_ts: str | None = None,
) -> dict:
    return {
        "command": command,
        "status": status,
        "run_id": run_id_value,
        "start_ts": start_ts or now_ts(),
        "end_ts": end_ts or now_ts(),
        "changed_files": [str(path) for path in (changed_files or [])],
        "evidence": evidence or [],
        "next_actions": next_actions or [],
        "errors": errors or [],
    }


def emit(resp: dict, format_: str, human: str | None = None) -> None:
    if format_ == "json":
        print(json.dumps(resp, indent=2, sort_keys=True))
        return
    if format_ == "yaml":
        print(yaml.safe_dump(resp, sort_keys=False).strip())
        return
    if human:
        print(human)
    else:
        print(json.dumps(resp, indent=2, sort_keys=True))


def _relative_paths(paths: list[Path]) -> list[str]:
    out: list[str] = []
    for item in paths:
        try:
            out.append(item.relative_to(ROOT).as_posix())
        except ValueError:
            out.append(str(item))
    return out


def _load_payload(path: Path) -> dict:
    if path.suffix.lower() == '.json':
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return read_yaml(path) if isinstance(read_yaml(path), dict) else {}


def _preflight_ok(require_gates: bool) -> tuple[bool, list[str]]:
    errors: list[str] = []
    governance_files = [
        ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery" / "master_ledger.yaml",
        ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery" / "recurrence_escalation.yaml",
        ROOT / "platform" / "sdlc" / "13_skills" / "skill_refinery" / "correction_ledgers",
    ]
    for path in governance_files:
        if not path.exists():
            errors.append(f"missing governance artifact: {path.relative_to(ROOT)}")

    if errors and require_gates:
        return False, errors

    if require_gates:
        payload = run_safe_gates()
        if payload.get("overall_verdict") != "pass":
            errors.append("governance gates failed; run atlas validate --safe-only to inspect blockers")
        return len(errors) == 0, errors

    return True, errors


def _load_graph_from_disk(graph_path: str | None = None) -> dict:
    path = Path(graph_path) if graph_path else None
    if path:
        if not path.is_absolute():
            path = ROOT / path
        data = _load_payload(path)
        return data if isinstance(data, dict) else {}

    manifest = read_yaml(ATLAS_GRAPH_ENGINE_MANIFEST)
    if isinstance(manifest, dict):
        latest = manifest.get("latest")
        if latest:
            value = _load_payload(ROOT / latest if not Path(latest).is_absolute() else Path(latest))
            if isinstance(value, dict):
                return value
    if GRAPH_SNAPSHOT.exists():
        value = _load_payload(GRAPH_SNAPSHOT)
        return value if isinstance(value, dict) else {}
    return {}


def _load_vault_from_disk() -> dict:
    manifest = read_yaml(ATLAS_KNOWLEDGE_VAULT_MANIFEST)
    if isinstance(manifest, dict):
        return manifest
    return {}


def _resolve_ingest_snapshot(path: str | None = None) -> tuple[dict, Path | None]:
    snapshot_path: Path | None = None
    if path:
        snapshot_path = Path(path)
        if not snapshot_path.is_absolute():
            snapshot_path = ROOT / snapshot_path
    if not snapshot_path:
        snapshot_path = latest_snapshot_path()
    if snapshot_path and snapshot_path.exists():
        return load_snapshot(snapshot_path), snapshot_path
    if INGEST_LATEST.exists():
        return load_snapshot(INGEST_LATEST), INGEST_LATEST
    return {}, snapshot_path


def cmd_status(args: argparse.Namespace) -> dict:
    start = now_ts()
    ensure_output_dirs()
    gate_payload = load_gate_payload()
    status = build_status(gate_payload.get("safe_gates", []))
    if args.apply and not args.check:
        write_status(status)
    changed = (
        [Path(item) for item in status["atlas_status"]["evidence"]["generated_files"]] if args.apply and not args.check else []
    )
    resp = response_model("status", "pass", run_id(), changed_files=changed, start_ts=start)
    if args.format == "text":
        emit(resp, "text", status_markdown(status))
    else:
        emit(resp, args.format)
    return resp


def cmd_inventory(args: argparse.Namespace) -> dict:
    start = now_ts()
    ensure_output_dirs()
    inventory = build_inventory()
    changed: list[Path] = []
    if not args.check:
        write_inventory(inventory)
        changed = [
            Path("23_evidence/atlas_platform/inventory/atlas_inventory.json"),
            Path("23_evidence/atlas_platform/inventory/atlas_inventory.md"),
        ]
    output = inventory_markdown(inventory) if args.format != "json" else None
    resp = response_model("inventory", "pass", run_id(), changed_files=changed, evidence=[str(rel(COMMAND_LATEST))], start_ts=start)
    if args.format == "json":
        emit({**resp, "inventory": inventory}, args.format)
    elif args.format == "yaml":
        emit(resp, args.format)
    elif output is not None:
        print(output)
    else:
        emit(resp, "text")
    return resp


def cmd_tenants(args: argparse.Namespace) -> dict:
    start = now_ts()
    ensure_output_dirs()
    manifest = build_tenant_manifest(args.tenant_id)
    changed: list[Path] = []
    if not args.check:
        changed = write_tenant_manifest(manifest)
    resp = response_model(
        "tenants",
        "pass",
        run_id(),
        changed_files=changed,
        evidence=[
            f"tenant_id={manifest['tenant']['tenant_id']}",
            f"repo_count={manifest['summary']['repo_count']}",
            f"wired_repo_twins={manifest['summary']['wired_repo_twins']}",
        ],
        start_ts=start,
    )
    if args.format == "json":
        emit({**resp, "tenant_manifest": manifest}, args.format)
    elif args.format == "yaml":
        emit({**resp, "tenant_manifest": manifest}, args.format)
    else:
        print(tenant_markdown(manifest))
    return resp


def cmd_repo_event(args: argparse.Namespace) -> dict:
    start = now_ts()
    ensure_output_dirs()
    event = build_repo_event(
        tenant_id=args.tenant_id,
        repo_name=args.repo,
        event_type=args.event_type,
        commit_sha=args.commit_sha,
        branch=args.branch,
        summary=args.summary,
        changed_files=args.changed_file or [],
        evidence=args.evidence or [],
    )
    changed: list[Path] = []
    if not args.check:
        changed = write_repo_event(event)
    resp = response_model(
        "repo-event",
        "pass",
        run_id(),
        changed_files=changed,
        evidence=[
            f"tenant_id={event['tenant_id']}",
            f"repo_name={event['repo_name']}",
            f"event_type={event['event_type']}",
            f"changed_files={len(event['changed_files'])}",
        ],
        start_ts=start,
    )
    if args.format == "json":
        emit({**resp, "repo_event": event}, args.format)
    elif args.format == "yaml":
        emit({**resp, "repo_event": event}, args.format)
    else:
        print(f"Accepted repo event for {event['tenant_id']} / {event['repo_name']} ({event['event_type']}).")
    return resp


def cmd_ingest(args: argparse.Namespace) -> dict:
    start = now_ts()
    rid = run_id()
    snapshot = build_snapshot()
    changed: list[Path] = []
    evidence: list[str] = ["source-of-truth manifests", "skill manifests", "registry scan"]

    if args.check:
        changed = []
        status = "pass"
        resp = response_model("ingest", status, rid, changed_files=changed, evidence=evidence, start_ts=start)
        emit(resp, "json" if args.format == "json" else args.format)
        return resp

    ensure_output_dirs()
    _, written, report = write_ingest_artifacts(snapshot, apply_latest=args.apply)
    changed = [Path(p) for p in written]
    if report:
        changed.append(report)
    status = "pass"
    resp = response_model(
        "ingest",
        status,
        rid,
        changed_files=changed,
        evidence=[str(rel(INGEST_LATEST)), "manifest count: %d" % snapshot.inventory["atlas_inventory"]["tracked_files_total"]],
        start_ts=start,
    )
    emit(
        resp,
        args.format,
        human=inventory_markdown(snapshot.inventory) if args.format == "text" else None,
    )
    return resp


def cmd_graph(args: argparse.Namespace) -> dict:
    start = now_ts()
    rid = run_id()
    enforce, blockers = _preflight_ok(args.require_gates)
    if not enforce:
        resp = response_model("graph", "blocked", rid, errors=blockers, start_ts=start)
        emit(resp, args.format)
        return resp

    ingest_payload, ingest_path = _resolve_ingest_snapshot(args.from_ingest)
    if not ingest_payload:
        resp = response_model(
            "graph",
            "blocked",
            rid,
            errors=["No ingest snapshot found; run atlas ingest first or pass --from-ingest"],
            start_ts=start,
        )
        emit(resp, args.format)
        return resp

    graph = build_graph(ingest_payload)
    if args.check:
        resp = response_model(
            "graph",
            "pass",
            rid,
            changed_files=[],
            evidence=[f"ingest_snapshot={ingest_path}", f"nodes={len(graph.get('nodes', []))}"],
            start_ts=start,
        )
        emit(resp, args.format)
        return resp

    changed, json_path, report_path = write_graph_artifacts(graph, rid, apply_latest=args.apply)
    resp = response_model(
        "graph",
        "pass",
        rid,
        changed_files=[Path(p) for p in changed],
        evidence=[str(rel(json_path)), str(rel(report_path)), f"from_ingest={ingest_path}"],
        start_ts=start,
    )
    if args.format == "text":
        emit(resp, "text", graph_markdown(graph))
    else:
        emit(resp, args.format)
    return resp


def cmd_knowledge_vault(args: argparse.Namespace) -> dict:
    start = now_ts()
    rid = run_id()
    _ok, blockers = _preflight_ok(args.require_gates)
    if not _ok:
        resp = response_model("knowledge_vault", "blocked", rid, errors=blockers, start_ts=start)
        emit(resp, args.format)
        return resp

    status = load_status_if_available()
    graph_payload = _load_graph_from_disk(args.from_graph) if args.from_graph else {}
    if args.from_ingest:
        _resolve_ingest_snapshot(args.from_ingest)
    if not graph_payload:
        graph_payload = _load_graph_from_disk()

    vault_payload = payload_from_files(graph_payload=graph_payload, status_path="23_evidence/atlas_platform/status/atlas_status.json")
    if args.check:
        resp = response_model(
            "knowledge_vault",
            "pass",
            rid,
            changed_files=[],
            evidence=[f"status_present={bool(status)}", f"graph_ref={graph_payload.get('graph_id', 'missing') if isinstance(graph_payload, dict) else 'missing'}"],
            start_ts=start,
        )
        emit(resp, args.format)
        return resp

    changed, report = write_vault(vault_payload, rid, apply_latest=args.apply)
    resp = response_model(
        "knowledge_vault",
        "pass",
        rid,
        changed_files=changed,
        evidence=[
            f"notes={len(vault_payload.get('notes', []))}",
            f"vault_id={vault_payload.get('vault_id', 'missing')}",
        ],
        start_ts=start,
    )
    if args.format == "text":
        emit(resp, "text", report.read_text())
    else:
        emit(resp, args.format)
    return resp


def cmd_validate(args: argparse.Namespace) -> dict:
    start = now_ts()
    rid = run_id()
    if not args.safe_only:
        resp = response_model("validate", "blocked", rid, errors=["Only safe-only validation is supported in v0.2"], start_ts=start)
        emit(resp, args.format)
        return resp

    payload = run_safe_gates()
    changed = [Path(item) for item in [
        ROOT / "08_verification" / "gate_results" / "atlas_platform_core_safe_gates.yaml",
        ROOT / "08_verification" / "gate_results" / "atlas_platform_core_safe_gates.json",
    ]]
    changed.extend([p for p in GATE_LOG_DIR.glob("*.txt")])

    status = "pass" if payload.get("overall_verdict") == "pass" else "fail"
    evidence = [f"gate_count={len(payload.get('safe_gates', []))}", "unsafe_skipped=%d" % len(payload.get("unsafe_skipped", []))]
    resp = response_model("validate", status, rid, changed_files=changed, evidence=evidence, start_ts=start)
    if args.format == "json":
        emit({**resp, "gates": payload}, args.format)
    elif args.format == "yaml":
        emit({**resp, "gates": payload}, args.format)
    else:
        lines = ["Atlas safe-gate validation summary", "", f"overall={status}", f"safe_gates={len(payload.get('safe_gates', []))}"]
        print("\n".join(lines))
    return resp


def cmd_compile_context(args: argparse.Namespace) -> dict:
    start = now_ts()
    rid = run_id()
    enforce, blockers = _preflight_ok(args.require_gates)
    if not enforce and args.require_gates:
        resp = response_model("compile_context", "blocked", rid, errors=blockers, start_ts=start)
        emit(resp, args.format)
        return resp

    gate_payload = load_gate_payload()
    status = build_status(gate_payload.get("safe_gates", []))
    ingest_payload, _ = _resolve_ingest_snapshot(args.from_ingest)
    graph_payload = _load_graph_from_disk(args.from_graph)
    vault_payload = _load_vault_from_disk()

    packet = build_context_packet(status, gate_payload=gate_payload, ingest_snapshot=ingest_payload, graph_payload=graph_payload, vault_payload=vault_payload)
    if args.check:
        resp = response_model(
            "compile_context",
            "pass",
            rid,
            evidence=[f"run_id={rid}", f"ingest_present={bool(ingest_payload)}", f"graph_present={bool(graph_payload)}"],
            start_ts=start,
        )
        emit(resp, args.format)
        return resp

    write_context_packet(packet)
    changed = [CONTEXT_PACKET]
    resp = response_model(
        "compile_context",
        "pass",
        rid,
        changed_files=changed,
        evidence=[f"next=atlas report", f"packet_path={rel(CONTEXT_PACKET)}"],
        start_ts=start,
    )
    if args.format == "text":
        emit(resp, "text", json.dumps(packet, indent=2, sort_keys=True))
    else:
        emit(resp, args.format)
    return resp


def cmd_report(args: argparse.Namespace) -> dict:
    start = now_ts()
    rid = run_id()
    status = build_status(load_gate_payload().get("safe_gates", []))
    inventory = build_inventory()
    if not args.check:
        write_status(status)
        write_inventory(inventory)
    gate_payload = run_safe_gates()
    packet = build_context_packet(status, gate_payload=gate_payload)
    if args.check:
        changed: list[Path] = []
        resp = response_model(
            "report",
            "pass",
            rid,
            changed_files=changed,
            evidence=[f"context_status={status['atlas_status']['system_name']}", "skipped_mutating_steps"],
            start_ts=start,
        )
        if args.format == "json":
            emit({**resp, "release_report": "not_created"}, args.format)
        elif args.format == "yaml":
            emit({**resp, "release_report": "not_created"}, args.format)
        else:
            print("Atlas intelligence report skipped in check mode.")
        return resp

    if args.require_gates:
        if gate_payload.get("overall_verdict") != "pass":
            resp = response_model(
                "report",
                "blocked",
                rid,
                evidence=["Safe gates failed: run atlas validate --safe-only"],
                start_ts=start,
            )
            if args.format == "json":
                emit({**resp, "release_report": "not_created"}, args.format)
            elif args.format == "yaml":
                emit({**resp, "release_report": "not_created"}, args.format)
            else:
                print("Atlas intelligence report blocked by safe-gate failure.")
            return resp

    if not args.check:
        write_context_packet(packet)

    changed: list[Path] = []
    if not args.check:
        changed = [Path(path) for path in generate_intelligence_report(
            status,
            inventory,
            gate_payload,
            rel(CONTEXT_PACKET),
            require_gates=args.require_gates,
        )]

    resp = response_model(
        "report",
        "pass",
        rid,
        changed_files=[Path(c) for c in changed],
        evidence=[f"context_status={status['atlas_status']['system_name']}", f"release_report={changed[0] if changed else 'not_created'}"],
        start_ts=start,
    )

    if args.format == "json":
        emit({**resp, "release_report": str(changed[0]) if changed else "not_created"}, args.format)
    elif args.format == "yaml":
        emit({**resp, "release_report": str(changed[0]) if changed else "not_created"}, args.format)
    else:
        print("Atlas intelligence report generated." if changed else "Atlas intelligence report skipped in check mode.")
    return resp


def cmd_flow(args: argparse.Namespace) -> dict:
    start = now_ts()
    rid = run_id()
    steps = [step.strip() for step in (args.steps or "ingest,graph,knowledge_vault,status,validate,compile_context,report").split(",") if step.strip()]
    if not steps:
        raise ValueError("flow requires at least one step")

    step_aliases = {
        "ingest": cmd_ingest,
        "graph": cmd_graph,
        "knowledge_vault": cmd_knowledge_vault,
        "status": cmd_status,
        "validate": cmd_validate,
        "compile-context": cmd_compile_context,
        "compile_context": cmd_compile_context,
        "report": cmd_report,
    }

    changed: list[Path] = []
    errors: list[str] = []
    for step in steps:
        handler = step_aliases.get(step)
        if not handler:
            errors.append(f"unsupported flow step: {step}")
            continue
        if step in {"graph", "knowledge_vault", "compile_context", "compile-context", "report"} and args.require_gates:
            ok, blockers = _preflight_ok(True)
            if not ok:
                errors.append(f"blocked before {step}: {','.join(blockers)}")
                continue
        ns = argparse.Namespace(
            check=args.check,
            apply=args.apply,
            format="json",
            safe_only=True,
            require_gates=args.require_gates,
            from_ingest=args.from_ingest,
            from_graph=args.from_graph,
        )
        # status command does not use apply/format extras in this flow.
        try:
            res = handler(ns)
            changed.extend([Path(p) for p in res["changed_files"]])
        except Exception as exc:  # pragma: no cover - command-level runtime issues
            errors.append(f"{step}: {exc}")

    FLOW_LATEST.parent.mkdir(parents=True, exist_ok=True)
    flow_log = FLOW_DIR / f"atlas_flow_{rid}.json"
    flow_payload = {
        "run_id": rid,
        "start_ts": start,
        "steps": steps,
        "errors": errors,
        "changed_files": _relative_paths(changed),
    }
    flow_log.write_text(json.dumps(flow_payload, indent=2, sort_keys=True))
    if args.apply:
        FLOW_LATEST.write_text(flow_log.read_text())

    status = "fail" if errors else "pass"
    resp = response_model("flow", status, rid, changed_files=changed, errors=errors, start_ts=start)
    emit(resp, args.format if args.format != "text" else "json")
    return resp


def load_status_if_available() -> dict:
    path = ROOT / "23_evidence" / "atlas_platform" / "status" / "atlas_status.json"
    if path.exists():
        data = read_yaml(path)
        return data if isinstance(data, dict) else {}
    return {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SUPER C Atlas Intelligence Core v0.2")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--require-gates", action="store_true", help="Require safe gates before mutating steps")
    common.add_argument("--format", choices=["text", "json", "yaml"], default="text", help="Response format")
    common.add_argument("--check", "--dry-run", "-n", action="store_true", help="Dry-run mode")
    common.add_argument("--apply", action="store_true", help="Update latest pointers and stable output files")

    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", parents=[common], help="Read-only system status")
    status.set_defaults(func=cmd_status)

    inventory = sub.add_parser("inventory", parents=[common], help="List repository inventory")
    inventory.set_defaults(func=cmd_inventory)

    tenants = sub.add_parser("tenants", parents=[common], help="Build ATLAS multi-tenant repo connector manifest")
    tenants.add_argument("--tenant-id", default="desmond-personal-poc", help="Tenant id for the POC corpus")
    tenants.set_defaults(func=cmd_tenants)

    repo_event = sub.add_parser("repo-event", parents=[common], help="Ingest a tenant-scoped repo commit/change event")
    repo_event.add_argument("--tenant-id", default="desmond-personal-poc")
    repo_event.add_argument("--repo", required=True, help="Repository name")
    repo_event.add_argument("--event-type", default="commit", choices=["commit", "diff", "validation", "sync", "agent_report"])
    repo_event.add_argument("--commit-sha")
    repo_event.add_argument("--branch")
    repo_event.add_argument("--summary", default="")
    repo_event.add_argument("--changed-file", action="append", default=[])
    repo_event.add_argument("--evidence", action="append", default=[])
    repo_event.set_defaults(func=cmd_repo_event)

    ingest = sub.add_parser("ingest", parents=[common], help="Collect Atlas source truth and ingest snapshot")
    ingest.set_defaults(func=cmd_ingest)

    graph = sub.add_parser("graph", parents=[common], help="Build Atlas graph snapshot from ingest")
    graph.add_argument("--from-ingest", dest="from_ingest", help="Use specific ingest snapshot")
    graph.set_defaults(func=cmd_graph)

    knowledge_vault = sub.add_parser(
        "knowledge_vault",
        aliases=["knowledge-vault"],
        parents=[common],
        help="Export Atlas Knowledge Vault notes",
    )
    knowledge_vault.add_argument("--from-ingest", dest="from_ingest", help="Use specific ingest snapshot")
    knowledge_vault.add_argument("--from-graph", dest="from_graph", help="Use specific graph artifact")
    knowledge_vault.set_defaults(func=cmd_knowledge_vault)

    validate = sub.add_parser("validate", parents=[common], help="Run validation gate checks")
    validate.add_argument("--safe-only", action="store_true", default=True)
    validate.set_defaults(func=cmd_validate)

    compile_context = sub.add_parser(
        "compile-context",
        aliases=["compile_context"],
        parents=[common],
        help="Build Atlas context packet",
    )
    compile_context.add_argument("--from-ingest", dest="from_ingest", help="Ingest snapshot for context provenance")
    compile_context.add_argument("--from-graph", dest="from_graph", help="Graph artifact for provenance")
    compile_context.set_defaults(func=cmd_compile_context)

    report = sub.add_parser("report", parents=[common], help="Generate Atlas intelligence report")
    report.add_argument("--from-ingest", dest="from_ingest", help="Ingest snapshot for report provenance")
    report.set_defaults(func=cmd_report)

    flow = sub.add_parser("flow", parents=[common], help="Run convergence flow")
    flow.add_argument("--steps", help="Comma-separated flow steps")
    flow.add_argument("--from-ingest", dest="from_ingest", help="Optional ingest snapshot for flow provenance")
    flow.add_argument("--from-graph", dest="from_graph", help="Optional graph artifact for flow provenance")
    flow.set_defaults(func=cmd_flow)

    # V0.1 compatibility aliases and names used by legacy callsites.
    context_cmd = sub.add_parser("context", help="Alias for compile_context")
    context_cmd.set_defaults(func=cmd_compile_context)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = args.func(args)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
