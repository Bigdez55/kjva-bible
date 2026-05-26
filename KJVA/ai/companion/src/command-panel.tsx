// SPDX-License-Identifier: LicenseRef-Proprietary
// Copyright (c) 2026 Tokenless Models Project
/**
 * command-panel.tsx — Full-featured Companion command panel component.
 *
 * Features:
 *   - Chat input (multiline textarea at bottom)
 *     Enter = submit, Shift+Enter = newline
 *   - Message history (user right-aligned, AI left-aligned)
 *   - "Thinking" animation: 3 pulsing dots while AI processes
 *   - Action trace: tool calls rendered as expandable items
 *   - Undo button: reverts last AI action (if reversible)
 *   - Minimizable to a dock icon
 *   - Keyboard shortcut: Ctrl+Space to open/close
 *
 * Design tokens consumed from styles.css CSS custom properties.
 */

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

// ── Types ────────────────────────────────────────────────────────────────────

/** A single chat message in the conversation history. */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  timestamp: number;
}

/** A tool-call trace entry shown in the action trace panel. */
export interface TraceItem {
  id: string;
  label: string;
  detail?: string;
  status: "pending" | "success" | "error";
  timestamp: number;
  /** Whether this action can be undone. */
  reversible?: boolean;
  /** Opaque action ID passed to the undo endpoint. */
  actionId?: string;
}

export interface CommandPanelProps {
  /** Called when the user submits a message. Must return the assistant reply. */
  onSend: (message: string) => Promise<{
    response: string;
    tool_result?: unknown;
    agent?: string;
    latency_ms?: number;
  }>;
  /** Called when the user clicks Undo for a trace item. */
  onUndo?: (actionId: string) => Promise<{ status: string }>;
  /** Whether the panel is minimized to the dock icon. */
  minimized?: boolean;
  /** Controlled open/close setter (optional). */
  onToggleMinimize?: () => void;
}

// ── ID generator ─────────────────────────────────────────────────────────────

let _idCounter = 0;
function nextId(prefix: string): string {
  _idCounter += 1;
  return `${prefix}-${Date.now()}-${_idCounter}`;
}

// ── ThinkingDots ─────────────────────────────────────────────────────────────

/**
 * Three pulsing dots shown while the AI is generating a response.
 * Uses CSS animations only — no JavaScript timers.
 */
function ThinkingDots(): JSX.Element {
  return (
    <span className="cp-thinking" aria-label="AI is thinking" role="status">
      <span className="cp-dot cp-dot-1" aria-hidden="true" />
      <span className="cp-dot cp-dot-2" aria-hidden="true" />
      <span className="cp-dot cp-dot-3" aria-hidden="true" />
    </span>
  );
}

// ── TraceRow ──────────────────────────────────────────────────────────────────

interface TraceRowProps {
  item: TraceItem;
  onUndo?: (actionId: string) => void;
  undoing: boolean;
}

function TraceRow({ item, onUndo, undoing }: TraceRowProps): JSX.Element {
  const [expanded, setExpanded] = useState(false);

  const statusIcon =
    item.status === "pending" ? "⏳" : item.status === "success" ? "✓" : "✗";

  return (
    <li
      className={`cp-trace-row cp-trace-${item.status}`}
      aria-label={`Tool action: ${item.label}, status: ${item.status}`}
    >
      <button
        className="cp-trace-toggle"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-label={`${expanded ? "Collapse" : "Expand"} trace: ${item.label}`}
      >
        <span className="cp-trace-icon" aria-hidden="true">{statusIcon}</span>
        <span className="cp-trace-label">{item.label}</span>
        <span className="cp-trace-arrow" aria-hidden="true">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {expanded && item.detail && (
        <pre className="cp-trace-detail">{item.detail}</pre>
      )}

      {item.reversible && item.actionId && onUndo && (
        <button
          className="cp-undo-btn"
          onClick={() => onUndo(item.actionId!)}
          disabled={undoing}
          aria-label={`Undo: ${item.label}`}
          aria-busy={undoing}
        >
          {undoing ? "Undoing…" : "↩ Undo"}
        </button>
      )}
    </li>
  );
}

// ── MessageBubble ─────────────────────────────────────────────────────────────

interface BubbleProps {
  message: ChatMessage;
}

function MessageBubble({ message }: BubbleProps): JSX.Element {
  const isUser = message.role === "user";
  return (
    <div
      className={`cp-msg cp-msg-${message.role}`}
      aria-label={`${isUser ? "You" : "Companion"}: ${message.text}`}
    >
      <span className="cp-msg-text">{message.text}</span>
      <span className="cp-msg-time" aria-hidden="true">
        {new Date(message.timestamp).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        })}
      </span>
    </div>
  );
}

// ── CommandPanel ──────────────────────────────────────────────────────────────

export function CommandPanel({
  onSend,
  onUndo,
  minimized = false,
  onToggleMinimize,
}: CommandPanelProps): JSX.Element {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [trace, setTrace] = useState<TraceItem[]>([]);
  const [thinking, setThinking] = useState(false);
  const [undoingId, setUndoingId] = useState<string | null>(null);

  const historyEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll message history to bottom on new messages.
  useEffect(() => {
    historyEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  // Ctrl+Space global keyboard shortcut to toggle minimized state.
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.key === " ") {
        event.preventDefault();
        onToggleMinimize?.();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onToggleMinimize]);

  // Focus textarea when panel opens.
  useEffect(() => {
    if (!minimized) {
      // Deferred to let CSS transitions settle.
      const timer = setTimeout(() => inputRef.current?.focus(), 120);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [minimized]);

  // ── Send message ────────────────────────────────────────────────────────

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || thinking) return;

    setInput("");

    const userMsg: ChatMessage = {
      id: nextId("msg"),
      role: "user",
      text,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setThinking(true);

    // Add a pending trace entry for the inference call.
    const inferenceTraceId = nextId("trace");
    setTrace((prev) => [
      ...prev,
      {
        id: inferenceTraceId,
        label: "Processing with Tokenless AI...",
        status: "pending",
        timestamp: Date.now(),
      },
    ]);

    try {
      const result = await onSend(text);

      // Update inference trace to success.
      setTrace((prev) =>
        prev.map((item) =>
          item.id === inferenceTraceId
            ? {
                ...item,
                status: "success",
                label: `AI response (${result.latency_ms ?? "?"}ms)`,
                detail: result.tool_result
                  ? JSON.stringify(result.tool_result, null, 2)
                  : undefined,
              }
            : item
        )
      );

      // If there was a tool call, add a separate trace row.
      if (result.tool_result !== null && result.tool_result !== undefined) {
        const toolTrace: TraceItem = {
          id: nextId("tool"),
          label: `Tool executed by ${result.agent ?? "agent"}`,
          detail: JSON.stringify(result.tool_result, null, 2),
          status: "success",
          timestamp: Date.now(),
          reversible: true,
          actionId: inferenceTraceId,
        };
        setTrace((prev) => [...prev, toolTrace]);
      }

      const assistantMsg: ChatMessage = {
        id: nextId("msg"),
        role: "assistant",
        text: result.response,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: unknown) {
      const reason = err instanceof Error ? err.message : "Unknown error";

      setTrace((prev) =>
        prev.map((item) =>
          item.id === inferenceTraceId
            ? { ...item, status: "error", label: `Error: ${reason}` }
            : item
        )
      );

      const errorMsg: ChatMessage = {
        id: nextId("msg"),
        role: "assistant",
        text: "I encountered an issue processing that. Please try again.",
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setThinking(false);
    }
  }, [input, thinking, onSend]);

  // ── Undo ────────────────────────────────────────────────────────────────

  const handleUndo = useCallback(
    async (actionId: string) => {
      if (!onUndo) return;
      setUndoingId(actionId);
      try {
        await onUndo(actionId);
        setTrace((prev) =>
          prev.map((item) =>
            item.actionId === actionId
              ? { ...item, label: `${item.label} (undone)`, status: "success" }
              : item
          )
        );
      } catch {
        // Silently log — undo is best-effort.
      } finally {
        setUndoingId(null);
      }
    },
    [onUndo]
  );

  // ── Clear trace ─────────────────────────────────────────────────────────

  const clearTrace = useCallback(() => setTrace([]), []);

  // ── Keyboard handler for textarea ───────────────────────────────────────

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        send().catch(() => undefined);
      }
    },
    [send]
  );

  // ── Minimize/dock icon ───────────────────────────────────────────────────

  if (minimized) {
    return (
      <button
        className="cp-dock-icon"
        onClick={onToggleMinimize}
        aria-label="Open Tokenless Companion (Ctrl+Space)"
        title="Open Tokenless Companion (Ctrl+Space)"
      >
        <span className="cp-dock-icon-inner" aria-hidden="true">G</span>
      </button>
    );
  }

  // ── Full panel ───────────────────────────────────────────────────────────

  return (
    <section className="cp-panel" aria-label="Tokenless Companion command panel">
      {/* Header ─────────────────────────────────────────────── */}
      <header className="cp-header">
        <span className="cp-header-title">Tokenless Companion</span>
        <div className="cp-header-actions">
          {trace.length > 0 && (
            <button
              className="cp-btn-ghost"
              onClick={clearTrace}
              aria-label="Clear action trace"
            >
              Clear trace
            </button>
          )}
          <button
            className="cp-btn-ghost"
            onClick={onToggleMinimize}
            aria-label="Minimize companion panel (Ctrl+Space)"
            title="Ctrl+Space"
          >
            −
          </button>
        </div>
      </header>

      {/* Message history ────────────────────────────────────── */}
      <div
        className="cp-history"
        role="log"
        aria-label="Conversation history"
        aria-live="polite"
        aria-atomic="false"
      >
        {messages.length === 0 && (
          <p className="cp-empty-state">
            Ask me to open apps, summarize notes, or automate tasks.
          </p>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {thinking && <ThinkingDots />}
        <div ref={historyEndRef} aria-hidden="true" />
      </div>

      {/* Action trace ───────────────────────────────────────── */}
      {trace.length > 0 && (
        <div className="cp-trace-section">
          <span className="cp-trace-heading" aria-hidden="true">
            Action Trace
          </span>
          <ul
            className="cp-trace-list"
            aria-label="AI action trace"
            aria-live="polite"
          >
            {trace.map((item) => (
              <TraceRow
                key={item.id}
                item={item}
                onUndo={onUndo ? handleUndo : undefined}
                undoing={undoingId === item.actionId}
              />
            ))}
          </ul>
        </div>
      )}

      {/* Input area ─────────────────────────────────────────── */}
      <div className="cp-input-area">
        <textarea
          ref={inputRef}
          className="cp-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question or give a command… (Enter to send, Shift+Enter for newline)"
          aria-label="Message input"
          aria-multiline="true"
          rows={3}
          disabled={thinking}
        />
        <div className="cp-input-row">
          <button
            className="cp-send-btn"
            onClick={() => send().catch(() => undefined)}
            disabled={!input.trim() || thinking}
            aria-label="Send message"
            aria-busy={thinking}
          >
            {thinking ? <ThinkingDots /> : "Send"}
          </button>
        </div>
      </div>
    </section>
  );
}

// ── CSS injected into the document head (scoped to .cp-* classes) ────────────
// This keeps the component self-contained; it merges with styles.css.

const COMMAND_PANEL_CSS = `
/* CommandPanel — cp-* scoped styles */

.cp-panel {
  display: grid;
  grid-template-rows: auto 1fr auto auto;
  height: 100%;
  min-height: 0;
  background: var(--color-neutral-100);
  border-radius: var(--radius-lg);
  border: 1px solid rgba(255,255,255,0.08);
  overflow: hidden;
}

.cp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid rgba(255,255,255,0.07);
  background: var(--color-neutral-200);
}
.cp-header-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-primary);
  letter-spacing: 0.02em;
}
.cp-header-actions { display: flex; gap: var(--space-1); align-items: center; }

.cp-btn-ghost {
  background: transparent;
  border: none;
  color: var(--color-neutral-900);
  font-size: var(--text-xs);
  opacity: 0.6;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  min-height: 24px;
  transition: opacity var(--motion-fast);
}
.cp-btn-ghost:hover { opacity: 1; background: rgba(255,255,255,0.06); }
.cp-btn-ghost:focus-visible { outline: 2px solid var(--color-secondary); outline-offset: 1px; }

/* ── History ── */
.cp-history {
  overflow-y: auto;
  padding: var(--space-2) var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-height: 80px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.12) transparent;
}

.cp-empty-state {
  color: var(--color-neutral-900);
  opacity: 0.4;
  font-size: var(--text-sm);
  margin: auto;
  text-align: center;
  padding: var(--space-4) 0;
}

.cp-msg {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-width: 88%;
}
.cp-msg-user {
  align-self: flex-end;
  align-items: flex-end;
}
.cp-msg-assistant {
  align-self: flex-start;
  align-items: flex-start;
}

.cp-msg-text {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.cp-msg-user .cp-msg-text {
  background: var(--color-primary);
  color: #0d1115;
  border-bottom-right-radius: 4px;
}
.cp-msg-assistant .cp-msg-text {
  background: var(--color-neutral-200);
  color: var(--color-neutral-900);
  border-bottom-left-radius: 4px;
}

.cp-msg-time {
  font-size: 10px;
  opacity: 0.4;
  padding: 0 4px;
}

/* ── Thinking dots ── */
.cp-thinking {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  padding: 8px 12px;
  background: var(--color-neutral-200);
  border-radius: var(--radius-md);
  border-bottom-left-radius: 4px;
  align-self: flex-start;
}
.cp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-primary);
  opacity: 0.3;
  animation: cp-dot-pulse 1.2s ease-in-out infinite;
}
.cp-dot-2 { animation-delay: 0.2s; }
.cp-dot-3 { animation-delay: 0.4s; }

@keyframes cp-dot-pulse {
  0%, 100% { opacity: 0.3; transform: scale(1); }
  50%       { opacity: 1;   transform: scale(1.25); }
}
@media (prefers-reduced-motion: reduce) {
  .cp-dot { animation: none; opacity: 0.6; }
}

/* ── Action trace ── */
.cp-trace-section {
  border-top: 1px solid rgba(255,255,255,0.07);
  padding: var(--space-1) var(--space-3) var(--space-2);
  max-height: 140px;
  overflow-y: auto;
  scrollbar-width: thin;
}
.cp-trace-heading {
  display: block;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-neutral-900);
  opacity: 0.45;
  margin-bottom: var(--space-1);
}
.cp-trace-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 2px; }

.cp-trace-row {
  font-size: var(--text-xs);
  border-radius: 6px;
  overflow: hidden;
}
.cp-trace-pending .cp-trace-toggle { color: var(--color-neutral-900); opacity: 0.65; }
.cp-trace-success .cp-trace-toggle { color: #17b978; }
.cp-trace-error   .cp-trace-toggle { color: #ef476f; }

.cp-trace-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  width: 100%;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 6px;
  text-align: left;
  transition: background var(--motion-fast);
}
.cp-trace-toggle:hover { background: rgba(255,255,255,0.05); }
.cp-trace-toggle:focus-visible { outline: 2px solid var(--color-secondary); outline-offset: 1px; }
.cp-trace-icon { flex-shrink: 0; font-size: 11px; }
.cp-trace-label { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cp-trace-arrow { flex-shrink: 0; font-size: 9px; opacity: 0.5; }

.cp-trace-detail {
  font-size: 11px;
  padding: 4px 8px 6px 24px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--color-neutral-900);
  opacity: 0.7;
  line-height: 1.4;
}

.cp-undo-btn {
  margin: 2px 6px 4px 24px;
  background: transparent;
  border: 1px solid var(--color-primary);
  color: var(--color-primary);
  border-radius: 4px;
  font-size: 11px;
  padding: 2px 8px;
  cursor: pointer;
  min-height: 24px;
  transition: background var(--motion-fast);
}
.cp-undo-btn:hover { background: rgba(255,117,24,0.12); }
.cp-undo-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.cp-undo-btn:focus-visible { outline: 2px solid var(--color-secondary); outline-offset: 1px; }

/* ── Input area ── */
.cp-input-area {
  border-top: 1px solid rgba(255,255,255,0.07);
  padding: var(--space-2) var(--space-3);
  display: grid;
  gap: var(--space-1);
}
.cp-input {
  resize: none;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-neutral-300);
  background: var(--color-neutral-200);
  color: var(--color-neutral-900);
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  line-height: 1.5;
  transition: border-color var(--motion-fast);
  width: 100%;
  box-sizing: border-box;
}
.cp-input:focus { outline: none; border-color: var(--color-secondary); }
.cp-input:disabled { opacity: 0.5; cursor: not-allowed; }

.cp-input-row { display: flex; justify-content: flex-end; }
.cp-send-btn {
  min-width: 72px;
  min-height: 36px;
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-primary);
  background: var(--color-primary);
  color: #0d1115;
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  transition: background var(--motion-fast), opacity var(--motion-fast);
}
.cp-send-btn:hover:not(:disabled) { background: #e06b14; }
.cp-send-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.cp-send-btn:focus-visible { outline: 2px solid var(--color-secondary); outline-offset: 2px; }

/* ── Minimized dock icon ── */
.cp-dock-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--color-primary);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 20px rgba(255,117,24,0.4);
  transition: transform var(--motion-fast), box-shadow var(--motion-fast);
  animation: cp-dock-breathe 2.4s ease-in-out infinite;
}
.cp-dock-icon:hover { transform: scale(1.08); box-shadow: 0 6px 28px rgba(255,117,24,0.55); }
.cp-dock-icon:focus-visible { outline: 2px solid var(--color-secondary); outline-offset: 3px; }
.cp-dock-icon-inner {
  font-size: 20px;
  font-weight: 700;
  color: #0d1115;
  line-height: 1;
  font-family: var(--font-sans);
}

@keyframes cp-dock-breathe {
  0%, 100% { box-shadow: 0 4px 20px rgba(255,117,24,0.4); }
  50%       { box-shadow: 0 4px 32px rgba(255,117,24,0.65); }
}
@media (prefers-reduced-motion: reduce) {
  .cp-dock-icon { animation: none; }
}
`;

// Inject CSS once on module load.
if (typeof document !== "undefined") {
  const styleId = "cp-injected-styles";
  if (!document.getElementById(styleId)) {
    const style = document.createElement("style");
    style.id = styleId;
    style.textContent = COMMAND_PANEL_CSS;
    document.head.appendChild(style);
  }
}
