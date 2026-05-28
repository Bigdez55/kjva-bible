#!/usr/bin/env python3
"""Validate deterministic trigger routing and all-skills invocation semantics."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infrastructure/scripts"))

from route_intent import route_text  # noqa: E402

PROJECT_PREFIXES = ("SKILL_ELSON_", "SKILL_IPOS_", "SKILL_GENOS_", "SKILL_SUPER_C_", "SKILL_SC_")
MACHINE_ENCODING_SKILL = "SKILL_VERIFIED_MACHINE_ENCODING_001"
ASSISTANT_ACQUISITION_SKILLS = {
    "SKILL_GLOBAL_CLAUDE_REPOSITORY_ACQUISITION_001",
    "SKILL_CODEX_GEMINI_REPOSITORY_ACQUISITION_001",
}


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def assert_file(path: str, failures: list[str]) -> None:
    if not (ROOT / path).exists():
        fail(f"missing required file: {path}", failures)


def assert_in(item: Any, collection: list[Any], message: str, failures: list[str]) -> None:
    if item not in collection:
        fail(message, failures)


def assert_not_in(item: Any, collection: list[Any], message: str, failures: list[str]) -> None:
    if item in collection:
        fail(message, failures)


def load_yaml(path: str) -> dict[str, Any]:
    return yaml.safe_load((ROOT / path).read_text()) or {}


def validate_surface_contracts(test: dict[str, Any], failures: list[str]) -> None:
    for path in test.get("required_files", []):
        assert_file(path, failures)

    for surface in test.get("runtime_surfaces", []):
        path = surface.get("required_file")
        name = surface.get("name", path)
        if not path:
            fail(f"runtime surface {name}: missing required_file", failures)
            continue
        target = ROOT / path
        if not target.exists():
            fail(f"runtime surface {name}: missing file {path}", failures)
            continue
        text = target.read_text()
        for snippet in surface.get("must_contain", []):
            if snippet not in text:
                fail(f"runtime surface {name}: {path} missing required text {snippet!r}", failures)


def validate_case(case: dict[str, Any], failures: list[str]) -> None:
    text = case["input"]
    routed = route_text(text)
    context = f"route case {text!r}"

    if expected := case.get("expected_intent"):
        assert_in(expected, routed.get("matched_intents", []), f"{context}: missing intent {expected}; actual={routed.get('matched_intents')}", failures)
    if expected := case.get("expected_root"):
        if routed.get("selected_root") != expected:
            fail(f"{context}: selected_root={routed.get('selected_root')} expected={expected}", failures)
    if "expected_selected_noun" in case and routed.get("selected_noun") != case["expected_selected_noun"]:
        fail(f"{context}: selected_noun={routed.get('selected_noun')} expected={case['expected_selected_noun']}", failures)
    if expected := case.get("expected_selected_target"):
        if routed.get("selected_target") != expected:
            fail(f"{context}: selected_target={routed.get('selected_target')} expected={expected}", failures)
    if expected := case.get("expected_target"):
        if routed.get("selected_target") != expected:
            fail(f"{context}: selected_target={routed.get('selected_target')} expected={expected}", failures)

    for skill in case.get("must_include_skills", []) + case.get("must_include", []):
        assert_in(skill, routed.get("skills", []), f"{context}: missing skill {skill}; actual={routed.get('skills')}", failures)
    for skill in case.get("must_not_include_skills", []):
        assert_not_in(skill, routed.get("skills", []), f"{context}: forbidden skill active {skill}", failures)
    for intent in case.get("must_not_include_intents", []):
        assert_not_in(intent, routed.get("matched_intents", []), f"{context}: forbidden intent active {intent}", failures)
    for output in case.get("must_include_outputs", []):
        assert_in(output, routed.get("required_outputs", []), f"{context}: missing output {output}", failures)

    for prefix in case.get("must_not_include_project_prefixes", []):
        offenders = [skill for skill in routed.get("skills", []) if skill.startswith(prefix)]
        if offenders:
            fail(f"{context}: project prefix {prefix} should be suppressed; offenders={offenders}", failures)
    for prefix in case.get("must_include_project_prefixes", []):
        if not any(skill.startswith(prefix) for skill in routed.get("skills", [])):
            fail(f"{context}: expected active project prefix {prefix}; actual={routed.get('skills')}", failures)


def validate_universal_contract(failures: list[str]) -> None:
    routed = route_text("invoke all skills now")
    context = "universal invocation contract"
    assert_in("all_skills", routed.get("matched_intents", []), f"{context}: missing all_skills intent", failures)
    assert_not_in("unified_assistant_surface_acquisition", routed.get("matched_intents", []), f"{context}: acquisition intent leaked", failures)
    if "tool_called_skills" not in routed:
        fail(f"{context}: missing tool_called_skills field", failures)
    disciplines = routed.get("playbook_applied_disciplines", [])
    if not disciplines:
        fail(f"{context}: no playbook_applied_disciplines returned", failures)
    for item in disciplines:
        playbook = item.get("playbook")
        if not playbook or not (ROOT / playbook).exists():
            fail(f"{context}: missing playbook for discipline {item}", failures)
    for skill in ASSISTANT_ACQUISITION_SKILLS:
        assert_not_in(skill, routed.get("skills", []), f"{context}: assistant acquisition skill leaked into invocation: {skill}", failures)


def validate_generic_suppression(failures: list[str]) -> None:
    generic_inputs = ["build a platform", "build dashboard", "audit security", "fix API"]
    for text in generic_inputs:
        routed = route_text(text)
        offenders = [skill for skill in routed.get("skills", []) if skill.startswith(PROJECT_PREFIXES) or skill in ASSISTANT_ACQUISITION_SKILLS]
        if offenders:
            fail(f"generic suppression miss for {text!r}: offenders={offenders}", failures)


def validate_target_activation(failures: list[str]) -> None:
    cases = {
        "build Elson platform": "SKILL_ELSON_",
        "build IPOS dashboard": "SKILL_IPOS_",
        "build compiler": ("SKILL_GENOS_", "SKILL_SUPER_C_", "SKILL_SC_"),
        "fix LDUR STUR encoding": (MACHINE_ENCODING_SKILL,),
        "debug emitted constant SIGSEGV": (MACHINE_ENCODING_SKILL,),
        "apex-verified-machine-encoding": (MACHINE_ENCODING_SKILL,),
        "pull all new skills from .claude .codex .gemini": tuple(ASSISTANT_ACQUISITION_SKILLS),
    }
    for text, expected in cases.items():
        routed = route_text(text)
        expected_tuple = expected if isinstance(expected, tuple) else (expected,)
        if not any(skill.startswith(expected_tuple) or skill in expected_tuple for skill in routed.get("skills", [])):
            fail(f"target activation miss for {text!r}: expected={expected_tuple}; actual={routed.get('skills')}", failures)


def main() -> int:
    failures: list[str] = []

    required_files = [
        "platform/sdlc/13_skills/skill_refinery/deterministic_trigger_operating_contract.md",
        "platform/sdlc/13_skills/skill_refinery/universal_skill_invocation_policy.md",
        "platform/sdlc/13_skills/skill_refinery/cross_runtime_invoke_all_skills_contract.md",
        ".claude/commands/invoke-all-skills.md",
        ".codex/commands/invoke-all-skills.md",
        "AGENTS.md",
        "CLAUDE.md",
        "platform/sdlc/13_skills/skill_refinery/validation_tests/TEST_UNIVERSAL_SKILL_INVOCATION_001.yaml",
        "platform/sdlc/13_skills/skill_refinery/validation_tests/TEST_MULTI_TENANT_SECURITY_SKILLS_001.yaml",
    ]
    for path in required_files:
        assert_file(path, failures)

    for path in required_files:
        if path.endswith(".yaml"):
            try:
                load_yaml(path)
            except Exception as exc:
                fail(f"invalid YAML {path}: {exc}", failures)

    universal_test = load_yaml("platform/sdlc/13_skills/skill_refinery/validation_tests/TEST_UNIVERSAL_SKILL_INVOCATION_001.yaml")
    validate_surface_contracts(universal_test, failures)
    for case in universal_test.get("cases", []):
        validate_case(case, failures)

    security_test = load_yaml("platform/sdlc/13_skills/skill_refinery/validation_tests/TEST_MULTI_TENANT_SECURITY_SKILLS_001.yaml")
    for skill in security_test.get("expected_active_skills", []):
        assert_file(f"platform/sdlc/13_skills/active/{skill}.yaml", failures)
        assert_file(f"platform/sdlc/13_skills/active/{skill}.playbook.md", failures)
    for case in security_test.get("route_cases", []):
        validate_case(case, failures)

    validate_universal_contract(failures)
    validate_generic_suppression(failures)
    validate_target_activation(failures)

    if failures:
        print("FAIL: trigger determinism validation")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("PASS: trigger determinism validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
