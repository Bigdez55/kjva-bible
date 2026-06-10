#!/usr/bin/env python3
"""Operate the Tokenless omni training program registry.

This script is the meta-program layer: it inventories training methods, exports
the program corpus, validates registry wiring, plans compatible stacks, and
delegates runnable stages to concrete orchestrators.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_REGISTRY = REPO_ROOT / "ml-training/programs/omni_training_registry.json"
DEFAULT_PROGRAM = REPO_ROOT / "ml-training/programs/kjv_omni_program.yaml"


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def simple_yaml_load(path: Path) -> dict[str, Any]:
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    lines: list[tuple[int, str]] = []
    for raw in raw_lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        content = raw.split("#", 1)[0].rstrip()
        if content:
            lines.append((len(raw) - len(raw.lstrip(" ")), content.strip()))

    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    for idx, (indent, content) in enumerate(lines):
        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if content.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"list item without list parent at line {idx + 1}: {content}")
            parent.append(parse_scalar(content[2:]))
            continue
        if ":" not in content:
            raise ValueError(f"invalid YAML line {idx + 1}: {content}")
        key, value = content.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            if not isinstance(parent, dict):
                raise ValueError(f"mapping item without mapping parent at line {idx + 1}")
            parent[key] = parse_scalar(value)
            continue
        next_is_list = False
        for next_indent, next_content in lines[idx + 1:]:
            if next_indent <= indent:
                break
            next_is_list = next_content.startswith("- ")
            break
        container: Any = [] if next_is_list else {}
        if not isinstance(parent, dict):
            raise ValueError(f"mapping item without mapping parent at line {idx + 1}")
        parent[key] = container
        stack.append((indent, container))
    return root


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data or {}
    except Exception:
        return simple_yaml_load(path)


def resolve_path(value: str | Path, base: Path = REPO_ROOT) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return (base / path).resolve()


def load_registry(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_program(path: Path) -> dict[str, Any]:
    return load_yaml(path)


def method_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {method["id"]: method for method in registry.get("methods", [])}


def stack_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {stack["id"]: stack for stack in registry.get("stacks", [])}


def default_stack(registry: dict[str, Any]) -> dict[str, Any]:
    stacks = registry.get("stacks", [])
    for stack in stacks:
        if stack.get("default"):
            return stack
    if not stacks:
        raise ValueError("registry contains no stacks")
    return stacks[0]


def validate_registry(registry: dict[str, Any]) -> dict[str, Any]:
    methods = registry.get("methods", [])
    ids = [method.get("id") for method in methods]
    counts = Counter(ids)
    duplicates = sorted(k for k, v in counts.items() if v > 1)
    missing_fields = []
    missing_runners = []
    valid_status = {"implemented", "extension_spec", "planned", "blocked"}
    invalid_status = []
    for method in methods:
        for field in ["id", "name", "family", "status", "requires", "produces", "summary"]:
            if field not in method:
                missing_fields.append({"id": method.get("id"), "field": field})
        if method.get("status") not in valid_status:
            invalid_status.append({"id": method.get("id"), "status": method.get("status")})
        runner = method.get("runner")
        if method.get("status") == "implemented":
            if not runner:
                missing_runners.append({"id": method.get("id"), "issue": "missing_runner"})
            elif runner.get("kind") == "script" and not resolve_path(runner["path"]).exists():
                missing_runners.append({"id": method.get("id"), "path": runner.get("path")})

    missing_stack_methods = []
    known = set(ids)
    for stack in registry.get("stacks", []):
        for phase in stack.get("phases", []):
            for method_id in phase.get("methods", []):
                if method_id not in known:
                    missing_stack_methods.append({
                        "stack": stack.get("id"),
                        "phase": phase.get("id"),
                        "method": method_id,
                    })

    status_counts = Counter(method.get("status", "unknown") for method in methods)
    family_counts = Counter(method.get("family", "unknown") for method in methods)
    report = {
        "registry_id": registry.get("registry_id"),
        "method_count": len(methods),
        "status_counts": dict(sorted(status_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "duplicates": duplicates,
        "missing_fields": missing_fields,
        "invalid_status": invalid_status,
        "missing_runners": missing_runners,
        "missing_stack_methods": missing_stack_methods,
    }
    report["pass"] = not any([
        duplicates,
        missing_fields,
        invalid_status,
        missing_runners,
        missing_stack_methods,
    ])
    return report


def plan_stack(registry: dict[str, Any], program: dict[str, Any] | None = None,
               stack_id: str | None = None) -> dict[str, Any]:
    methods = method_index(registry)
    stacks = stack_index(registry)
    selected_stack = (
        stacks[stack_id]
        if stack_id
        else stacks.get((program or {}).get("stack", ""))
        or default_stack(registry)
    )
    active_export = None
    active_export_path: Path | None = None
    if program:
        active_export = program.get("base_gate", {}).get("active_export")
        if active_export:
            active_export = str(active_export)
            active_export_path = resolve_path(active_export, REPO_ROOT)

    artifacts: set[str] = set((program or {}).get("initial_artifacts", []))
    phases = []
    for phase in selected_stack.get("phases", []):
        phase_methods = []
        blocked = []
        gate = phase.get("gate")
        gate_pass = True
        if gate == "requires_published_base_checkpoint":
            gate_pass = bool(active_export_path and active_export_path.exists())
        for method_id in phase.get("methods", []):
            method = methods[method_id]
            missing = sorted(set(method.get("requires", [])) - artifacts)
            runnable = method.get("status") == "implemented" and not missing and gate_pass
            if gate and not gate_pass:
                blocked.append({"method": method_id, "reason": gate})
            elif missing:
                blocked.append({"method": method_id, "missing_artifacts": missing})
            phase_methods.append({
                "id": method_id,
                "name": method.get("name"),
                "family": method.get("family"),
                "status": method.get("status"),
                "runnable_now": runnable,
                "requires": method.get("requires", []),
                "produces": method.get("produces", []),
            })
            artifacts.update(method.get("produces", []))
        phases.append({
            "id": phase.get("id"),
            "gate": gate,
            "gate_pass": gate_pass,
            "methods": phase_methods,
            "blocked": blocked,
        })

    return {
        "program_id": (program or {}).get("program_id"),
        "registry_id": registry.get("registry_id"),
        "stack_id": selected_stack.get("id"),
        "active_export": active_export,
        "phases": phases,
        "final_artifacts": sorted(artifacts),
    }


def export_program_corpus(registry: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for method in registry.get("methods", []):
            row = {
                "id": method["id"],
                "name": method["name"],
                "family": method["family"],
                "status": method["status"],
                "requires": method.get("requires", []),
                "produces": method.get("produces", []),
                "summary": method.get("summary", ""),
                "training_program_text": " ".join([
                    method["id"],
                    method["name"],
                    method["family"],
                    method["status"],
                    "requires " + ", ".join(method.get("requires", [])),
                    "produces " + ", ".join(method.get("produces", [])),
                    method.get("summary", ""),
                ]),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def print_matrix(registry: dict[str, Any]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for method in registry.get("methods", []):
        grouped[method["family"]].append(method)
    for family in sorted(grouped):
        print(f"[{family}]")
        for method in sorted(grouped[family], key=lambda m: m["id"]):
            print(f"  {method['id']:<32} {method['status']:<14} {method['name']}")


def run_delegate(program: dict[str, Any], stage: str, dry_run: bool) -> int:
    delegate = resolve_path(program["delegate_recipe"])
    py_config = Path(str(program.get("python_bin", sys.executable))).expanduser()
    py = str(py_config if py_config.is_absolute() else REPO_ROOT / py_config)
    cmd = [
        py,
        str(SCRIPT_DIR / "run_retrain.py"),
        "--recipe",
        str(delegate),
    ]
    if stage != "all":
        cmd.extend(["--stage", stage])
    if dry_run:
        cmd.append("--dry-run")
    print("+ " + " ".join(cmd), flush=True)
    env = dict(os.environ)
    if program.get("tokenless_home"):
        env["TOKENLESS_HOME"] = str(resolve_path(program["tokenless_home"], REPO_ROOT))
    return subprocess.run(cmd, cwd=REPO_ROOT, env=env, check=False).returncode


def run_peft(
    program: dict[str, Any],
    method: str,
    dry_run: bool,
    extra_args: list[str],
) -> int:
    """Dispatch a PEFT/alignment method run to train_peft.py."""
    py_config = Path(str(program.get("python_bin", sys.executable))).expanduser()
    py = str(py_config if py_config.is_absolute() else REPO_ROOT / py_config)
    train_peft_script = SCRIPT_DIR / "train_peft.py"

    if not train_peft_script.exists():
        print(f"[ERROR] train_peft.py not found at {train_peft_script}", file=sys.stderr)
        return 2

    cmd = [py, str(train_peft_script), "--method", method]
    if dry_run:
        cmd.append("--dry-run")
    cmd.extend(extra_args)

    print("+ " + " ".join(cmd), flush=True)
    env = dict(os.environ)
    if program.get("tokenless_home"):
        env["TOKENLESS_HOME"] = str(resolve_path(program["tokenless_home"], REPO_ROOT))
    return subprocess.run(cmd, cwd=REPO_ROOT, env=env, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--program", default=str(DEFAULT_PROGRAM))
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("validate")

    list_p = sub.add_parser("list")
    list_p.add_argument("--status", default=None)
    list_p.add_argument("--family", default=None)

    inspect_p = sub.add_parser("inspect")
    inspect_p.add_argument("method_id")

    plan_p = sub.add_parser("plan")
    plan_p.add_argument("--stack", default=None)
    plan_p.add_argument("--out", default=None)

    corpus_p = sub.add_parser("export-corpus")
    corpus_p.add_argument("--out", required=True)

    sub.add_parser("matrix")

    run_p = sub.add_parser("run")
    run_p.add_argument("--stage", default="all",
                       choices=["all", "prepare", "train", "evaluate", "export", "publish"])
    run_p.add_argument("--dry-run", action="store_true")

    peft_p = sub.add_parser("run-peft", help="Run a PEFT/alignment method via train_peft.py")
    peft_p.add_argument("--method", required=True,
                        help="PEFT method ID (lora, dora, ia3, sft, dpo, omni, ...)")
    peft_p.add_argument("--dry-run", action="store_true")
    peft_p.add_argument("extra_args", nargs=argparse.REMAINDER,
                        help="Extra flags passed directly to train_peft.py")

    args = parser.parse_args()
    registry = load_registry(resolve_path(args.registry))
    program_path = resolve_path(args.program)
    program = load_program(program_path) if program_path.exists() else {}

    if args.cmd == "validate":
        report = validate_registry(registry)
        print(json.dumps(report, indent=2))
        return 0 if report["pass"] else 1

    if args.cmd == "list":
        rows = registry.get("methods", [])
        if args.status:
            rows = [row for row in rows if row.get("status") == args.status]
        if args.family:
            rows = [row for row in rows if row.get("family") == args.family]
        for row in rows:
            print(f"{row['id']:<32} {row['status']:<14} {row['family']:<24} {row['name']}")
        return 0

    if args.cmd == "inspect":
        methods = method_index(registry)
        if args.method_id not in methods:
            print(f"unknown method: {args.method_id}", file=sys.stderr)
            return 2
        print(json.dumps(methods[args.method_id], indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "plan":
        plan = plan_stack(registry, program, args.stack)
        text = json.dumps(plan, indent=2, ensure_ascii=False)
        print(text)
        if args.out:
            out = resolve_path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text + "\n", encoding="utf-8")
        return 0

    if args.cmd == "export-corpus":
        export_program_corpus(registry, resolve_path(args.out))
        print(f"wrote {resolve_path(args.out)}")
        return 0

    if args.cmd == "matrix":
        print_matrix(registry)
        return 0

    if args.cmd == "run":
        return run_delegate(program, args.stage, args.dry_run)

    if args.cmd == "run-peft":
        return run_peft(program, args.method, args.dry_run, getattr(args, "extra_args", []))

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
