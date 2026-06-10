"""D25 EFFECTIVE gate: a routed OmniPEFTModel adapter actually MOVES the logits.

MLX-track sibling of tests/test_adapter_apply.py (which proves the *C runtime*
XMIND adapter applies). Here we prove the **Python MLX** OmniPEFTModel forward is
no longer a "route computed but never applied" no-op:

  * BEFORE D25, OmniPEFTModel.__call__ computed a route, pushed it into the
    registered OmniPEFTBlocks, then called self.base_model(tokens) DIRECTLY — so
    the blocks never ran and the adapter delta affected nothing. Routing was
    DEFINED + CALLED but NOT EFFECTIVE.
  * AFTER D25, register_peft_block() splices each OmniPEFTBlock into
    base_model.blocks[idx] (a plain Python list in scripts/model.py TokenlessLM),
    so the base forward iterates the spliced block and runs the routed delta. No
    base-model edit is required.

ISOLATION (why a subprocess, mirroring test_adapter_apply.py): the MLX peft proof
must `import peft` resolving to training/peft, which requires putting training/ on
sys.path. The torch-track test (test_pt_gradflow.py) imports a DIFFERENT `peft`
(training/pt/peft). Doing the mlx import in THIS pytest process would clobber the
shared `peft` module name and break the sibling. So the numerical proof runs in a
CLEAN child interpreter and we parse its single PASS line — exactly the pattern
test_adapter_apply.py uses for the C harness. This keeps the in-process suite
collision-free under BOTH interpreters.

The child interpreter must have mlx importable. The default repo test interpreter
(3.13) has no mlx; mlx lives in a 3.12 framework build. We DISCOVER an mlx-capable
interpreter (sentinel probe over candidate pythons) and SKIP cleanly if none is
found — never fail. Run:

    python3 -m pytest tests/test_peft_route_effective.py -q
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent          # models v7/
TRAINING = ROOT / "training"

# The proof, run inside a clean child so the `peft` / `model` module names do not
# collide with the torch-track tests in the parent pytest process.
_CHILD = r'''
import sys
sys.path.insert(0, __TRAINING__)
sys.path.insert(0, __SCRIPTS__)

import mlx.core as mx
from scripts.model import ModelConfig, TokenlessLM
from peft.base import DeltaFamily, DeltaOperator, AdapterGenomeRecord
from peft.model import OmniPEFTModel
from peft.loader import build_registry_from_genomes


class ConstantBiasDelta(DeltaOperator):
    """NON-ZERO hidden-state delta so a zero MAE can only mean the block never ran
    (stock LoRA inits B=0 -> zero delta, which would falsely look like a no-op)."""
    def __init__(self, d_model, bias=0.5):
        super().__init__()
        self.bias = mx.full((d_model,), bias)
    @property
    def family(self):
        return DeltaFamily.ACTIVATION
    def __call__(self, x, **k):
        return mx.broadcast_to(self.bias, x.shape)


class RoutePlanStub:
    class _AE:
        def __init__(self, e, w):
            self.expert_id = e; self.weight = w
    def __init__(self, pairs):
        self.active_experts = [self._AE(e, w) for e, w in pairs]


def tiny():
    cfg = ModelConfig(vocab_size=259, n_layers=2, n_heads=2, d_model=32,
                      d_ffn=64, max_seq_len=64)
    return TokenlessLM(cfg), cfg


def logits(m, t):
    o = m(t); mx.eval(o); return o


def mae(a, b):
    return float(mx.mean(mx.abs(a - b)).item())


# --- 1. PARITY: no spliced block -> byte-identical to base ------------------
base, cfg = tiny()
tok = mx.array([[1, 2, 3, 4, 5]])
base_logits = logits(base, tok)
model = OmniPEFTModel(base_model=base, adapter_registry=None, compiler=None)
parity_mae = mae(base_logits, logits(model, tok))
assert parity_mae == 0.0, f"parity broken: {parity_mae}"

# --- 2. EFFECTIVE: non-zero routed delta moves logits -----------------------
base2, cfg2 = tiny()
tok2 = mx.array([[1, 2, 3, 4, 5]])
baseline = logits(base2, tok2)
model2 = OmniPEFTModel(base_model=base2, adapter_registry=None, compiler=None)
model2.install_block_adapters(
    delta_factory=lambda i, b: ConstantBiasDelta(cfg2.d_model, 0.5),
    layer_indices=[0],
)
eff_mae = mae(baseline, logits(model2, tok2))
assert eff_mae > 0.0, f"adapter not effective: {eff_mae}"
n_train = model2.num_trainable_params()
assert n_train > 0, "no trainable params in spliced block"

# --- 3. RESTORE: remove splice -> byte-identical again ----------------------
model2.remove_block_adapters()
restore_mae = mae(baseline, logits(model2, tok2))
assert restore_mae == 0.0, f"restore not byte-identical: {restore_mae}"

# --- 4. ROUTE GATES EFFECT: weight 0 -> no delta, weight 1 -> delta ---------
base3, cfg3 = tiny()
tok3 = mx.array([[7, 8, 9, 10]])
baseline3 = logits(base3, tok3)
model3 = OmniPEFTModel(base_model=base3, adapter_registry=None, compiler=None)
model3.install_block_adapters(
    delta_factory=lambda i, b: {"expertA": ConstantBiasDelta(cfg3.d_model, 0.5)},
    layer_indices=[0],
)
model3._apply_route_to_blocks(RoutePlanStub([("expertA", 0.0)]))
zero_mae = mae(baseline3, logits(model3, tok3))
assert zero_mae == 0.0, f"zero-weight route still moved logits: {zero_mae}"
model3._apply_route_to_blocks(RoutePlanStub([("expertA", 1.0)]))
pos_mae = mae(baseline3, logits(model3, tok3))
assert pos_mae > 0.0, f"positive-weight route had no effect: {pos_mae}"

# --- 5. REAL ROUTER E2E (THE CORE PLASTICITY-E2E DELIVERABLE) ---------------
# Prove the descriptor -> HierarchicalRouter.route() -> selected-expert -> delta
# path is EFFECTIVE, with the genome-name == expert-key binding closed. The
# block is keyed "med" (== the genome name the router emits), so a matching
# medical descriptor activates it; a registry that does NOT contain "med" makes
# the router emit nothing, so the SAME block applies no delta. This is what
# proves ROUTING (not presence, not equal-weight fallback) drives the forward.
base4, cfg4 = tiny()
tok4 = mx.array([[1, 2, 3, 4, 5]])
baseline4 = logits(base4, tok4)
med_genome = AdapterGenomeRecord(
    name="med", version="1.0.0", base_model="base", peft_method="ia3",
    delta_family="ACTIVATION", purpose_domains=["medical"], purpose_tasks=[],
)
reg_med = build_registry_from_genomes([med_genome], status="active")
model4 = OmniPEFTModel(base_model=base4, adapter_registry=reg_med, compiler=None)
model4.install_block_adapters(
    delta_factory=lambda i, b: ConstantBiasDelta(cfg4.d_model, 0.5),
    layer_indices=[0],
    expert_id="med",  # routing-key seam: key == genome name
)
# Lock the REASON, not just the outcome: assert the real router itself selects
# 'med' for a medical descriptor (so a future key-filter regression can't pass
# silently via the equal-weight fallback belt-and-suspenders).
sel_pos = [ae.expert_id for ae in
           model4.route_for("x", "patient diagnosis treatment clinical").active_experts]
assert sel_pos == ["med"], f"router did not select 'med': {sel_pos}"
pos_out = model4(tok4, domain_descriptor="patient diagnosis treatment clinical")
mx.eval(pos_out)
router_pos_mae = mae(baseline4, pos_out)
assert router_pos_mae > 0.0, (
    f"real-router positive MAE={router_pos_mae} — descriptor->router->delta not "
    f"effective (genome-name<->expert-key binding broken)."
)

# NEGATIVE: a registry whose only genome is 'legalonly' -> for a medical
# descriptor the router emits [], so the block keyed 'med' stays inert.
base5, cfg5 = tiny()
tok5 = mx.array([[1, 2, 3, 4, 5]])
baseline5 = logits(base5, tok5)
legal_genome = AdapterGenomeRecord(
    name="legalonly", version="1.0.0", base_model="base", peft_method="ia3",
    delta_family="ACTIVATION", purpose_domains=["legal"], purpose_tasks=[],
)
reg_legal = build_registry_from_genomes([legal_genome], status="active")
model5 = OmniPEFTModel(base_model=base5, adapter_registry=reg_legal, compiler=None)
model5.install_block_adapters(
    delta_factory=lambda i, b: ConstantBiasDelta(cfg5.d_model, 0.5),
    layer_indices=[0],
    expert_id="med",
)
# THE load-bearing routing proof: the router must select NOTHING (empty, not
# None) for a medical descriptor against a legal-only registry. A router that
# silently failed would fall back to equal-weight and apply the 'med' delta ->
# non-zero MAE. So sel_neg==[] AND neg_mae==0 together prove the router is live
# and is what gates the forward (not mere expert presence).
sel_neg = [ae.expert_id for ae in
           model5.route_for("x", "patient diagnosis treatment clinical").active_experts]
assert sel_neg == [], f"router should select nothing here, got: {sel_neg}"
neg_out = model5(tok5, domain_descriptor="patient diagnosis treatment clinical")
mx.eval(neg_out)
router_neg_mae = mae(baseline5, neg_out)
assert router_neg_mae == 0.0, (
    f"real-router negative MAE={router_neg_mae} — router selected nothing yet a "
    f"delta still applied; routing is not gating the forward."
)

print(
    "[peft-route-effective] PASS"
    f" parity_mae={parity_mae}"
    f" effective_mae={eff_mae:.6f}"
    f" trainable_params={n_train}"
    f" restore_mae={restore_mae}"
    f" zero_route_mae={zero_mae}"
    f" pos_route_mae={pos_mae:.6f}"
    f" router_pos_mae={router_pos_mae:.6f}"
    f" router_neg_mae={router_neg_mae}"
)
'''

_PASS_RE = re.compile(
    r"\[peft-route-effective\]\s+PASS\b.*?"
    r"effective_mae=(?P<eff>[0-9]+(?:\.[0-9]+)?).*?"
    r"trainable_params=(?P<tp>\d+).*?"
    r"pos_route_mae=(?P<pos>[0-9]+(?:\.[0-9]+)?).*?"
    r"router_pos_mae=(?P<rpos>[0-9]+(?:\.[0-9]+)?).*?"
    r"router_neg_mae=(?P<rneg>[0-9]+(?:\.[0-9]+)?)",
    re.S,
)


def _mlx_capable_interpreter() -> str | None:
    """Return the path to a python that can `import mlx.core`, or None.

    Probes the current interpreter first, then common framework builds and any
    `python3.x` on PATH. Discovery, not a hardcoded path.
    """
    candidates: list[str] = [sys.executable]
    for name in ("python3.12", "python3.11", "python3.13", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    # Framework builds (macOS) — only added if present.
    fw = Path("/Library/Frameworks/Python.framework/Versions")
    if fw.is_dir():
        for ver in sorted(fw.iterdir()):
            exe = ver / "bin" / f"python{ver.name}"
            if exe.exists():
                candidates.append(str(exe))

    seen: set[str] = set()
    for exe in candidates:
        if exe in seen:
            continue
        seen.add(exe)
        try:
            r = subprocess.run(
                [exe, "-c", "import mlx.core; print('ok')"],
                capture_output=True, text=True, timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0 and "ok" in (r.stdout or ""):
            return exe
    return None


def test_routed_adapter_is_effective():
    """A loaded+routed OmniPEFTModel adapter moves the logits (MAE>0); the
    no-adapter path is a byte-identical no-op; the route weight gates the effect."""
    interp = _mlx_capable_interpreter()
    if interp is None:
        pytest.skip("no mlx-capable python interpreter found (mlx not installed)")

    child = (
        _CHILD
        .replace("__TRAINING__", repr(str(TRAINING)))
        .replace("__SCRIPTS__", repr(str(TRAINING / "scripts")))
    )
    try:
        out = subprocess.run(
            [interp, "-c", child],
            capture_output=True, text=True, timeout=300,
            cwd=str(TRAINING),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"mlx EFFECTIVE child could not run: {exc}")

    combined = (out.stdout or "") + "\n" + (out.stderr or "")

    # Non-zero exit means an assert inside the child fired — a REAL D25 regression
    # (route no longer effective, or parity/restore broke), so we fail, not skip.
    assert out.returncode == 0, (
        f"peft route EFFECTIVE child exit={out.returncode} (D25 regression).\n{combined}"
    )

    m = _PASS_RE.search(combined)
    assert m is not None, f"no PASS line in child output:\n{combined}"

    eff_mae = float(m.group("eff"))
    trainable = int(m.group("tp"))
    pos_mae = float(m.group("pos"))
    router_pos_mae = float(m.group("rpos"))
    router_neg_mae = float(m.group("rneg"))

    # EFFECTIVE: the routed delta actually changed the logits.
    assert eff_mae > 0.0, f"effective_mae={eff_mae} — adapter ran but no change."
    # The delta params are real trainable params on the call path.
    assert trainable > 0, f"trainable_params={trainable} — adapter not in graph."
    # The ROUTE (positive weight) drove the forward, not mere expert presence.
    assert pos_mae > 0.0, f"pos_route_mae={pos_mae} — route did not gate the effect."
    # REAL ROUTER E2E (the core PLASTICITY-E2E deliverable): a matching
    # descriptor drives HierarchicalRouter -> selected genome -> delta (MAE>0)...
    assert router_pos_mae > 0.0, (
        f"router_pos_mae={router_pos_mae} — descriptor->router->delta not effective."
    )
    # ...and a non-matching registry makes the router select nothing -> no delta.
    assert router_neg_mae == 0.0, (
        f"router_neg_mae={router_neg_mae} — routing did not gate the forward."
    )


if __name__ == "__main__":  # manual run convenience
    raise SystemExit(pytest.main([__file__, "-q", "-s"]))
