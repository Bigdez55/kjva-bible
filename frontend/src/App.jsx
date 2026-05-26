import React, { useState } from "react";
import VerseBrowser from "./components/VerseBrowser";
import CompletionPanel from "./components/CompletionPanel";
import StubPanel from "./components/StubPanel";

const TABS = [
  { id: "browse",   label: "Browse" },
  { id: "complete", label: "Completion" },
  { id: "search",   label: "Search" },
  { id: "qa",       label: "Q&A" },
  { id: "xref",     label: "Cross-Reference" },
];

const styles = {
  header: {
    background: "#1a1714",
    borderBottom: "1px solid #3a3128",
    padding: "16px 24px",
    display: "flex",
    alignItems: "center",
    gap: "16px",
  },
  title: {
    fontSize: "1.4rem",
    fontWeight: "normal",
    letterSpacing: "0.04em",
    color: "#d4af7a",
  },
  subtitle: {
    fontSize: "0.75rem",
    color: "#7a6a55",
    marginTop: "2px",
  },
  nav: {
    display: "flex",
    gap: "4px",
    padding: "8px 24px 0",
    background: "#1a1714",
    borderBottom: "1px solid #3a3128",
  },
  tab: (active) => ({
    padding: "8px 16px",
    background: active ? "#2a2420" : "transparent",
    border: "none",
    borderBottom: active ? "2px solid #d4af7a" : "2px solid transparent",
    color: active ? "#d4af7a" : "#7a6a55",
    cursor: "pointer",
    fontSize: "0.875rem",
    fontFamily: "Georgia, serif",
    transition: "color 0.15s",
  }),
  content: {
    flex: 1,
    padding: "24px",
    maxWidth: "900px",
    margin: "0 auto",
    width: "100%",
  },
};

export default function App() {
  const [activeTab, setActiveTab] = useState("browse");

  return (
    <>
      <header style={styles.header}>
        <div>
          <h1 style={styles.title}>KJVA Bible</h1>
          <div style={styles.subtitle}>King James Version · KJVA AI Model (18M params)</div>
        </div>
      </header>

      <nav style={styles.nav}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            style={styles.tab(activeTab === tab.id)}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <main style={styles.content}>
        {activeTab === "browse"   && <VerseBrowser />}
        {activeTab === "complete" && <CompletionPanel />}
        {activeTab === "search"   && (
          <StubPanel
            feature="Semantic Search"
            description="Find verses by meaning, not just keywords."
            requires="a sentence-embedding adapter trained on KJVA"
            phase="Phase 2"
          />
        )}
        {activeTab === "qa" && (
          <StubPanel
            feature="Q&A / Commentary"
            description="Ask questions and receive scripture-grounded answers."
            requires="an SFT instruction-tuning adapter trained on KJVA"
            phase="Phase 3"
          />
        )}
        {activeTab === "xref" && (
          <StubPanel
            feature="Cross-Reference"
            description="Surface related passages and thematic connections."
            requires="an embedding similarity index or precomputed reference graph"
            phase="Phase 4"
          />
        )}
      </main>
    </>
  );
}
