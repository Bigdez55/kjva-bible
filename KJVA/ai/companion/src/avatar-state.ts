/**
 * avatar-state.ts -- Avatar state machine for Tokenless Companion
 *
 * Implements a strict finite state machine for the conversational lifecycle:
 *   idle -> listening -> thinking -> speaking -> idle
 *
 * Any active state can reset to idle (completion) or flip to error; error
 * recovers to idle. Invalid transitions are silently rejected and logged.
 *
 * `AvatarState` is the SINGLE canonical avatar-state type — the view
 * (avatar-view.tsx), the DOM renderer (avatar-renderer.ts) and the agent
 * bridge (agent-bridge.ts) all import it from here. (Previously avatar.ts and
 * avatar.tsx each declared their own divergent `AvatarState`, both resolving to
 * "./avatar" — a collision that is now removed.)
 *
 * Causal chain:
 *   (User Input)        -> (listening)   user is talking to the companion
 *   (API Call)          -> (thinking)    request is being processed
 *   (Response / stream) -> (speaking)    companion is responding / conversing
 *   (Completion)        -> (idle)
 *   (Failure)           -> (error)       -> (idle) on recovery
 */

export type AvatarState = "idle" | "listening" | "thinking" | "speaking" | "error";

/**
 * Transition table: maps each state to the set of valid next states.
 * Every active state can transition to "idle" (completion) and "error";
 * "error" recovers to "idle".
 */
const VALID_TRANSITIONS: Record<AvatarState, ReadonlySet<AvatarState>> = {
  idle: new Set(["listening", "error"]),
  listening: new Set(["thinking", "idle", "error"]),
  thinking: new Set(["speaking", "idle", "error"]),
  speaking: new Set(["idle", "error"]),
  error: new Set(["idle"]),
};

/** All recognized avatar states for runtime validation. */
const ALL_STATES: ReadonlySet<string> = new Set<string>([
  "idle",
  "listening",
  "thinking",
  "speaking",
  "error",
]);

type StateChangeCallback = (state: AvatarState) => void;

export class AvatarStateMachine {
  private _currentState: AvatarState = "idle";
  private readonly _listeners: StateChangeCallback[] = [];

  /**
   * Attempt a state transition. Only valid transitions are executed.
   * Invalid transitions are logged but do not throw -- the machine
   * remains in its current state.
   */
  transition(newState: AvatarState): void {
    if (!ALL_STATES.has(newState)) {
      console.warn(
        `[AvatarStateMachine] Rejected unknown state: "${String(newState)}"`
      );
      return;
    }

    if (newState === this._currentState) {
      return; // No-op: already in target state.
    }

    const allowed = VALID_TRANSITIONS[this._currentState];
    if (!allowed.has(newState)) {
      console.warn(
        `[AvatarStateMachine] Invalid transition: "${this._currentState}" -> "${newState}". ` +
          `Allowed: [${Array.from(allowed).join(", ")}]`
      );
      return;
    }

    this._currentState = newState;
    this._notifyListeners();
  }

  /** Return the current avatar state. */
  getCurrentState(): AvatarState {
    return this._currentState;
  }

  /**
   * Register a callback invoked on every successful state change.
   * Returns a teardown function that removes the listener.
   */
  onStateChange(callback: StateChangeCallback): () => void {
    this._listeners.push(callback);
    return () => {
      const index = this._listeners.indexOf(callback);
      if (index !== -1) {
        this._listeners.splice(index, 1);
      }
    };
  }

  /** Force reset to idle regardless of current state. */
  reset(): void {
    if (this._currentState !== "idle") {
      this._currentState = "idle";
      this._notifyListeners();
    }
  }

  /** Check whether a transition from the current state to newState is valid. */
  canTransition(newState: AvatarState): boolean {
    if (!ALL_STATES.has(newState)) {
      return false;
    }
    return VALID_TRANSITIONS[this._currentState].has(newState);
  }

  private _notifyListeners(): void {
    const state = this._currentState;
    for (const listener of this._listeners) {
      try {
        listener(state);
      } catch (err) {
        console.error("[AvatarStateMachine] Listener error:", err);
      }
    }
  }
}
