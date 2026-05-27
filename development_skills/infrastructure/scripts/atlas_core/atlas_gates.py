"""Safe gate runner for Atlas Platform Core."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

from atlas_models import write_yaml
from atlas_paths import GATE_LOG_DIR, GATES_DIR, ROOT, VERIFICATION_GATE_DIR, rel


@dataclass(frozen=True)
class SafeGate:
    name: str
    command: list[str]
    reason: str


SAFE_GATES = [
    SafeGate("validate_skills_stack", ["python3", "infrastructure/scripts/validate_skills_stack.py"], "Read-only v7 artifact validation."),
    SafeGate("regression_runner", ["python3", "infrastructure/scripts/regression_runner.py"], "Read-only route regression checks."),
    SafeGate("registry_sync_check", ["python3", "infrastructure/scripts/registry_sync/sync_registries.py", "--check"], "Registry check mode only."),
    SafeGate("truth_drift_check", ["python3", "infrastructure/scripts/drift_checkers/check_truth_drift.py", "--check", "--no-write"], "Truth drift no-write mode."),
    SafeGate("skill_drift_check", ["python3", "infrastructure/scripts/drift_checkers/check_skill_drift.py"], "Skill metadata validation."),
    SafeGate("traceability_drift_check", ["python3", "infrastructure/scripts/drift_checkers/check_traceability_drift.py"], "Traceability coverage check."),
    SafeGate("git_diff_check", ["git", "diff", "--check"], "Git whitespace check."),
]

UNSAFE_SKIPPED = [
    {
        "command": "python3 infrastructure/scripts/rebuild_master_ledger.py --check",
        "reason": "No true check mode; script writes master_ledger.yaml.",
    },
    {
        "command": "07_build/scripts/rebuild_all.sh",
        "reason": "Runs mutating generators for registries, docs, proof, and mesh outputs.",
    },
]


def run_safe_gates() -> dict[str, Any]:
    GATES_DIR.mkdir(parents=True, exist_ok=True)
    GATE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    VERIFICATION_GATE_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for gate in SAFE_GATES:
        proc = subprocess.run(gate.command, cwd=ROOT, text=True, capture_output=True, env=env)
        stdout_path = GATE_LOG_DIR / f"{gate.name}.stdout.txt"
        stderr_path = GATE_LOG_DIR / f"{gate.name}.stderr.txt"
        stdout_path.write_text(proc.stdout or "")
        stderr_path.write_text(proc.stderr or "")
        results.append(
            {
                "name": gate.name,
                "command": " ".join(gate.command),
                "return_code": proc.returncode,
                "verdict": "pass" if proc.returncode == 0 else "fail",
                "reason": gate.reason,
                "stdout_path": rel(stdout_path),
                "stderr_path": rel(stderr_path),
            }
        )
    payload = {
        "safe_gates": results,
        "unsafe_skipped": UNSAFE_SKIPPED,
        "overall_verdict": "pass" if all(r["return_code"] == 0 for r in results) else "fail",
    }
    write_yaml(VERIFICATION_GATE_DIR / "atlas_platform_core_safe_gates.yaml", payload)
    (VERIFICATION_GATE_DIR / "atlas_platform_core_safe_gates.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (GATES_DIR / "atlas_safe_gate_results.md").write_text(gates_markdown(payload))
    return payload


def gates_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Atlas Platform Core Safe Gate Results",
        "",
        f"Overall verdict: `{payload['overall_verdict']}`",
        "",
        "| Gate | Command | Return Code | Verdict | Output |",
        "|---|---|---:|---|---|",
    ]
    for gate in payload["safe_gates"]:
        lines.append(
            f"| `{gate['name']}` | `{gate['command']}` | {gate['return_code']} | `{gate['verdict']}` | `{gate['stdout_path']}` |"
        )
    lines.extend(["", "## Unsafe Gates Skipped", ""])
    for item in payload["unsafe_skipped"]:
        lines.append(f"- `{item['command']}`: {item['reason']}")
    lines.append("")
    return "\n".join(lines)
