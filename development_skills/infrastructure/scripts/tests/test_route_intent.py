import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infrastructure/scripts"))

from route_intent import route_text


class RouteIntentLayerTests(unittest.TestCase):
    def test_build_platform_precedence(self):
        routed = route_text("build a platform")
        self.assertEqual(routed["selected_root"], "build")
        self.assertEqual(routed["selected_noun"], "platform")
        self.assertIn("platform_build", routed["matched_intents"])

    def test_nearest_noun_after_root_wins(self):
        routed = route_text("build a dashboard for platform leadership")
        self.assertEqual(routed["selected_root"], "build")
        self.assertEqual(routed["selected_noun"], "dashboard")

    def test_proof_and_output_modifiers_are_active(self):
        routed = route_text("build dashboard DeepThink proof one-shot")
        self.assertTrue(routed["proof_requirements"]["required"])
        self.assertIn("one_shot", routed["active_output_contract"]["modifiers"])

    def test_atlas_command_aliases_use_canonical_targets(self):
        graph = route_text("/atlas:graph")
        self.assertEqual(graph["selected_noun"], "atlas")
        self.assertEqual(graph["selected_target"], "atlas_graph_engine")
        self.assertIn("atlas_graph_engine", graph["matched_intents"])

        vault = route_text("/atlas:knowledge_vault")
        self.assertEqual(vault["selected_noun"], "atlas")
        self.assertEqual(vault["selected_target"], "atlas_knowledge_vault")
        self.assertIn("atlas_knowledge_vault", vault["matched_intents"])

    def test_corrective_override(self):
        routed = route_text("wrong target re-read missed it")
        self.assertEqual(routed["corrective_override"]["trigger"], "wrong_target")
        self.assertIn("Miss classification", routed["required_outputs"])

    def test_invoke_all_skills_uses_playbook_disciplines_not_acquisition(self):
        routed = route_text("invoke all skills now")
        self.assertIn("all_skills", routed["matched_intents"])
        self.assertNotIn("unified_assistant_surface_acquisition", routed["matched_intents"])
        self.assertEqual(routed["tool_called_skills"], [])
        self.assertTrue(routed["playbook_applied_disciplines"])
        self.assertIn("SKILL_TRIGGER_ROUTER_001", [item["skill"] for item in routed["playbook_applied_disciplines"]])
        self.assertNotIn("SKILL_GLOBAL_CLAUDE_REPOSITORY_ACQUISITION_001", routed["skills"])

    def test_generic_routes_suppress_project_specific_skills(self):
        for text in ["build a platform", "build dashboard", "audit security", "fix API"]:
            routed = route_text(text)
            offenders = [
                skill
                for skill in routed["skills"]
                if skill.startswith(("SKILL_ELSON_", "SKILL_IPOS_", "SKILL_GENOS_", "SKILL_SUPER_C_", "SKILL_SC_"))
                or skill in {"SKILL_GLOBAL_CLAUDE_REPOSITORY_ACQUISITION_001", "SKILL_CODEX_GEMINI_REPOSITORY_ACQUISITION_001"}
            ]
            self.assertEqual(offenders, [], f"{text} leaked project-specific skills: {offenders}")

    def test_targets_reactivate_project_specific_skills(self):
        self.assertTrue(any(skill.startswith("SKILL_ELSON_") for skill in route_text("build Elson platform")["skills"]))
        self.assertTrue(any(skill.startswith("SKILL_IPOS_") for skill in route_text("build IPOS dashboard")["skills"]))
        self.assertTrue(any(skill.startswith(("SKILL_GENOS_", "SKILL_SUPER_C_", "SKILL_SC_")) for skill in route_text("build compiler")["skills"]))


if __name__ == "__main__":
    unittest.main()
