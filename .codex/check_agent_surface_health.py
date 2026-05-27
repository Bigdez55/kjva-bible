#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from agent_surface_health import command_drift_report


def _run_validator(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)
    payload['exit_code'] = completed.returncode
    return payload


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    codex = _run_validator(repo_root / '.codex' / 'check_registration.py')
    claude = _run_validator(repo_root / '.claude' / 'check_registration.py')
    drift = command_drift_report(repo_root)
    combined_ok = bool(codex.get('ok')) and bool(claude.get('ok'))
    result = {
        'repo_root': str(repo_root),
        'codex': codex,
        'claude': claude,
        'combined': {
            'ok': combined_ok,
            'command_drift': drift,
        },
    }
    print(json.dumps(result, indent=2))
    return 0 if combined_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
