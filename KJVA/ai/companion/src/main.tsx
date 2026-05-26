import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { colors, motion, radius, spacing, typography } from "./tokens";
import "./styles.css";

type Mood = "idle" | "listening" | "thinking" | "acting" | "celebrating" | "confused";
type TraceEntry = { at: string; text: string };

function App(): JSX.Element {
  const [input, setInput] = useState("");
  const [mood, setMood] = useState<Mood>("idle");
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [enabled, setEnabled] = useState(true);

  const proactivePrompt = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) return "Morning focus mode active. Need a priority list?";
    if (hour < 18) return "Looks like a heavy work block. Want a quick summary?";
    return "Evening wrap-up detected. Need a progress recap?";
  }, []);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const timer = setTimeout(() => {
      setTrace((current) => [{ at: new Date().toISOString(), text: proactivePrompt }, ...current].slice(0, 20));
    }, 6000);
    return () => clearTimeout(timer);
  }, [enabled, proactivePrompt]);

  const send = async (): Promise<void> => {
    if (!input.trim()) {
      return;
    }
    setMood("listening");
    setTrace((current) => [{ at: new Date().toISOString(), text: `You: ${input}` }, ...current].slice(0, 20));
    setMood("thinking");
    try {
      const reply = await window.companion.ask("desktop-user", input);
      setMood("acting");
      setTrace((current) => [{ at: new Date().toISOString(), text: `Companion: ${reply.response}` }, ...current].slice(0, 20));
      setMood("celebrating");
    } catch {
      setMood("confused");
      setTrace((current) => [{ at: new Date().toISOString(), text: "Companion: I hit an issue while processing that." }, ...current].slice(0, 20));
    } finally {
      setInput("");
      setTimeout(() => setMood("idle"), 1200);
    }
  };

  return (
    <main className={`companion ${mood}`}>
      <section className="avatar" aria-label={`Companion avatar — current mood: ${mood}`}>
        <div className="head" />
        <div className="label">{mood}</div>
      </section>

      <section className="panel" aria-label="Companion command panel">
        <textarea
          aria-label="Ask a question or give a command"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              send().catch(() => undefined);
            }
          }}
          placeholder="Ask me to open apps, summarize, or automate tasks"
        />

        <div className="row">
          <button
            onClick={() => send().catch(() => undefined)}
            aria-label="Send message to Companion"
            aria-busy={mood === "thinking" || mood === "listening"}
            disabled={!input.trim() || mood === "thinking"}
            style={{
              background: colors.primary,
              borderColor: colors.primary,
              color: colors.neutral0,
              fontWeight: typography.weight.semibold,
              minWidth: "80px",
              transition: `background ${motion.fast}`
            }}
          >
            {mood === "thinking" ? "Thinking…" : "Send"}
          </button>
          <button
            aria-label="Fill input: open the browser"
            onClick={() => setInput("open the browser")}
          >
            open the browser
          </button>
          <button
            aria-label="Fill input: create a note"
            onClick={() => setInput("create a note called Hello")}
          >
            create note
          </button>
          <button
            aria-label="Fill input: what did I just do"
            onClick={() => setInput("what did I just do?")}
          >
            what did I do?
          </button>
        </div>

        <div className="row">
          <button
            aria-label={enabled ? "Disable proactive suggestions" : "Enable proactive suggestions"}
            aria-pressed={enabled}
            onClick={() => setEnabled((v) => !v)}
            style={{
              borderColor: enabled ? colors.secondary : colors.neutral300,
              color: enabled ? colors.secondary : colors.neutral900
            }}
          >
            {enabled ? "disable proactive" : "enable proactive"}
          </button>
          <button
            aria-label="Dismiss Companion panel"
            onClick={() => window.companion.dismiss().catch(() => undefined)}
          >
            dismiss
          </button>
          <button
            aria-label="Clear action trace"
            onClick={() => setTrace([])}
          >
            clear trace
          </button>
        </div>

        <ul aria-label="Action trace — most recent first" aria-live="polite" aria-atomic="false">
          {trace.map((entry) => (
            <li key={`${entry.at}-${entry.text}`}>
              <span
                aria-label="Timestamp"
                style={{ fontSize: typography.scale.xs, opacity: 0.45, marginRight: spacing.x2 }}
              >
                {new Date(entry.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
              {entry.text}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(<App />);
}
