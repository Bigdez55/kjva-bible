"""sensory/provision.py — self-provisioning senses.

The model installs its OWN perception engines on demand — "anywhere and everywhere", as
part of its function — so a sense works the first time it is used with no manual setup.

A sense seam (asr / vision) calls :func:`ensure` when it needs an engine:
  * if the package is already importable → use it;
  * else, if auto-provision is enabled (DEFAULT ON), best-effort ``pip install`` it in a
    subprocess, then re-import and use it;
  * else / on any failure → return False and the seam degrades gracefully (never crashes).

Controllable for locked-down / reproducible / air-gapped deployments:
  * ``TOKENLESS_SENSES_AUTOPROVISION=0`` disables runtime installation (pre-bake the engines
    instead, then this is a pure import check).
  * ``TOKENLESS_SENSES_INSTALL_TIMEOUT`` (seconds) bounds each install.

Where pip does not exist (mobile, browser, frozen builds), a host plugs a native engine via
the seam's ``register_engine()`` — so senses are available everywhere either way. The result
of each attempt is CACHED per process, so a missing/offline engine is tried once, not per turn.
"""
from __future__ import annotations

import importlib
import logging
import os
import subprocess
import sys

logger = logging.getLogger("tokenless.sensory.provision")

# import_name -> resolved availability (so we never re-attempt an install every call).
_cache: dict[str, bool] = {}


def autoprovision_enabled() -> bool:
    """Runtime self-install is ON by default; opt OUT for locked-down/offline deploys."""
    val = os.environ.get("TOKENLESS_SENSES_AUTOPROVISION", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def _install_timeout_s() -> int:
    try:
        return max(30, int(os.environ.get("TOKENLESS_SENSES_INSTALL_TIMEOUT", "900")))
    except ValueError:
        return 900


def _try_import(import_name: str) -> bool:
    try:
        importlib.import_module(import_name)
        return True
    except Exception:  # noqa: BLE001
        return False


def ensure(import_name: str, pip_name: str) -> bool:
    """Ensure a perception-engine package is importable, auto-installing if needed.

    Returns True iff the package is importable after the attempt. NEVER raises — any
    failure (no network, no pip, sandbox, install error) is fail-open (returns False)."""
    if import_name in _cache:
        return _cache[import_name]
    if _try_import(import_name):
        _cache[import_name] = True
        return True
    if not autoprovision_enabled():
        logger.info("auto-provision disabled — '%s' unavailable (set TOKENLESS_SENSES_AUTOPROVISION=1 "
                    "or pre-install %s to enable this sense)", import_name, pip_name)
        _cache[import_name] = False
        return False
    try:
        logger.info("auto-provisioning sense engine: pip install %s …", pip_name)
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "--disable-pip-version-check", pip_name],
            capture_output=True, text=True, timeout=_install_timeout_s(),
        )
        if proc.returncode != 0:
            logger.warning("auto-provision of %s failed (rc=%s) — sense degraded: %s",
                           pip_name, proc.returncode, (proc.stderr or "").strip()[-300:])
            _cache[import_name] = False
            return False
        importlib.invalidate_caches()
        ok = _try_import(import_name)
        _cache[import_name] = ok
        logger.info("auto-provisioned %s — sense engine %s", pip_name,
                    "ready" if ok else "still not importable (degraded)")
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.warning("auto-provision of %s errored (fail-open): %s", pip_name, exc)
        _cache[import_name] = False
        return False


def reset_cache() -> None:
    """Forget cached availability (mainly for tests)."""
    _cache.clear()
