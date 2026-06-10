/**
 * action-trace.ts -- Action trace panel for Tokenless Companion
 *
 * Displays a scrollable panel showing AI agent actions in real-time.
 * Each entry tracks the full lifecycle of an agent action:
 *   intent -> context -> inference -> tool_call -> result
 *
 * Causal topology:
 *   AgentBridge polls /v1/actions -> pushes ActionTraceEntry ->
 *   ActionTracePanel.addEntry() -> DOM li appended with animation ->
 *   auto-scroll to latest entry
 *
 * Renders with semantic HTML (ul/li), ARIA roles for accessibility.
 * All CSS classes reference avatar-animations.css.
 */

/** Valid action types in the agent trace lifecycle. */
export type ActionType =
  | "intent"
  | "context"
  | "inference"
  | "tool_call"
  | "result";

/** Status of an individual trace entry. */
export type ActionStatus = "pending" | "success" | "error";

/** A single action trace entry from the AI agent runtime. */
export interface ActionTraceEntry {
  /** Unique identifier for this trace entry. */
  id: string;
  /** Unix timestamp (ms) when the action was initiated. */
  timestamp: number;
  /** The phase of agent execution this entry represents. */
  action_type: ActionType;
  /** Human-readable description of what happened. */
  description: string;
  /** How long this action took, in milliseconds. Absent while pending. */
  duration_ms?: number;
  /** Current status of this trace entry. */
  status: ActionStatus;
}

/**
 * Determinant slice of per-turn provenance — the SAFE, non-sensitive projection of
 * the spine's `DeterminantProbabilityRecord` (heptagon/determinant_record.py,
 * ADR-0001 §10.1). The spine record carries deterministic input snapshot hashes and
 * probabilistic outputs; the UI receives ONLY the route, the selection reason, the
 * scalar confidence, and a SHORT (already-truncated by the spine) hash digest for
 * visual audit — never the raw candidate/retrieval scores or full snapshot hashes.
 */
export interface DeterminantProvenance {
  /** Route the deterministic control layer SELECTED (e.g. "direct", "memory_mediated"). */
  selected_route: string;
  /** Human-readable reason the control layer chose this route. */
  selection_reason?: string;
  /** Probabilistic-output confidence in [0,1] (DeterminantProbabilityRecord.confidence). */
  confidence?: number;
  /** Whether identical inputs would replay to an identical route (§10.1 replay property). */
  replayable?: boolean;
  /** Short hash digest (spine-truncated, e.g. first 8 hex of route_policy_hash) for audit. */
  route_policy_digest?: string;
}

/**
 * Materialization slice of per-turn provenance — the SAFE projection of the spine's
 * `MaterializationRecord` (materialization/materialization_record.py, ADR-0001 §11.2).
 * The UI receives the materialization id, type, lifecycle status, confidence, privacy
 * class, and a single short source-hash digest. NEVER the full source_refs/source_hashes
 * lists, transforms, lineage, or runtime_location.
 */
export interface MaterializationProvenance {
  /** Stable id of the materialization (MaterializationRecord.materialization_id). */
  materialization_id: string;
  /** adapter|memory|sensory|simulation|action|response|provenance|model_artifact|... */
  materialization_type: string;
  /** planned|active|committed|rolled_back|revoked|archived (§11.2). */
  status: string;
  /** Confidence in [0,1] (MaterializationRecord.confidence). */
  confidence?: number;
  /** public|internal|private|sealed (MaterializationRecord.privacy_class). */
  privacy_class?: string;
  /** Short hash digest (spine-truncated) of the primary source artifact, for audit. */
  source_digest?: string;
}

/**
 * Safe per-turn provenance surfaced to the UI (ADR-0001 §10.2 response provenance
 * object, §11.2 step 19). Contains ONLY non-sensitive pipeline metadata — never raw
 * user text, memory contents, session IDs, or full snapshot hashes.
 *
 * D30/D31 ledger (consume side): `determinant` and `materialization` are the SAFE
 * projections of the spine's `DeterminantProbabilityRecord` and `MaterializationRecord`
 * that the agent now emits per turn. They are OPTIONAL so this interface stays
 * backward-compatible with the pre-ledger pipeline metadata fields below.
 */
export interface TurnProvenance {
  turn_id: string;
  latency_ms: number;
  /** Whether the response is grounded in retrieved/materialized evidence (D31). */
  grounded?: boolean;
  /** SAFE projection of DeterminantProbabilityRecord (D30). */
  determinant?: DeterminantProvenance;
  /** SAFE projection of MaterializationRecord (D31). */
  materialization?: MaterializationProvenance;
  // ── Pre-ledger pipeline metadata (retained for backward compatibility) ──
  heptagon_active?: boolean;
  shard_count?: number;
  route_reason?: string;
  degraded?: boolean;
  evidence_salience?: number;
  sensory_scope?: string[];
}

/**
 * Format a TurnProvenance into a single safe summary line. Pure (no DOM) so it is
 * unit-testable and reusable by command-panel.tsx. Renders the D30/D31 ledger
 * projection first (route · grounded · confidence · materialization status), then
 * any retained pipeline metadata. Every branch is guarded so partial/legacy records
 * format cleanly.
 */
export function formatProvenance(p: TurnProvenance): string {
  const parts: string[] = [`turn ${p.turn_id.slice(0, 8)}`, `${p.latency_ms}ms`];

  // ── D30: determinant route + confidence ──
  if (p.determinant) {
    const d = p.determinant;
    parts.push(`route ${d.selected_route}`);
    if (typeof d.confidence === "number") {
      parts.push(`conf ${d.confidence.toFixed(2)}`);
    }
    if (d.replayable === false) {
      parts.push("⚠ non-replayable");
    }
  } else if (p.route_reason) {
    // Legacy fallback when no determinant slice is present.
    parts.push(p.route_reason);
  }

  // ── D31: grounded yes/no ──
  if (typeof p.grounded === "boolean") {
    parts.push(`grounded ${p.grounded ? "yes" : "no"}`);
  }

  // ── D31: materialization id/type/status ──
  if (p.materialization) {
    const m = p.materialization;
    parts.push(`mat ${m.materialization_type}:${m.status}`);
  }

  // ── Retained pipeline metadata (only if no ledger slices supplied them) ──
  if (!p.determinant && typeof p.heptagon_active === "boolean") {
    parts.push(`heptagon ${p.heptagon_active ? "on" : "off"}`);
  }
  if (typeof p.shard_count === "number") {
    parts.push(`${p.shard_count} shard${p.shard_count === 1 ? "" : "s"}`);
  }
  if (typeof p.evidence_salience === "number") {
    parts.push(`salience ${p.evidence_salience.toFixed(2)}`);
  }
  if (p.sensory_scope && p.sensory_scope.length > 0) {
    parts.push(`scope ${p.sensory_scope.join("/")}`);
  }
  if (p.degraded) {
    parts.push("⚠ degraded");
  }
  return parts.join(" · ");
}

/** Maximum entries retained in the panel before oldest are evicted. */
const MAX_ENTRIES = 50;

type EntryAddedCallback = (entry: ActionTraceEntry) => void;

/**
 * ActionTracePanel manages a scrollable list of AI agent action entries.
 *
 * It maintains both an in-memory array and a live DOM subtree.
 * Entries are appended at the bottom and the panel auto-scrolls
 * to keep the latest entry visible.
 */
export class ActionTracePanel {
  private readonly _entries: ActionTraceEntry[] = [];
  private readonly _listeners: EntryAddedCallback[] = [];
  private _listElement: HTMLUListElement | null = null;
  private _containerElement: HTMLElement | null = null;
  private _provenanceElement: HTMLElement | null = null;

  /**
   * Mount the trace panel into the given container element.
   * Creates the full DOM subtree with header and scrollable list.
   *
   * DOM structure:
   *   <div class="action-trace-panel" role="log" aria-label="...">
   *     <div class="action-trace-header">
   *       <span>Action Trace</span>
   *       <button>Clear</button>
   *     </div>
   *     <ul class="action-trace-list" aria-live="polite">
   *       <!-- entries appended here -->
   *     </ul>
   *   </div>
   */
  mount(container: HTMLElement): void {
    this._containerElement = container;

    const panel = document.createElement("div");
    panel.className = "action-trace-panel";
    panel.setAttribute("role", "log");
    panel.setAttribute("aria-label", "AI agent action trace");

    // Header
    const header = document.createElement("div");
    header.className = "action-trace-header";

    const title = document.createElement("span");
    title.textContent = "Action Trace";
    header.appendChild(title);

    const clearBtn = document.createElement("button");
    clearBtn.textContent = "Clear";
    clearBtn.setAttribute("aria-label", "Clear action trace");
    clearBtn.addEventListener("click", () => this.clearEntries());
    header.appendChild(clearBtn);

    panel.appendChild(header);

    // Scrollable list
    const list = document.createElement("ul");
    list.className = "action-trace-list";
    list.setAttribute("aria-live", "polite");
    list.setAttribute("aria-relevant", "additions");
    this._listElement = list;
    panel.appendChild(list);

    container.appendChild(panel);
  }

  /**
   * Append a new trace entry to the panel.
   * If the entry limit is exceeded, the oldest entry is evicted.
   * The panel auto-scrolls to the newly added entry.
   */
  addEntry(entry: ActionTraceEntry): void {
    // Validate entry structure defensively
    if (!entry.id || !entry.action_type || !entry.description) {
      console.warn("[ActionTracePanel] Rejected malformed entry:", entry);
      return;
    }

    this._entries.push(entry);

    // Evict oldest if over limit
    if (this._entries.length > MAX_ENTRIES) {
      const evicted = this._entries.shift();
      if (evicted && this._listElement) {
        const firstChild = this._listElement.firstElementChild;
        if (firstChild) {
          this._listElement.removeChild(firstChild);
        }
      }
    }

    // Render DOM element
    if (this._listElement) {
      const li = this._renderEntry(entry);
      this._listElement.appendChild(li);
      this._autoScroll();
    }

    // Notify listeners
    for (const listener of this._listeners) {
      try {
        listener(entry);
      } catch (err) {
        console.error("[ActionTracePanel] Listener error:", err);
      }
    }
  }

  /**
   * Update an existing entry's status and duration.
   * Useful for transitioning an entry from "pending" to "success"/"error"
   * once the action completes.
   */
  updateEntry(
    id: string,
    updates: { status?: ActionStatus; duration_ms?: number }
  ): void {
    const entry = this._entries.find((e) => e.id === id);
    if (!entry) {
      return;
    }

    if (updates.status !== undefined) {
      entry.status = updates.status;
    }
    if (updates.duration_ms !== undefined) {
      entry.duration_ms = updates.duration_ms;
    }

    // Re-render the specific DOM element
    if (this._listElement) {
      const existingLi = this._listElement.querySelector(
        `[data-trace-id="${CSS.escape(id)}"]`
      );
      if (existingLi) {
        const newLi = this._renderEntry(entry);
        // Preserve the appear animation state
        newLi.style.opacity = "1";
        newLi.style.transform = "translateY(0)";
        newLi.style.animation = "none";
        this._listElement.replaceChild(newLi, existingLi);
      }
    }
  }

  /** Remove all entries from the panel and DOM. */
  clearEntries(): void {
    this._entries.length = 0;
    if (this._listElement) {
      this._listElement.innerHTML = "";
    }
  }

  /** Return a shallow copy of all current entries. */
  getEntries(): ActionTraceEntry[] {
    return [...this._entries];
  }

  /**
   * Render the safe per-turn provenance summary (§11.2 step 19) into the panel.
   * Idempotent: replaces any prior summary. Shows only non-sensitive metadata.
   *
   * Renders the one-line summary plus, when the D30/D31 ledger slices are present,
   * a SAFE structured block of labeled chips (route, grounded, confidence,
   * materialization id/type/status). Only the projected fields defined on
   * Determinant/MaterializationProvenance are read — never raw hashes or content.
   */
  setProvenance(p: TurnProvenance): void {
    if (!this._containerElement) {
      return;
    }
    const panel = this._containerElement.querySelector(".action-trace-panel");
    if (!panel) {
      return;
    }
    const summary = document.createElement("div");
    summary.className = "action-trace-provenance";
    summary.setAttribute("role", "status");
    summary.setAttribute("aria-label", "Response provenance");

    // Line 1: compact single-line summary (D30/D31 aware).
    const line = document.createElement("div");
    line.className = "provenance-summary-line";
    line.textContent = formatProvenance(p);
    summary.appendChild(line);

    // Line 2+: SAFE structured chips when ledger slices are present.
    const chips = this._renderProvenanceChips(p);
    if (chips) {
      summary.appendChild(chips);
    }

    if (p.degraded) {
      summary.classList.add("degraded");
      summary.setAttribute("title", "Pipeline ran in degraded mode");
    }
    if (this._provenanceElement && this._provenanceElement.parentElement) {
      this._provenanceElement.parentElement.replaceChild(summary, this._provenanceElement);
    } else {
      panel.appendChild(summary);
    }
    this._provenanceElement = summary;
  }

  /**
   * Build a SAFE chip row from the D30/D31 ledger projections. Returns null when no
   * ledger slice is present (legacy/partial records render only the summary line).
   * Each chip is a labeled span; only projected, non-sensitive fields are read.
   */
  private _renderProvenanceChips(p: TurnProvenance): HTMLElement | null {
    const chipSpecs: Array<{ label: string; value: string; tone?: string }> = [];

    if (p.determinant) {
      const d = p.determinant;
      chipSpecs.push({ label: "route", value: d.selected_route });
      if (typeof d.confidence === "number") {
        chipSpecs.push({ label: "confidence", value: d.confidence.toFixed(2) });
      }
      if (typeof d.replayable === "boolean") {
        chipSpecs.push({
          label: "replay",
          value: d.replayable ? "deterministic" : "non-replayable",
          tone: d.replayable ? "ok" : "warn",
        });
      }
      if (d.route_policy_digest) {
        chipSpecs.push({ label: "policy", value: d.route_policy_digest });
      }
    }

    if (typeof p.grounded === "boolean") {
      chipSpecs.push({
        label: "grounded",
        value: p.grounded ? "yes" : "no",
        tone: p.grounded ? "ok" : "warn",
      });
    }

    if (p.materialization) {
      const m = p.materialization;
      chipSpecs.push({ label: "materialization", value: m.materialization_id });
      chipSpecs.push({ label: "type", value: m.materialization_type });
      chipSpecs.push({
        label: "status",
        value: m.status,
        tone: m.status === "committed" ? "ok" : m.status === "rolled_back" || m.status === "revoked" ? "warn" : undefined,
      });
      if (m.privacy_class) {
        chipSpecs.push({ label: "privacy", value: m.privacy_class });
      }
      if (m.source_digest) {
        chipSpecs.push({ label: "source", value: m.source_digest });
      }
    }

    if (chipSpecs.length === 0) {
      return null;
    }

    const row = document.createElement("div");
    row.className = "provenance-chips";
    row.setAttribute("role", "group");
    row.setAttribute("aria-label", "Turn provenance ledger");

    for (const spec of chipSpecs) {
      const chip = document.createElement("span");
      chip.className = "provenance-chip";
      if (spec.tone) {
        chip.classList.add(`provenance-chip-${spec.tone}`);
      }
      chip.setAttribute("aria-label", `${spec.label}: ${spec.value}`);

      const key = document.createElement("span");
      key.className = "provenance-chip-key";
      key.textContent = spec.label;
      chip.appendChild(key);

      const val = document.createElement("span");
      val.className = "provenance-chip-value";
      val.textContent = spec.value;
      chip.appendChild(val);

      row.appendChild(chip);
    }
    return row;
  }

  /**
   * Register a callback invoked each time a new entry is added.
   * Returns a teardown function that removes the listener.
   */
  onEntryAdded(callback: EntryAddedCallback): () => void {
    this._listeners.push(callback);
    return () => {
      const index = this._listeners.indexOf(callback);
      if (index !== -1) {
        this._listeners.splice(index, 1);
      }
    };
  }

  /** Unmount the panel from the DOM and clear internal state. */
  unmount(): void {
    if (this._containerElement) {
      const panel = this._containerElement.querySelector(
        ".action-trace-panel"
      );
      if (panel) {
        this._containerElement.removeChild(panel);
      }
    }
    this._listElement = null;
    this._containerElement = null;
    this._entries.length = 0;
    this._listeners.length = 0;
  }

  // -- Private helpers ----------------------------------------------------

  /**
   * Render a single ActionTraceEntry to an <li> element.
   *
   * Structure:
   *   <li class="action-trace-entry" data-trace-id="..." aria-label="...">
   *     <span class="trace-type-badge type-{action_type}">{action_type}</span>
   *     <span class="trace-description">{description}</span>
   *     <span class="trace-meta">
   *       <span class="trace-status-dot status-{status}"></span>
   *       <span>{duration_ms}ms</span>
   *     </span>
   *   </li>
   */
  private _renderEntry(entry: ActionTraceEntry): HTMLLIElement {
    const li = document.createElement("li");
    li.className = "action-trace-entry";
    li.setAttribute("data-trace-id", entry.id);

    // Build accessible label
    const timeStr = new Date(entry.timestamp).toLocaleTimeString();
    const durationStr =
      entry.duration_ms !== undefined ? ` in ${entry.duration_ms}ms` : "";
    li.setAttribute(
      "aria-label",
      `${entry.action_type}: ${entry.description}, ${entry.status}${durationStr}, at ${timeStr}`
    );

    // Type badge
    const badge = document.createElement("span");
    badge.className = `trace-type-badge type-${entry.action_type}`;
    badge.textContent = entry.action_type;
    li.appendChild(badge);

    // Description
    const desc = document.createElement("span");
    desc.className = "trace-description";
    desc.textContent = entry.description;
    desc.setAttribute("title", entry.description); // tooltip for truncated text
    li.appendChild(desc);

    // Meta: status dot + duration
    const meta = document.createElement("span");
    meta.className = "trace-meta";

    const dot = document.createElement("span");
    dot.className = `trace-status-dot status-${entry.status}`;
    dot.setAttribute("aria-hidden", "true");
    meta.appendChild(dot);

    if (entry.duration_ms !== undefined) {
      const dur = document.createElement("span");
      dur.textContent = `${entry.duration_ms}ms`;
      meta.appendChild(dur);
    } else if (entry.status === "pending") {
      const pending = document.createElement("span");
      pending.textContent = "...";
      meta.appendChild(pending);
    }

    li.appendChild(meta);

    return li;
  }

  /** Scroll the list to the bottom to show the most recent entry. */
  private _autoScroll(): void {
    if (this._listElement) {
      // Use requestAnimationFrame to ensure the DOM has updated
      requestAnimationFrame(() => {
        if (this._listElement) {
          this._listElement.scrollTop = this._listElement.scrollHeight;
        }
      });
    }
  }
}
