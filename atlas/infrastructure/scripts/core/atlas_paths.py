"""Path constants for Atlas platform and intelligence core automation."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TODAY = "2026-05-17"

ATLAS_EVIDENCE = ROOT / "platform" / "systems" / "23_evidence" / "atlas_platform"
STATUS_DIR = ATLAS_EVIDENCE / "status"
INVENTORY_DIR = ATLAS_EVIDENCE / "inventory"
GATES_DIR = ATLAS_EVIDENCE / "gates"
GATE_LOG_DIR = GATES_DIR / "logs"
FLOW_DIR = ATLAS_EVIDENCE / "flows"
FLOW_LATEST = FLOW_DIR / "atlas_flow_latest.yaml"
COMMANDS_DIR = ATLAS_EVIDENCE / "commands"
COMMAND_LATEST = COMMANDS_DIR / "atlas_latest.yaml"
INGEST_DIR = ATLAS_EVIDENCE / "ingest"
INGEST_LATEST = INGEST_DIR / "atlas_ingest_latest.yaml"
PREFLIGHT_DIR = ATLAS_EVIDENCE / "preflight"
GRAPH_EVIDENCE_DIR = ATLAS_EVIDENCE / "graph"
VAULT_EVIDENCE_DIR = ATLAS_EVIDENCE / "vault"
TENANT_EVIDENCE_DIR = ATLAS_EVIDENCE / "tenants"
REPO_EVENTS_DIR = ATLAS_EVIDENCE / "repo_events"

GENERATED_DOC = ROOT / "platform" / "sdlc" / "11_documentation" / "generated" / "ATLAS_PLATFORM_STATUS.generated.md"
ATLAS_GRAPH_ENGINE_GENERATED_DOC = ROOT / "platform" / "sdlc" / "11_documentation" / "generated" / "ATLAS_GRAPH_ENGINE_STATUS.generated.md"
ATLAS_KNOWLEDGE_VAULT_GENERATED_DOC = ROOT / "platform" / "sdlc" / "11_documentation" / "generated" / "ATLAS_KNOWLEDGE_VAULT_STATUS.generated.md"

CONTEXT_PACKET = ROOT / "platform" / "systems" / "42_context_compiler" / "output" / "generated" / "CP-super-c-atlas-intelligence-core.yaml"
PLATFORM_CONTEXT_PACKET = ROOT / "platform" / "systems" / "42_context_compiler" / "output" / "generated" / "CP-super-c-atlas-platform-core.yaml"

RELEASE_REPORT = ROOT / "platform" / "sdlc" / "09_release" / "release_evidence" / f"{TODAY}_super_c_atlas_intelligence_core_v0_1_report.md"
INTELLIGENCE_CORE_REPORT = ROOT / "platform" / "sdlc" / "09_release" / "release_evidence" / f"{TODAY}_super_c_atlas_intelligence_core_v0_2_report.md"
PLATFORM_RELEASE_REPORT = ROOT / "platform" / "sdlc" / "09_release" / "release_evidence" / f"{TODAY}_super_c_atlas_platform_core_v0_1_report.md"

VERIFICATION_GATE_DIR = ROOT / "platform" / "sdlc" / "08_verification" / "gate_results"

ATLAS_GRAPH_ENGINE_ROOT = ROOT / "platform" / "systems" / "43_graph_engine"
ATLAS_GRAPH_ENGINE_GRAPHS = ATLAS_GRAPH_ENGINE_ROOT / "graphs"
ATLAS_GRAPH_ENGINE_EXPORTS = ATLAS_GRAPH_ENGINE_ROOT / "exports"
ATLAS_GRAPH_ENGINE_REPORTS = ATLAS_GRAPH_ENGINE_ROOT / "reports"
ATLAS_GRAPH_ENGINE_MANIFEST = ATLAS_GRAPH_ENGINE_ROOT / "atlas_graph_engine.manifest.yaml"
GRAPH_SNAPSHOT = ATLAS_GRAPH_ENGINE_EXPORTS / "graph_snapshot.json"

ATLAS_KNOWLEDGE_VAULT_ROOT = ROOT / "platform" / "systems" / "44_knowledge_vault"
ATLAS_KNOWLEDGE_VAULT_REPORTS = ATLAS_KNOWLEDGE_VAULT_ROOT / "reports"
ATLAS_KNOWLEDGE_VAULT_NOTES = ATLAS_KNOWLEDGE_VAULT_ROOT / "notes"
ATLAS_KNOWLEDGE_VAULT_MANIFEST = ATLAS_KNOWLEDGE_VAULT_ROOT / "knowledge_vault.manifest.yaml"

FLOW_LOGS_DIR = FLOW_DIR / "logs"


def rel(path: Path) -> str:
    """Return a stable repo-relative path."""
    return path.relative_to(ROOT).as_posix()


def ensure_output_dirs() -> None:
    for path in [
        STATUS_DIR,
        INVENTORY_DIR,
        GATES_DIR,
        GATE_LOG_DIR,
        INGEST_DIR,
        COMMANDS_DIR,
        FLOW_DIR,
        PREFLIGHT_DIR,
        GRAPH_EVIDENCE_DIR,
        VAULT_EVIDENCE_DIR,
        TENANT_EVIDENCE_DIR,
        REPO_EVENTS_DIR,
        COMMANDS_DIR,
        ATLAS_GRAPH_ENGINE_GRAPHS,
        ATLAS_GRAPH_ENGINE_EXPORTS,
        ATLAS_GRAPH_ENGINE_REPORTS,
        ATLAS_GRAPH_ENGINE_MANIFEST.parent,
        ATLAS_KNOWLEDGE_VAULT_REPORTS,
        ATLAS_KNOWLEDGE_VAULT_NOTES,
        ATLAS_KNOWLEDGE_VAULT_MANIFEST.parent,
        GENERATED_DOC.parent,
        ATLAS_GRAPH_ENGINE_GENERATED_DOC.parent,
        ATLAS_KNOWLEDGE_VAULT_GENERATED_DOC.parent,
        CONTEXT_PACKET.parent,
        PLATFORM_CONTEXT_PACKET.parent,
        RELEASE_REPORT.parent,
        INTELLIGENCE_CORE_REPORT.parent,
        PLATFORM_RELEASE_REPORT.parent,
        VERIFICATION_GATE_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
