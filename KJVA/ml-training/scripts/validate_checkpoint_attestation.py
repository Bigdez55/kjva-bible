#!/usr/bin/env python3
"""Validate export-bundle checkpoint attestation fields."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED_MANIFEST_FIELDS = [
    "export_id",
    "model_id",
    "source_ckpt_sha256",
    "weights_sha256",
    "weights_match_source_checkpoint",
    "tokenization",
    "architecture",
    "n_parameters",
    "tokenless_attestation",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_bundle(bundle_dir: Path) -> dict[str, Any]:
    manifest_path = bundle_dir / "manifest.json"
    weights_path = bundle_dir / "weights.safetensors"
    config_path = bundle_dir / "model_config.json"
    errors = []
    if not manifest_path.exists():
        errors.append("missing manifest.json")
        return {"bundle_dir": str(bundle_dir), "pass": False, "errors": errors}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            errors.append(f"missing manifest field: {field}")
    if not weights_path.exists():
        errors.append("missing weights.safetensors")
    if not config_path.exists():
        errors.append("missing model_config.json")
    if weights_path.exists() and manifest.get("weights_sha256") != sha256_file(weights_path):
        errors.append("weights_sha256 does not match weights.safetensors")
    if manifest.get("weights_match_source_checkpoint") is not True:
        errors.append("weights_match_source_checkpoint is not true")
    if int(manifest.get("n_parameters") or 0) <= 0:
        errors.append("n_parameters must be positive")
    if "pretrained weights" not in str(manifest.get("tokenless_attestation", "")).lower():
        errors.append("attestation does not explicitly mention pretrained weight policy")
    return {
        "bundle_dir": str(bundle_dir),
        "model_id": manifest.get("model_id"),
        "tokenization": manifest.get("tokenization"),
        "n_parameters": manifest.get("n_parameters"),
        "pass": not errors,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    report = validate_bundle(Path(args.bundle_dir))
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
