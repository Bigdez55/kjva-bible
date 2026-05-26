/**
 * avatar-renderer.ts -- DOM renderer for Tokenless Companion avatar
 *
 * Creates and manages the circular avatar container with state-driven
 * CSS classes. Each AvatarState maps to a CSS class that activates
 * the corresponding animation defined in avatar-animations.css.
 *
 * Causal topology:
 *   AvatarStateMachine.onStateChange -> renderAvatar callback ->
 *   DOM class swap -> CSS animation transition (300ms ease-out)
 *
 * Design system tokens consumed via CSS custom properties:
 *   --genos-primary, --genos-accent, --genos-surface, --genos-success,
 *   --genos-warning, --genos-text
 */

import { AvatarStateMachine, type AvatarState } from "./avatar";

/** All state CSS class names for cleanup during transitions. */
const STATE_CLASSES: readonly string[] = [
  "state-idle",
  "state-listening",
  "state-thinking",
  "state-acting",
  "state-error",
] as const;

/**
 * Human-readable labels for each state, used in the ARIA live region
 * and the visible state label beneath the avatar.
 */
const STATE_LABELS: Record<AvatarState, string> = {
  idle: "Idle",
  listening: "Listening",
  thinking: "Thinking",
  acting: "Acting",
};

/**
 * Build the avatar DOM subtree inside the given container and wire it
 * to the provided AvatarStateMachine.
 *
 * DOM structure created:
 *   <div class="avatar-container state-idle" role="img" aria-label="...">
 *     <div class="avatar-core"></div>
 *     <div class="avatar-ripple-ring"></div>
 *     <div class="avatar-orbit-track">
 *       <span class="avatar-orbit-dot"></span>
 *       <span class="avatar-orbit-dot"></span>
 *       <span class="avatar-orbit-dot"></span>
 *     </div>
 *     <span class="avatar-state-label">Idle</span>
 *     <span class="sr-only" aria-live="polite"></span>
 *   </div>
 *
 * Returns a teardown function that removes the listener and clears the container.
 */
export function renderAvatar(
  container: HTMLElement,
  stateMachine: AvatarStateMachine
): () => void {
  // -- Build DOM elements ------------------------------------------------

  const wrapper = document.createElement("div");
  wrapper.className = "avatar-container state-idle";
  wrapper.setAttribute("role", "img");
  wrapper.setAttribute(
    "aria-label",
    `Companion avatar -- currently ${STATE_LABELS.idle}`
  );

  // Core circle
  const core = document.createElement("div");
  core.className = "avatar-core";
  wrapper.appendChild(core);

  // Ripple ring (third ring for listening state; first two are ::before/::after)
  const rippleRing = document.createElement("div");
  rippleRing.className = "avatar-ripple-ring";
  wrapper.appendChild(rippleRing);

  // Orbital dots track (for thinking state)
  const orbitTrack = document.createElement("div");
  orbitTrack.className = "avatar-orbit-track";
  for (let i = 0; i < 3; i++) {
    const dot = document.createElement("span");
    dot.className = "avatar-orbit-dot";
    orbitTrack.appendChild(dot);
  }
  wrapper.appendChild(orbitTrack);

  // Visible state label
  const label = document.createElement("span");
  label.className = "avatar-state-label";
  label.textContent = STATE_LABELS.idle;
  wrapper.appendChild(label);

  // Screen-reader-only live region for state announcements
  const srOnly = document.createElement("span");
  srOnly.className = "sr-only";
  srOnly.setAttribute("aria-live", "polite");
  srOnly.setAttribute("aria-atomic", "true");
  srOnly.style.position = "absolute";
  srOnly.style.width = "1px";
  srOnly.style.height = "1px";
  srOnly.style.overflow = "hidden";
  srOnly.style.clip = "rect(0, 0, 0, 0)";
  srOnly.style.whiteSpace = "nowrap";
  srOnly.style.border = "0";
  wrapper.appendChild(srOnly);

  // Mount into provided container
  container.appendChild(wrapper);

  // -- State change handler -----------------------------------------------

  function applyState(state: AvatarState): void {
    // Remove all state classes, then add the current one
    for (const cls of STATE_CLASSES) {
      wrapper.classList.remove(cls);
    }
    wrapper.classList.add(`state-${state}`);

    // Update accessible label
    const readableLabel = STATE_LABELS[state] ?? state;
    wrapper.setAttribute(
      "aria-label",
      `Companion avatar -- currently ${readableLabel}`
    );
    label.textContent = readableLabel;

    // Announce to screen readers
    srOnly.textContent = `Companion state changed to ${readableLabel}`;
  }

  // Apply initial state
  applyState(stateMachine.getCurrentState());

  // Subscribe to future state changes
  const unsubscribe = stateMachine.onStateChange(applyState);

  // -- Teardown -----------------------------------------------------------

  return () => {
    unsubscribe();
    container.removeChild(wrapper);
  };
}

/**
 * Convenience: apply an error visual state to the avatar container.
 * This is outside the state machine's valid transitions -- it is a
 * purely visual indicator driven by the AgentBridge when the connection
 * to the AI runtime is lost.
 */
export function setAvatarError(container: HTMLElement, isError: boolean): void {
  const wrapper = container.querySelector(".avatar-container");
  if (!wrapper) {
    return;
  }
  if (isError) {
    for (const cls of STATE_CLASSES) {
      wrapper.classList.remove(cls);
    }
    wrapper.classList.add("state-error");
  }
}
