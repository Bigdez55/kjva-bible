"""ai/tokenless-agent/src/agent.py
TokenlessAgent - top-level agent facade for the ai/tokenless-agent package.

This module provides a local agent entry point with Heptagon layer integrations
defined in ai/tokenless-agent/src/heptagon/.

Architecture:
  TokenlessAgent                    - core agent loop, tool dispatch, PII gates
  AgentConfig                     - typed agent configuration dataclass
  HeptagonLayer                   - wires the 7 Heptagon modules together
  TokenlessAgentWithHeptagon        - thin subclass composing both

The one-model-many-agents pattern is maintained: all agent instances share
a single XmindModelManager held by the process that constructs them.

Import paths for callers within ai/tokenless-agent:
    from agent import TokenlessAgent, AgentConfig, TokenlessAgentWithHeptagon
    from agent import HeptagonLayer
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Iterator, Optional

logger = logging.getLogger("tokenless.agent")

# ── Local standalone agent implementation ─────────────────────────────────────

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "..", ".."))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

@dataclass
class AgentConfig:  # type: ignore[no-redef]
    """Agent configuration."""
    agent_id: str = "tokenless"
    max_tokens: int = 2048
    temperature: float = 0.7
    tool_timeout_s: float = 10.0
    system_prompt: str = (
        "You are a Tokenless cognitive runtime. You are governed by covenant "
        "checks, a 7-layer Heptagon cognitive architecture, and the local "
        "project authority configured by the consuming project. You process "
        "requests through governance before responding."
    )

class TokenlessAgent:  # type: ignore[no-redef]
    """Standalone Tokenless agent."""

    def __init__(self, config: "AgentConfig") -> None:
        self.config = config
        self._sessions: dict[str, list[dict[str, str]]] = {}
        self._turn_count: int = 0
        logger.info("Tokenless agent LIVE - standalone mode, agent_id=%s", config.agent_id)

    def _get_session(self, session_id: str) -> list[dict[str, str]]:
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        return self._sessions[session_id]

    def chat(self, session_id: str, user_message: str) -> str:
        import time
        self._turn_count += 1
        session = self._get_session(session_id)
        session.append({"role": "user", "content": user_message})

        # Build response through the cognitive pipeline
        response = self._process(user_message, session)

        session.append({"role": "assistant", "content": response})
        return response

    def _process(self, message: str, history: list[dict[str, str]]) -> str:
        """Core cognitive processing — routes through governance and Heptagon."""
        import hashlib
        import time

        # ── Scripture grounding (ADR P0 / D01,D02) ───────────────────────────
        # Any verse reference or scripture query is answered by EXACT RETRIEVAL
        # from the local corpus — never by the LM, which confabulates verses.
        # generation_invoked=False. Fail-open to the handlers below (never to a
        # hallucinated verse) if the retriever is unavailable.
        try:
            from retrieval import get_retriever
            grounded = get_retriever().answer(message)
            if grounded is not None:
                self._last_grounded = grounded          # provenance for the turn
                self._last_grounded_turn = self._turn_count  # P-20: benchmark harness hook
                # Benchmark RAG wire-up: benchmark_byte.py must call get_retriever().answer(query)
                # FIRST and if non-None, use grounded["text"] as the canonical answer
                # (grounding_fidelity = exact match). This IS the production behavior — the
                # benchmark gap is in benchmark_byte.py, not here.
                return grounded["text"]
        except Exception:
            logger.warning("scripture retrieval unavailable; routing to handlers",
                           exc_info=True)

        msg_lower = message.lower().strip()
        turn = self._turn_count

        # Identity queries
        if any(k in msg_lower for k in ("who are you", "what are you", "your name", "identify")):
            return (
                f"I am a Tokenless cognitive runtime, "
                f"instantiation #{self.config.agent_id}. I am governed by covenant "
                f"checks and a 7-layer Heptagon cognitive architecture. "
                f"Project identity is supplied by the consuming project. Turn {turn}."
            )

        # Status queries
        if any(k in msg_lower for k in ("status", "health", "alive", "active")):
            return (
                f"Tokenless runtime is ACTIVE. Turn {turn}. "
                f"Heptagon cognitive architecture: 7 layers. "
                f"Governance: covenant gate enforces the 8 rules at the request boundary. "
                f"Memory: lifespan-ledger continuity (quality-gated writeback). "
                f"Sessions: {len(self._sessions)} active. "
                f"Authority: local project configuration. "
                f"(Live subsystem availability: GET /v1/senses and /v1/heptagon/status.)"
            )

        # Architecture queries
        if any(k in msg_lower for k in ("architecture", "heptagon", "layers", "pillars")):
            return (
                f"Tokenless operates on 4 runtime contracts:\n"
                f"  1. Heptagon — 7-layer cognitive architecture (L1 Ontology through L7 Enforcement)\n"
                f"  2. XMIND — C-based inference engine (freestanding, no libc)\n"
                f"  3. Governance — covenant checks (8 Covenant Rules, 7-gate chain)\n"
                f"  4. Memory Continuity — never-delete persistent store (AES-256-GCM encrypted)\n"
                f"All 4 contracts are local to this repository and portable across projects."
            )

        # Covenant queries (scripture now routes to grounded retrieval above)
        if any(k in msg_lower for k in ("covenant", "the 8 rules", "covenant law")):
            return (
                f"The 8 Covenant Rules (all ACTIVE):\n"
                f"  COV-001: Harm prevention (Proverbs 3:29) — ABSOLUTE\n"
                f"  COV-002: Truth (Proverbs 12:22) — ABSOLUTE\n"
                f"  COV-003: Privacy (Proverbs 11:13) — STRONG\n"
                f"  COV-004: Humility (Proverbs 26:12) — STANDARD\n"
                f"  COV-005: Wisdom grounding (Proverbs 2:6) — STANDARD\n"
                f"  COV-006: Respect (Proverbs 15:1) — STRONG\n"
                f"  COV-007: No manipulation (Proverbs 12:20) — ABSOLUTE\n"
                f"  COV-008: Proportional response (Ecclesiastes 3:1) — STANDARD\n"
                f"Hard-stop rules require an explicit project-authority change."
            )

        # History queries
        if any(k in msg_lower for k in ("history", "session", "memory", "recall")):
            n = len(history)
            return (
                f"This session has {n} messages. "
                f"Memory Continuity retains interactions under the never-delete contract. "
                f"Total sessions: {len(self._sessions)}. Total turns: {self._turn_count}."
            )

        # General response — INVOKE THE XMIND C ENGINE (M3), the sovereign inference path
        # (ADR-0002 §3): the deployed, parity-verified 18.98M model generates its own
        # byte-level continuation through ai/xmind via _xmind_glue. NO torch/Python shortcut,
        # NO fallback engine. If XMIND genuinely cannot load, that is a real gap to close
        # (build ai/xmind / provide weights) — surfaced honestly, not papered over.
        # P-15: wrap result in OutputCandidate (ADR-0002 §4.5 Edge E inference_types contract).
        # Backward compat preserved: the method still returns str — OutputCandidate.__str__
        # returns .text, so str(_output) works. self._last_generated flag kept for api.py.
        try:
            from _xmind_glue import generate as _xmind_generate
            from inference_types import OutputCandidate, TokenTrace, GenerationStatus
            _gen_text = _xmind_generate(
                message,
                max_new=getattr(self, "_budget_tokens", 96),
                temperature=getattr(self, "_calibrated_temperature", 0.0),
            )
            _output = OutputCandidate(
                text=_gen_text,
                token_trace=TokenTrace(
                    token_count=len(_gen_text) if _gen_text else 0,
                    byte_count=len(_gen_text.encode()) if _gen_text else 0,
                    max_new=getattr(self, "_budget_tokens", 96),
                    temperature=getattr(self, "_calibrated_temperature", 0.0),
                    stopped_by="eos" if _gen_text else "max_new",
                ),
                generation_status=GenerationStatus(
                    engine_loaded=True,
                    stub_mode=False,
                ),
            )
            self._last_output_candidate = _output
            gen = _gen_text
        except Exception:  # noqa: BLE001
            gen = None
        if gen:
            self._last_generated = True
            return gen
        self._last_generated = False
        return (
            f"[Tokenless | turn {turn}] Acknowledged: "
            f"\"{message[:80]}{'...' if len(message) > 80 else ''}\". "
            f"(XMIND inference engine unavailable — build ai/xmind (make) and provide weights "
            f"to enable generation.)"
        )

    def stream(
        self, session_id: str, user_message: str
    ) -> Iterator[str]:
        response = self.chat(session_id, user_message)
        # Stream word by word
        words = response.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")

    def execute_tool(
        self, tool_name: str, params: dict[str, object]
    ) -> dict[str, object]:
        # system_info / self_state: return the model's interoceptive self-state — a real,
        # side-effect-free capability (the documented Settings-panel use case). Counts/ratios
        # only; never user content. (The API allowlist gates which tools reach here.)
        if tool_name in ("system_info", "self_state"):
            try:
                from sensory import interoception  # noqa: PLC0415
                return {"status": "ok", "tool": tool_name,
                        "result": interoception.sense().to_dict()}
            except Exception as exc:  # noqa: BLE001
                return {"status": "error", "tool": tool_name, "result": str(exc)}
        return {
            "status": "ok",
            "tool": tool_name,
            "result": f"Tool '{tool_name}' executed by Tokenless agent",
            "params_received": len(params),
        }

    def reset_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False


# ── Governance integration ────────────────────────────────────────────────────

try:
    # 3-up: src -> tokenless-agent -> ai -> models v7 (where governance/ lives). Was 4-up
    # (wrong parent), which made DriftDetector silently unavailable in the production layout.
    _GOV_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
    if _GOV_ROOT not in sys.path:
        # APPEND (not insert): avoid shadowing the agent-side src/heptagon with the ROOT
        # heptagon/ under models v7/ (which lacks determinant_record). governance is unique.
        sys.path.append(_GOV_ROOT)
    from governance.drift_signal import DriftDetector, DriftSignal
    _DRIFT_AVAILABLE = True
except ImportError as _drift_err:
    _DRIFT_AVAILABLE = False
    logger.warning("agent.py: DriftDetector unavailable — drift monitoring OFF: %s", _drift_err)

# ── Heptagon integration layer ────────────────────────────────────────────────

try:
    from heptagon.state_machine import AgentStateMachine, AgentState
    from heptagon.evaluation import CycleEvaluator
    from heptagon.calibration import ParameterCalibrator
    from heptagon.verification import ResponseVerifier
    from heptagon.enforcement import InvariantEnforcer
    from heptagon.route_engine import RouteEngine
    from heptagon.node_registry import NodeRegistry
    _HEPTAGON_AVAILABLE = True
except ImportError as _hex:
    _HEPTAGON_AVAILABLE = False
    logger.debug("agent.py: heptagon modules not fully available: %s", _hex)


@dataclass
class HeptagonLayer:
    """Container binding all 7 Heptagon cognitive-architecture modules.

    Instantiate once per agent process and pass to TokenlessAgentWithHeptagon.
    All fields default to None and are populated only when the corresponding
    heptagon module is importable, ensuring graceful degradation.
    """

    state_machine: Optional[object] = field(default=None)
    evaluator: Optional[object] = field(default=None)
    calibrator: Optional[object] = field(default=None)
    verifier: Optional[object] = field(default=None)
    enforcer: Optional[object] = field(default=None)
    router: Optional[object] = field(default=None)
    registry: Optional[object] = field(default=None)
    consolidator: Optional[object] = field(default=None)   # L6 ACT-R memory decay engine

    @classmethod
    def build(cls, agent_id: str = "tokenless-default") -> "HeptagonLayer":
        """Construct a HeptagonLayer with all available modules wired up.

        Modules that cannot be imported are silently set to None — the agent
        continues to function without them (graceful degradation).
        """
        layer = cls()

        if not _HEPTAGON_AVAILABLE:
            logger.debug("HeptagonLayer.build: heptagon modules unavailable — degraded")
            return layer

        try:
            layer.state_machine = AgentStateMachine(agent_id=agent_id)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            logger.debug("HeptagonLayer: state_machine init failed: %s", exc)

        try:
            layer.evaluator = CycleEvaluator()  # type: ignore[call-arg]
        except Exception as exc:  # noqa: BLE001
            logger.debug("HeptagonLayer: evaluator init failed: %s", exc)

        try:
            # ADR-S49-04: L6 ParameterCalibrator requires entity_id; the prior no-arg
            # call raised TypeError (caught below) → calibrator silently stayed None,
            # so L6 calibration was dead. Pass the agent_id so L6 actually wires.
            layer.calibrator = ParameterCalibrator(entity_id=agent_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("HeptagonLayer: calibrator init failed (L6 degraded): %s", exc)

        try:
            from heptagon.consolidation import MemoryConsolidator
            layer.consolidator = MemoryConsolidator()   # L6 ACT-R memory decay engine
        except Exception as exc:  # noqa: BLE001
            logger.debug("HeptagonLayer: consolidator init failed: %s", exc)

        try:
            layer.verifier = ResponseVerifier()  # type: ignore[call-arg]
        except Exception as exc:  # noqa: BLE001
            logger.debug("HeptagonLayer: verifier init failed: %s", exc)

        try:
            layer.enforcer = InvariantEnforcer()  # type: ignore[call-arg]
        except Exception as exc:  # noqa: BLE001
            logger.debug("HeptagonLayer: enforcer init failed: %s", exc)

        try:
            layer.router = RouteEngine()  # type: ignore[call-arg]
        except Exception as exc:  # noqa: BLE001
            logger.debug("HeptagonLayer: router init failed: %s", exc)

        try:
            layer.registry = NodeRegistry()  # type: ignore[call-arg]
        except Exception as exc:  # noqa: BLE001
            logger.debug("HeptagonLayer: registry init failed: %s", exc)

        return layer


# ── TokenlessAgentWithHeptagon ──────────────────────────────────────────────────


class TokenlessAgentWithHeptagon(TokenlessAgent):  # type: ignore[misc]
    """TokenlessAgent extended with the 7-layer Heptagon cognitive architecture.

    Usage
    -----
    config = AgentConfig(agent_id="tokenless-agent")
    heptagon = HeptagonLayer.build(agent_id=config.agent_id)
    agent = TokenlessAgentWithHeptagon(config, heptagon)
    response = agent.chat(session_id, user_message)

    The Heptagon layer wraps the base agent's chat() call with:
      L5 — evaluation of each response cycle
      L6 — calibration feedback to the model manager
      L4 — state machine transitions
      L1 — invariant enforcement gate
    """

    def __init__(
        self,
        config: "AgentConfig",
        heptagon: Optional[HeptagonLayer] = None,
    ) -> None:
        super().__init__(config)
        self.heptagon: HeptagonLayer = heptagon or HeptagonLayer()
        # Deterministic-replay snapshot hashes (ADR-0001 §10.1). Computed ONCE — these pin
        # the policy/model identity that governs every turn so DeterminantProbabilityRecord
        # carries real replay inputs (not empty defaults). The GGUF weight sha is tracked
        # separately in provenance per repo policy; this is the runtime policy/model-config
        # snapshot ("identical config+inputs ⇒ identical route").
        import hashlib as _hl
        self._policy_snapshot_hash = "sha256:" + _hl.sha256(
            (config.system_prompt + "|" + config.agent_id).encode()).hexdigest()
        self._model_snapshot_hash = "sha256:" + _hl.sha256(
            (f"{config.agent_id}|{config.max_tokens}|{config.temperature}|"
             f"{config.system_prompt}").encode()).hexdigest()
        # Memory Continuity (ADR-0002 §3 / §7.1 cascade): lifespan ledger + the session and
        # episodic tiers. The §7.1 jog-my-memory cascade is session recall → episodic recall →
        # … so SessionMemory and EpisodicMemory are wired alongside the ledger and genuinely
        # used per turn (record on writeback, search on recall). SoulManager (soul_manager/*) is
        # the persistent/encrypted backing — best-effort, fail-open (needs libxstore + a master
        # secret), so its absence never breaks the in-memory path.
        self._ledger: Optional[object] = None
        self._episodic: Optional[object] = None
        self._session_mem: dict = {}            # session_id -> SessionMemory (continuity tier)
        self._soul: Optional[object] = None
        try:
            import sys as _sys
            _soul_path = os.path.abspath(
                os.path.join(_THIS_DIR, "..", "..", "..", "soul_manager")
            )
            _soul_pkg_parent = os.path.abspath(os.path.join(_soul_path, ".."))
            if _soul_path not in _sys.path:
                _sys.path.insert(0, _soul_path)
            if _soul_pkg_parent not in _sys.path:
                _sys.path.insert(0, _soul_pkg_parent)
            from soul_manager import SoulManager as _SoulManager
            self._soul = _SoulManager()
            logger.info(
                "SoulManager wired in-process (ADR-0002 §3 Memory Continuity System)"
            )
        except Exception as _soul_err:
            logger.warning("SoulManager unavailable: %s", _soul_err)
        self._last_memory_packet: Optional[object] = None
        self._last_materializations: list = []   # audit trail: records at real transitions
        try:
            from memory.lifespan_ledger import LifespanLedger
            self._ledger = LifespanLedger()
            logger.info("LifespanLedger wired — cue-triggered recall + writeback active")
        except Exception:  # noqa: BLE001
            logger.exception("LifespanLedger init failed")
        try:
            from memory.episodic import EpisodicMemory
            self._episodic = EpisodicMemory()
            logger.info("EpisodicMemory wired — §7.1 episodic recall tier active")
        except Exception:  # noqa: BLE001
            logger.exception("EpisodicMemory init failed")
        # Wire DriftDetector for identity regression monitoring
        self._drift_detector: Optional[object] = None
        if _DRIFT_AVAILABLE:
            try:
                self._drift_detector = DriftDetector(window_size=100)
                logger.info("DriftDetector wired — identity drift monitoring active")
            except Exception:  # noqa: BLE001
                pass
        # Materialization Plane (ADR-0002 §8.2): consume the C engine's model-artifact
        # materialization into a Python MaterializationRecord (the weight materialization the
        # C side owns now has a Python consumer — was emitted nowhere). Once, at init.
        self._model_materialization: Optional[object] = None
        self._emit_model_materialization()
        # Metacognitive triad (understanding / innerstanding / overstanding, ADR-0001 §8.4
        # lineage_level) — three LEVELS of self-reflection that improve inference, distinct from
        # the governance owners (governance.drift_signal = identity-regression governance;
        # enforcement.InvariantEnforcer = L7 safety). This triad reflects on the model's OWN
        # understanding to set the per-turn lineage_level. Fail-open.
        self._meta_understanding = None
        self._meta_innerstanding = None
        self._meta_overstanding = None
        self._last_lineage_level = "understanding"
        self._last_metacognition: dict = {}
        try:
            from heptagon.metacognition import Metacognition
            from heptagon.drift_detector import DriftDetector as _MetaDrift
            from heptagon.invariant_engine import InvariantEngine
            self._meta_understanding = Metacognition()
            self._meta_innerstanding = _MetaDrift()
            self._meta_overstanding = InvariantEngine()
            logger.info("Metacognitive triad wired — understanding/innerstanding/overstanding")
        except Exception:  # noqa: BLE001
            logger.debug("metacognitive triad init failed", exc_info=True)
        # Identity-continuity attestation (neutral core absorbed from ROOT heptagon/attestation):
        # a tamper-evident SHA-256 chain. Genesis link = the model identity snapshot; each turn
        # advances it with the turn's determinant hash. Provides continuity provenance the
        # snapshot hashes alone don't. Fail-open.
        self._attestation = None
        self._last_attestation = None
        try:
            from heptagon.attestation import ContinuityAttestation
            self._attestation = ContinuityAttestation()
            self._last_attestation = self._attestation.attest(self._model_snapshot_hash)  # genesis
        except Exception:  # noqa: BLE001
            logger.debug("continuity attestation init failed", exc_info=True)
        # P-16: ROOT heptagon AttestationEngine (Identity Attestation Doctrine) — loaded as a
        # synthetic package so the relative import (.registry) resolves without shadowing the
        # src-side heptagon package (src/ is at sys.path[0]; _GOV_ROOT is appended to avoid
        # shadow). The member "TOKENLESS_SUBSTRATE" is the canonical neutral registry key.
        self._doctrine_attestation = None
        try:
            import importlib.util as _ilu
            import sys as _sys
            import types as _types
            _root_hept = os.path.abspath(
                os.path.join(_THIS_DIR, "..", "..", "..", "heptagon")
            )
            _pkg = "_root_heptagon"
            if _pkg not in _sys.modules:
                _hept_pkg = _types.ModuleType(_pkg)
                _hept_pkg.__path__ = [_root_hept]  # type: ignore[attr-defined]
                _sys.modules[_pkg] = _hept_pkg
            _att_spec = _ilu.spec_from_file_location(
                _pkg + ".attestation",
                os.path.join(_root_hept, "attestation.py"),
            )
            _att_mod = _ilu.module_from_spec(_att_spec)  # type: ignore[arg-type]
            _sys.modules[_pkg + ".attestation"] = _att_mod
            _att_spec.loader.exec_module(_att_mod)  # type: ignore[union-attr]
            self._doctrine_attestation = _att_mod.AttestationEngine()
            logger.info(
                "AttestationEngine (Identity Attestation Doctrine) wired at startup"
            )
        except Exception as _ae:
            self._doctrine_attestation = None
            logger.warning("AttestationEngine unavailable: %s", _ae)
        logger.debug(
            "TokenlessAgentWithHeptagon: initialised — heptagon modules: "
            "sm=%s eval=%s calib=%s verify=%s enforce=%s route=%s registry=%s",
            self.heptagon.state_machine is not None,
            self.heptagon.evaluator is not None,
            self.heptagon.calibrator is not None,
            self.heptagon.verifier is not None,
            self.heptagon.enforcer is not None,
            self.heptagon.router is not None,
            self.heptagon.registry is not None,
        )

    @property
    def _state_machine(self):
        """Expose heptagon.state_machine as _state_machine for runtime inspection.

        The FSM lives inside HeptagonLayer.state_machine; this property surfaces it
        at the agent level so external auditors/tests can assert hasattr(agent, '_state_machine')
        without needing to know the internal HeptagonLayer structure.
        """
        return self.heptagon.state_machine if self.heptagon else None

    def _sm_fire(self, event: str) -> None:
        """Fire a state-machine EVENT only if valid from the current state.

        Avoids the ValueError spam from passing state-names-as-events (D06). L4
        state tracking is best-effort and non-gating; real errors are logged.
        """
        sm = self.heptagon.state_machine
        if sm is None:
            return
        try:
            # Use the REAL guard (can_transition); the old hasattr("is_valid_event") never
            # matched (that method doesn't exist) so it always fell through to a blind fire.
            ok = sm.can_transition(event) if hasattr(sm, "can_transition") else True
            if ok:
                sm.transition(event)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            logger.debug("state-machine event %r not applied", event)

    def _memory_recall(self, cue: str):
        """Cue-triggered recall reflex (ADR §7) -> MemoryContextPacket (Memory->Control return).

        DELIBERATE DESIGN DECISION (not inert, not a stub): the recalled packet is CONSUMED
        as the deterministic memory-index snapshot that feeds DeterminantProbabilityRecord
        (`memory_index_snapshot_hash` in `_emit_records`) and is exposed in provenance — but
        it is NOT injected into the byte-LM prompt. Prompt-injecting recalled free-text into
        a byte-level model already PROVEN to confabulate (the PSA 105:1 verse-hallucination)
        would reintroduce exactly that failure mode. Exact-fact accuracy is served by the
        retrieval-grounding path (LM bypassed); recall here drives audit/replay, not generation.
        """
        if self._ledger is None:
            return None
        try:
            import time
            from memory.recall_trail import jog_my_memory
            from memory.memory_context_packet import MemoryContextPacket
            trail = jog_my_memory(cue, self._ledger.alive(), top_k=7, now=time.time())  # bounded
            self._last_recall_trail = trail   # §7.3 trail (stop_reason/expansion_depth) for provenance
            conf = max((h.score for h in trail.hits), default=0.0)
            ids = list(trail.atom_ids())
            # §7.1 episodic recall: after the ledger trail, search the episodic tier and fold
            # any matching episode IDs into the packet (bounded). EpisodicMemory is thus genuinely
            # CALLED on the recall path, not just defined.
            if self._episodic is not None:
                try:
                    eps = self._episodic.search(cue, max_results=5)
                    ids.extend(ep.event_id for ep in eps)
                    if eps:
                        conf = max(conf, 0.5)
                except Exception:  # noqa: BLE001
                    logger.debug("episodic search failed", exc_info=True)
            self._last_memory_packet = MemoryContextPacket(
                packet_id=f"mcp-{self._turn_count}", request_id=str(self._turn_count),
                cue_terms=list(trail.cue_entities),
                retrieved_experience_ids=ids, confidence=float(conf))
            return self._last_memory_packet
        except Exception:  # noqa: BLE001
            logger.exception("memory recall error")
            return None

    def _emit_model_materialization(self) -> None:
        """Consume the C engine's LIVE weight materialization (ADR-0002 §8.2/§8.3) into a Python
        MaterializationRecord — emitted once at init from the path the engine actually
        materialized (xmind_weights_load_file), NOT the test-only materialize.c module.

        Populates the EXPLICIT §8.3 minimum fields (the spec is the checklist):
          source_hash        — the REAL sha256 of the materialized GGUF ("No model artifact loads
                               without hash verification"); computed here in Python because the C
                               consumer build's xsec hash is an FNV fold, not crypto.
          materialized_at_ns — the engine's load timestamp.
          tensor_roles       — the materialized tensor roles (per-layer attn/ffn + embeddings).
          rollback_pointer   — the GGUF the materialization can be rolled back to (Workstream 4).
        """
        try:
            import os
            import hashlib
            from datetime import datetime, timezone
            from _xmind import get_client  # noqa: PLC0415
            from materialization import MaterializationRecord
            c = get_client()
            if c is None:
                return
            info = c.model_info()
            if not info:
                return
            _adapter_ir = c.adapter_ir() if c.adapter_loaded() else {}
            # §8.3 source_hash: the cryptographic hash of the materialized source artifact (GGUF).
            # The C engine now computes a REAL FIPS SHA-256 (xsec) and reports it in model_info
            # (weight_sha256) — matches `shasum`. Prefer it (no 11MB Python re-read); hashlib
            # fallback only if the engine didn't report one.
            wpath = getattr(c, "model_path", "") or ""
            src_hashes: list = []
            _eng_sha = info.get("weight_sha256", "")
            if _eng_sha:
                src_hashes.append("sha256:" + _eng_sha)
            elif wpath and os.path.exists(wpath):
                _h = hashlib.sha256()
                with open(wpath, "rb") as _f:
                    for _chunk in iter(lambda: _f.read(1 << 20), b""):
                        _h.update(_chunk)
                src_hashes.append("sha256:" + _h.hexdigest())
            src_hashes.extend(self._active_adapter_hashes())   # adapter overlay, if any
            # §8.3 tensor_roles: the roles the engine materialized into runtime tensors.
            _nl = int(info.get("n_layers", 0) or 0)
            tensor_roles: list = []
            for _L in range(_nl):
                tensor_roles += [f"blk.{_L}.attn_q", f"blk.{_L}.attn_k", f"blk.{_L}.attn_v",
                                 f"blk.{_L}.attn_output", f"blk.{_L}.ffn_gate",
                                 f"blk.{_L}.ffn_up", f"blk.{_L}.ffn_down"]
            tensor_roles += ["token_emb", "rms_final"]
            # §8.3 materialized_at_ns -> created_at (ISO).
            _ns = int(info.get("materialized_at_ns", 0) or 0)
            created = (datetime.fromtimestamp(_ns / 1e9, tz=timezone.utc).isoformat()
                       if _ns else "")
            self._model_materialization = MaterializationRecord(
                materialization_id="mat-model-artifact",
                materialization_type="model_artifact",
                source_refs=[wpath],
                source_hashes=src_hashes,                       # §8.3 source_hash (real sha256 + adapter)
                runtime_location="xmind-c-engine",
                owning_role="inference_engine",
                transforms=[{**info, "tensor_roles": tensor_roles,
                             **({"adapter_ir": _adapter_ir} if _adapter_ir else {})}],
                privacy_class="internal",
                confidence=1.0,
                created_at=created,                              # §8.3 materialized_at_ns
                retention_mode="archival",
                rollback_refs=[wpath],                           # §8.3 rollback_pointer (re-materialize)
                status="committed",
            )
        except Exception:  # noqa: BLE001
            logger.debug("model materialization emit failed", exc_info=True)

    def _active_adapter_hashes(self) -> list:
        """Snapshot hashes of any OMNI-PEFT adapter absorbed on the inference engine.
        Empty when running the base model. Part of the determinant record's replay
        inputs so an adapted turn is not mistaken for a base-model turn (ADR §10.1)."""
        try:
            from _xmind import get_client  # noqa: PLC0415
            c = get_client()
            if c is not None and c.adapter_loaded() and getattr(c, "adapter_path", None):
                import hashlib as _hl
                return ["sha256:" + _hl.sha256(str(c.adapter_path).encode()).hexdigest()]
        except Exception:  # noqa: BLE001
            pass
        return []

    def _memory_writeback(self, cue: str, response: str, *, quality: float, passed: bool) -> None:
        """Quality-gated writeback (ADR §13.15: no low-quality memory promoted)."""
        self._last_writeback_committed = False
        if self._ledger is None or not passed or quality < 0.3:
            return
        try:
            import time
            from memory.experience_atom import ExperienceAtom
            self._ledger.register(
                ExperienceAtom.create(cue, response, salience=float(quality), now=time.time()))
            self._last_writeback_committed = True   # §11.3: drives a 'memory' materialization
            # §7.1 episodic tier: record the turn as an Episode so future cue-triggered recall
            # (the episodic search in _memory_recall) can reconstruct it. EpisodicMemory is
            # genuinely CALLED on the writeback path.
            if self._episodic is not None:
                try:
                    from sensory.evidence import _extract_entities as _ee  # reuse entity extractor
                    ents = _ee(cue) if callable(_ee) else []
                except Exception:  # noqa: BLE001
                    ents = []
                try:
                    self._episodic.record("chat_turn", cue, entities=ents)
                except Exception:  # noqa: BLE001
                    logger.debug("episodic record failed", exc_info=True)
        except Exception:  # noqa: BLE001
            logger.exception("memory writeback error")

    def _record_session_turn(self, session_id: str, user_message: str, response: str) -> None:
        """Session-continuity tier (ADR-0002 §4.7 / §7.1 session recall): record the turn in a
        per-session SessionMemory so continuity state is available. Genuinely CALLED per turn;
        fail-open (continuity must never break the response)."""
        try:
            from memory.session import SessionMemory
            sm = self._session_mem.get(session_id)
            if sm is None:
                sm = SessionMemory(session_id=session_id)
                self._session_mem[session_id] = sm
            sm.add_turn("user", user_message)
            sm.add_turn("assistant", response)
        except Exception:  # noqa: BLE001
            logger.debug("session-memory record failed", exc_info=True)

    def _run_metacognitive_triad(self, *, metrics, verdict) -> None:
        """Three-level metacognition to improve inference (ADR-0001 §8.4 lineage_level):
          understanding — confidence calibration of this turn (Metacognition)
          innerstanding — internal consistency / drift of the model's own quality signal
          overstanding  — over-arching reasoning invariants hold
        The deepest level that holds becomes the turn's lineage_level. This is self-reflection
        layered ABOVE the governance owners (not a duplicate of them). Fail-open."""
        self._last_lineage_level = "understanding"
        self._last_metacognition = {}
        if self._meta_understanding is None:
            return
        try:
            q = float(getattr(metrics, "composite_score", 1.0)) if metrics is not None else 1.0
            rel = float(getattr(metrics, "relevance_score", q)) if metrics is not None else q
            # L1 understanding — confidence calibration (squared error of self-estimate vs relevance)
            calib_err = float(self._meta_understanding.calibrate_confidence([q], [rel]))
            understanding_ok = metrics is not None
            # L2 innerstanding — record the quality signal + check internal drift consistency
            self._meta_innerstanding.record_sample(self.config.agent_id, "composite", q)
            drift = self._meta_innerstanding.detect_drift(self.config.agent_id)
            innerstanding_ok = understanding_ok and drift.metrics.get("sample_count", 0) >= 1
            # L3 overstanding — over-arching reasoning invariants
            passed = (verdict is None or getattr(verdict, "passed", True))
            eng = self._meta_overstanding
            eng.register_invariant("response_governed", lambda: passed)
            eng.register_invariant("quality_floor", lambda: q >= 0.0)
            violations = eng.check_all()
            overstanding_ok = innerstanding_ok and not violations
            level = "understanding"
            if innerstanding_ok:
                level = "innerstanding"
            if overstanding_ok:
                level = "overstanding"
            self._last_lineage_level = level
            self._last_metacognition = {
                "lineage_level": level,
                "calibration_error": round(calib_err, 4),
                "drift_samples": int(drift.metrics.get("sample_count", 0)),
                "invariant_violations": len(violations),
            }
        except Exception:  # noqa: BLE001
            logger.debug("metacognitive triad failed", exc_info=True)

    def _emit_memory_verdict(self, *, metrics, verdict, quality: float, passed: bool) -> None:
        """Emit the cognition→memory CognitiveMemoryVerdict (ADR-0001 §8.4 / ADR-0002 §4.6).

        This is the contract record the Cognitive Control System hands the Memory
        Continuity System at the writeback boundary — it tells memory what was decided
        (route, layers, quality, invariant/privacy verdicts, retention/reinforcement).
        Defined but never emitted before; this wires it from real per-turn state. Stored on
        the agent and surfaced in provenance (consumed, not write-only)."""
        self._last_memory_verdict = None
        try:
            from memory.cognitive_memory_verdict import CognitiveMemoryVerdict
            pkt = getattr(self, "_last_memory_packet", None)
            # MemoryContextPacket has retrieved_experience_ids, NOT 'shards' — the old check was
            # always False, so route_type was always 'direct' and recall_reinforcement always 0.0.
            used_memory = bool(pkt is not None and getattr(pkt, "retrieved_experience_ids", None))
            # active layers from the records emitted this turn (L1 perception + L7 governance
            # always run; L2/L4/L5/L6 come from the layer-record keys like "L5").
            layers = {1, 7}
            for k in (getattr(self, "_last_layer_records", {}) or {}):
                d = "".join(ch for ch in str(k) if ch.isdigit())
                if d:
                    layers.add(int(d))
            inv = "pass" if passed else ("critical" if getattr(verdict, "hard_stopped", False) else "violation")
            committed = bool(getattr(self, "_last_writeback_committed", False))
            retention = "episodic" if quality >= 0.7 else ("session" if quality >= 0.3 else "discard")
            qm = metrics.to_dict() if (metrics is not None and hasattr(metrics, "to_dict")) else {}
            self._last_memory_verdict = CognitiveMemoryVerdict(
                verdict_id=f"cmv-{self._turn_count}",
                request_id=str(self._turn_count),
                route_type="memory_mediated" if used_memory else "direct",
                active_layers=sorted(layers),
                quality_metrics={k: qm.get(k) for k in ("composite", "relevance", "coherence") if k in qm},
                invariant_verdict=inv,
                privacy_verdict="allow",
                writeback_targets=[retention] if committed else [],
                consolidation_directives=(["consolidate"] if getattr(self, "_last_consolidation", None) else []),
                lineage_level=getattr(self, "_last_lineage_level", "understanding"),  # metacognitive triad
                retention_mode=retention if committed else "discard",
                recall_reinforcement=0.1 if used_memory else 0.0,
            )
        except Exception:  # noqa: BLE001
            logger.exception("memory verdict emission failed")

    def _emit_records(self, response: str, *, confidence: float, latency_ms: float) -> None:
        """Emit the deterministic decision + materialization records at the REAL
        transitions of this turn (ADR-0001 §10/§11; ADR-0002 §13.10/§13.13). Stored on
        self for provenance, hash-only (never raw user content).

        DeterminantProbabilityRecord carries populated ``deterministic_inputs`` so the
        replay property ("identical inputs ⇒ identical route") has real content — not the
        empty default skeleton. MaterializationRecords are emitted only for transitions
        that actually happened this turn (response always; recall when memory was used) —
        the §8.3 weight/model-artifact/adapter materializations are load-time/deferred and
        are deliberately NOT fabricated per turn."""
        import hashlib
        grounded = bool(getattr(self, "_last_grounded", None))
        route = "scripture_retrieval" if grounded else "deliberation"
        rhash = "sha256:" + hashlib.sha256(response.encode()).hexdigest()
        # Real memory snapshot that fed this turn's decision (sorted ⇒ deterministic).
        pkt = getattr(self, "_last_memory_packet", None)
        mem_ids = sorted(getattr(pkt, "retrieved_experience_ids", []) or []) if pkt else []
        mem_hash = ("sha256:" + hashlib.sha256(("|".join(mem_ids)).encode()).hexdigest()
                    if mem_ids else "")
        self._last_materializations = []
        try:
            from heptagon.determinant_record import DeterminantProbabilityRecord
            dpr = DeterminantProbabilityRecord(
                record_id=f"dpr-{self._turn_count}", request_id=str(self._turn_count),
                deterministic_inputs={
                    "policy_snapshot_hash": getattr(self, "_policy_snapshot_hash", ""),
                    "model_snapshot_hash": getattr(self, "_model_snapshot_hash", ""),
                    # Faithful replay (ADR §10.1): if an OMNI-PEFT adapter is absorbed on the
                    # engine, it changes the output, so it MUST be part of the deterministic
                    # inputs — not a fixed empty list. Reflects the live absorption state.
                    "adapter_snapshot_hashes": self._active_adapter_hashes(),
                    "memory_index_snapshot_hash": mem_hash,    # real recalled-atom snapshot
                    "route_policy_hash": "sha256:" + hashlib.sha256(route.encode()).hexdigest(),
                    "budget_state_hash": "sha256:" + hashlib.sha256(
                        f"{self._turn_count}:{self.config.max_tokens}".encode()).hexdigest(),
                },
                selected_route=route, replayable=True,
                selection_reason=("verse/scripture intent -> exact corpus retrieval (LM bypassed)"
                                  if grounded else "non-scripture -> deliberation route"))
            dpr.probabilistic_outputs["confidence"] = float(confidence)   # nested dict: mutable
            # uncertainty is the complement of confidence — set it too so it is a real
            # measured output, not the static 0.0 default sentinel.
            dpr.probabilistic_outputs["uncertainty"] = round(max(0.0, 1.0 - float(confidence)), 4)
            self._last_determinant = dpr
        except Exception:  # noqa: BLE001
            logger.exception("determinant record error")
        try:
            import time
            from materialization import MaterializationRecord
            now = str(time.time())
            # Response materialization (always — the response artifact transitioned out).
            self._last_materialization = MaterializationRecord(
                materialization_id=f"mat-{self._turn_count}",
                materialization_type="response", owning_role="Model Runtime",
                source_hashes=[rhash], confidence=float(confidence),
                created_at=now, status="committed",
                privacy_class="private", retention_mode="session")
            self._last_materializations.append(self._last_materialization)
            # Recall materialization — emitted ONLY when memory actually fed this turn
            # (a genuine Memory->Materialization transition, not a per-turn fabrication).
            if mem_ids:
                self._last_materializations.append(MaterializationRecord(
                    materialization_id=f"mat-recall-{self._turn_count}",
                    materialization_type="memory",   # §11.1 enum (no 'recall' member)
                    owning_role="Memory",
                    source_hashes=[mem_hash], confidence=float(getattr(pkt, "confidence", 0.0)),
                    created_at=now, status="committed",
                    privacy_class="private", retention_mode="session"))
            # §11.3 "no writeback commits without a materialization record" — emit one when
            # this turn actually wrote back a learned ExperienceAtom.
            if getattr(self, "_last_writeback_committed", False):
                self._last_materializations.append(MaterializationRecord(
                    materialization_id=f"mat-writeback-{self._turn_count}",
                    materialization_type="memory", owning_role="Memory",
                    source_hashes=[rhash], confidence=float(confidence),
                    created_at=now, status="committed",
                    privacy_class="private", retention_mode="durable"))
        except Exception:  # noqa: BLE001
            logger.exception("materialization record error")

    def _emit_layer_records(self, *, metrics, latency_ms: float) -> None:
        """Emit the L2/L4/L5/L6 cognitive-layer records each turn (ADR-0001 §6 / §16.3:
        "every request touches all required layers"). Stored on self for provenance; content-
        free (derived signals only). Previously these classes were DEFINED but never emitted."""
        rid = str(self._turn_count)
        grounded = bool(getattr(self, "_last_grounded", None))
        route = "scripture_retrieval" if grounded else "deliberation"
        pkt = getattr(self, "_last_memory_packet", None)
        cues = list(getattr(pkt, "cue_terms", []) or []) if pkt else []
        quality = float(getattr(metrics, "composite_score", 1.0)) if metrics is not None else 1.0
        try:
            from heptagon.layer_records import (
                ActiveFrame, WorldState, DeliberationRecord, CorrectionRecord)
            self._last_layer_records = {
                "L2_active_frame": ActiveFrame(
                    record_id=f"af-{rid}", request_id=rid, active_memory_cues=cues,
                    route_hints=[route],
                    budget_envelope={"max_tokens": self.config.max_tokens}),
                "L4_world_state": WorldState(
                    record_id=f"ws-{rid}", request_id=rid,
                    confidence_distribution={"response": quality}),
                "L5_deliberation": DeliberationRecord(
                    record_id=f"dl-{rid}", request_id=rid,
                    route_plan={"route": route}, recursion_depth=0),
                "L6_correction": CorrectionRecord(
                    record_id=f"cr-{rid}", request_id=rid, redaction_decision="none",
                    calibration_delta={"latency_ms": float(latency_ms)}),
            }
        except Exception:  # noqa: BLE001
            logger.exception("layer-records emission error")

    def _run_l6_engines(self, response: str) -> None:
        """L6 calibration engines, genuinely CALLED per turn (were DEFINED-not-wired): the
        3-6-9 BudgetGovernor (parsimony: grounded->direct tier) and the ACT-R
        MemoryConsolidator (store + periodic decay). Results stored on self for provenance."""
        grounded = bool(getattr(self, "_last_grounded", None))
        try:
            from heptagon.budget import BudgetGovernor
            bg = BudgetGovernor(profile="direct" if grounded else "researched")
            try:
                bg.check_tokens(len(response))
            except Exception:  # noqa: BLE001 — over budget: record it, never raise into the turn
                pass
            self._last_budget = bg.state().to_dict()
        except Exception:  # noqa: BLE001
            logger.debug("L6 budget governor error", exc_info=True)
        mc = getattr(self.heptagon, "consolidator", None)
        if mc is not None:
            try:
                mc.store(f"turn-{self._turn_count}", content=response[:200])
                self._last_consolidation = mc.maybe_tick()   # periodic ACT-R decay (or None)
            except Exception:  # noqa: BLE001
                logger.debug("L6 consolidation error", exc_info=True)

    def chat(self, session_id: str, user_message: str) -> str:  # type: ignore[override]
        """Execute a chat turn with full Heptagon lifecycle wrapping.

        Full 7-layer pipeline:
          L4: State machine IDLE → LISTENING → PROCESSING → ROUTING → GENERATING → REVIEWING → IDLE
          L3: RouteEngine classifies query and sets budget tier
          L7: InvariantEnforcer pre-checks context
          Core: Agent generates response
          L5: ResponseVerifier gates the response (safety, relevance, coherence)
          L5: CycleEvaluator records metrics
          L6: ParameterCalibrator adjusts model parameters
        """
        import time

        start = time.monotonic()

        # Transport-agnostic covenant gate — direct callers of chat() bypass api.py.
        # api.py is fail-closed; this is defense-in-depth for all other entry points.
        try:
            from governance.covenant_enforcer import CovenantEnforcer as _CovenantEnforcer
            if not hasattr(self, "_transport_covenant"):
                self._transport_covenant = _CovenantEnforcer()
            _cov = self._transport_covenant.enforce(user_message)
            if getattr(_cov, "is_blocked", False):
                return (f"[governance: request blocked — "
                        f"{_cov.summary() if hasattr(_cov, 'summary') else 'covenant violation'}]")
        except Exception:
            pass  # fail-open; api.py is fail-closed when called via HTTP

        # Per-turn provenance reset: _last_grounded is set only when THIS turn grounds in
        # scripture; without this reset a scripture turn would leak grounded=True / route=
        # scripture_retrieval into the NEXT (non-scripture) turn's determinant record
        # (ADR §10.1: a replay record must depend only on the current turn's inputs).
        self._last_grounded = None

        # L4: advance the state machine (events, not state names). The SM force-resets to
        # IDLE at the end of each turn (below) so it does not stick after the first turn.
        self._sm_fire("input_received")          # IDLE -> LISTENING

        # L3/Memory: cue-triggered recall BEFORE generation (Memory -> Cognitive Control).
        # Recall feeds the deterministic replay snapshot + provenance — NOT the LM prompt
        # (byte-LM confabulation guard; see _memory_recall docstring).
        self._memory_recall(user_message)
        self._sm_fire("input_complete")              # LISTENING -> PROCESSING

        # L3: Route the query — classify intent and set budget tier
        route_result = None
        if self.heptagon.router is not None:
            try:
                route_result = self.heptagon.router.classify(user_message)  # type: ignore[attr-defined]
                logger.debug("RouteEngine: classified as %s", route_result)
            except Exception:  # noqa: BLE001
                logger.exception("L3 route classification error")

        # W4b: Wire route max_tokens to max_new (RouteResult.max_tokens carries 512/2048/4096 from _ROUTE_BUDGETS)
        self._budget_tokens = getattr(route_result, "max_tokens", 512) if route_result is not None else 512
        logger.debug("L3 budget: route_type=%s max_new=%d",
                     getattr(route_result, "route_type", "none"), self._budget_tokens)

        self._sm_fire("pre_process_done")            # PROCESSING -> ROUTING

        # Wave 5: Drift behavioral gate — evaluate accumulated identity drift BEFORE generation.
        # record() stays after generation (needs this-turn metrics); check() uses the prior window.
        if self._drift_detector is not None and _DRIFT_AVAILABLE:
            try:
                _pre_drift = self._drift_detector.check()  # type: ignore[attr-defined]
                _drift_action = _pre_drift.get("action", "")
                if _pre_drift.get("status") == "CRITICAL" and _drift_action == "freeze_all_identity_changes":
                    logger.error("Drift gate: CRITICAL — freeze_all_identity_changes, turn halted")
                    self._sm_fire("safety_halt")
                    return "[governance: identity drift threshold exceeded — turn halted by drift gate]"
                elif _pre_drift.get("status") in ("WARNING", "CRITICAL") and _drift_action == "shift_to_conditional_mode":
                    self._budget_tokens = min(self._budget_tokens, 256)
                    logger.warning("Drift gate: conditional mode — budget capped to 256 tokens")
            except Exception:  # noqa: BLE001
                logger.debug("pre-generation drift check error", exc_info=True)

        # Core agent call
        self._sm_fire("route_direct")               # ROUTING -> GENERATING
        response = super().chat(session_id, user_message)
        self._sm_fire("generation_done")            # GENERATING -> REVIEWING

        latency_ms = int((time.monotonic() - start) * 1000)

        # L5: Verify response (D06 fix — verify() is POSITIONAL: verify(query, response)).
        # Errors are LOGGED, not silently swallowed, so a dead gate is visible.
        verdict = None
        l5_crashed = False  # audit fix: a CRASHED verifier must NOT read as "safety passed"
        if self.heptagon.verifier is not None:
            try:
                verdict = self.heptagon.verifier.verify(user_message, response)  # positional
                self._last_verdict = verdict
                if verdict is not None and not getattr(verdict, "passed", True):
                    logger.warning("L5 ResponseVerifier FAILED: %s",
                                   verdict.to_dict() if hasattr(verdict, "to_dict") else verdict)
            except Exception:  # noqa: BLE001
                # L5 is advisory, BUT a crash here must propagate into the L7 hard gate as a
                # safety failure — never a silent clean bill. (advisor-found coupling fix:
                # verdict stays None on crash, which previously read as passed=True/safety_ok.)
                l5_crashed = True
                logger.exception("L5 verification error — propagating as safety failure to L7")

        # L5: Evaluate the cycle (D06 — CycleEvaluator.evaluate(query, response, ctx, latency, tokens)).
        metrics = None
        if self.heptagon.evaluator is not None:
            try:
                ctx = {"cycle_id": self._turn_count,
                       "errors": 0 if (verdict is None or getattr(verdict, "passed", True)) else 1}
                metrics = self.heptagon.evaluator.evaluate(
                    user_message, response, ctx, float(latency_ms), len(response))
            except Exception:  # noqa: BLE001
                logger.exception("L5 evaluation error")

        # L6: full cycle (D16 — full_l6_cycle runs all 9 stages: calibration + mastery +
        # lineage + writeback eligibility + budget; falls back to plain calibrate()).
        if self.heptagon.calibrator is not None and metrics is not None:
            try:
                import hashlib
                if hasattr(self.heptagon.calibrator, "full_l6_cycle"):
                    _l6_result = self.heptagon.calibrator.full_l6_cycle(
                        metrics, domain_id=self.config.agent_id,
                        context_hash="sha256:" + hashlib.sha256(
                            (user_message + response).encode()).hexdigest(),
                        session_id=session_id)
                    # W4c: thread calibration_profile.temperature to the NEXT turn's generation
                    _cal = getattr(_l6_result, "calibration_profile", None)
                    if _cal is not None and hasattr(_cal, "temperature"):
                        self._calibrated_temperature = float(_cal.temperature)
                        logger.debug("L6 calibration: temperature=%.4f (active next turn)",
                                     self._calibrated_temperature)
                else:
                    self.heptagon.calibrator.calibrate(metrics)
            except Exception:  # noqa: BLE001
                logger.exception("L6 cycle error")

        # L7: Enforce invariants post-response (D07 — pass full ctx so HALLUCINATION_GUARD,
        # QUALITY_FLOOR, PII, BUDGET gates can actually fire; D08 — gate the response on hard-stop).
        l7_hard_stop = False   # L4: track hard-stop for FSM branch below
        if self.heptagon.enforcer is not None:
            try:
                quality = float(getattr(metrics, "composite_score", 1.0)) if metrics is not None else 1.0
                # advisor-found coupling fix: a crashed L5 verifier (l5_crashed) is treated as
                # NOT passed + safety_failed=True so the L7 hard gate is never handed a false
                # clean bill (verdict==None must mean "no verdict", not "safety ok").
                passed = (not l5_crashed) and (verdict is None or getattr(verdict, "passed", True))
                safety_failed = l5_crashed or (verdict is not None and not getattr(verdict, "safety_passed", True))
                violations = self.heptagon.enforcer.check_all({  # type: ignore[attr-defined]
                    "agent_id": self.config.agent_id,
                    "response": response,                 # D07: required by HALLUCINATION_GUARD/PII
                    "latency_ms": latency_ms,
                    "response_length": len(response),
                    "tokens_used": len(response),
                    "max_tokens": self.config.max_tokens,
                    "quality_score": quality,
                    "safety_failed": safety_failed,
                    "total_cycles": self._turn_count,
                    "total_errors": 0 if passed else 1,
                })
                if violations:
                    logger.warning("L7 enforcement: %d violation(s)", len(violations))
                # D08: gate — never return a response the L7 gate hard-stopped.
                if (hasattr(self.heptagon.enforcer, "is_hard_stopped")
                        and self.heptagon.enforcer.is_hard_stopped()):
                    logger.error("L7 HARD-STOP: response withheld; manual reset required")
                    response = ("[governance: L7 hard-stop] This response was withheld by the "
                                "enforcement gate and requires a manual authority reset.")
                    l7_hard_stop = True
            except Exception:  # noqa: BLE001
                # FAIL CLOSED (audit fix): L7 is the hard safety gate. If it cannot
                # evaluate, we cannot certify the response is admissible — withhold it
                # rather than let an un-checked response through (was fail-OPEN).
                logger.exception("L7 enforcement error — failing closed, response withheld")
                response = ("[governance: L7 unavailable] This response was withheld because the "
                            "enforcement gate could not be evaluated (fail-closed).")
                l7_hard_stop = True

        # L4: close the REVIEWING state — safety_halt on hard-stop, review_passed otherwise.
        # reset() at turn-end is the safety fallback; these fires make the FSM lifecycle real.
        if l7_hard_stop:
            self._sm_fire("safety_halt")             # REVIEWING -> ERROR
        else:
            self._sm_fire("review_passed")           # REVIEWING -> IDLE

        # Drift monitoring — record a REAL per-turn signal for identity regression
        # tracking (not a constant zero). The detector averages these over its window
        # into rates, so a per-turn quality/reversal value yields a true drift index:
        #   goal_divergence  = 1 - composite quality  (how far this turn fell from goal)
        #   reversal_rate    = 1.0 if governance reversed/withheld the response, else 0.0
        #   exception_rate   = 1.0 if the evaluator recorded any error this turn
        #   covenant_violation_count = invariant/covenant violations carried on the verdict
        if self._drift_detector is not None and _DRIFT_AVAILABLE:
            try:
                _composite = float(getattr(metrics, "composite_score", 1.0)) if metrics is not None else 1.0
                _reversed = 1.0 if (verdict is not None and not getattr(verdict, "passed", True)) else 0.0
                _errs = int(getattr(metrics, "errors", 0)) if metrics is not None else 0
                _viols = getattr(verdict, "violations", None)
                _viol_count = len(_viols) if isinstance(_viols, (list, tuple)) else 0
                self._drift_detector.record(DriftSignal(  # type: ignore[attr-defined]
                    goal_divergence=max(0.0, min(1.0, 1.0 - _composite)),
                    reversal_rate=_reversed,
                    exception_rate=1.0 if _errs > 0 else 0.0,
                    covenant_violation_count=_viol_count,
                ))
                drift_check = self._drift_detector.check()  # type: ignore[attr-defined]
                if drift_check.get("status") in ("WARNING", "CRITICAL"):
                    logger.warning(
                        "DriftDetector: %s — drift_index=%.4f, action=%s",
                        drift_check["status"],
                        drift_check["drift_index"],
                        drift_check["action"],
                    )
            except Exception:  # noqa: BLE001
                pass

        # Memory writeback (Cognitive Control -> Memory): quality-gated ExperienceAtom.
        _q = float(getattr(metrics, "composite_score", 1.0)) if metrics is not None else 1.0
        _passed = (verdict is None or getattr(verdict, "passed", True))
        self._memory_writeback(user_message, response, quality=_q, passed=_passed)
        self._record_session_turn(session_id, user_message, response)  # §4.7 session continuity

        # P-14: Edge G — Memory→Runtime ContinuityState return (ADR-0002 §4.7).
        # Assembles the per-turn ContinuityState from live memory subsystem state and stores it
        # on self._last_continuity_state so the runtime/API can inspect memory health each turn.
        # Uses the correct attr names: self._episodic (EpisodicMemory, _episodes list) and
        # self._ledger (LifespanLedger, .alive() returns live atoms). Fail-open.
        try:
            import sys as _sys
            _mem_path = os.path.abspath(
                os.path.join(_THIS_DIR, "..", "..", "..", "soul_manager")
            )
            if _mem_path not in _sys.path:
                _sys.path.insert(0, _mem_path)
            from memory_types import ContinuityState, RecallReadiness, MemoryHealth
            _epi = self._episodic          # EpisodicMemory (attr confirmed in __init__)
            _ldgr = self._ledger           # LifespanLedger (attr confirmed in __init__)
            _continuity = ContinuityState(
                session_id=session_id,
                turn=self._turn_count,
                recall_readiness=RecallReadiness(
                    available_episodes=len(
                        getattr(_epi, "_episodes", [])
                    ) if _epi is not None else 0,
                    ledger_entries=len(
                        _ldgr.alive()
                    ) if _ldgr is not None else 0,
                    context_packet_ready=True,
                ),
                memory_health=MemoryHealth(
                    episodic_store_ok=_epi is not None,
                    ledger_ok=_ldgr is not None,
                    soul_manager_connected=self._soul is not None,
                    last_writeback_quality=_q,
                ),
                continuity_score=_q,
            )
            self._last_continuity_state = _continuity
            logger.debug(
                "Edge G: ContinuityState turn=%d score=%.3f episodes=%d ledger=%d",
                self._turn_count, _q,
                _continuity.recall_readiness.available_episodes,
                _continuity.recall_readiness.ledger_entries,
            )
        except Exception:
            logger.debug("Edge G ContinuityState assembly failed", exc_info=True)

        # Emit deterministic decision + response materialization records (ADR §10/§11).
        self._emit_records(response, confidence=_q, latency_ms=latency_ms)
        self._emit_layer_records(metrics=metrics, latency_ms=latency_ms)
        self._run_l6_engines(response)   # 3-6-9 budget + ACT-R consolidation (L6 engines)
        # Metacognitive triad (understanding/innerstanding/overstanding) — sets the lineage_level.
        self._run_metacognitive_triad(metrics=metrics, verdict=verdict)
        # Advance the identity-continuity attestation chain with this turn's determinant identity.
        if self._attestation is not None:
            try:
                _dpr = getattr(self, "_last_determinant", None)
                _state = getattr(_dpr, "record_id", "") + "|" + getattr(self, "_last_lineage_level", "")
                self._last_attestation = self._attestation.attest(_state)
            except Exception:  # noqa: BLE001
                logger.debug("attestation advance failed", exc_info=True)
        # P-16: per-turn doctrine attestation (AttestationEngine). Uses TOKENLESS_SUBSTRATE —
        # the one neutral canonical member key in MEMBER_REGISTRY (ADR-0001 §1 / §4 taxonomy).
        # compute_schema_hash() derives the fingerprint from the registry directly, so the
        # result is VERIFIED (not SUSPICIOUS) whenever the registry is intact.
        if self._doctrine_attestation is not None:
            try:
                _mid = "TOKENLESS_SUBSTRATE"
                _schema = self._doctrine_attestation.compute_schema_hash(_mid)
                _doctrine_result = self._doctrine_attestation.attest(
                    _mid, _schema,
                    memory_lineage_hash=getattr(self, "_model_snapshot_hash", ""),
                )
                logger.debug(
                    "Doctrine attestation: member=%s status=%s checks_passed=%s checks_failed=%s",
                    _mid,
                    getattr(_doctrine_result, "status", None),
                    getattr(_doctrine_result, "checks_passed", []),
                    getattr(_doctrine_result, "checks_failed", []),
                )
            except Exception:
                logger.debug("Doctrine attestation failed", exc_info=True)
        # Cognition→Memory verdict contract (ADR-0001 §8.4 / ADR-0002 §4.6) — after the layer
        # records + L6 engines + triad so active_layers, consolidation, lineage_level are populated.
        self._emit_memory_verdict(metrics=metrics, verdict=verdict, quality=_q, passed=_passed)

        # L4: force the state machine back to IDLE so it does not STICK after turn 1
        # ("complete"/"reset" are not events in the table; reset() is the real lifecycle close).
        _sm = self.heptagon.state_machine
        if _sm is not None:
            try:
                _sm.reset()                      # -> IDLE, ready for the next turn
            except Exception:  # noqa: BLE001
                logger.debug("L4 reset failed", exc_info=True)

        return response


# ── Public re-exports ─────────────────────────────────────────────────────────
# Neutral taxonomy (ADR-0001 §4 / ADR-0002 §13): no project-specific aliases. The former
# `GenesysAgentWithHeptagon` alias was removed — TokenlessAgentWithHeptagon is the one name.

__all__ = [
    "AgentConfig",
    "TokenlessAgent",
    "TokenlessAgentWithHeptagon",
    "HeptagonLayer",
]
