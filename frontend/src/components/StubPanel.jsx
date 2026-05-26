import React from "react";

const s = {
  container: {
    padding: "32px 24px",
    background: "#1a1714",
    border: "1px solid #3a3128",
    borderRadius: "6px",
    textAlign: "center",
    maxWidth: "520px",
    margin: "40px auto",
  },
  badge: {
    display: "inline-block",
    padding: "4px 10px",
    background: "#2a2420",
    border: "1px solid #3a3128",
    borderRadius: "12px",
    fontSize: "0.7rem",
    color: "#7a6a55",
    marginBottom: "16px",
    letterSpacing: "0.06em",
    textTransform: "uppercase",
  },
  title: { fontSize: "1.2rem", color: "#d4af7a", marginBottom: "12px" },
  desc: { color: "#9a8a75", lineHeight: "1.7", marginBottom: "16px" },
  requires: {
    padding: "12px",
    background: "#0f0e0d",
    border: "1px solid #2a2420",
    borderRadius: "4px",
    fontSize: "0.8rem",
    color: "#7a6a55",
  },
  label: { color: "#5a4a35", marginBottom: "4px" },
};

export default function StubPanel({ feature, description, requires, phase }) {
  return (
    <div style={s.container}>
      <div style={s.badge}>Planned · {phase}</div>
      <h2 style={s.title}>{feature}</h2>
      <p style={s.desc}>{description}</p>
      <div style={s.requires}>
        <div style={s.label}>Requires</div>
        {requires}
      </div>
    </div>
  );
}
