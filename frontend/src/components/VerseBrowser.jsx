import React, { useState, useEffect } from "react";

const s = {
  row: { display: "flex", gap: "12px", marginBottom: "20px", flexWrap: "wrap" },
  select: {
    padding: "8px 12px",
    background: "#1a1714",
    border: "1px solid #3a3128",
    color: "#e8dcc8",
    fontFamily: "Georgia, serif",
    fontSize: "0.875rem",
    borderRadius: "4px",
    cursor: "pointer",
    minWidth: "160px",
  },
  verseList: { display: "flex", flexDirection: "column", gap: "0" },
  verse: (active) => ({
    padding: "12px 16px",
    background: active ? "#2a2420" : "transparent",
    borderLeft: active ? "3px solid #d4af7a" : "3px solid transparent",
    cursor: "pointer",
    transition: "background 0.1s",
  }),
  verseNum: { color: "#d4af7a", fontSize: "0.75rem", marginBottom: "4px" },
  verseText: { lineHeight: "1.7", fontSize: "1rem" },
  detail: {
    marginTop: "24px",
    padding: "20px",
    background: "#1a1714",
    border: "1px solid #3a3128",
    borderRadius: "6px",
  },
  detailRef: { color: "#d4af7a", fontSize: "1.1rem", marginBottom: "12px" },
  detailText: { lineHeight: "1.9", fontSize: "1.05rem" },
  strongs: { marginTop: "12px", fontSize: "0.75rem", color: "#7a6a55" },
  error: { color: "#c84b4b", padding: "12px" },
  loading: { color: "#7a6a55", padding: "12px" },
};

export default function VerseBrowser() {
  const [books, setBooks] = useState([]);
  const [selectedBook, setSelectedBook] = useState("");
  const [chapters, setChapters] = useState([]);
  const [selectedChapter, setSelectedChapter] = useState("");
  const [verses, setVerses] = useState([]);
  const [selectedVerse, setSelectedVerse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/books")
      .then((r) => r.json())
      .then((data) => {
        setBooks(data);
        if (data.length > 0) setSelectedBook(data[0].code);
      })
      .catch(() => setError("Could not load books. Is the backend running?"));
  }, []);

  useEffect(() => {
    if (!selectedBook) return;
    setChapters([]);
    setSelectedChapter("");
    setVerses([]);
    setSelectedVerse(null);
    fetch(`/api/chapters/${selectedBook}`)
      .then((r) => r.json())
      .then((data) => {
        setChapters(data.chapters || []);
        if (data.chapters?.length) setSelectedChapter(String(data.chapters[0]));
      })
      .catch(() => setError("Could not load chapters."));
  }, [selectedBook]);

  useEffect(() => {
    if (!selectedBook || !selectedChapter) return;
    setLoading(true);
    setVerses([]);
    setSelectedVerse(null);
    fetch(`/api/verses/${selectedBook}/${selectedChapter}`)
      .then((r) => r.json())
      .then((data) => {
        setVerses(data.verses || []);
        setLoading(false);
      })
      .catch(() => {
        setError("Could not load verses.");
        setLoading(false);
      });
  }, [selectedBook, selectedChapter]);

  const bookMeta = books.find((b) => b.code === selectedBook);

  return (
    <div>
      <div style={s.row}>
        <select
          style={s.select}
          value={selectedBook}
          onChange={(e) => setSelectedBook(e.target.value)}
        >
          {books.map((b) => (
            <option key={b.code} value={b.code}>
              {b.name}
            </option>
          ))}
        </select>

        <select
          style={s.select}
          value={selectedChapter}
          onChange={(e) => setSelectedChapter(e.target.value)}
          disabled={chapters.length === 0}
        >
          {chapters.map((c) => (
            <option key={c} value={String(c)}>
              Chapter {c}
            </option>
          ))}
        </select>
      </div>

      {bookMeta && (
        <div style={{ fontSize: "0.75rem", color: "#7a6a55", marginBottom: "16px" }}>
          {bookMeta.full_name} · {bookMeta.canon_category.replace("_", " ")}
        </div>
      )}

      {error && <div style={s.error}>{error}</div>}
      {loading && <div style={s.loading}>Loading...</div>}

      <div style={s.verseList}>
        {verses.map((v) => (
          <div
            key={v.id}
            style={s.verse(selectedVerse?.id === v.id)}
            onClick={() => setSelectedVerse(v)}
          >
            <div style={s.verseNum}>{v.chapter}:{v.verse}</div>
            <div style={s.verseText}>{v.text}</div>
          </div>
        ))}
      </div>

      {selectedVerse && (
        <div style={s.detail}>
          <div style={s.detailRef}>{selectedVerse.ref}</div>
          <div style={s.detailText}>{selectedVerse.text}</div>
          {selectedVerse.strongs?.length > 0 && (
            <div style={s.strongs}>
              Strongs: {selectedVerse.strongs.join(" · ")}
            </div>
          )}
          {selectedVerse.footnotes?.length > 0 && (
            <div style={{ ...s.strongs, marginTop: "8px" }}>
              {selectedVerse.footnotes.join(" | ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
