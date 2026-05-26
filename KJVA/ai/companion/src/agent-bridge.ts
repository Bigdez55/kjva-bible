/**
 * agent-bridge.ts -- Bridge between AI Agent Runtime and Companion UI
 *
 * Connects the Tokenless cognitive runtime (Python, on localhost:8090)
 * to the Electron companion's AvatarStateMachine and ActionTracePanel.
 *
 * Architecture decision: All HTTP calls go through Electron IPC to
 * respect the security boundary. The renderer process NEVER makes
 * direct network requests. The bridge uses window.companion.bridgeStatus()
 * and window.companion.bridgeActions() if available, otherwise falls
 * back to polling via IPC.
 *
 * NOTE: The existing api.py does NOT expose /v1/status or /v1/actions.
 * It exposes:
 *   GET  /healthz  (unauthenticated, returns { status: "ok"|"degraded" })
 *   GET  /status   (authenticated, returns circuit breaker state)
 *
 * This bridge polls /healthz for connection liveness and synthesizes
 * ActionTraceEntry objects from /chat responses when they arrive.
 * The /v1/ prefix endpoints are documented as the future target API.
 * For now, the bridge maps existing endpoints:
 *   /healthz          -> connection health
 *   /status           -> agent state (requires auth via IPC)
 *
 * Retry strategy: exponential backoff starting at 2s, max 30s.
 * Backoff doubles on each consecutive failure, resets on success.
 *
 * Causal topology:
 *   AgentBridge.start() -> poll timer -> fetch /healthz via IPC ->
 *   response analysis -> AvatarStateMachine.transition() +
 *   ActionTracePanel.addEntry()
 */

import type { AvatarState } from "./avatar";
import { AvatarStateMachine } from "./avatar";
import type { ActionTraceEntry, ActionStatus, ActionType } from "./action-trace";
import { ActionTracePanel } from "./action-trace";

/** Configuration for the AgentBridge. */
export interface AgentBridgeConfig {
  /** Base URL for the AI agent runtime. Default: http://localhost:8090 */
  agentBaseUrl?: string;
  /** Polling interval in ms. Default: 2000 */
  pollIntervalMs?: number;
  /** Minimum backoff in ms on connection failure. Default: 2000 */
  minBackoffMs?: number;
  /** Maximum backoff in ms. Default: 30000 */
  maxBackoffMs?: number;
}

/** Internal connection state. */
type ConnectionState = "connected" | "disconnected" | "connecting";

/** Monotonic ID counter for synthetic trace entries. */
let _traceIdCounter = 0;
function nextTraceId(): string {
  _traceIdCounter += 1;
  return `trace-${Date.now()}-${_traceIdCounter}`;
}

/**
 * AgentBridge manages the bidirectional link between the AI agent
 * runtime and the companion's visual components.
 *
 * Usage:
 *   const sm = new AvatarStateMachine();
 *   const tp = new ActionTracePanel();
 *   const bridge = new AgentBridge(sm, tp, { agentBaseUrl: "http://localhost:8090" });
 *   bridge.start();
 *   // ... later
 *   bridge.stop();
 */
export class AgentBridge {
  private readonly _stateMachine: AvatarStateMachine;
  private readonly _tracePanel: ActionTracePanel;
  private readonly _baseUrl: string;
  private readonly _pollInterval: number;
  private readonly _minBackoff: number;
  private readonly _maxBackoff: number;

  private _pollTimer: ReturnType<typeof setTimeout> | null = null;
  private _connectionState: ConnectionState = "disconnected";
  private _currentBackoff: number;
  private _consecutiveFailures: number = 0;
  private _running: boolean = false;

  /** Last known agent status from /healthz. */
  private _lastHealthStatus: string = "unknown";

  /** Last known circuit state from /status (authenticated). */
  private _lastCircuitOpen: boolean = false;

  constructor(
    stateMachine: AvatarStateMachine,
    tracePanel: ActionTracePanel,
    config?: AgentBridgeConfig
  ) {
    this._stateMachine = stateMachine;
    this._tracePanel = tracePanel;
    // Default points at the KJV bundle runtime on :8091.
    // Override via config.agentBaseUrl for tunnel / remote / alt ports.
    this._baseUrl = config?.agentBaseUrl ?? "http://localhost:8091";
    this._pollInterval = config?.pollIntervalMs ?? 2000;
    this._minBackoff = config?.minBackoffMs ?? 2000;
    this._maxBackoff = config?.maxBackoffMs ?? 30000;
    this._currentBackoff = this._minBackoff;
  }

  /** Start polling the agent runtime. */
  start(): void {
    if (this._running) {
      return;
    }
    this._running = true;
    this._connectionState = "connecting";
    this._addSystemTraceEntry("intent", "Connecting to AI agent runtime...");
    this._schedulePoll(0);
  }

  /** Stop polling and clean up timers. */
  stop(): void {
    this._running = false;
    if (this._pollTimer !== null) {
      clearTimeout(this._pollTimer);
      this._pollTimer = null;
    }
    this._connectionState = "disconnected";
  }

  /** Returns true if the bridge has an active connection to the agent runtime. */
  isConnected(): boolean {
    return this._connectionState === "connected";
  }

  /** Return the current connection state for diagnostics. */
  getConnectionState(): ConnectionState {
    return this._connectionState;
  }

  /** Return consecutive failure count for diagnostics. */
  getConsecutiveFailures(): number {
    return this._consecutiveFailures;
  }

  // -- Private: Polling Logic -----------------------------------------------

  private _schedulePoll(delayMs: number): void {
    if (!this._running) {
      return;
    }
    this._pollTimer = setTimeout(() => {
      this._poll().catch((err) => {
        console.error("[AgentBridge] Unexpected poll error:", err);
      });
    }, delayMs);
  }

  private async _poll(): Promise<void> {
    if (!this._running) {
      return;
    }

    try {
      const healthOk = await this._fetchHealth();

      if (healthOk) {
        this._onConnectionSuccess();
      } else {
        this._onConnectionFailure("Agent reported degraded status");
      }
    } catch (err) {
      this._onConnectionFailure(
        err instanceof Error ? err.message : "Connection failed"
      );
    }

    // Schedule next poll
    if (this._running) {
      const nextDelay =
        this._connectionState === "connected"
          ? this._pollInterval
          : this._currentBackoff;
      this._schedulePoll(nextDelay);
    }
  }

  /**
   * Fetch /healthz from the agent runtime.
   *
   * This goes through IPC if window.companion.healthCheck is available.
   * Otherwise falls back to a direct fetch (which will only work if
   * CSP allows it -- in production, the IPC path is the only valid route).
   */
  private async _fetchHealth(): Promise<boolean> {
    // Prefer IPC path (secure, tokens stay in main process)
    if (
      typeof window !== "undefined" &&
      window.companion &&
      typeof (window.companion as Record<string, unknown>).healthCheck === "function"
    ) {
      const result = await (
        window.companion as Record<string, unknown> & {
          healthCheck: () => Promise<{ status: string }>;
        }
      ).healthCheck();
      this._lastHealthStatus = result.status;
      return result.status === "ok";
    }

    // Fallback: direct fetch to /healthz (unauthenticated endpoint)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(`${this._baseUrl}/healthz`, {
        method: "GET",
        signal: controller.signal,
      });

      if (!response.ok) {
        this._lastHealthStatus = "error";
        return false;
      }

      const data = (await response.json()) as { status: string };
      this._lastHealthStatus = data.status;
      return data.status === "ok";
    } finally {
      clearTimeout(timeoutId);
    }
  }

  private _onConnectionSuccess(): void {
    const wasDisconnected = this._connectionState !== "connected";
    this._connectionState = "connected";
    this._consecutiveFailures = 0;
    this._currentBackoff = this._minBackoff;

    if (wasDisconnected) {
      this._addSystemTraceEntry(
        "result",
        "Connected to AI agent runtime",
        "success"
      );

      // Reset avatar to idle on reconnection
      this._stateMachine.reset();
    }
  }

  private _onConnectionFailure(reason: string): void {
    this._consecutiveFailures += 1;
    this._connectionState = "disconnected";

    // Exponential backoff: double each failure, cap at maxBackoff
    this._currentBackoff = Math.min(
      this._minBackoff * Math.pow(2, this._consecutiveFailures - 1),
      this._maxBackoff
    );

    // Only log the first failure and then every 5th to avoid trace spam
    if (
      this._consecutiveFailures === 1 ||
      this._consecutiveFailures % 5 === 0
    ) {
      this._addSystemTraceEntry(
        "result",
        `Connection failed: ${reason} (attempt ${this._consecutiveFailures}, retry in ${Math.round(this._currentBackoff / 1000)}s)`,
        "error"
      );
    }

    // Reset avatar to idle when disconnected
    this._stateMachine.reset();
  }

  // -- Public: Chat Action Tracing ------------------------------------------

  /**
   * Record a chat interaction's lifecycle as trace entries.
   * Called by the main UI when a chat request/response cycle occurs.
   *
   * This synthesizes trace entries from the existing /chat response
   * structure since /v1/actions does not exist in the current API.
   *
   * Usage from main.tsx integration:
   *   bridge.traceChat("user message", responsePromise);
   */
  async traceChat(
    userMessage: string,
    responsePromise: Promise<{
      response: string;
      latency_ms?: number;
      tool_result?: unknown;
      agent?: string;
    }>
  ): Promise<void> {
    const intentId = nextTraceId();
    const inferenceId = nextTraceId();

    // Phase 1: Intent received
    this._stateMachine.transition("listening");
    this._tracePanel.addEntry({
      id: intentId,
      timestamp: Date.now(),
      action_type: "intent",
      description: `User: "${this._truncate(userMessage, 80)}"`,
      status: "success",
    });

    // Phase 2: Inference starts
    this._stateMachine.transition("thinking");
    this._tracePanel.addEntry({
      id: inferenceId,
      timestamp: Date.now(),
      action_type: "inference",
      description: "Processing with Llama 3.2 3B...",
      status: "pending",
    });

    const inferenceStart = Date.now();

    try {
      const result = await responsePromise;
      const latencyMs = result.latency_ms ?? Date.now() - inferenceStart;

      // Update inference entry to success
      this._tracePanel.updateEntry(inferenceId, {
        status: "success",
        duration_ms: latencyMs,
      });

      // Phase 3: Tool call (if present)
      if (result.tool_result !== undefined && result.tool_result !== null) {
        this._stateMachine.transition("acting");
        this._tracePanel.addEntry({
          id: nextTraceId(),
          timestamp: Date.now(),
          action_type: "tool_call",
          description: `Tool executed by ${result.agent ?? "agent"}`,
          duration_ms: latencyMs,
          status: "success",
        });
      } else {
        this._stateMachine.transition("acting");
      }

      // Phase 4: Result
      this._tracePanel.addEntry({
        id: nextTraceId(),
        timestamp: Date.now(),
        action_type: "result",
        description: this._truncate(result.response, 120),
        duration_ms: latencyMs,
        status: "success",
      });

      // Return to idle
      this._stateMachine.transition("idle");
    } catch (err) {
      const duration = Date.now() - inferenceStart;

      this._tracePanel.updateEntry(inferenceId, {
        status: "error",
        duration_ms: duration,
      });

      this._tracePanel.addEntry({
        id: nextTraceId(),
        timestamp: Date.now(),
        action_type: "result",
        description: `Error: ${err instanceof Error ? err.message : "Unknown error"}`,
        duration_ms: duration,
        status: "error",
      });

      this._stateMachine.reset();
    }
  }

  // -- Private: Helpers -----------------------------------------------------

  /**
   * Add a system-generated trace entry (connection events, diagnostics).
   */
  private _addSystemTraceEntry(
    actionType: ActionType,
    description: string,
    entryStatus: ActionStatus = "pending"
  ): void {
    this._tracePanel.addEntry({
      id: nextTraceId(),
      timestamp: Date.now(),
      action_type: actionType,
      description,
      status: entryStatus,
    });
  }

  /** Truncate a string to maxLen characters, appending "..." if truncated. */
  private _truncate(text: string, maxLen: number): string {
    if (text.length <= maxLen) {
      return text;
    }
    return text.slice(0, maxLen - 3) + "...";
  }
}
