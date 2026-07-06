import { FileSpreadsheet, FileText, Image, Layers, Presentation, Search, Upload, X } from "lucide-react";
import { useMemo, useState } from "react";
import { DOCS, fmtBytes } from "../lib/mock";
import type { Doc } from "../types";

const TYPE_ICON: Record<string, { icon: React.ReactNode; hue: number }> = {
  pdf: { icon: <FileText size={17} />, hue: 2 },
  docx: { icon: <FileText size={17} />, hue: 215 },
  xlsx: { icon: <FileSpreadsheet size={17} />, hue: 145 },
  csv: { icon: <FileSpreadsheet size={17} />, hue: 160 },
  pptx: { icon: <Presentation size={17} />, hue: 25 },
  image: { icon: <Image size={17} />, hue: 280 },
  txt: { icon: <FileText size={17} />, hue: 190 },
};

const PIPELINE = ["Upload", "Layout detection", "OCR", "Table extraction", "Chunking", "Embeddings", "Indexed"];

const STATUS_PILL: Record<Doc["status"], string> = { indexed: "good", processing: "warn", queued: "dim", failed: "bad" };

let uploadCounter = 0;

export default function KnowledgeApp() {
  const [docs, setDocs] = useState<Doc[]>(DOCS);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Doc | null>(null);

  const filtered = useMemo(
    () =>
      docs.filter(
        (d) =>
          d.title.toLowerCase().includes(query.toLowerCase()) ||
          d.tags.some((t) => t.includes(query.toLowerCase()))
      ),
    [docs, query]
  );

  const indexedCount = docs.filter((d) => d.status === "indexed").length;
  const totalChunks = docs.reduce((sum, d) => sum + d.chunk_count, 0);

  function simulateUpload() {
    uploadCounter += 1;
    const id = `up-${uploadCounter}`;
    const doc: Doc = {
      id,
      title: `Uploaded Document ${uploadCounter}`,
      filename: `upload_${uploadCounter}.pdf`,
      doc_type: "pdf",
      status: "processing",
      chunk_count: 0,
      size_bytes: 700_000 + Math.floor(Math.random() * 2_000_000),
      created_at: new Date().toISOString().slice(0, 10),
      owner: "You",
      tags: ["new"],
    };
    setQuery("");  // make the new upload visible even mid-search
    setDocs((d) => [doc, ...d]);
    setTimeout(() => {
      setDocs((all) =>
        all.map((d) => (d.id === id ? { ...d, status: "indexed" as const, chunk_count: 8 + Math.floor(Math.random() * 40) } : d))
      );
    }, 3200);
  }

  return (
    <div className="app-pane" style={{ flexDirection: "row" }}>
      <div className="app-pane">
        <div className="app-toolbar">
          <div className="field" style={{ flex: 1, maxWidth: 300, padding: "6px 11px" }}>
            <Search size={14} className="faint" />
            <input placeholder="Search documents & tags…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search documents" />
          </div>
          <span className="pill info"><Layers size={11} /> {totalChunks} chunks</span>
          <span className="pill good">{indexedCount}/{docs.length} indexed</span>
          <button className="btn primary sm" style={{ marginLeft: "auto" }} onClick={simulateUpload}>
            <Upload size={13} /> Upload
          </button>
        </div>

        {/* RAG pipeline strip */}
        <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "10px 16px", borderBottom: "1px solid var(--hairline)", overflowX: "auto" }}>
          {PIPELINE.map((stage, i) => (
            <span key={stage} style={{ display: "flex", alignItems: "center", gap: 4, flex: "none" }}>
              {i > 0 && <span className="faint" aria-hidden>→</span>}
              <span className="plan-chip" style={i === PIPELINE.length - 1 ? { color: "var(--good)", borderColor: "rgba(52,211,153,.3)" } : {}}>
                {stage}
              </span>
            </span>
          ))}
        </div>

        <div className="app-content">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(215px, 1fr))", gap: 12 }}>
            {filtered.map((doc) => {
              const t = TYPE_ICON[doc.doc_type] ?? TYPE_ICON.txt;
              return (
                <button
                  key={doc.id}
                  className="card hover"
                  style={{ textAlign: "left", cursor: "pointer", display: "flex", flexDirection: "column", gap: 9 }}
                  onClick={() => setSelected(doc)}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div className="app-icon md" style={{ "--hue": t.hue } as React.CSSProperties}>{t.icon}</div>
                    <span className={`pill ${STATUS_PILL[doc.status]}`}>
                      {doc.status === "processing" && <span className="dot pulse" style={{ width: 5, height: 5, background: "var(--warn)" }} />}
                      {doc.status}
                    </span>
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13, lineHeight: 1.3 }}>{doc.title}</div>
                    <div className="faint" style={{ fontSize: 11, marginTop: 3 }}>
                      {doc.doc_type.toUpperCase()} · {fmtBytes(doc.size_bytes)} · {doc.chunk_count} chunks
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                    {doc.tags.map((t2) => <span key={t2} className="pill dim">{t2}</span>)}
                  </div>
                </button>
              );
            })}
          </div>
          {filtered.length === 0 && <div className="empty">No documents match “{query}”.</div>}
        </div>
      </div>

      {selected && (
        <aside className="app-sidebar" style={{ width: 265, borderRight: "none", borderLeft: "1px solid var(--hairline)", padding: 16, gap: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 className="h-display" style={{ fontSize: 14 }}>Document details</h3>
            <button className="mb-item" onClick={() => setSelected(null)} aria-label="Close details"><X size={14} /></button>
          </div>
          <div style={{ fontWeight: 600 }}>{selected.title}</div>
          <div className="faint mono" style={{ fontSize: 11 }}>{selected.filename}</div>
          {([
            ["Status", selected.status],
            ["Chunks", String(selected.chunk_count)],
            ["Size", fmtBytes(selected.size_bytes)],
            ["Uploaded", selected.created_at],
            ["Owner", selected.owner],
          ] as const).map(([k, v]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, borderBottom: "1px solid rgba(148,163,184,.08)", padding: "6px 0" }}>
              <span className="faint">{k}</span>
              <span className="muted">{v}</span>
            </div>
          ))}
          <div>
            <div className="palette-section" style={{ padding: "4px 0" }}>Sample chunk</div>
            <div className="code-block" style={{ fontSize: 11, maxHeight: 130, overflowY: "auto" }}>
              {selected.status === "indexed"
                ? `[${selected.title} · chunk 1/${selected.chunk_count}] ` +
                  "Semantic chunk with section metadata, page anchor, and a 384-dim embedding stored in the vector index for hybrid retrieval…"
                : "Not indexed yet — chunks appear once the pipeline completes."}
            </div>
          </div>
          <button className="btn sm" style={{ justifyContent: "center" }}>Re-run pipeline</button>
        </aside>
      )}
    </div>
  );
}
