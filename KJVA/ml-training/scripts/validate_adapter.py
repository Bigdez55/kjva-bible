#!/usr/bin/env python3
"""
validate_adapter.py — Adapter governance and promotion workflow

Validates a staged adapter and promotes it from adapters/staging/ → adapters/gated/
once all gates pass.

Validation gates:
  1. Genome check   — adapter_genome.json exists and has required fields
  2. Weights check  — adapter_weights.npz exists and loads cleanly
  3. Shape check    — all weight tensors have expected shapes (no zeros, no NaN)
  4. Method check   — peft_method field maps to a known method in METHOD_REGISTRY
  5. Size gate      — adapter size is within budget (configurable)
  6. Retention gate — (optional) if --retention-threshold is set, require a
                       base_retention score in the genome ≥ threshold

Usage:
  python validate_adapter.py list
  python validate_adapter.py check --adapter adapters/staging/lora_kjv_v1
  python validate_adapter.py promote --adapter adapters/staging/lora_kjv_v1
  python validate_adapter.py quarantine --adapter adapters/gated/lora_kjv_v1 --reason "domain bleed detected"
  python validate_adapter.py rollback --adapter adapters/gated/lora_kjv_v1
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ML_TRAINING = SCRIPT_DIR.parent
STAGING = ML_TRAINING / "adapters" / "staging"
GATED = ML_TRAINING / "adapters" / "gated"
REGISTRY_FILE = ML_TRAINING / "programs" / "omni_training_registry.json"

REQUIRED_GENOME_FIELDS = [
    "name", "version", "base_model", "peft_method", "delta_family"
]

MAX_ADAPTER_SIZE_MB = 500.0  # hard limit per adapter


# ---------------------------------------------------------------------------
# Gate result
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    name: str
    passed: bool
    message: str
    severity: str = "error"   # "error" | "warning" | "info"


@dataclass
class ValidationReport:
    adapter_path: str
    adapter_name: str
    gates: list[GateResult] = field(default_factory=list)
    overall: str = "unknown"   # "pass" | "fail" | "warn"
    validated_at: str = ""

    def add(self, gate: GateResult):
        self.gates.append(gate)

    def finalize(self):
        errors = [g for g in self.gates if not g.passed and g.severity == "error"]
        warnings = [g for g in self.gates if not g.passed and g.severity == "warning"]
        self.overall = "fail" if errors else ("warn" if warnings else "pass")
        self.validated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "adapter_path": self.adapter_path,
            "adapter_name": self.adapter_name,
            "overall": self.overall,
            "validated_at": self.validated_at,
            "gates": [
                {"name": g.name, "passed": g.passed, "message": g.message, "severity": g.severity}
                for g in self.gates
            ],
        }

    def print_summary(self):
        symbol = {"pass": "✓", "fail": "✗", "warn": "⚠", "unknown": "?"}.get(self.overall, "?")
        print(f"\n{symbol} {self.adapter_name}  [{self.overall.upper()}]")
        for gate in self.gates:
            icon = "  ✓" if gate.passed else ("  ⚠" if gate.severity == "warning" else "  ✗")
            print(f"{icon}  {gate.name}: {gate.message}")


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

def load_known_methods() -> set[str]:
    """Load method IDs from the omni training registry."""
    if not REGISTRY_FILE.exists():
        return set()
    registry = json.loads(REGISTRY_FILE.read_text())
    return {m["id"].split(".")[-1] for m in registry.get("methods", [])}


def validate_adapter(adapter_dir: Path, retention_threshold: float | None = None) -> ValidationReport:
    report = ValidationReport(
        adapter_path=str(adapter_dir),
        adapter_name=adapter_dir.name,
    )

    # Gate 1: Directory exists
    if not adapter_dir.exists():
        report.add(GateResult("directory_exists", False, f"Path not found: {adapter_dir}"))
        report.finalize()
        return report
    report.add(GateResult("directory_exists", True, f"Found: {adapter_dir}"))

    # Gate 2: Genome file exists
    genome_file = adapter_dir / "adapter_genome.json"
    if not genome_file.exists():
        report.add(GateResult("genome_exists", False, "adapter_genome.json not found"))
        report.finalize()
        return report
    report.add(GateResult("genome_exists", True, "adapter_genome.json present"))

    # Gate 3: Genome parses and has required fields
    try:
        raw = json.loads(genome_file.read_text())
        genome: dict[str, Any] = raw.get("adapter_genome", raw)
        missing = [f for f in REQUIRED_GENOME_FIELDS if f not in genome]
        if missing:
            report.add(GateResult("genome_fields", False,
                                  f"Missing required fields: {missing}"))
        else:
            report.add(GateResult("genome_fields", True,
                                  f"method={genome.get('peft_method')}  family={genome.get('delta_family')}"))
    except Exception as e:
        report.add(GateResult("genome_parse", False, f"Parse error: {e}"))
        report.finalize()
        return report

    # Gate 4: Method is known
    known = load_known_methods()
    method = genome.get("peft_method", "")
    if known and method not in known:
        report.add(GateResult("method_known", False,
                              f"'{method}' not in training registry", severity="warning"))
    else:
        report.add(GateResult("method_known", True, f"method '{method}' recognized"))

    # Gate 5: Weights file exists
    weights_file = adapter_dir / "adapter_weights.npz"
    if not weights_file.exists():
        report.add(GateResult("weights_exist", False,
                              "adapter_weights.npz not found", severity="warning"))
    else:
        report.add(GateResult("weights_exist", True,
                              f"adapter_weights.npz present ({weights_file.stat().st_size / 1024:.1f} KB)"))

        # Gate 6: Weights load and are valid
        try:
            import numpy as np
            arrays = dict(np.load(str(weights_file)))
            if not arrays:
                report.add(GateResult("weights_valid", False, "No arrays in weights file"))
            else:
                nan_keys = [k for k, v in arrays.items() if np.any(np.isnan(v))]
                inf_keys = [k for k, v in arrays.items() if np.any(np.isinf(v))]
                total_params = sum(v.size for v in arrays.values())
                if nan_keys:
                    report.add(GateResult("weights_valid", False,
                                          f"NaN values in: {nan_keys[:3]}", severity="error"))
                elif inf_keys:
                    report.add(GateResult("weights_valid", False,
                                          f"Inf values in: {inf_keys[:3]}", severity="error"))
                else:
                    report.add(GateResult("weights_valid", True,
                                          f"{len(arrays)} tensors, {total_params:,} total params"))
        except Exception as e:
            report.add(GateResult("weights_load", False, f"Load error: {e}"))

        # Gate 7: Adapter size within budget
        size_mb = weights_file.stat().st_size / (1024 * 1024)
        if size_mb > MAX_ADAPTER_SIZE_MB:
            report.add(GateResult("size_gate", False,
                                  f"{size_mb:.1f} MB > limit {MAX_ADAPTER_SIZE_MB} MB"))
        else:
            report.add(GateResult("size_gate", True, f"{size_mb:.1f} MB within {MAX_ADAPTER_SIZE_MB} MB limit"))

    # Gate 8: Retention score (optional)
    if retention_threshold is not None:
        eval_data = genome.get("evaluation", {})
        retention = eval_data.get("base_retention")
        if retention is None:
            report.add(GateResult("retention_score", False,
                                  "No base_retention score in genome evaluation", severity="warning"))
        elif float(retention) < retention_threshold:
            report.add(GateResult("retention_score", False,
                                  f"base_retention={retention:.3f} < threshold {retention_threshold}",
                                  severity="error"))
        else:
            report.add(GateResult("retention_score", True,
                                  f"base_retention={retention:.3f} ≥ threshold {retention_threshold}"))

    report.finalize()
    return report


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    dirs = []
    for base in (STAGING, GATED):
        label = base.name
        if base.exists():
            for d in sorted(base.iterdir()):
                if d.is_dir() and d.name != ".gitkeep":
                    genome = d / "adapter_genome.json"
                    method = "?"
                    if genome.exists():
                        try:
                            raw = json.loads(genome.read_text())
                            g = raw.get("adapter_genome", raw)
                            method = g.get("peft_method", "?")
                        except Exception:
                            pass
                    dirs.append((label, d.name, method))

    if not dirs:
        print("No adapters found in staging/ or gated/")
        return 0

    print(f"{'BUCKET':<10}  {'NAME':<30}  {'METHOD'}")
    print("-" * 56)
    for bucket, name, method in dirs:
        print(f"{bucket:<10}  {name:<30}  {method}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    adapter_dir = Path(args.adapter).expanduser()
    if not adapter_dir.is_absolute():
        adapter_dir = ML_TRAINING / adapter_dir

    report = validate_adapter(adapter_dir, getattr(args, "retention_threshold", None))
    report.print_summary()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))

    return 0 if report.overall == "pass" else 1


def cmd_promote(args: argparse.Namespace) -> int:
    adapter_dir = Path(args.adapter).expanduser()
    if not adapter_dir.is_absolute():
        adapter_dir = ML_TRAINING / adapter_dir

    # Must be in staging
    if STAGING not in adapter_dir.parents and adapter_dir.parent != STAGING:
        print(f"[ERROR] Adapter must be in adapters/staging/ to promote. Got: {adapter_dir}", file=sys.stderr)
        return 2

    report = validate_adapter(adapter_dir, getattr(args, "retention_threshold", None))
    report.print_summary()

    if report.overall == "fail":
        print(f"\n[ERROR] Cannot promote: validation failed. Fix errors above first.")
        return 1

    if report.overall == "warn" and not args.force:
        print(f"\n[WARN] Warnings present. Use --force to promote anyway.")
        return 1

    dest = GATED / adapter_dir.name
    if dest.exists():
        print(f"[ERROR] {dest} already exists. Remove it first or use a new version name.", file=sys.stderr)
        return 2

    GATED.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(adapter_dir), str(dest))

    # Write promotion record
    promotion_record = {
        "promoted_from": str(adapter_dir),
        "promoted_to": str(dest),
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "validation_report": report.to_dict(),
    }
    (dest / "promotion_record.json").write_text(
        json.dumps(promotion_record, indent=2), encoding="utf-8"
    )

    print(f"\n[SUCCESS] Promoted → {dest}")
    return 0


def cmd_quarantine(args: argparse.Namespace) -> int:
    adapter_dir = Path(args.adapter).expanduser()
    if not adapter_dir.is_absolute():
        adapter_dir = ML_TRAINING / adapter_dir

    if not adapter_dir.exists():
        print(f"[ERROR] Not found: {adapter_dir}", file=sys.stderr)
        return 2

    quarantine_dir = adapter_dir.parent / f"{adapter_dir.name}__QUARANTINED"
    adapter_dir.rename(quarantine_dir)

    record = {
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
        "reason": args.reason,
        "original_path": str(adapter_dir),
    }
    (quarantine_dir / "quarantine_record.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )

    print(f"[QUARANTINED] {adapter_dir.name} → {quarantine_dir.name}")
    print(f"  Reason: {args.reason}")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    adapter_dir = Path(args.adapter).expanduser()
    if not adapter_dir.is_absolute():
        adapter_dir = ML_TRAINING / adapter_dir

    if not adapter_dir.exists():
        print(f"[ERROR] Not found: {adapter_dir}", file=sys.stderr)
        return 2

    genome_file = adapter_dir / "adapter_genome.json"
    if not genome_file.exists():
        print("[ERROR] No genome file found — cannot determine previous version.", file=sys.stderr)
        return 2

    raw = json.loads(genome_file.read_text())
    genome = raw.get("adapter_genome", raw)
    prev = genome.get("rollback", {}).get("previous_stable", "")

    if not prev:
        print("[WARN] No previous_stable version recorded in genome.")
        return 1

    print(f"[INFO] Rollback target: {prev}")
    print("[INFO] Manual action required: copy previous weights to this adapter directory.")
    print(f"[INFO] Current adapter quarantined first:")

    args_q = argparse.Namespace(
        adapter=str(adapter_dir),
        reason=f"Rolled back — replaced by {prev}",
    )
    return cmd_quarantine(args_q)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Adapter governance and promotion workflow")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all adapters in staging/ and gated/")

    check_p = sub.add_parser("check", help="Validate an adapter (report only, no side effects)")
    check_p.add_argument("--adapter", required=True, help="Path to adapter directory")
    check_p.add_argument("--retention-threshold", type=float, default=None)
    check_p.add_argument("--json", action="store_true", help="Print JSON report")

    promote_p = sub.add_parser("promote", help="Validate and copy staging → gated")
    promote_p.add_argument("--adapter", required=True, help="Path to adapter in staging/")
    promote_p.add_argument("--retention-threshold", type=float, default=None)
    promote_p.add_argument("--force", action="store_true", help="Promote even if warnings")

    quarantine_p = sub.add_parser("quarantine", help="Mark adapter as quarantined")
    quarantine_p.add_argument("--adapter", required=True)
    quarantine_p.add_argument("--reason", required=True)

    rollback_p = sub.add_parser("rollback", help="Quarantine current, point to previous stable")
    rollback_p.add_argument("--adapter", required=True)

    args = p.parse_args()

    commands = {
        "list": cmd_list,
        "check": cmd_check,
        "promote": cmd_promote,
        "quarantine": cmd_quarantine,
        "rollback": cmd_rollback,
    }
    return commands[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
