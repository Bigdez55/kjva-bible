"""conftest.py — suite-wide test defaults for the sensory seams.

Auto-provisioning (the model installing its own ASR/vision engines) is a PRODUCTION feature.
Tests must be deterministic, offline and fast: they exercise the seams with injected fake
engines (register_engine) and must NEVER trigger a real pip install or load a real model.

So for every test we:
  * disable runtime auto-provision (TOKENLESS_SENSES_AUTOPROVISION=0), and
  * force the auto-resolver to "already tried, found nothing" so available()/transcribe()/
    describe() return only what a test explicitly registers — no real WhisperModel/RapidOCR
    is constructed.

`test_self_provision.py` tests the provision orchestration directly with a MOCKED subprocess,
so it is unaffected by this (it never calls the real installer either).
"""
import os
import sys
from pathlib import Path

import pytest

# Hard-set (NOT setdefault): an exported =1 must not let the suite self-install.
os.environ["TOKENLESS_SENSES_AUTOPROVISION"] = "0"
# Dev mode so TestClient-based tests don't hit the (now fail-closed) auth gate.
os.environ.setdefault("TOKENLESS_DEV_MODE", "1")

_SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# ----------------------------------------------------------------------------------------
# Local-`peft` package disambiguation (only an issue once MLX is installed).
# ----------------------------------------------------------------------------------------
# The repo has TWO local packages BOTH importable as the bare name `peft`:
#   training/peft        — MLX  (router/conflict/base/alignment.distillation)
#   training/pt/peft     — torch (attach_adapters/operators/DeltaOperator)
# plus `model`/`train_peft` which also exist under both training/pt and training/scripts.
# In the shared pytest process whichever is imported first wins sys.modules, so a later
# `from peft.X import` in a different test resolves the WRONG package. This was latent while
# the MLX tests SKIPPED; installing MLX exposes it as order-dependent cross-test failures.
#
# Fix WITHOUT renaming an ADR-mapped package: per peft-using test FILE, (1) at collectstart
# purge any stale colliding cache so the file's own module-level `sys.path.insert(0, dir)` +
# `import peft` resolves fresh; (2) around each test BODY, pin the file's dirs at sys.path
# front and CONDITIONALLY purge only a WRONG-dir cached module (so a correctly-bound module
# keeps its class identity — else a re-import makes `issubclass` spuriously fail), then
# RESTORE sys.path on teardown so nothing leaks to other tests (the leak was the bug in the
# first attempt). No-op for every non-peft test file.
_PEFT_DIRS_BY_FILE = {
    "test_pt_gradflow.py":          ["training/pt"],
    "test_distillation_wiring.py":  ["training", "training/scripts"],
    "test_peft_trust_chain.py":     ["training"],
    "test_adapter_genome_scope.py": ["training"],
    "test_peft_route_effective.py": ["training", "training/scripts"],
}
_COLLIDING = ("peft", "model", "train_peft")
_REPO = Path(__file__).resolve().parent.parent


def _purge_wrong(wanted):
    # A colliding module `top` (peft/model/train_peft) provided by dir W lives at W/top(.py|/…).
    # Match on the W/top prefix, NOT just W — else `training/pt/peft` is wrongly accepted under
    # wanted dir `training` (training/pt startswith training), defeating the purge.
    for name in list(sys.modules):
        top = name.split(".")[0]
        if top in _COLLIDING:
            f = getattr(sys.modules.get(name), "__file__", "") or ""
            if f and not any(f.startswith(str(Path(w) / top)) for w in wanted):
                del sys.modules[name]


def pytest_collectstart(collector):
    # NOTE: correctness here does not depend on collection ORDER — the autouse fixture below
    # pins+purges per-test-body and snapshot/restores, so even pytest-randomly is safe. This
    # collectstart purge is a belt-and-suspenders for module-level imports at collection time.
    name = getattr(collector, "name", "") or ""
    if not name.endswith(".py"):
        return
    rels = _PEFT_DIRS_BY_FILE.get(Path(name).name)
    if rels:
        # Purge stale cache only (NO sys.path change) so the module's own inserts take effect.
        _purge_wrong([str(_REPO / r) for r in rels])


@pytest.fixture(autouse=True)
def _pin_local_peft(request):
    rels = _PEFT_DIRS_BY_FILE.get(Path(str(request.node.fspath)).name)
    if not rels:
        yield
        return
    wanted = [str(_REPO / r) for r in rels]
    saved_path = list(sys.path)
    # Snapshot the colliding module objects so teardown can restore them EXACTLY. Purging
    # (not restoring) would evict another file's correctly-bound module — e.g. gradflow's
    # module-level training/pt/peft — forcing its body to re-import a DIFFERENT object and
    # breaking `issubclass` (two distinct DeltaOperator class objects).
    saved_mods = {k: v for k, v in sys.modules.items() if k.split(".")[0] in _COLLIDING}
    for d in reversed(wanted):
        if d in sys.path:
            sys.path.remove(d)
        sys.path.insert(0, d)
    _purge_wrong(wanted)
    try:
        yield
    finally:
        sys.path[:] = saved_path                      # restore sys.path exactly — no leak
        for k in [m for m in sys.modules if m.split(".")[0] in _COLLIDING]:
            del sys.modules[k]
        sys.modules.update(saved_mods)                # restore colliding modules exactly


@pytest.fixture(autouse=True)
def _isolate_sense_engines():
    """Each test starts with NO registered/auto engine; the auto-resolver is neutralized so
    no real model is ever built. Tests opt into an engine via register_engine()."""
    try:
        from sensory import asr, vision, provision  # noqa: PLC0415
        provision.reset_cache()
        asr.reset_engine(); vision.reset_engine()
        # Pretend the (heavy) auto-resolve already ran and found nothing.
        asr._auto_tried = True; asr._auto_engine = None; asr._auto_name = ""
        vision._auto_tried = True; vision._auto_engine = None; vision._auto_name = ""
    except Exception:  # noqa: BLE001 — sensory may be off-path in some suites
        pass
    # Neutralize the XMIND inference engine so the suite stays fast + deterministic (no real
    # C-engine model load per general prompt). A dedicated subprocess test proves real XMIND
    # generation separately. (This neutralizes the binding only in tests — not a product fallback.)
    try:
        from _xmind import client as _xmc  # noqa: PLC0415
        _xmc._init_failed = True; _xmc._client = None
    except Exception:  # noqa: BLE001
        pass
    yield
    try:
        from sensory import asr, vision  # noqa: PLC0415
        asr.reset_engine(); vision.reset_engine()
    except Exception:  # noqa: BLE001
        pass
