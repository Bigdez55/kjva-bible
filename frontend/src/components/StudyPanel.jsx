import React, { useEffect, useState } from "react";

const s = {
  field: { display: "flex", flexDirection: "column", gap: "4px" },
  label: { fontSize: "0.75rem", color: "#7a6a55" },
  input: {
    width: "100%", padding: "12px", background: "#1a1714", border: "1px solid #3a3128",
    color: "#e8dcc8", fontFamily: "Georgia, serif", fontSize: "1rem", borderRadius: "4px", outline: "none",
  },
  row: { display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "flex-end" },
  select: {
    padding: "10px 12px", background: "#1a1714", border: "1px solid #3a3128", color: "#e8dcc8",
    fontFamily: "Georgia, serif", fontSize: "0.9rem", borderRadius: "4px", maxWidth: "220px",
  },
  btn: (d) => ({
    padding: "12px 26px", background: d ? "#2a2420" : "#8b6f3a", color: d ? "#5a4a35" : "#f0e0c0",
    border: "none", borderRadius: "4px", cursor: d ? "not-allowed" : "pointer",
    fontFamily: "Georgia, serif", fontSize: "0.9rem", marginLeft: "auto",
  }),
  hint: { fontSize: "0.75rem", color: "#5a4a35", marginTop: "8px", lineHeight: 1.6 },
  answer: { color: "#e8dcc8", lineHeight: "1.8", padding: "14px 16px", background: "#1f1a14", border: "1px solid #4a3f2a", borderRadius: "4px", marginTop: "16px" },
  section: { color: "#d4af7a", fontSize: "0.78rem", textTransform: "uppercase", letterSpacing: "0.07em", margin: "20px 0 8px" },
  chips: { display: "flex", flexWrap: "wrap", gap: "6px" },
  chip: { fontSize: "0.78rem", color: "#b9a98f", background: "#1a1714", border: "1px solid #3a3128", borderRadius: "12px", padding: "3px 10px" },
  secName: { color: "#9a8a6a", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em", margin: "14px 0 6px", borderBottom: "1px solid #2a2420", paddingBottom: "4px" },
  card: { padding: "10px 12px", background: "#1a1714", border: "1px solid #3a3128", borderRadius: "4px", marginBottom: "8px" },
  ref: { color: "#d4af7a", fontSize: "0.82rem", marginBottom: "3px" },
  text: { color: "#e8dcc8", lineHeight: "1.65" },
  terms: { marginTop: "5px", fontSize: "0.7rem", color: "#6a8a6a" },
  exeg: { color: "#b9a98f", lineHeight: "1.7", padding: "12px 14px", background: "#161a20", border: "1px solid #2a3340", borderRadius: "4px" },
  follow: { display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "10px" },
  fbtn: { padding: "7px 14px", background: "#22201a", color: "#d4af7a", border: "1px solid #4a3f2a", borderRadius: "16px", cursor: "pointer", fontFamily: "Georgia, serif", fontSize: "0.8rem" },
  abstain: { color: "#c8a24b", padding: "14px", background: "#1a1714", border: "1px solid #3a3128", borderRadius: "4px", marginTop: "16px", lineHeight: 1.7 },
  error: { color: "#c84b4b", marginTop: "12px" },
};

function asMessage(x) {
  if (x == null) return "";
  if (typeof x === "string") return x;
  return x.reason || x.detail || x.message || JSON.stringify(x);
}

function Verse({ v }) {
  return (
    <div style={s.card}>
      <div style={s.ref}>{v.reference}</div>
      <div style={s.text}>{v.text}</div>
      {v.shared_terms?.length > 0 && <div style={s.terms}>shares: {v.shared_terms.slice(0, 6).join(", ")}</div>}
    </div>
  );
}

export default function StudyPanel() {
  const [query, setQuery] = useState("");
  const [book, setBook] = useState("");
  const [canon, setCanon] = useState("");
  const [books, setBooks] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/books").then((r) => r.json()).then(setBooks).catch(() => setBooks([]));
  }, []);

  const run = async (scope = "") => {
    if (!query.trim()) return;
    setLoading(true); setError(""); if (!scope) setData(null);
    try {
      const res = await fetch("/api/study", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), book, canon, scope }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(asMessage(d.detail) || `HTTP ${res.status}`);
      setData(d);
    } catch (e) { setError(asMessage(e.message || e)); }
    finally { setLoading(false); }
  };

  const isVerse = data && data.cross_references?.length >= 0 && data.primary?.length > 0 && data.witnesses_by_section.length === 0;

  return (
    <div>
      <div style={{ ...s.field, marginBottom: "10px" }}>
        <span style={s.label}>One box — a reference, a quote, a word, or a question. The scribe infers the rest.</span>
        <textarea rows={2} style={s.input} value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); run(); } }}
          placeholder='"enemies"  ·  "John 3:16"  ·  "the Lord is my shepherd"  ·  "what does scripture say about mercy?"' />
      </div>
      <div style={s.row}>
        <div style={s.field}>
          <span style={s.label}>Book</span>
          <select style={s.select} value={book} onChange={(e) => setBook(e.target.value)}>
            <option value="">All books</option>
            {books.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}
          </select>
        </div>
        <div style={s.field}>
          <span style={s.label}>Canon</span>
          <select style={s.select} value={canon} onChange={(e) => setCanon(e.target.value)}>
            <option value="">All</option>
            <option value="ot">Old Testament</option>
            <option value="nt">New Testament</option>
            <option value="apocrypha">Apocrypha</option>
          </select>
        </div>
        <button style={s.btn(loading || !query.trim())} onClick={() => run()} disabled={loading || !query.trim()}>
          {loading ? "Studying..." : "Study"}
        </button>
      </div>
      <div style={s.hint}>
        Reference → exact verse + cross-references. Word/topic → related terms + witnesses grouped across
        the canon (Torah → Apocrypha). Every verse is real scripture; nothing is generated. Unresolvable
        references <em>abstain</em>.
      </div>

      {error && <div style={s.error}>{error}</div>}

      {data && data.status === "FOUND" && (
        <>
          {data.answer && <div style={s.answer}>{data.answer}</div>}

          {/* Grounded Q&A block (question / explanation intents) */}
          {data.qa && (
            <>
              <div style={s.section}>Answer</div>
              <div style={s.exeg}>{data.qa.answer}</div>
              {data.qa.witnesses?.length > 0 && (
                <>
                  <div style={s.section}>Scripture witnesses</div>
                  {data.qa.witnesses.map((w) => <Verse key={w.reference} v={w} />)}
                  <div style={{ ...s.exeg, marginTop: "8px", fontSize: "0.85rem", color: "#8a7a60" }}>{data.qa.explanation}</div>
                </>
              )}
            </>
          )}

          {/* Reference / quote: exact verse + cross-references */}
          {isVerse && (
            <>
              <div style={s.section}>Scripture</div>
              {data.primary.map((v) => <Verse key={v.reference} v={v} />)}
              {data.cross_references.length > 0 && (
                <>
                  <div style={s.section}>Cross-references (lexical/topical) · {data.cross_references.length}</div>
                  {data.cross_references.map((v) => <Verse key={v.reference} v={v} />)}
                </>
              )}
            </>
          )}

          {/* Topic / word / question: related terms + canon-grouped witnesses */}
          {data.related_terms?.length > 0 && (
            <>
              <div style={s.section}>Related terms</div>
              <div style={s.chips}>{data.related_terms.map((t) => <span key={t} style={s.chip}>{t}</span>)}</div>
            </>
          )}
          {data.witnesses_by_section?.length > 0 && (
            <>
              <div style={s.section}>Scripture witnesses across the canon</div>
              {data.witnesses_by_section.map((g) => (
                <div key={g.section}>
                  <div style={s.secName}>{g.name} · {g.verses.length}</div>
                  {g.verses.slice(0, 6).map((v) => <Verse key={v.reference} v={v} />)}
                </div>
              ))}
            </>
          )}

          {data.exegesis && (
            <>
              <div style={s.section}>Exegetical breakdown</div>
              <div style={s.exeg}>
                {data.exegesis.definition && <div>{data.exegesis.definition}</div>}
                {data.exegesis.synthesis && <div style={{ marginTop: "8px" }}>{data.exegesis.synthesis}</div>}
                {data.exegesis.key_terms?.length > 0 && <div style={{ marginTop: "8px" }}>Key terms: {data.exegesis.key_terms.join(", ")}</div>}
                {data.exegesis.takeaway && <div style={{ marginTop: "8px", color: "#8a7a60", fontSize: "0.85rem" }}>{data.exegesis.takeaway}</div>}
              </div>
            </>
          )}

          {data.follow_up?.length > 0 && (
            <>
              <div style={s.section}>Narrow the scope</div>
              <div style={s.follow}>
                {data.follow_up.map((f) => (
                  <button key={f.scope} style={s.fbtn} onClick={() => run(f.scope === "full" ? "" : f.scope)}>{f.label}</button>
                ))}
              </div>
            </>
          )}
        </>
      )}

      {data && data.status !== "FOUND" && (
        <div style={s.abstain}>
          {asMessage(data.reason) || "No grounded scripture match."}
          {data.related_terms?.length > 0 && <div style={{ ...s.chips, marginTop: "10px" }}>{data.related_terms.map((t) => <span key={t} style={s.chip}>{t}</span>)}</div>}
        </div>
      )}
    </div>
  );
}
