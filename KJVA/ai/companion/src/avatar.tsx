// SPDX-License-Identifier: LicenseRef-Proprietary
// Copyright (c) 2026 Tokenless Models Project
/**
 * avatar.tsx - Animated React avatar component for the Tokenless companion.
 *
 * States:
 *   idle       — gentle breathing pulse (primary orange)
 *   speaking   — rapid ripple outward (blue accent, emitted when AI streams)
 *   thinking   — 3 orbital dots rotating (amber warning)
 *   error      — red blink pulse
 *
 * Size: 64×64px.  Positioned at the top of the command panel.
 * Uses CSS animations only — no Lottie, no JavaScript timers.
 * Respects prefers-reduced-motion.
 *
 * Design tokens are pulled from CSS custom properties defined in styles.css.
 */

import React, { useEffect, useRef } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

export type AvatarState = "idle" | "speaking" | "thinking" | "error";

export interface AvatarProps {
  /** Current avatar state. Drives animation class. */
  state: AvatarState;
  /** Optional label override (defaults to state name). */
  label?: string;
  /** Pixel size; defaults to 64. */
  size?: number;
}

// ── Human-readable labels for ARIA ──────────────────────────────────────────

const STATE_LABELS: Record<AvatarState, string> = {
  idle: "Idle",
  speaking: "Speaking",
  thinking: "Thinking",
  error: "Error",
};

// ── Component ────────────────────────────────────────────────────────────────

export function Avatar({ state, label, size = 64 }: AvatarProps): JSX.Element {
  const ariaLabel = label ?? `Companion avatar — ${STATE_LABELS[state]}`;
  const liveRef = useRef<HTMLSpanElement>(null);

  // Announce state changes to screen readers via the live region.
  useEffect(() => {
    if (liveRef.current) {
      liveRef.current.textContent = `Companion is now ${STATE_LABELS[state]}`;
    }
  }, [state]);

  const px = `${size}px`;

  return (
    <div
      className={`av-container av-${state}`}
      role="img"
      aria-label={ariaLabel}
      style={{ width: px, height: px, position: "relative", display: "inline-flex", alignItems: "center", justifyContent: "center" }}
    >
      {/* Ripple ring (speaking state) */}
      <div className="av-ripple-1" aria-hidden="true" />
      <div className="av-ripple-2" aria-hidden="true" />

      {/* Orbital track with 3 dots (thinking state) */}
      <div className="av-orbit-track" aria-hidden="true">
        <span className="av-orbit-dot av-orbit-dot-1" />
        <span className="av-orbit-dot av-orbit-dot-2" />
        <span className="av-orbit-dot av-orbit-dot-3" />
      </div>

      {/* Core circle */}
      <div className="av-core" aria-hidden="true" />

      {/* Screen-reader-only live region */}
      <span
        ref={liveRef}
        className="av-sr-only"
        aria-live="polite"
        aria-atomic="true"
      />
    </div>
  );
}

// ── CSS injected once on module load (scoped to .av-* classes) ───────────────

const AVATAR_CSS = `
/* Avatar component — av-* scoped styles */

.av-container {
  flex-shrink: 0;
}

/* ── Core circle ── */
.av-core {
  position: absolute;
  width: 46px;
  height: 46px;
  border-radius: 50%;
  background: var(--color-primary, #ff7518);
  z-index: 2;
  transition: background 300ms ease-out, box-shadow 300ms ease-out;
}

/* ── Ripple rings ── */
.av-ripple-1, .av-ripple-2 {
  position: absolute;
  width: 46px;
  height: 46px;
  border-radius: 50%;
  border: 2px solid transparent;
  z-index: 1;
  pointer-events: none;
}

/* ── Orbital track ── */
.av-orbit-track {
  display: none;
  position: absolute;
  width: 56px;
  height: 56px;
  top: 50%;
  left: 50%;
  margin-top: -28px;
  margin-left: -28px;
  z-index: 3;
  pointer-events: none;
}

.av-orbit-dot {
  position: absolute;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-neutral-900, #f7fbff);
  box-shadow: 0 0 5px rgba(247,251,255,0.5);
}
.av-orbit-dot-1 { top: 0; left: 50%; margin-left: -3px; }
.av-orbit-dot-2 { bottom: 8px; right: 2px; }
.av-orbit-dot-3 { bottom: 8px; left: 2px; }

/* ── Screen reader only ── */
.av-sr-only {
  position: absolute;
  width: 1px; height: 1px;
  overflow: hidden;
  clip: rect(0,0,0,0);
  white-space: nowrap;
  border: 0;
}

/* ── State: IDLE — breathing pulse ── */
.av-idle .av-core {
  background: var(--color-primary, #ff7518);
  animation: av-breathe 2s ease-in-out infinite;
  box-shadow: 0 0 0 0 rgba(255,117,24,0.35);
}

@keyframes av-breathe {
  0%, 100% { transform: scale(1);    box-shadow: 0 0 0   0 rgba(255,117,24,0.35); }
  50%       { transform: scale(1.07); box-shadow: 0 0 14px 4px rgba(255,117,24,0.2); }
}

/* ── State: SPEAKING — ripple outward (blue) ── */
.av-speaking .av-core {
  background: var(--color-secondary, #1aa7ec);
  animation: none;
  box-shadow: 0 0 18px 4px rgba(26,167,236,0.3);
}

.av-speaking .av-ripple-1,
.av-speaking .av-ripple-2 {
  border-color: var(--color-secondary, #1aa7ec);
  animation: av-ripple 1.4s ease-out infinite;
}
.av-speaking .av-ripple-2 { animation-delay: 0.45s; }

@keyframes av-ripple {
  0%   { transform: scale(1);   opacity: 0.55; }
  100% { transform: scale(1.9); opacity: 0; }
}

/* ── State: THINKING — orbital dots (amber) ── */
.av-thinking .av-core {
  background: #ffbe0b;
  animation: av-think-glow 1.1s ease-in-out infinite;
}

.av-thinking .av-orbit-track {
  display: block;
  animation: av-orbit 1.3s linear infinite;
}

@keyframes av-think-glow {
  0%, 100% { box-shadow: 0 0  8px 2px rgba(255,190,11,0.2); }
  50%       { box-shadow: 0 0 18px 6px rgba(255,190,11,0.4); }
}

@keyframes av-orbit {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

/* ── State: ERROR — red blink ── */
.av-error .av-core {
  background: #ef476f;
  animation: av-error-blink 0.9s ease-in-out infinite;
  box-shadow: 0 0 12px 4px rgba(239,71,111,0.4);
}

@keyframes av-error-blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.45; }
}

/* ── Reduced motion ── */
@media (prefers-reduced-motion: reduce) {
  .av-idle .av-core,
  .av-speaking .av-core,
  .av-thinking .av-core,
  .av-error .av-core {
    animation: none !important;
  }
  .av-speaking .av-ripple-1,
  .av-speaking .av-ripple-2 {
    animation: none !important;
    display: none;
  }
  .av-thinking .av-orbit-track {
    animation: none !important;
  }
  .av-idle .av-core     { box-shadow: 0 0 8px 2px rgba(255,117,24,0.25); }
  .av-speaking .av-core { box-shadow: 0 0 8px 2px rgba(26,167,236,0.3); }
  .av-thinking .av-core { box-shadow: 0 0 8px 2px rgba(255,190,11,0.3); }
  .av-error .av-core    { box-shadow: 0 0 8px 2px rgba(239,71,111,0.3); }
}
`;

// Inject CSS once on module load.
if (typeof document !== "undefined") {
  const styleId = "av-injected-styles";
  if (!document.getElementById(styleId)) {
    const style = document.createElement("style");
    style.id = styleId;
    style.textContent = AVATAR_CSS;
    document.head.appendChild(style);
  }
}
