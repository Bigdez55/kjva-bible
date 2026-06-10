#!/usr/bin/env bash
# =============================================================================
# scripts/ci/verify_lane.sh — SKIP-IS-FAIL guard for the XMIND C-engine lane.
#
# Ledger #11: a green `pytest` with libxmind-core unbuilt SILENTLY SKIPS the
# entire C-engine set (parity / adapter / generation / materialization), so
# "green" is hollow on the core path. This guard makes green mean the core path
# was genuinely exercised: it parses `pytest -ra` short-summary output and FAILS
# the lane if any C-ENGINE test skipped *for a reason inside the lane's control*
# (the library was not built / would not bind).
#
# USAGE
#   verify_lane.sh <pytest-ra-output-file>     # parse an existing -ra log
#   pytest ... -ra | verify_lane.sh -          # parse from stdin
#
# Exit 0 = no in-scope C-engine skip; nonzero = a required C-engine test skipped.
#
# -----------------------------------------------------------------------------
# C-ENGINE TEST CLASSIFICATION  (the files whose skips are guarded)
# -----------------------------------------------------------------------------
# These five test FILES depend on the compiled libxmind-core C engine (the .a /
# .dylib / .so built by `make` in ai/xmind, and the `xmind_easy_*` ctypes API in
# ai/tokenless-agent/src/_xmind/client.py). With the engine built they MUST run;
# a skip here means the build did not happen or the binding failed:
#
#   tests/test_pt_xmind_parity.py          C forward == pt/model.py forward (parity harness)
#   tests/test_xmind_generation.py         general prompt generates via libxmind-core (M3)
#   tests/test_adapter_runtime_absorption.py  runtime absorbs TOKENLESS_ADAPTER via the engine
#   tests/test_adapter_apply.py            adapter_apply_check C harness (apply_count/MAE)
#   tests/test_model_materialization.py    xmind_easy_model_info() materialization consumer
#
# NOT C-engine (their skips must NOT trip this guard):
#   * MLX-gated   : test_distillation_wiring.py (KL/loop), test_peft_route_effective.py,
#                   test_adapter_genome_scope.py  — skip cleanly when mlx is absent.
#   * torch-gated : test_pt_parity.py, test_pt_gradflow.py  — need torch, NOT the C lib.
#   * stub/files  : test_substrate_smoke.py  — only checks files exist / stub import.
#   There is ZERO overlap between the MLX set and the C-engine set in this repo, so
#   the task's "needs BOTH MLX and the C engine" case is empty here.
#
# -----------------------------------------------------------------------------
# REASON-AWARE GUARD  (why we key on the skip REASON, not just the file path)
# -----------------------------------------------------------------------------
# A literal "any C-engine path in the skip list => fail" guard is WRONG for this
# repo, because three of the five tests also gate on gitignored, non-reproducible
# weight artifacts (*.safetensors / *.gguf are gitignored by policy; no Git LFS;
# the proof adapter likewise). On a clean CI runner those artifacts are absent, so
# the test skips for an ARTIFACT reason the lane cannot control — that is NOT a
# hollow-green, and must not fail the job. (The unconditional C smoke — `xmind-cli`
# PASS in the workflow — is the honest floor that proves the built lib works even
# when these artifact-gated pytests skip.)
#
# Worse, get_client() in _xmind/client.py returns None when EITHER the lib is
# unbuilt OR the .gguf weights are missing, and test_xmind_generation.py /
# test_model_materialization.py both emit the SAME message ("XMIND C engine not
# built") in both cases. So that exact string is AMBIGUOUS: on a weights-less
# runner it is an artifact skip, not a build skip. We therefore classify by reason:
#
#   FAIL the lane (in lane's control — build/bind problem) when the reason matches:
#       "could not be built"      (adapter_apply_check harness compile failed)
#       "binary missing after build"
#       "could not run"           (built harness failed to exec)
#       "run `make` in ai/xmind"  (engine-not-built phrasing from runtime tests)
#
#   DO NOT fail (outside lane's control — artifact / MLX / torch absent) when:
#       "artifacts not present" | "not present" | "no XMIND weights" |
#       "XMIND C engine not built"  (bare — ambiguous; conflated with weights-missing)
#       + any MLX / torch importorskip line.
#
# Applying the task's own principle ("required only when its non-MLX dependencies
# are present"): a C-engine test trips the guard only when the *one* dependency the
# lane is responsible for — the built+bindable library — is the thing that failed.
# When weights/artifacts are committable on the runner (set XMIND_REQUIRE_ARTIFACTS=1),
# the artifact-reason allowance is dropped and a bare "XMIND C engine not built" /
# "not present" skip on a C-engine file ALSO fails the lane.
# =============================================================================
set -euo pipefail

SRC="${1:-}"
if [[ -z "$SRC" ]]; then
  echo "usage: verify_lane.sh <pytest-ra-output-file|->" >&2
  exit 64
fi

# C-engine test files (basename match is enough; -ra prints the path).
CENGINE_FILES=(
  "test_pt_xmind_parity.py"
  "test_xmind_generation.py"
  "test_adapter_runtime_absorption.py"
  "test_adapter_apply.py"
  "test_model_materialization.py"
)

# Two policy toggles, because the artifact classes differ in how cheaply CI can
# provision them:
#
#   XMIND_REQUIRE_WEIGHTS=1  — the lane PROVISIONED the base weights/GGUF
#       (training/gguf/clean_base_soup_v1.gguf + the matching soup_best.safetensors)
#       via the unmodified pt/train_byte.py + pt/export.py, so the WEIGHTS-class
#       C-engine tests (parity / generation / materialization) MUST run. A
#       weights-reason skip of those is then a FAILURE (the provisioning broke or
#       the build did not bind). Empirically a cheap 8-layer model clears parity
#       (measured: MAE 0.04, argmax match), so requiring them is safe, not flaky.
#
#   XMIND_REQUIRE_ARTIFACTS=1 — also require the PROOF-ADAPTER class (the two
#       adapter tests). OFF by default: a valid, correctly-canonicalized proof
#       adapter cannot be provisioned cheaply on CI, and a bad one would make the
#       "output differs" assertion FAIL (false red) rather than skip. So the
#       adapter tests stay allowed-to-skip unless an operator deliberately supplies
#       the proof adapter and flips this on.
REQUIRE_WEIGHTS="${XMIND_REQUIRE_WEIGHTS:-0}"
REQUIRE_ARTIFACTS="${XMIND_REQUIRE_ARTIFACTS:-0}"

# Read the -ra output (file or stdin).
if [[ "$SRC" == "-" ]]; then
  RA_OUT="$(cat)"
else
  RA_OUT="$(cat "$SRC")"
fi

# Pull only the SKIPPED summary lines.  Format (pytest -ra):
#   SKIPPED [n] path/to/test_x.py:LINE: <reason text>
SKIP_LINES="$(printf '%s\n' "$RA_OUT" | grep -E '^SKIPPED ' || true)"

violations=0
while IFS= read -r line; do
  [[ -z "$line" ]] && continue

  # Does this skip line belong to a C-engine test file?
  is_cengine=0
  for f in "${CENGINE_FILES[@]}"; do
    case "$line" in
      *"$f"*) is_cengine=1; break ;;
    esac
  done
  [[ "$is_cengine" -eq 0 ]] && continue

  lc="$(printf '%s' "$line" | tr '[:upper:]' '[:lower:]')"

  # --- PROOF-ADAPTER class (checked FIRST — most specific) ------------------
  # The two adapter tests skip when the gitignored proof adapter is absent. This
  # class is allowed UNLESS XMIND_REQUIRE_ARTIFACTS=1 (a proof adapter can't be
  # cheaply/safely provisioned on CI; see the toggle note above).
  #   "proof adapter not present"                         (adapter_runtime:71)
  #   "d09 artifacts not present (gguf / proof adapter ..." (adapter_apply:93)
  if [[ "$lc" == *"proof adapter not present"* ]] \
     || [[ "$lc" == *"d09 artifacts not present"* ]]; then
    if [[ "$REQUIRE_ARTIFACTS" == "1" ]]; then
      echo "GUARD FAIL (proof adapter required on this lane): $line" >&2
      violations=$((violations + 1))
    else
      echo "guard: allowed C-engine skip (proof adapter outside lane control): $line" >&2
    fi
    continue
  fi

  # --- WEIGHTS / GGUF class (incl. the AMBIGUOUS get_client()-None message) -
  # These reasons mean the base weights/GGUF were absent. Allowed by default, but
  # a FAILURE when XMIND_REQUIRE_WEIGHTS=1 (the lane provisioned them, so the
  # parity / generation / materialization tests MUST have run).
  #
  # Critical: "XMIND *C* engine not built" (test_xmind_generation.py /
  # test_model_materialization.py) is emitted whenever get_client() returns None,
  # which in _xmind/client.py happens for EITHER a missing lib OR missing .gguf
  # weights — so on a weights-less runner it is a WEIGHTS skip, not a build skip,
  # and must be allowed by default. We detect it by the literal "c engine not
  # built" phrasing (note the 'C'). Matched BEFORE the build/bind block so its
  # embedded "run `make`" hint cannot mis-route it to a build failure.
  if [[ "$lc" == *"soup artifacts not present"* ]] \
     || [[ "$lc" == *"no xmind weights"* ]] \
     || [[ "$lc" == *"c engine not built"* ]]; then
    if [[ "$REQUIRE_WEIGHTS" == "1" ]]; then
      echo "GUARD FAIL (weights provisioned but C-engine test still skipped): $line" >&2
      violations=$((violations + 1))
    else
      echo "guard: allowed C-engine skip (weights/GGUF outside lane control): $line" >&2
    fi
    continue
  fi

  # --- IN-LANE BUILD/BIND class -> always a violation ----------------------
  # Reasons that can ONLY mean the lib failed to build/bind (no weights ambiguity):
  #   * "could not be built" / "binary missing after build" / "could not run"
  #       — test_adapter_apply.py harness compile/exec failures.
  #   * "libxmind-core not built"
  #       — XMindUnavailable from _xmind/client.py when the .dylib/.so is absent.
  #   * "engine not built (run `make` in ai/xmind):"
  #       — test_adapter_runtime_absorption.py:74. UNLIKE the conflated message
  #         above, this fires ONLY AFTER its proof-adapter precheck passed, so it
  #         is a trustworthy build/bind signal (note: "engine not built", no 'C',
  #         followed by a ':' + the engine stderr).
  if [[ "$lc" == *"could not be built"* ]] \
     || [[ "$lc" == *"binary missing after build"* ]] \
     || [[ "$lc" == *"could not run"* ]] \
     || [[ "$lc" == *"libxmind-core not built"* ]] \
     || [[ "$lc" == *'engine not built (run `make` in ai/xmind):'* ]]; then
    echo "GUARD FAIL (build/bind): $line" >&2
    violations=$((violations + 1))
    continue
  fi

  # Unknown reason on a C-engine file: be strict — treat as a violation so a new
  # skip phrasing can never silently slip past the guard.
  echo "GUARD FAIL (unrecognized C-engine skip reason — classify it): $line" >&2
  violations=$((violations + 1))
done <<< "$SKIP_LINES"

if [[ "$violations" -gt 0 ]]; then
  echo "" >&2
  echo "SKIP-IS-FAIL: $violations C-engine test(s) skipped for an in-lane reason —" >&2
  echo "the core path did NOT run. Build the engine (cd ai/xmind && make) and re-run." >&2
  exit 1
fi

echo "guard ok: no C-engine test skipped for an in-lane (build/bind) reason."
exit 0
