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
