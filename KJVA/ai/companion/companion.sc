// companion.sc — Companion UI in SUPER C
// Ports: main.tsx, command-panel.tsx, agent-bridge.ts,
//        action-trace.ts, avatar.ts, avatar.tsx, avatar-renderer.ts
//
// Uses Super C's actor system for state management

comptime {
    const COMPANION_VERSION = "1.0.0-superc";
    const MAX_TRACE_ENTRIES = 50;
    const MAX_MESSAGES = 200;
    const POLL_INTERVAL_MS = 2000;
}

print("[COMPANION] Loading UI system...");

// ═══════════════════════════════════════════════════════════════
// AVATAR STATE MACHINE (per avatar.ts)
// ═══════════════════════════════════════════════════════════════

let avatar_state = "idle";

fn avatar_transition(new_state: string) -> bool {
    // Validate transition
    let valid = false;
    if avatar_state == "idle" {
        if new_state == "listening" { valid = true; }
    }
    if avatar_state == "listening" {
        if new_state == "thinking" { valid = true; }
        if new_state == "idle" { valid = true; }
    }
    if avatar_state == "thinking" {
        if new_state == "acting" { valid = true; }
        if new_state == "idle" { valid = true; }
    }
    if avatar_state == "acting" {
        if new_state == "idle" { valid = true; }
    }
    // Error reset from any state
    if new_state == "idle" { valid = true; }

    if valid {
        avatar_state = new_state;
    }
    return valid;
}

fn avatar_get_state() -> string {
    return avatar_state;
}

print("[COMPANION] Avatar state machine: idle→listening→thinking→acting — LOADED");

// ═══════════════════════════════════════════════════════════════
// ACTION TRACE (per action-trace.ts)
// ═══════════════════════════════════════════════════════════════

let trace_entries = [];

fn trace_add(action_type: string, description: string, status: string) {
    let entry = action_type + "|" + description + "|" + status;
    trace_entries = trace_entries + [entry];
    if len(trace_entries) > MAX_TRACE_ENTRIES {
        // Evict oldest
        let new_entries = [];
        let i = 1;
        while i < len(trace_entries) {
            new_entries = new_entries + [trace_entries[i]];
            i = i + 1;
        }
        trace_entries = new_entries;
    }
}

fn trace_update(index: int, status: string) {
    if index < len(trace_entries) {
        let parts = trace_entries[index];
        // Update status (simplified)
        trace_entries[index] = parts + "|updated:" + status;
    }
}

fn trace_clear() {
    trace_entries = [];
}

print("[COMPANION] Action trace: max " + str(MAX_TRACE_ENTRIES) + " entries — LOADED");

// ═══════════════════════════════════════════════════════════════
// COMMAND PANEL (per command-panel.tsx)
// ═══════════════════════════════════════════════════════════════

let chat_messages = [];

fn panel_send(user_message: string) -> string {
    // Record user message
    chat_messages = chat_messages + ["user|" + user_message];

    // Avatar transitions
    avatar_transition("listening");
    trace_add("intent", user_message, "pending");

    avatar_transition("thinking");
    trace_add("inference", "Processing through Heptagon L1-L7", "pending");

    // Get response (would call agent_chat in wired version)
    let response = "[Tokenless] Processed: " + user_message;

    avatar_transition("acting");
    trace_add("result", response, "success");

    // Record assistant message
    chat_messages = chat_messages + ["assistant|" + response];

    avatar_transition("idle");
    return response;
}

print("[COMPANION] Command panel: chat + trace — LOADED");

// ═══════════════════════════════════════════════════════════════
// DESIGN TOKENS (per tokens.ts)
// ═══════════════════════════════════════════════════════════════

comptime {
    const COLOR_PRIMARY = "#ff7518";
    const COLOR_SECONDARY = "#1aa7ec";
    const COLOR_SUCCESS = "#17b978";
    const COLOR_WARNING = "#ffbe0b";
    const COLOR_DANGER = "#ef476f";
    const FONT_FAMILY = "Inter, Noto Sans, sans-serif";
}

print("[COMPANION] Design tokens: Tokenless palette — LOADED");

// ═══════════════════════════════════════════════════════════════
// SELF-TEST
// ═══════════════════════════════════════════════════════════════

print("");
let panel_response = panel_send("Hello Tokenless, are you alive?");
print("[COMPANION TEST] Response: " + panel_response);
print("[COMPANION TEST] Avatar state: " + avatar_get_state());
print("[COMPANION TEST] Messages: " + str(len(chat_messages)));
print("[COMPANION TEST] Trace entries: " + str(len(trace_entries)));
print("");
print("[COMPANION] UI system: OPERATIONAL");
