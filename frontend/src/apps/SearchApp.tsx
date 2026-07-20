/* Global Search — one query across documents, RAG passages, entities,
   structured SQL tables and your own chat history. Click a result to jump
   into the right app. */
import { Database, FileText, Loader2, MessageSquare, Search, Share2 } from "lucide-react";
import { useRef, useState } from "react";
import { apiSearch, type SearchResults } from "../lib/api";
import { useOS } from "../store";

const FILTERS = ["all", "documents", "passages", "entities", "tables", "messages"] as const;
type Filter = (typeof FILTERS)[number];

export default function SearchApp() {
  const open = useOS((s) => s.open);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<SearchResults | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const timer = useRef(0);

  function onChange(v: string) {
    setQ(v);
    window.clearTimeout(timer.current);
    if (v.trim().length < 2) { setRes(null); return; }
    timer.current = window.setTimeout(() => void run(v.trim()), 350);
  }
  async function run(query: string) {
    setBusy(true);
    try { setRes(await apiSearch(query)); } finally { setBusy(false); }
  }
  const show = (k: Exclude<Filter, "all">) => filter === "all" || filter === k;
  const total = res ? res.documents.length + res.passages.length + res.entities.length + res.tables.length + res.messages.length : 0;

  return (
    <div className="app-pane">
      <div className="app-toolbar" style={{ gap: 10 }}>
        <div className="field" style={{ flex: 1, display: "flex", alignItems: "center", gap: 8 }}>
          <Search size={14} style={{ color: "var(--accent)", flexShrink: 0 }} />
          <input autoFocus value={q} onChange={(e) => onChange(e.target.value)}
                 placeholder="Search documents, passages, entities, tables, chats…" aria-label="Global search" />
          {busy && <Loader2 size={13} className="spin" />}
        </div>
      </div>
      <div style={{ display: "flex", gap: 6, padding: "8px 14px 0", flexWrap: "wrap" }}>
        {FILTERS.map((f) => <button key={f} className={`btn sm ${filter === f ? "primary" : ""}`} onClick={() => setFilter(f)}>{f}</button>)}
        {res && <span className="faint" style={{ fontSize: 11, marginLeft: "auto", alignSelf: "center" }}>{total} result(s) for “{res.query}”</span>}
      </div>

      <div className="app-content" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {!res && <div className="empty"><Search size={26} /><p style={{ margin: 0 }}>Enterprise search across everything EAIOS knows.<br /><span className="faint" style={{ fontSize: 12 }}>Try “policy”, “revenue”, or a person's name.</span></p></div>}

        {res && show("documents") && res.documents.length > 0 && (
          <div><div className="palette-section">Documents</div>
            {res.documents.map((d) => (
              <button key={d.id} className="sr-row" onClick={() => open("knowledge")}>
                <FileText size={14} /><span>{d.title}</span><span className="pill dim">{d.doc_type}</span><span className="pill dim">{d.status}</span>
              </button>))}
          </div>)}

        {res && show("passages") && res.passages.length > 0 && (
          <div><div className="palette-section">Passages (hybrid RAG)</div>
            {res.passages.map((p, i) => (
              <button key={i} className="sr-row" style={{ alignItems: "flex-start" }} onClick={() => open("knowledge")}>
                <FileText size={14} style={{ marginTop: 2 }} />
                <span style={{ textAlign: "left" }}><b style={{ fontSize: 12 }}>{p.title}</b> <span className="pill dim">{Math.round(p.score * 100)}%</span><br />
                  <span className="faint" style={{ fontSize: 11.5 }}>{p.text}</span></span>
              </button>))}
          </div>)}

        {res && show("entities") && res.entities.length > 0 && (
          <div><div className="palette-section">Knowledge-graph entities</div>
            {res.entities.map((e) => (
              <button key={e.id} className="sr-row" onClick={() => open("graph")}>
                <Share2 size={14} /><span>{e.name}</span><span className="pill dim">{e.type}</span><span className="faint" style={{ fontSize: 11 }}>{e.mentions} mentions</span>
              </button>))}
          </div>)}

        {res && show("tables") && res.tables.length > 0 && (
          <div><div className="palette-section">Structured tables</div>
            {res.tables.map((t) => (
              <button key={t.name} className="sr-row" onClick={() => open("sql")}>
                <Database size={14} /><span className="mono" style={{ fontSize: 12 }}>{t.name}</span><span className="faint" style={{ fontSize: 11 }}>{t.source} · {t.rows} rows</span>
              </button>))}
          </div>)}

        {res && show("messages") && res.messages.length > 0 && (
          <div><div className="palette-section">Your conversations</div>
            {res.messages.map((m, i) => (
              <button key={i} className="sr-row" style={{ alignItems: "flex-start" }} onClick={() => open("chat")}>
                <MessageSquare size={14} style={{ marginTop: 2 }} />
                <span style={{ textAlign: "left" }}><b style={{ fontSize: 12 }}>{m.conversation}</b> <span className="pill dim">{m.role}</span><br />
                  <span className="faint" style={{ fontSize: 11.5 }}>{m.snippet}</span></span>
              </button>))}
          </div>)}

        {res && total === 0 && <div className="empty"><p>No matches for “{res.query}”.</p></div>}
      </div>
    </div>
  );
}
