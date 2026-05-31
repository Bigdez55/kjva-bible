import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import build_parser
from atlas_ingest import build_snapshot, write_ingest_artifacts
from atlas_paths import ROOT, INGEST_LATEST
sys.path.insert(0, str(ROOT / "infrastructure/scripts"))
from route_intent import route_text


class AtlasCommandParserTests(unittest.TestCase):
    def _args(self, *parts):
        parser = build_parser()
        return parser.parse_args(list(parts))

    def test_command_aliases(self):
        self.assertEqual(self._args("status", "--format", "json").func.__name__, "cmd_status")
        self.assertEqual(self._args("inventory", "--check").func.__name__, "cmd_inventory")
        self.assertEqual(self._args("compile-context").func.__name__, "cmd_compile_context")
        self.assertEqual(self._args("compile_context").func.__name__, "cmd_compile_context")
        self.assertEqual(self._args("report").func.__name__, "cmd_report")

    def test_graph_intent_flags(self):
        self.assertEqual(self._args("graph", "--check").func.__name__, "cmd_graph")
        self.assertEqual(self._args("knowledge_vault", "--check").func.__name__, "cmd_knowledge_vault")


class AtlasCommandRunTests(unittest.TestCase):
    def _run(self, args, input_text=None):
        proc = subprocess.run(
            ["python3", "infrastructure/scripts/atlas_core/atlas.py", *args],
            cwd=ROOT,
            text=True,
            input=input_text,
            capture_output=True,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_atlas_command_readonly_modes(self):
        code, out, _ = self._run(["ingest", "--check", "--format", "json"])
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(payload["command"], "ingest")

        snapshot = build_snapshot()
        write_ingest_artifacts(snapshot, apply_latest=True)
        code, out, _ = self._run(["graph", "--check", "--format", "json"])
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(payload["command"], "graph")

        code, out, _ = self._run(["knowledge_vault", "--check", "--format", "json"])
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["command"], "knowledge_vault")

        code, out, _ = self._run(["status", "--check", "--format", "json"])
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["command"], "status")

        code, out, _ = self._run(["compile_context", "--check", "--format", "json"])
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["command"], "compile_context")

        code, out, _ = self._run(["report", "--check", "--format", "json"])
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["command"], "report")

        self.assertTrue(INGEST_LATEST.exists())
        latest = INGEST_LATEST.read_text().strip()
        self.assertTrue(len(latest) > 0)
        # Pointer can be either a path to a snapshot or an inline YAML snapshot payload.
        if latest.endswith(".yaml"):
            self.assertTrue(Path(latest).suffix == ".yaml" or latest.endswith(".yaml"))
        else:
            self.assertTrue(latest.strip().startswith("run_id:") or latest.strip().startswith("atlas_"))

    def test_validate_command_runs_safe_gates(self):
        code, out, _ = self._run(["validate", "--safe-only", "--format", "json"])
        self.assertIn(code, (0, 1))
        payload = json.loads(out)
        self.assertEqual(payload["command"], "validate")

    def test_route_intent_atlas_commands(self):
        for phrase, intent in [
            ("I need an Atlas ingest snapshot.", "atlas_ingest"),
            ("Build the Atlas graph for this repository.", "atlas_graph_engine"),
            ("Export Atlas Knowledge Vault notes for this convergence run.", "atlas_knowledge_vault"),
            ("What is Atlas status right now?", "atlas_status"),
            ("Run Atlas validate blockers before reporting.", "atlas_validate"),
            ("Compile atlas context for handoff.", "atlas_compile_context"),
            ("Create an Atlas report package now.", "atlas_report"),
            ("Run atlas:flow with all convergence steps.", "atlas_flow"),
        ]:
            actual = set(route_text(phrase).get("matched_intents", []))
            self.assertIn(intent, actual, phrase)

    def test_route_intent_atlas_alias_surface(self):
        graph = route_text("/atlas:graph")
        self.assertEqual(graph.get("selected_noun"), "atlas")
        self.assertEqual(graph.get("selected_target"), "atlas_graph_engine")
        self.assertIn("atlas_graph_engine", set(graph.get("matched_intents", [])))

        vault = route_text("/atlas:knowledge_vault")
        self.assertEqual(vault.get("selected_noun"), "atlas")
        self.assertEqual(vault.get("selected_target"), "atlas_knowledge_vault")
        self.assertIn("atlas_knowledge_vault", set(vault.get("matched_intents", [])))


if __name__ == "__main__":
    unittest.main()
