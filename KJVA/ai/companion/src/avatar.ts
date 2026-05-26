/**
 * avatar.ts -- Avatar state machine for Tokenless Companion
 *
 * Implements a strict finite state machine with 4 states:
 *   idle -> listening -> thinking -> acting -> idle
 *
 * Any state can reset to idle (error recovery / completion).
 * Invalid transitions are silently rejected and logged to console.warn.
 *
 * Causal chain:
 *   (User Input) -> [triggers] -> (listening)
 *   (API Call)   -> [triggers] -> (thinking)
 *   (Tool Dispatch) -> [triggers] -> (acting)
 *   (Completion/Error) -> [triggers] -> (idle)
 */

export type AvatarState = "idle" | "listening" | "thinking" | "acting";

/**
 * Transition table: maps each state to the set of valid next states.
 * Every state can transition to "idle" (reset path).
 */
const VALID_TRANSITIONS: Record<AvatarState, ReadonlySet<AvatarState>> = {
  idle: new Set(["listening", "idle"]),
  listening: new Set(["thinking", "idle"]),
  thinking: new Set(["acting", "idle"]),
  acting: new Set(["idle"]),
};

/** All recognized avatar states for runtime validation. */
const ALL_STATES: ReadonlySet<string> = new Set<string>([
  "idle",
  "listening",
  "thinking",
  "acting",
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
