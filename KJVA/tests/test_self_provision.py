"""test_self_provision.py — the model installs its own perception engines (no manual setup).

sensory/provision.ensure(import_name, pip_name) makes a sense engine importable, auto-pip-
installing it if missing. Default ON, fail-open, cached, disable-able. These tests pin the
ORCHESTRATION deterministically (subprocess + import are mocked, so no real network/install):

  1. already-importable      -> True, and pip is NOT invoked.
  2. missing + autoprovision  -> pip IS invoked; True if the post-install import succeeds.
  3. install fails (rc!=0)    -> False (fail-open), never raises.
  4. autoprovision disabled   -> False, pip NOT invoked (locked-down/offline deploys).
  5. cached                   -> a second call does not re-invoke pip.

Run:  PYTHONPATH=ai/tokenless-agent/src python3 -m pytest tests/test_self_provision.py -q
"""
import sys
import types
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

provision = pytest.importorskip("sensory.provision")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    provision.reset_cache()
    monkeypatch.setenv("TOKENLESS_SENSES_AUTOPROVISION", "1")
    yield
    provision.reset_cache()


def _mock_pip(monkeypatch, returncode=0):
    calls = []

    def _run(cmd, *a, **k):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=returncode, stdout="", stderr="boom")

    monkeypatch.setattr(provision.subprocess, "run", _run)
    return calls


def test_already_present_skips_install(monkeypatch):
    calls = _mock_pip(monkeypatch)
    assert provision.ensure("os", "os") is True          # stdlib, always importable
    assert calls == [], "pip must NOT run when the package is already importable"


def test_missing_then_installed(monkeypatch):
    calls = _mock_pip(monkeypatch, returncode=0)
    # import fails first, then "succeeds" after the (mocked) install.
    seq = iter([False, True])
    monkeypatch.setattr(provision, "_try_import", lambda name: next(seq))
    assert provision.ensure("totally_missing_pkg", "totally-missing-pkg") is True
    assert len(calls) == 1 and "install" in calls[0], "pip install should have run once"


def test_install_failure_is_fail_open(monkeypatch):
    _mock_pip(monkeypatch, returncode=1)                 # pip returns non-zero
    monkeypatch.setattr(provision, "_try_import", lambda name: False)
    assert provision.ensure("nope_pkg", "nope-pkg") is False   # degraded, not raised


def test_disabled_does_not_install(monkeypatch):
    monkeypatch.setenv("TOKENLESS_SENSES_AUTOPROVISION", "0")
    calls = _mock_pip(monkeypatch)
    monkeypatch.setattr(provision, "_try_import", lambda name: False)
    assert provision.ensure("x_pkg", "x-pkg") is False
    assert calls == [], "auto-provision disabled -> pip must not run"


def test_result_is_cached(monkeypatch):
    calls = _mock_pip(monkeypatch, returncode=1)
    monkeypatch.setattr(provision, "_try_import", lambda name: False)
    provision.ensure("cached_pkg", "cached-pkg")
    provision.ensure("cached_pkg", "cached-pkg")          # second call
    assert len(calls) == 1, "a failed/looked-up engine must be cached, not retried every turn"
