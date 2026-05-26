"""ai/tokenless-agent/src/heptagon/state_machine.py
AgentStateMachine - 12-state FSM governing the lifecycle of a Tokenless AI agent.
Includes on_enter callbacks and a fixed-size history ring buffer.
"""
from __future__ import annotations

import collections
import logging
import time
from enum import Enum, auto
from typing import Any, Callable, Deque, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("tokenless.heptagon.state_machine")

# ── AgentState ────────────────────────────────────────────────────────────────

class AgentState(Enum):
    """12-state lifecycle for a Tokenless AI agent."""
    IDLE            = auto()   # Waiting for input
    LISTENING       = auto()   # Receiving user input
    PROCESSING      = auto()   # Tokenising / pre-processing
    ROUTING         = auto()   # RouteEngine classifying query
    EXECUTING       = auto()   # Running tool calls / actions
    GENERATING      = auto()   # XMIND token generation in progress
    REVIEWING       = auto()   # ResponseVerifier checking output
    DELEGATING      = auto()   # Handing task to sub-agent
    WAITING_HUMAN   = auto()   # Paused for human approval (ESCALATED)
    ERROR           = auto()   # Recoverable error state
    RECOVERING      = auto()   # Attempting recovery from ERROR
    SHUTDOWN        = auto()   # Terminal — agent is offline


# ── Transition table ──────────────────────────────────────────────────────────
# Maps (from_state) -> set of valid event strings -> to_state
# Format: {AgentState: {event_name: AgentState}}

_TRANSITIONS: Dict[AgentState, Dict[str, AgentState]] = {
    AgentState.IDLE: {
        "input_received":    AgentState.LISTENING,
        "shutdown":          AgentState.SHUTDOWN,
    },
    AgentState.LISTENING: {
        "input_complete":    AgentState.PROCESSING,
        "cancel":            AgentState.IDLE,
        "error":             AgentState.ERROR,
        "shutdown":          AgentState.SHUTDOWN,
    },
    AgentState.PROCESSING: {
        "pre_process_done":  AgentState.ROUTING,
        "error":             AgentState.ERROR,
        "shutdown":          AgentState.SHUTDOWN,
    },
    AgentState.ROUTING: {
        "route_direct":      AgentState.GENERATING,
        "route_execute":     AgentState.EXECUTING,
        "route_delegate":    AgentState.DELEGATING,
        "route_escalate":    AgentState.WAITING_HUMAN,
        "error":             AgentState.ERROR,
        "shutdown":          AgentState.SHUTDOWN,
    },
    AgentState.EXECUTING: {
        "execution_done":    AgentState.GENERATING,
        "delegate":          AgentState.DELEGATING,
        "error":             AgentState.ERROR,
        "shutdown":          AgentState.SHUTDOWN,
    },
    AgentState.GENERATING: {
        "generation_done":   AgentState.REVIEWING,
        "budget_exceeded":   AgentState.ERROR,
        "error":             AgentState.ERROR,
        "shutdown":          AgentState.SHUTDOWN,
    },
    AgentState.REVIEWING: {
        "review_passed":     AgentState.IDLE,
        "review_failed":     AgentState.GENERATING,   # regenerate
        "safety_halt":       AgentState.ERROR,
        "error":             AgentState.ERROR,
        "shutdown":          AgentState.SHUTDOWN,
    },
    AgentState.DELEGATING: {
        "delegation_done":   AgentState.REVIEWING,
        "error":             AgentState.ERROR,
        "shutdown":          AgentState.SHUTDOWN,
    },
    AgentState.WAITING_HUMAN: {
        "human_approved":    AgentState.EXECUTING,
        "human_rejected":    AgentState.IDLE,
        "timeout":           AgentState.ERROR,
        "shutdown":          AgentState.SHUTDOWN,
    },
    AgentState.ERROR: {
        "recover":           AgentState.RECOVERING,
        "abort":             AgentState.IDLE,
        "shutdown":          AgentState.SHUTDOWN,
    },
    AgentState.RECOVERING: {
        "recovery_success":  AgentState.IDLE,
        "recovery_failed":   AgentState.SHUTDOWN,
        "shutdown":          AgentState.SHUTDOWN,
    },
    AgentState.SHUTDOWN: {
        # Terminal — no transitions out
    },
}

# ── History entry ─────────────────────────────────────────────────────────────

class _HistoryEntry:
    __slots__ = ("from_state", "event", "to_state", "timestamp")

    def __init__(
        self,
        from_state: AgentState,
        event: str,
        to_state: AgentState,
    ) -> None:
        self.from_state = from_state
        self.event = event
        self.to_state = to_state
        self.timestamp = time.monotonic()

    def __repr__(self) -> str:
        return (
            f"[{self.from_state.name}]--{self.event}-->[{self.to_state.name}]"
            f" @{self.timestamp:.3f}"
        )


# ── AgentStateMachine ─────────────────────────────────────────────────────────

_HISTORY_CAPACITY: int = 128   # ring buffer size

class AgentStateMachine:
    """
    Deterministic FSM for one Tokenless AI agent instance.

    Usage
    -----
        sm = AgentStateMachine(agent_id="agent-01")
        sm.transition("input_received")    # IDLE -> LISTENING
        sm.transition("input_complete")    # LISTENING -> PROCESSING
        ...

    on_enter callbacks are invoked immediately after each successful transition.
    Multiple callbacks can be registered per state.
    """

    def __init__(self, agent_id: str = "default") -> None:
        self._agent_id = agent_id
        self._state = AgentState.IDLE
        self._history: Deque[_HistoryEntry] = collections.deque(maxlen=_HISTORY_CAPACITY)
        self._on_enter: Dict[AgentState, List[Callable[[AgentState, str], None]]] = {}
        logger.debug("AgentStateMachine[%s]: initialised in IDLE", agent_id)

    # ── Core transition ───────────────────────────────────────────────────────

    def transition(self, event: str, context: Any = None) -> AgentState:
        """
        Attempt a state transition triggered by event.

        Parameters
        ----------
        event   : event name string (e.g. "input_received")
        context : optional payload passed to on_enter callbacks

        Returns
        -------
        The new AgentState after the transition.

        Raises
        ------
        ValueError if the event is not valid from the current state.
        RuntimeError if the machine is already SHUTDOWN.
        """
        if self._state == AgentState.SHUTDOWN:
            raise RuntimeError(
                f"AgentStateMachine[{self._agent_id}]: cannot transition from SHUTDOWN"
            )
        valid = _TRANSITIONS.get(self._state, {})
        if event not in valid:
            allowed = list(valid.keys())
            raise ValueError(
                f"AgentStateMachine[{self._agent_id}]: "
                f"event '{event}' is not valid from state {self._state.name}. "
                f"Allowed: {allowed}"
            )
        from_state = self._state
        to_state = valid[event]
        self._history.append(_HistoryEntry(from_state, event, to_state))
        self._state = to_state
        logger.debug(
            "AgentStateMachine[%s]: %s --%s--> %s",
            self._agent_id, from_state.name, event, to_state.name,
        )
        self._fire_on_enter(to_state, event)
        return to_state

    # ── Query ─────────────────────────────────────────────────────────────────

    def current_state(self) -> AgentState:
        """Return the current state."""
        return self._state

    def allowed_events(self) -> List[str]:
        """Return all valid events from the current state."""
        return list(_TRANSITIONS.get(self._state, {}).keys())

    def can_transition(self, event: str) -> bool:
        """Return True if event is valid from current state."""
        return event in _TRANSITIONS.get(self._state, {})

    def is_terminal(self) -> bool:
        """Return True if the FSM has reached SHUTDOWN."""
        return self._state == AgentState.SHUTDOWN

    def is_idle(self) -> bool:
        return self._state == AgentState.IDLE

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def on_enter(
        self,
        state: AgentState,
        callback: Callable[[AgentState, str], None],
    ) -> None:
        """
        Register a callback to fire when the FSM enters `state`.
        Callback signature: callback(new_state, triggering_event) -> None.
        Multiple callbacks per state are supported.
        """
        if state not in self._on_enter:
            self._on_enter[state] = []
        self._on_enter[state].append(callback)

    def _fire_on_enter(self, state: AgentState, event: str) -> None:
        for cb in self._on_enter.get(state, []):
            try:
                cb(state, event)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "AgentStateMachine[%s]: on_enter callback for %s raised: %s",
                    self._agent_id, state.name, exc,
                )

    # ── History ───────────────────────────────────────────────────────────────

    def history(self) -> List[_HistoryEntry]:
        """Return history as a list (oldest first)."""
        return list(self._history)

    def last_transition(self) -> Optional[_HistoryEntry]:
        """Return the most recent history entry or None."""
        return self._history[-1] if self._history else None

    def history_summary(self) -> List[str]:
        """Return compact string representations of recent transitions."""
        return [repr(h) for h in self._history]

    # ── Reset ─────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """
        Force-reset to IDLE state without validation.
        Use only for testing or explicit recovery scenarios.
        Clears history and callbacks.
        """
        logger.warning(
            "AgentStateMachine[%s]: force-reset from %s to IDLE",
            self._agent_id, self._state.name,
        )
        self._state = AgentState.IDLE
        self._history.clear()
        self._on_enter.clear()

    # ── Representation ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"AgentStateMachine(agent_id={self._agent_id!r}, "
            f"state={self._state.name}, "
            f"history_len={len(self._history)})"
        )

    @staticmethod
    def all_states() -> List[AgentState]:
        return list(AgentState)

    @staticmethod
    def transition_table() -> Dict[str, Dict[str, str]]:
        """Return the full transition table as a serialisable dict."""
        return {
            src.name: {evt: dst.name for evt, dst in events.items()}
            for src, events in _TRANSITIONS.items()
        }
