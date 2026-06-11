"""
test_peft_imports.py — Verify every PEFT module imports cleanly.

Run from training/:
  python3 tests/test_peft_imports.py
  python3 -m pytest tests/test_peft_imports.py -v
"""
from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

ML_TRAINING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ML_TRAINING))

# All modules expected to exist and import cleanly
MODULES = [
    # Core OS
    "peft.base",
    "peft.profiler",
    "peft.fingerprint",
    "peft.compiler",
    "peft.registry",
    "peft.conflict",
    "peft.router",
    "peft.tournament",
    "peft.deployment",
    # Low-rank family
    "peft.low_rank.lora",
    "peft.low_rank.dora",
    "peft.low_rank.qlora",
    "peft.low_rank.adalora",
    "peft.low_rank.vera",
    "peft.low_rank.pissa",
    "peft.low_rank.rslora",
    "peft.low_rank.olora",
    "peft.low_rank.loha",
    "peft.low_rank.lokr",
    "peft.low_rank.rosa",
    # Additive adapters
    "peft.additive.houlsby",
    "peft.additive.pfeiffer",
    # Prompt family
    "peft.prompt.prompt_tuning",
    "peft.prompt.prefix_tuning",
    "peft.prompt.p_tuning",
    # Activation
    "peft.activation.ia3",
    # Selective/sparse
    "peft.selective.bitfit",
    "peft.selective.diffpruning",
    "peft.selective.fishmask",
    "peft.selective.far",
    # Hybrid
    "peft.hybrid.unipelt",
    "peft.hybrid.mam_adapter",
    "peft.hybrid.compacter",
    "peft.hybrid.xlora",
    # Structural
    "peft.structural.oft",
    "peft.structural.boft",
    "peft.structural.fourier_ft",
    # Alignment
    "peft.alignment.sft",
    "peft.alignment.dpo",
    "peft.alignment.ipo",
    "peft.alignment.kto",
    "peft.alignment.orpo",
    "peft.alignment.ppo_rlhf",
    "peft.alignment.grpo",
]

# Expected classes/objects in each module
MODULE_SYMBOLS = {
    "peft.base":                ["DeltaOperator", "DeltaFamily", "AdapterGenomeRecord",
                                 "HardwareBudget", "AdaptationConstraints", "RoutePlan"],
    "peft.profiler":            ["ModelProfiler", "LayerPlasticityMap", "LayerProfile"],
    "peft.fingerprint":         ["TaskFingerprinter", "TaskFingerprint", "DataSize", "DomainShift"],
    "peft.compiler":            ["PEFTCompiler", "AdaptationPlan", "LayerAdaptationSpec"],
    "peft.registry":            ["AdapterGenomeRegistry", "RegistryEntry"],
    "peft.conflict":            ["ConflictResolver", "ConflictReport"],
    "peft.router":              ["HierarchicalRouter", "RouterConfig"],
    "peft.tournament":          ["TrainingTournament", "ParetoWinner", "CandidateResult"],
    "peft.deployment":          ["DeploymentManager", "DeploymentMode", "DeploymentPackage"],
    "peft.low_rank.lora":       ["LoRALinear"],
    "peft.low_rank.dora":       ["DoRALinear"],
    "peft.low_rank.adalora":    ["AdaLoRALinear"],
    "peft.low_rank.vera":       ["VeRALinear"],
    "peft.activation.ia3":      ["IA3Layer"],
    "peft.selective.bitfit":    ["BitFitOperator"],
    "peft.alignment.sft":       ["SFTTrainer"],
    "peft.alignment.dpo":       ["DPOTrainer"],
    "peft.alignment.grpo":      ["GRPOTrainer"],
}


def test_all_modules_import():
    """Every PEFT module must import without error."""
    failed = []
    for module_name in MODULES:
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None, f"{module_name} imported as None"
        except Exception as e:
            failed.append((module_name, str(e)))
            print(f"  FAIL  {module_name}: {e}")

    if failed:
        raise AssertionError(
            f"{len(failed)}/{len(MODULES)} modules failed to import:\n"
            + "\n".join(f"  {m}: {e}" for m, e in failed)
        )


def test_module_symbols():
    """Key symbols must be present in their expected modules."""
    missing = []
    for module_name, symbols in MODULE_SYMBOLS.items():
        try:
            mod = importlib.import_module(module_name)
        except Exception as e:
            missing.append((module_name, "*", str(e)))
            continue
        for sym in symbols:
            if not hasattr(mod, sym):
                missing.append((module_name, sym, "not found"))

    if missing:
        raise AssertionError(
            f"{len(missing)} missing symbols:\n"
            + "\n".join(f"  {m}.{s}: {e}" for m, s, e in missing)
        )


def test_delta_family_completeness():
    """DeltaFamily enum must cover all implemented method families."""
    from peft.base import DeltaFamily
    required = {
        "WEIGHT_ADDITIVE", "ACTIVATION", "PROMPT",
        "MODULE", "STRUCTURAL", "SPARSE", "ROUTING", "ALIGNMENT"
    }
    actual = {f.name for f in DeltaFamily}
    missing = required - actual
    assert not missing, f"Missing DeltaFamily members: {missing}"


def test_delta_operator_is_abstract():
    """DeltaOperator must be an abstract class — cannot be instantiated directly."""
    import abc
    from peft.base import DeltaOperator
    assert hasattr(DeltaOperator, "__abstractmethods__"), "DeltaOperator must have abstract methods"
    assert len(DeltaOperator.__abstractmethods__) > 0, "DeltaOperator must declare at least one abstract method"


def test_train_peft_cli_importable():
    """train_peft.py must import cleanly and expose METHOD_REGISTRY."""
    scripts_dir = ML_TRAINING / "scripts"
    sys.path.insert(0, str(scripts_dir))
    import train_peft
    assert hasattr(train_peft, "METHOD_REGISTRY"), "train_peft.py missing METHOD_REGISTRY"
    assert len(train_peft.METHOD_REGISTRY) >= 35, (
        f"Expected ≥35 methods, got {len(train_peft.METHOD_REGISTRY)}"
    )


if __name__ == "__main__":
    tests = [
        test_all_modules_import,
        test_module_symbols,
        test_delta_family_completeness,
        test_delta_operator_is_abstract,
        test_train_peft_cli_importable,
    ]
    passed = failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test.__name__}: {e}")
            failed += 1

    print(f"\n{passed + failed} tests  |  {passed} passed  |  {failed} failed")
    sys.exit(0 if failed == 0 else 1)
