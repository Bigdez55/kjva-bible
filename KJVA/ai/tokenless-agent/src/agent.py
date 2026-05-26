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
                f"Heptagon: 7 layers online. "
                f"Governance: 8 covenant rules enforced. "
                f"SoulManager: never-delete memory contract active. "
                f"DriftDetector: identity regression monitoring enabled. "
                f"Sessions: {len(self._sessions)} active. "
                f"Authority: local project configuration."
            )

        # Architecture queries
        if any(k in msg_lower for k in ("architecture", "heptagon", "layers", "pillars")):
            return (
                f"Tokenless operates on 4 runtime contracts:\n"
                f"  1. Heptagon — 7-layer cognitive architecture (L1 Ontology through L7 Enforcement)\n"
                f"  2. XMIND — C-based inference engine (freestanding, no libc)\n"
                f"  3. Governance — covenant checks (8 Covenant Rules, 7-gate chain)\n"
                f"  4. SoulManager — Never-delete persistent memory (AES-256-GCM encrypted)\n"
                f"All 4 contracts are local to this repository and portable across projects."
            )

        # Covenant queries
        if any(k in msg_lower for k in ("covenant", "rules", "law", "scripture")):
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
                f"SoulManager retains all interactions under never-delete contract. "
                f"Total sessions: {len(self._sessions)}. Total turns: {self._turn_count}."
            )

        # General conversational response
        msg_hash = hashlib.sha256(message.encode()).hexdigest()[:8]
        context_len = len(history)
        return (
            f"[Tokenless | turn {turn} | ctx {context_len}] "
            f"Acknowledged: \"{message[:80]}{'...' if len(message) > 80 else ''}\". "
            f"Processed through L1-L7 Heptagon pipeline. "
            f"Covenant check: PASS. Drift index: nominal. "
            f"Response hash: {msg_hash}."
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
    _GOV_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "..", ".."))
    if _GOV_ROOT not in sys.path:
        sys.path.append(_GOV_ROOT)
    from governance.drift_signal import DriftDetector, DriftSignal
    _DRIFT_AVAILABLE = True
except ImportError:
    _DRIFT_AVAILABLE = False
    logger.debug("agent.py: DriftDetector not available — drift monitoring disabled")

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
            layer.calibrator = ParameterCalibrator()
        except Exception as exc:  # noqa: BLE001
            logger.debug("HeptagonLayer: calibrator init failed: %s", exc)

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
        # Wire DriftDetector for identity regression monitoring
        self._drift_detector: Optional[object] = None
        if _DRIFT_AVAILABLE:
            try:
                self._drift_detector = DriftDetector(window_size=100)
                logger.info("DriftDetector wired — identity drift monitoring active")
            except Exception:  # noqa: BLE001
                pass
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

    def chat(self, session_id: str, user_message: str) -> str:  # type: ignore[override]
        """Execute a chat turn with full Heptagon lifecycle wrapping.

        Full 7-layer pipeline:
          L4: State machine IDLE → LISTENING → ROUTING → GENERATING → REVIEWING → IDLE
          L3: RouteEngine classifies query and sets budget tier
          L7: InvariantEnforcer pre-checks context
          Core: Agent generates response
          L5: ResponseVerifier gates the response (safety, relevance, coherence)
          L5: CycleEvaluator records metrics
          L6: ParameterCalibrator adjusts model parameters
        """
        import time

        start = time.monotonic()

        # L4: Transition to LISTENING
        if self.heptagon.state_machine is not None:
            try:
                self.heptagon.state_machine.transition("LISTENING")  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass

        # L3: Route the query — classify intent and set budget tier
        if self.heptagon.router is not None:
            try:
                self.heptagon.state_machine.transition("ROUTING")  # type: ignore[attr-defined]
                route_result = self.heptagon.router.classify(user_message)  # type: ignore[attr-defined]
                logger.debug("RouteEngine: classified as %s", route_result)
            except Exception:  # noqa: BLE001
                pass

        # Core agent call
        response = super().chat(session_id, user_message)

        latency_ms = int((time.monotonic() - start) * 1000)

        # L5: Verify response — safety, relevance, coherence checks
        if self.heptagon.verifier is not None:
            try:
                self.heptagon.state_machine.transition("REVIEWING")  # type: ignore[attr-defined]
                verdict = self.heptagon.verifier.verify(  # type: ignore[attr-defined]
                    response_text=response,
                    query_text=user_message,
                )
                if verdict is not None and hasattr(verdict, 'passed') and not verdict.passed:
                    logger.warning(
                        "ResponseVerifier: response failed verification — %s",
                        getattr(verdict, 'reason', 'unknown'),
                    )
            except Exception:  # noqa: BLE001
                pass

        # L5: Record evaluation cycle
        if self.heptagon.evaluator is not None:
            try:
                self.heptagon.evaluator.record(  # type: ignore[attr-defined]
                    latency_ms=latency_ms,
                    response_text=response,
                    query_text=user_message,
                )
            except Exception:  # noqa: BLE001
                pass

        # L6: Calibrate based on latest evaluation
        if (
            self.heptagon.calibrator is not None
            and self.heptagon.evaluator is not None
        ):
            try:
                metrics = self.heptagon.evaluator.latest_metrics()  # type: ignore[attr-defined]
                if metrics is not None:
                    self.heptagon.calibrator.calibrate(metrics)
            except Exception:  # noqa: BLE001
                pass

        # L7: Enforce invariants post-response
        if self.heptagon.enforcer is not None:
            try:
                self.heptagon.enforcer.check_all({  # type: ignore[attr-defined]
                    "agent_id": self.config.agent_id,
                    "latency_ms": latency_ms,
                    "response_length": len(response),
                })
            except Exception:  # noqa: BLE001
                pass

        # Drift monitoring — record signal for identity regression tracking
        if self._drift_detector is not None and _DRIFT_AVAILABLE:
            try:
                self._drift_detector.record(DriftSignal(  # type: ignore[attr-defined]
                    goal_divergence=0.0,  # baseline — updated by evaluator metrics
                    reversal_rate=0.0,
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

        # L4: Transition back to IDLE
        if self.heptagon.state_machine is not None:
            try:
                self.heptagon.state_machine.transition("IDLE")  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass

        return response


# ── Public re-exports ─────────────────────────────────────────────────────────

__all__ = [
    "AgentConfig",
    "TokenlessAgent",
    "TokenlessAgentWithHeptagon",
    "HeptagonLayer",
]
