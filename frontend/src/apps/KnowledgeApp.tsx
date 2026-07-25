import { Camera, FileSpreadsheet, FileText, Image, Layers, Loader2, Presentation, ScanSearch, Search, Trash2, Upload, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiAnalyze, apiDeleteDocument, apiDocuments, apiUploadDocument, isSupportedFile, UPLOAD_ACCEPT, type AnalyzeCard } from "../lib/api";
import { useOS } from "../store";
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

const ANALYZE_KINDS = [
  { id: "auto", label: "Auto" },
  { id: "resume", label: "Resume" },
  { id: "contract", label: "Contract" },
  { id: "invoice", label: "Invoice" },
] as const;

export default function KnowledgeApp() {
  const [docs, setDocs] = useState<Doc[]>(DOCS);
  const [query, setQuery] = useState("");
  // Citation jump: a chat citation chip sets this and opens Knowledge —
  // adopt it as the search filter so the cited document is front and center.
  const kq = useOS((s) => s.knowledgeQuery);
  useEffect(() => {
    if (kq) { setQuery(kq); useOS.getState().setKnowledgeQuery(""); }
  }, [kq]);
  const [selected, setSelected] = useState<Doc | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeCard | null>(null);
  const [analyzing, setAnalyzing] = useState<string | null>(null);

  /* ── real uploads ── */
  const fileRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState<{ name: string; pct: number } | null>(null);
  const [uploadErr, setUploadErr] = useState("");
  const [dragging, setDragging] = useState(false);
  const live = useOS((s) => s.live);

  // Load this workspace's real documents (demo corpus when offline).
  const refresh = useCallback(() => {
    apiDocuments().then(setDocs).catch(() => { /* keep whatever is on screen */ });
  }, []);
  useEffect(() => { refresh(); }, [refresh, live]);

  // While anything is still being parsed/indexed, poll until it settles.
  useEffect(() => {
    if (!live || !docs.some((d) => d.status === "queued" || d.status === "processing")) return;
    const t = setInterval(refresh, 2500);
    return () => clearInterval(t);
  }, [live, docs, refresh]);

  /** Open the OS file dialog. showPicker() is the modern API; .click() is the
   *  universal fallback (and what older Safari/Firefox need). */
  function openPicker(ref: React.RefObject<HTMLInputElement>) {
    const el = ref.current;
    if (!el) return;
    try {
      const withPicker = el as HTMLInputElement & { showPicker?: () => void };
      if (typeof withPicker.showPicker === "function") { withPicker.showPicker(); return; }
    } catch { /* not allowed in this context — fall through to click() */ }
    el.click();
  }

  async function uploadFiles(files: FileList | File[]) {
    const list = Array.from(files);
    if (!list.length) return;
    setUploadErr("");
    for (const file of list) {
      if (!isSupportedFile(file.name)) {
        setUploadErr(`“${file.name}” isn’t a supported file type.`);
        continue;
      }
      setUploading({ name: file.name, pct: 0 });
      try {
        const doc = await apiUploadDocument(file, (pct) => setUploading({ name: file.name, pct }));
        setQuery("");                        // make it visible even mid-search
        setDocs((all) => [doc, ...all.filter((d) => d.id !== doc.id)]);
        useOS.getState().pushFeed({ agent: "pipeline", text: `Indexing “${doc.title}”…`, kind: "index" });
      } catch (e) {
        setUploadErr(e instanceof Error ? e.message : "Upload failed");
      } finally {
        setUploading(null);
      }
    }
    refresh();
    if (fileRef.current) fileRef.current.value = "";      // allow re-picking the same file
    if (cameraRef.current) cameraRef.current.value = "";
  }

  async function removeDoc(doc: Doc) {
    try {
      await apiDeleteDocument(doc.id);
      setDocs((all) => all.filter((d) => d.id !== doc.id));
      if (selected?.id === doc.id) { setSelected(null); setAnalysis(null); }
    } catch (e) {
      setUploadErr(e instanceof Error ? e.message : "Couldn't delete that document");
    }
  }

  async function runAnalyze(kind: string) {
    if (!selected || analyzing) return;
    setAnalyzing(kind);
    setAnalysis(null);
    try {
      setAnalysis(await apiAnalyze(selected.id, kind, selected.title));
    } finally {
      setAnalyzing(null);
    }
  }

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

  return (
    <div className="app-pane" style={{ flexDirection: "row" }}>
      <div
        className={`app-pane ${dragging ? "drop-active" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files?.length) uploadFiles(e.dataTransfer.files); }}
      >
        {dragging && (
          <div className="drop-veil"><Upload size={22} /><b>Drop files to add them to your knowledge base</b>
            <span className="faint" style={{ fontSize: 11.5 }}>PDF · Word · PowerPoint · Excel · CSV · text · images</span>
          </div>
        )}
        <div className="app-toolbar">
          <div className="field" style={{ flex: 1, maxWidth: 300, padding: "6px 11px" }}>
            <Search size={14} className="faint" />
            <input placeholder="Search documents & tags…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search documents" />
          </div>
          <span className="pill info"><Layers size={11} /> {totalChunks} chunks</span>
          <span className="pill good">{indexedCount}/{docs.length} indexed</span>
          {/* Real file pickers. On phones/tablets the OS sheet offers Files,
              Photo Library and Camera; `capture` opens the camera directly. */}
          <input ref={fileRef} type="file" multiple accept={UPLOAD_ACCEPT}
                 className="sr-file" tabIndex={-1} aria-hidden data-testid="file-input"
                 onChange={(e) => e.target.files && uploadFiles(e.target.files)} />
          <input ref={cameraRef} type="file" accept="image/*" capture="environment"
                 className="sr-file" tabIndex={-1} aria-hidden data-testid="camera-input"
                 onChange={(e) => e.target.files && uploadFiles(e.target.files)} />
          <button className="btn sm mobile-only" style={{ marginLeft: "auto" }}
                  onClick={() => openPicker(cameraRef)} title="Scan a document with the camera">
            <Camera size={13} /> Scan
          </button>
          <button className="btn primary sm" data-testid="upload-btn"
                  style={{ marginLeft: "auto" }}
                  disabled={!!uploading}
                  onClick={() => openPicker(fileRef)}>
            {uploading ? <Loader2 size={13} className="spin" /> : <Upload size={13} />}
            {uploading ? `${uploading.pct}%` : "Upload"}
          </button>
        </div>

        {uploading && (
          <div className="up-bar" data-testid="upload-progress">
            <span style={{ width: `${uploading.pct}%` }} />
            <em>Uploading {uploading.name}… {uploading.pct}%</em>
          </div>
        )}
        {uploadErr && (
          <div className="pill bad" data-testid="upload-error"
               style={{ margin: "8px 16px", display: "inline-flex", alignSelf: "flex-start" }}>
            {uploadErr}
            <button className="link-btn" style={{ marginLeft: 8 }} onClick={() => setUploadErr("")}>dismiss</button>
          </div>
        )}

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
                  onClick={() => { setSelected(doc); setAnalysis(null); }}
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
          {filtered.length === 0 && (
            <div className="empty" style={{ textAlign: "center", gap: 10 }}>
              {query ? (
                <>No documents match “{query}”.</>
              ) : (
                <>
                  <Upload size={26} style={{ opacity: .5 }} />
                  <b style={{ fontSize: 14 }}>Your knowledge base is empty</b>
                  <span className="faint" style={{ fontSize: 12, maxWidth: 300 }}>
                    Add your company’s PDFs, Word docs, spreadsheets or slides — the AI answers
                    from them with citations. You can also drag files straight onto this window.
                  </span>
                  <button className="btn primary sm" onClick={() => openPicker(fileRef)}>
                    <Upload size={13} /> Upload your first document
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {selected && (
        <aside className="app-sidebar" style={{ width: 285, borderRight: "none", borderLeft: "1px solid var(--hairline)", padding: 16, gap: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 className="h-display" style={{ fontSize: 14 }}>Document details</h3>
            <span style={{ display: "flex", gap: 4 }}>
              <button className="mb-item" data-testid="delete-doc" title="Delete this document"
                      onClick={() => removeDoc(selected)} aria-label="Delete document">
                <Trash2 size={14} />
              </button>
              <button className="mb-item" onClick={() => setSelected(null)} aria-label="Close details"><X size={14} /></button>
            </span>
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
          <div>
            <div className="palette-section" style={{ padding: "4px 0", display: "flex", alignItems: "center", gap: 6 }}>
              <ScanSearch size={12} /> AI analyzer
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {ANALYZE_KINDS.map((k) => (
                <button key={k.id} className="btn sm" disabled={!!analyzing || selected.status !== "indexed"}
                        onClick={() => runAnalyze(k.id)} aria-label={`Analyze as ${k.label}`}>
                  {analyzing === k.id ? <Loader2 size={12} className="spin" /> : null} {k.label}
                </button>
              ))}
            </div>
          </div>
          {analysis && (
            <div className="scorecard">
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className={`score-ring ${analysis.score >= 75 ? "good" : analysis.score >= 50 ? "warn" : "bad"}`}>
                  {analysis.score}
                </span>
                <span style={{ minWidth: 0 }}>
                  <b style={{ fontSize: 12.5, display: "block" }}>{analysis.verdict}</b>
                  <span className="faint" style={{ fontSize: 10.5 }}>{analysis.kind} · {analysis.engine}</span>
                </span>
              </div>
              {analysis.highlights.map((h, i) => (
                <div key={i} className="score-row">
                  <span className="dot" style={{ background: h.status === "good" ? "var(--good)" : h.status === "warn" ? "var(--warn)" : "var(--bad)", marginTop: 4 }} />
                  <span style={{ minWidth: 0 }}>
                    <b style={{ fontSize: 11 }}>{h.label}</b>
                    <span style={{ display: "block", fontSize: 11.5, color: "var(--text-dim)", overflowWrap: "anywhere" }}>{h.value}</span>
                  </span>
                </div>
              ))}
              <p style={{ margin: 0, fontSize: 11.5, lineHeight: 1.55, color: "var(--text-dim)" }}>{analysis.summary}</p>
            </div>
          )}
          <button className="btn sm" style={{ justifyContent: "center" }}>Re-run pipeline</button>
        </aside>
      )}
    </div>
  );
}
