#!/usr/bin/env python3
"""Route natural-language text through the canonical verb-first trigger router."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "platform" / "systems" / "37_command_protocol" / "trigger_router.yaml"
REGISTRY = ROOT / "platform" / "sdlc" / "13_skills" / "skills.registry.yaml"
UNIVERSAL_SURFACE = ROOT / "platform" / "sdlc" / "13_skills" / "universal_surface" / "index.yaml"


@dataclass(frozen=True)
class TermMatch:
    key: str
    term: str
    start: int
    end: int
    layer: str
    data: dict[str, Any]

    @property
    def length(self) -> int:
        return self.end - self.start


def load_router(path: Path = ROUTER) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def _load_registry_summary() -> dict[str, Any]:
    if not REGISTRY.exists():
        return {
            "registry": REGISTRY.relative_to(ROOT).as_posix(),
            "active_skill_count": 0,
            "error": "registry_missing",
        }
    data = yaml.safe_load(REGISTRY.read_text()) or {}
    skills = data.get("skills", []) or []
    return {
        "registry": REGISTRY.relative_to(ROOT).as_posix(),
        "active_skill_count": len(skills),
        "active_skill_dir": str(data.get("scan_dir", "platform/sdlc/13_skills/active")),
        "last_updated": data.get("last_updated"),
    }


def _normalize_text(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"/([a-z0-9_-]+):([a-z0-9_-]+)", r"\1 \2", normalized)
    normalized = re.sub(r"\b([a-z0-9_-]+):([a-z0-9_-]+)", r"\1 \2", normalized)
    normalized = normalized.replace("_", " ").replace("-", " ")
    normalized = re.sub(r"[^a-z0-9.]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_term(term: str) -> str:
    return _normalize_text(term)


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


PROJECT_SKILL_PREFIXES = {
    "elson": ("SKILL_ELSON_",),
    "ipos": ("SKILL_IPOS_",),
    "genos": ("SKILL_GENOS_", "SKILL_SUPER_C_", "SKILL_SC_"),
    "assistant_surface": ("SKILL_GLOBAL_CLAUDE_REPOSITORY_ACQUISITION_001", "SKILL_CODEX_GEMINI_REPOSITORY_ACQUISITION_001"),
}

PROJECT_BINDING_TERMS = {
    "elson": ("elson", "trading", "portfolio", "market", "finance", "vllm"),
    "ipos": ("ipos", "paratransit", "transit", "vta", "trapeze", "otp", "otpa", "td report", "ld"),
    "genos": (
        "genos",
        "gen os",
        "gen.os",
        "super c",
        "superc",
        "compiler",
        "kernel",
        "qemu",
        "xkabi",
        "xframe",
        "gensd",
        "aetherboot",
        "scc",
        "seedc",
        "scir",
        "arm64",
        "aarch64",
        "machine encoding",
        "emit constant",
        "opcode",
        "instruction word",
        "ldur",
        "stur",
        "ldr",
        "str",
        "sc miss 005",
    ),
    "assistant_surface": (".claude", ".codex", ".gemini", "assistant surface", "assistant surfaces", "acquire all skills", "acquire all agents", "pull all new skills"),
}


def _term_present(haystack: str, term: str) -> bool:
    normalized_term = _normalize_term(term)
    if not normalized_term:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", haystack))


def _allowed_project_families(normalized: str, selected_noun: str | None, selected_target: str | None) -> set[str]:
    allowed: set[str] = set()
    haystack = f"{normalized} {selected_noun or ''} {selected_target or ''}"
    for family, terms in PROJECT_BINDING_TERMS.items():
        if any(_term_present(haystack, term) for term in terms):
            allowed.add(family)
    if selected_target in {"elson", "ipos_dashboard", "genos", "super_c", "assistant_surface_inventory", "claude_repository_assets", "codex_gemini_repository_assets"}:
        target_family = {"ipos_dashboard": "ipos", "assistant_surface_inventory": "assistant_surface", "claude_repository_assets": "assistant_surface", "codex_gemini_repository_assets": "assistant_surface"}.get(selected_target, selected_target)
        allowed.add(target_family)
    if selected_noun in {"compiler", "machine_encoding"}:
        allowed.add("genos")
    return allowed


def _skill_project_family(skill: str) -> str | None:
    for family, prefixes in PROJECT_SKILL_PREFIXES.items():
        if any(skill.startswith(prefix) for prefix in prefixes):
            return family
    return None


def _suppress_unbound_project_skills(skills: list[str], allowed_families: set[str]) -> tuple[list[str], list[str]]:
    active: list[str] = []
    suppressed: list[str] = []
    for skill in skills:
        family = _skill_project_family(skill)
        if family and family not in allowed_families:
            suppressed.append(skill)
        else:
            active.append(skill)
    return _dedupe(active), _dedupe(suppressed)


def _playbook_path_for_skill(skill: str) -> str | None:
    if not re.fullmatch(r"SKILL_[A-Z0-9_]+", skill):
        return None
    candidate = ROOT / "platform" / "sdlc" / "13_skills" / "active" / f"{skill}.playbook.md"
    if candidate.exists():
        return candidate.relative_to(ROOT).as_posix()
    return None


def _aliases(key: str, data: dict[str, Any]) -> list[str]:
    values = [key]
    values.extend(str(item) for item in data.get("aliases", []) or [])
    return _dedupe(values)


def _find_aliases(text: str, key: str, layer: str, data: dict[str, Any]) -> list[TermMatch]:
    matches: list[TermMatch] = []
    seen_terms: set[str] = set()
    for alias in _aliases(key, data):
        term = _normalize_term(alias)
        if not term or term in seen_terms:
            continue
        seen_terms.add(term)
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        for found in re.finditer(pattern, text):
            matches.append(TermMatch(key=key, term=term, start=found.start(), end=found.end(), layer=layer, data=data))
    return matches


def _find_grouped_modifiers(text: str, router: dict) -> dict[str, list[dict[str, Any]]]:
    active: dict[str, list[dict[str, Any]]] = {}
    for group, entries in (router.get("modifiers") or {}).items():
        group_hits: list[dict[str, Any]] = []
        for key, aliases in (entries or {}).items():
            for alias in aliases or []:
                term = _normalize_term(str(alias))
                if not term:
                    continue
                pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
                for found in re.finditer(pattern, text):
                    group_hits.append({"key": key, "term": term, "start": found.start(), "end": found.end()})
        if group_hits:
            group_hits.sort(key=lambda item: (item["start"], -(item["end"] - item["start"])))
            active[group] = group_hits
    return active


def _best_root(root_matches: list[TermMatch]) -> TermMatch | None:
    if not root_matches:
        return None
    return sorted(root_matches, key=lambda item: (item.start, -item.length, item.key))[0]


def _best_noun(noun_matches: list[TermMatch], root: TermMatch | None) -> TermMatch | None:
    if not noun_matches:
        return None
    if root:
        after_root = [item for item in noun_matches if item.start >= root.end]
        candidates = after_root or noun_matches
        return sorted(candidates, key=lambda item: (abs(item.start - root.end), item.start, -item.length, item.key))[0]
    return sorted(noun_matches, key=lambda item: (item.start, -item.length, item.key))[0]


def _best_target(target_matches: list[TermMatch], noun: TermMatch | None, root: TermMatch | None) -> TermMatch | None:
    if not target_matches:
        return None
    anchor = noun or root
    if anchor:
        return sorted(target_matches, key=lambda item: (-item.length, abs(item.start - anchor.start), item.start, item.key))[0]
    return sorted(target_matches, key=lambda item: (item.start, -item.length, item.key))[0]


def _find_layer(text: str, router: dict, section: str, layer: str) -> list[TermMatch]:
    matches: list[TermMatch] = []
    for key, data in (router.get(section) or {}).items():
        matches.extend(_find_aliases(text, str(key), layer, data or {}))
    return matches


def _compatibility_intents(
    text: str,
    router: dict,
    selected_root: str | None,
    selected_noun: str | None,
    selected_target: str | None,
    proof_keys: list[str],
) -> list[dict[str, Any]]:
    intents: list[dict[str, Any]] = []
    for intent, cfg in (router.get("compatibility_intents") or {}).items():
        triggers = cfg.get("triggers") or {}
        phrase_hit = False
        for phrase in triggers.get("phrases") or []:
            term = _normalize_term(str(phrase))
            if term and re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
                phrase_hit = True

        dimension_checks: list[bool] = []
        if triggers.get("noun"):
            dimension_checks.append(bool(selected_noun and selected_noun in (triggers.get("noun") or [])))
        if triggers.get("target"):
            dimension_checks.append(bool(selected_target and selected_target in (triggers.get("target") or [])))
        if triggers.get("root"):
            dimension_checks.append(bool(selected_root and selected_root in (triggers.get("root") or [])))
        if triggers.get("proof"):
            dimension_checks.append(bool(set(proof_keys).intersection(set(triggers.get("proof") or []))))

        dimension_hit = bool(dimension_checks) and all(dimension_checks)
        hit = phrase_hit or dimension_hit

        if hit:
            intents.append(
                {
                    "intent": intent,
                    "matched_terms": [intent],
                    "description": cfg.get("description", ""),
                    "source": "compatibility_intent",
                    "skills": cfg.get("skills", []) or [],
                    "required_outputs": cfg.get("required_outputs", []) or [],
                }
            )
    return intents


def route_text(text: str, router: dict | None = None) -> dict:
    router = router or load_router()
    normalized = _normalize_text(text)

    protocol_matches = _find_layer(normalized, router, "behavioral_protocols", "behavioral_protocol")
    root_matches = _find_layer(normalized, router, "root_verbs", "root_verb")
    noun_matches = _find_layer(normalized, router, "noun_branches", "noun_branch")
    target_matches = _find_layer(normalized, router, "targets", "target")
    corrective_matches = _find_layer(normalized, router, "correctives", "corrective")
    modifiers = _find_grouped_modifiers(normalized, router)

    selected_root = _best_root(root_matches)
    selected_noun = _best_noun(noun_matches, selected_root)
    selected_target = _best_target(target_matches, selected_noun, selected_root)
    all_skills_active = any(match.key == "all_skills" for match in protocol_matches)
    universal_skill_surface = None
    if all_skills_active:
        registry_summary = _load_registry_summary()
        universal_skill_surface = {
            "surface": UNIVERSAL_SURFACE.relative_to(ROOT).as_posix(),
            "contract": "platform/sdlc/13_skills/universal_surface/UNIVERSAL_SKILL_SURFACE.md",
            "policy": "platform/sdlc/13_skills/skill_refinery/universal_skill_invocation_policy.md",
            "cross_runtime_contract": "platform/sdlc/13_skills/skill_refinery/cross_runtime_invoke_all_skills_contract.md",
            **registry_summary,
            "semantics": "Repository-native disciplines are available through the universal surface; runtime tool-callable skills are only a subset.",
        }

    if selected_target and selected_target.data.get("noun"):
        target_noun = str(selected_target.data["noun"]).lower()
        target_noun_match = next((item for item in noun_matches if item.key.lower() == target_noun), None)
        if target_noun_match:
            selected_noun = target_noun_match
        elif target_noun in (router.get("noun_branches") or {}):
            selected_noun = TermMatch(
                key=target_noun,
                term=target_noun,
                start=selected_target.start,
                end=selected_target.end,
                layer="noun_branch",
                data=(router.get("noun_branches") or {})[target_noun],
            )

    if all_skills_active and selected_noun and selected_noun.key == "agent":
        assistant_acquisition_target = selected_target and selected_target.key == "assistant_surface_inventory"
        acquisition_language = re.search(r"(?<![a-z0-9])(acquire|pull|scan|import)(?![a-z0-9])", normalized)
        if not assistant_acquisition_target and not acquisition_language:
            selected_noun = None

    corrective = sorted(corrective_matches, key=lambda item: (item.start, -item.length))[0] if corrective_matches else None

    skills: list[str] = []
    outputs: list[str] = []
    matches: list[dict[str, Any]] = []

    def add_match(match: TermMatch, source: str | None = None) -> None:
        matches.append(
            {
                "intent": match.key,
                "layer": match.layer,
                "matched_terms": [match.term],
                "description": match.data.get("meaning") or match.data.get("default_output") or "",
                "source": source or match.layer,
            }
        )
        skills.extend(match.data.get("skills", []) or [])
        outputs.extend(match.data.get("required_outputs", []) or [])
        default_output = match.data.get("default_output")
        if default_output:
            outputs.append(str(default_output))

    for match in sorted(protocol_matches, key=lambda item: (item.start, -item.length)):
        add_match(match)
    if selected_root:
        add_match(selected_root)
    if selected_noun:
        add_match(selected_noun)
    if selected_target:
        add_match(selected_target)
    if corrective:
        add_match(corrective)
        skills.extend(["SKILL_ERROR_LOGGING_ENGINE_001", "SKILL_SKILL_REFINEMENT_SIMULATOR_001", "SKILL_AUTOMATED_REGRESSION_TESTING_001"])
        outputs.extend(["Miss classification", "Responsible skill", "Ledger update", "Regression case"])

    active_modifiers = {
        group: [item["key"] for item in hits]
        for group, hits in modifiers.items()
    }
    proof_keys = active_modifiers.get("proof", [])

    if proof_keys:
        skills.extend(["SKILL_PROOF_MATRIX_001", "SKILL_RUNTIME_REGRESSION_VERIFY_001"])
        outputs.extend(["Proof requirements", "Validation gates"])

    if "output" in active_modifiers:
        outputs.extend([key.replace("_", " ") for key in active_modifiers["output"]])

    compatibility = _compatibility_intents(
        normalized,
        router,
        selected_root.key if selected_root else None,
        selected_noun.key if selected_noun else None,
        selected_target.key if selected_target else None,
        proof_keys,
    )
    for compat in compatibility:
        matches.append(compat)
        skills.extend(compat.get("skills", []) or [])
        outputs.extend(compat.get("required_outputs", []) or [])

    if selected_target and selected_target.data.get("matched_intent"):
        target_intent = str(selected_target.data["matched_intent"])
        if target_intent not in [item.get("intent") for item in matches]:
            matches.append(
                {
                    "intent": target_intent,
                    "layer": "target",
                    "matched_terms": [selected_target.term],
                    "description": selected_target.data.get("default_output", ""),
                    "source": "target_intent",
                }
            )

    if not matches:
        skills.extend(router.get("default_core_skills", []) or [])

    proof_requirements = {
        "required": bool(proof_keys),
        "triggers": proof_keys,
        "outputs": ["Proof requirements", "Validation gates"] if proof_keys else [],
    }
    active_output_contract = {
        "default": (
            selected_target.data.get("default_output")
            if selected_target
            else selected_noun.data.get("default_output")
            if selected_noun
            else selected_root.data.get("default_output")
            if selected_root
            else None
        ),
        "modifiers": active_modifiers.get("output", []),
        "required_outputs": _dedupe(outputs),
    }

    matched_intents = _dedupe([str(item["intent"]) for item in matches])
    allowed_project_families = _allowed_project_families(
        normalized,
        selected_noun.key if selected_noun else None,
        selected_target.key if selected_target else None,
    )
    active_skills, suppressed_skills = _suppress_unbound_project_skills(skills, allowed_project_families)
    playbook_disciplines = [
        {"skill": skill, "playbook": playbook}
        for skill in active_skills
        if (playbook := _playbook_path_for_skill(skill))
    ]

    return {
        "input": text,
        "normalized_input": normalized,
        "selected_root": selected_root.key if selected_root else None,
        "selected_noun": selected_noun.key if selected_noun else None,
        "selected_target": selected_target.key if selected_target else None,
        "active_modifiers": active_modifiers,
        "active_output_contract": active_output_contract,
        "proof_requirements": proof_requirements,
        "corrective_override": {
            "trigger": corrective.key,
            "miss_type": corrective.data.get("miss_type"),
            "action": corrective.data.get("action"),
        }
        if corrective
        else None,
        "matched_intents": matched_intents,
        "matches": matches,
        "skills": active_skills,
        "suppressed_skills": suppressed_skills,
        "tool_called_skills": [],
        "playbook_applied_disciplines": playbook_disciplines,
        "universal_skill_surface": universal_skill_surface,
        "allowed_project_families": sorted(allowed_project_families),
        "required_outputs": _dedupe(outputs),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="*", help="Text to route")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of YAML")
    args = parser.parse_args()

    text = " ".join(args.text).strip()
    if not text:
        parser.error("text is required")

    result = route_text(text)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(yaml.safe_dump(result, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
