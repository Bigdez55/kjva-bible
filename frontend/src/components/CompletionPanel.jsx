import React, { useState } from "react";

const s = {
  label: { fontSize: "0.8rem", color: "#7a6a55", marginBottom: "6px" },
  textarea: {
    width: "100%",
    minHeight: "100px",
    padding: "12px",
    background: "#1a1714",
    border: "1px solid #3a3128",
    color: "#e8dcc8",
    fontFamily: "Georgia, serif",
    fontSize: "1rem",
    lineHeight: "1.7",
    borderRadius: "4px",
    resize: "vertical",
    outline: "none",
  },
  controls: { display: "flex", gap: "16px", alignItems: "center", marginTop: "12px", flexWrap: "wrap" },
  slider: { display: "flex", flexDirection: "column", gap: "4px" },
  sliderLabel: { fontSize: "0.75rem", color: "#7a6a55" },
  input: {
    width: "120px",
    padding: "4px 8px",
    background: "#1a1714",
    border: "1px solid #3a3128",
    color: "#e8dcc8",
    fontFamily: "Georgia, serif",
    fontSize: "0.85rem",
    borderRadius: "4px",
  },
  btn: (disabled) => ({
    padding: "10px 24px",
    background: disabled ? "#2a2420" : "#8b6f3a",
    color: disabled ? "#5a4a35" : "#f0e0c0",
    border: "none",
    borderRadius: "4px",
    cursor: disabled ? "not-allowed" : "pointer",
    fontFamily: "Georgia, serif",
    fontSize: "0.875rem",
    marginLeft: "auto",
  }),
  output: {
    marginTop: "20px",
    padding: "16px",
    background: "#1a1714",
    border: "1px solid #3a3128",
    borderRadius: "4px",
    lineHeight: "1.9",
    fontSize: "1rem",
  },
  prompt: { color: "#d4af7a" },
  completion: { color: "#e8dcc8" },
  error: { color: "#c84b4b", marginTop: "12px", fontSize: "0.875rem" },
  hint: { fontSize: "0.75rem", color: "#5a4a35", marginTop: "8px" },
};

export default function CompletionPanel() {
  const [prompt, setPrompt] = useState("In the beginning God created");
  const [maxTokens, setMaxTokens] = useState(150);
  const [temperature, setTemperature] = useState(0.8);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await fetch("/api/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: prompt.trim(),
          max_new_tokens: maxTokens,
          temperature,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail?.error || err.detail || `HTTP ${res.status}`);
      }
      setResult(await res.json());
    } catch (e) {
      setError(String(e.message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={s.label}>Prompt — type a verse fragment or any KJV-style text</div>
      <textarea
        style={s.textarea}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="In the beginning..."
      />

      <div style={s.controls}>
        <div style={s.slider}>
          <div style={s.sliderLabel}>Max tokens: {maxTokens}</div>
          <input
            type="range" min={10} max={512} step={10}
            value={maxTokens}
            onChange={(e) => setMaxTokens(Number(e.target.value))}
            style={{ width: "140px" }}
          />
        </div>
        <div style={s.slider}>
          <div style={s.sliderLabel}>Temperature: {temperature.toFixed(1)}</div>
          <input
            type="range" min={0} max={2} step={0.1}
            value={temperature}
            onChange={(e) => setTemperature(Number(e.target.value))}
            style={{ width: "140px" }}
          />
        </div>
        <button style={s.btn(loading || !prompt.trim())} onClick={run} disabled={loading || !prompt.trim()}>
          {loading ? "Generating..." : "Generate"}
        </button>
      </div>

      <div style={s.hint}>
        KJVA is a byte-level model trained on KJV+Apocrypha. It generates KJV-style text — not guaranteed accurate scripture.
      </div>

      {error && (
        <div style={s.error}>
          {error}
          {error.includes("not installed") && (
            <div style={{ marginTop: "8px", fontFamily: "monospace", fontSize: "0.8rem" }}>
              cp &lt;Tokenless Models&gt;/KJVA/training/weights.safetensors models/kjva/weights.safetensors
            </div>
          )}
        </div>
      )}

      {result && (
        <div style={s.output}>
          <span style={s.prompt}>{result.prompt}</span>
          <span style={s.completion}>{result.completion}</span>
        </div>
      )}
    </div>
  );
}
