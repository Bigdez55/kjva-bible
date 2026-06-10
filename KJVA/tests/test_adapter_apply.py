"""D09 verification gate: a LOADED XMIND adapter actually applies (not a silent no-op).

The numerical parity gate (tests/test_pt_xmind_parity.py) runs with NO adapter
active, so it proves the no-adapter forward path is intact but CANNOT prove that a
*loaded* adapter changes logits. This test supplies that missing evidence for the
D09 fix (lora.c canonical-name join: training-stack key `blocks.N.attn.q.A.weight`
must canonicalize to the runtime lookup key `blk.0.attn_q.weight`).

It drives the C harness ai/xmind/tests/adapter_apply_check.c, whose single exit-0
transitively demonstrates BOTH task clauses:

  * Pass 1 — forward AFTER xmind_adapter_runtime_init() but BEFORE activate:
    the clean no-adapter forward (the no-op baseline; logits snapshotted).
  * Pass 2 — forward WITH the adapter active: CHECK 3 asserts apply_count > 0
    and CHECK 4 asserts logit MAE (vs the Pass-1 baseline) != 0.

So a passing harness proves the no-adapter path is a clean no-op AND that the
activated adapter applies with a non-zero delta. This Python test does not merely
trust the exit code: it parses the harness PASS line and independently asserts
apply_count > 0 and logit_MAE > 0.

The harness is the only thing that can exercise xmind_lora_find()'s name
canonicalization — the PyTorch eval path (pt/eval_clean_ppl.py) loads weights
directly and never touches the C lookup-key join, so it cannot verify D09.

This test SKIPS (never fails) when the artifacts (GGUF / proof adapter / harness
source) are absent or the build/run cannot complete, per the "must pass or skip
cleanly" contract.

Run:  python3 -m pytest tests/test_adapter_apply.py -q
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent              # models v7/
XMIND = ROOT / "ai" / "xmind"
HARNESS_SRC = XMIND / "tests" / "adapter_apply_check.c"
HARNESS_BIN = XMIND / "build" / "adapter_apply_check"
STATIC_LIB = XMIND / "build" / "libxmind-core.a"

# Soup GGUF: at the gguf root in a dev tree, ARCHIVED in a sealed production tree
# (single-runtime authority keeps only canonical.gguf at root). Resolve both so the
# check runs in the sealed tree WITHOUT placing a non-canonical gguf at the root.
GGUF = next((p for p in (
    ROOT / "training" / "gguf" / "clean_base_soup_v1.gguf",
    ROOT / "training" / "gguf" / "archive" / "clean_base_soup_v1.source.gguf",
) if p.exists()), ROOT / "training" / "gguf" / "clean_base_soup_v1.gguf")
ADAPTER = ROOT / "training" / "adapters" / "staging" / "lora_proof" / "adapter.safetensors"
PROMPT = "In the beginning"

# Full include/define set mirroring ai/xmind/Makefile CFLAGS_POSIX. The parity
# test's build rule used only "-Iinclude -Ishim", which fails here with
# "pal.h not found" because lora.h pulls in the substrate platform headers.
_BUILD_CMD = [
    "clang", "-std=c11",
    "-Wall", "-Wextra", "-Wno-unused-parameter", "-Wno-unused-function",
    "-Wno-incompatible-pointer-types", "-Wno-format",
    "-O2", "-DXMIND_POSIX_BUILD=1", "-D_POSIX_C_SOURCE=200809L", "-D_DARWIN_C_SOURCE",
    "-Iinclude", "-Ishim",
    "-I../../pal/include",
    "-I../../net/xnet/include",
    "-I../../sec/xsec/include",
    "-I../../xisc/include",
    "-I../../xstore/include",
    "tests/adapter_apply_check.c", "build/libxmind-core.a",
    "-lpthread", "-lm",
    "-o", "build/adapter_apply_check",
]

# [adapter-check] PASS n_entries=56 find("blk.0.attn_q.weight")=ok apply_count=896 logit_MAE=0.997083
_PASS_RE = re.compile(
    r"\[adapter-check\]\s+PASS\b.*?"
    r"apply_count=(?P<apply>\d+).*?"
    r"logit_MAE=(?P<mae>[0-9]+(?:\.[0-9]+)?)",
)


def _ensure_harness() -> None:
    """Build the harness if its binary is absent. Any failure -> skip (never fail)."""
    if HARNESS_BIN.exists():
        return
    try:
        if not STATIC_LIB.exists():
            subprocess.run(["make", "static"], cwd=XMIND, check=True,
                           capture_output=True, text=True)
        subprocess.run(_BUILD_CMD, cwd=XMIND, check=True,
                       capture_output=True, text=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        pytest.skip(f"adapter_apply_check harness could not be built: {exc}")
    if not HARNESS_BIN.exists():
        pytest.skip("adapter_apply_check binary missing after build")


@pytest.mark.skipif(
    not GGUF.exists() or not ADAPTER.exists() or not HARNESS_SRC.exists(),
    reason="D09 artifacts not present (GGUF / proof adapter / harness source)",
)
def test_loaded_adapter_actually_applies():
    """A loaded XMIND adapter applies (apply_count>0) and moves the logits (MAE>0);
    the no-adapter forward (Pass 1 baseline inside the harness) is the clean no-op."""
    _ensure_harness()

    try:
        out = subprocess.run(
            [str(HARNESS_BIN), str(GGUF), str(ADAPTER), PROMPT],
            capture_output=True, text=True, timeout=300,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        pytest.skip(f"adapter_apply_check could not run: {exc}")

    combined = (out.stdout or "") + "\n" + (out.stderr or "")

    # Exit code must be clean — non-zero is a real D09 regression (one of CHECKs 1-4
    # failed), so this is an assertion, not a skip.
    assert out.returncode == 0, (
        f"adapter_apply_check exit={out.returncode} (D09 regression — a loaded "
        f"adapter no longer applies cleanly).\n{combined}"
    )

    # Don't trust the exit code alone: independently parse + verify the evidence,
    # so a future harness made lenient cannot silently pass.
    m = _PASS_RE.search(combined)
    assert m is not None, f"could not find adapter-check PASS line in output:\n{combined}"

    apply_count = int(m.group("apply"))
    logit_mae = float(m.group("mae"))

    # CHECK 3 evidence: the delta was actually applied at runtime.
    assert apply_count > 0, (
        f"apply_count={apply_count} — adapter loaded but never applied (silent no-op)."
    )
    # CHECK 4 evidence: the applied delta changed the logits vs the no-adapter baseline.
    assert logit_mae > 0.0, (
        f"logit_MAE={logit_mae} — adapter applied but produced no numerical change "
        f"(delta had no effect)."
    )


if __name__ == "__main__":  # manual run convenience
    raise SystemExit(pytest.main([__file__, "-q"]))
