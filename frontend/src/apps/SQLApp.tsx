import { ChevronDown, ChevronRight, Database, FileSpreadsheet, Play, ShieldCheck, Table2 } from "lucide-react";
import { useEffect, useState } from "react";
import { apiSchema, apiSql, type SchemaTable, type SQLResult } from "../lib/api";
import { useOS } from "../store";

const KEYWORDS = /\b(SELECT|FROM|WHERE|GROUP|BY|ORDER|LIMIT|AS|COUNT|AVG|SUM|ROUND|DESC|ASC|JOIN|ON)\b/g;

function Highlight({ sql }: { sql: string }) {
  const parts = sql.split(KEYWORDS);
  return (
    <>
      {parts.map((part, i) =>
        KEYWORDS.test(`\b${part}\b`) || ["SELECT","FROM","WHERE","GROUP","BY","ORDER","LIMIT","AS","COUNT","AVG","SUM","ROUND","DESC","ASC","JOIN","ON"].includes(part)
          ? <span key={i} className="kw">{part}</span>
          : <span key={i}>{part}</span>
      )}
    </>
  );
}

const EXAMPLES = ["Documents by type", "Agent runs with average latency", "How many users do we have?", "Latest documents"];

export default function SQLApp() {
  const live = useOS((s) => s.live);
  const [question, setQuestion] = useState("");
  const [schema, setSchema] = useState<SchemaTable[]>([]);
  const [openTables, setOpenTables] = useState<Set<string>>(new Set(["documents"]));
  const [result, setResult] = useState<SQLResult | null>(null);
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<string[]>([]);

  useEffect(() => {
    let alive = true;
    apiSchema().then((s) => alive && setSchema(s)).catch(() => {});
    return () => { alive = false; };
  }, [live]);

  function toggleTable(name: string) {
    setOpenTables((s) => {
      const next = new Set(s);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  async function run(q: string) {
    const clean = q.trim();
    if (!clean) return;
    setRunning(true);
    setResult(null);
    try {
      setResult(await apiSql(clean));
      setHistory((h) => [clean, ...h.filter((x) => x !== clean)].slice(0, 6));
    } catch {
      setResult({ sql: "", explanation: "The SQL service is unreachable right now.", warning: "request failed", columns: [], rows: [] });
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="app-pane" style={{ flexDirection: "row" }}>
      <aside className="app-sidebar" style={{ padding: "12px 8px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "0 8px 10px" }}>
          <Database size={14} style={{ color: "var(--good)" }} />
          <span style={{ fontWeight: 600, fontSize: 12.5 }}>eaios · {live ? "live" : "demo"}</span>
        </div>
        {schema.map((t) => (
          <div key={t.table}>
            <button className="tree-item" onClick={() => toggleTable(t.table)} title={t.source ? `Extracted from: ${t.source}` : undefined}>
              {openTables.has(t.table) ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              {t.source
                ? <FileSpreadsheet size={12} style={{ color: "#a78bfa" }} />
                : <Table2 size={12} style={{ color: "#67e8f9" }} />}
              {t.table}
              <span className="faint" style={{ marginLeft: "auto", fontSize: 10 }}>{t.rows}</span>
            </button>
            {openTables.has(t.table) && t.source && (
              <div className="tree-item" style={{ paddingLeft: 34, fontSize: 10.5, color: "#a78bfa" }}>⇪ {t.source}</div>
            )}
            {openTables.has(t.table) &&
              t.columns.map((c) => (
                <div key={c} className="tree-item" style={{ paddingLeft: 34, fontSize: 11.5, color: "var(--text-faint)" }}>{c}</div>
              ))}
          </div>
        ))}
        {history.length > 0 && (
          <>
            <div className="palette-section">History</div>
            {history.map((h) => (
              <button key={h} className="tree-item" style={{ fontFamily: "var(--font-ui)", fontSize: 11.5 }} onClick={() => { setQuestion(h); run(h); }}>
                {h}
              </button>
            ))}
          </>
        )}
      </aside>

      <div className="app-pane">
        <form className="app-toolbar" onSubmit={(e) => { e.preventDefault(); run(question); }}>
          <div className="field" style={{ flex: 1 }}>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Describe the data you need in plain English…"
              aria-label="Natural language query"
            />
          </div>
          <button className="btn primary" disabled={running || !question.trim()}>
            <Play size={13} /> {running ? "Running…" : "Generate & run"}
          </button>
        </form>

        <div className="app-content" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {!result && !running && (
            <div className="empty">
              <Database size={26} />
              <p style={{ margin: 0 }}>Natural language → guarded SQL. Try an example:</p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
                {EXAMPLES.map((e) => (
                  <button key={e} className="btn sm" onClick={() => { setQuestion(e); run(e); }}>{e}</button>
                ))}
              </div>
            </div>
          )}

          {running && <div className="empty"><span className="dot pulse" style={{ background: "var(--accent)" }} /> Generating SQL…</div>}

          {result && (
            <>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <span className="pill info">generated sql</span>
                  <span className="pill good"><ShieldCheck size={11} /> read-only · LIMIT 50</span>
                  {result.warning && <span className="pill warn">⚠ {result.warning}</span>}
                </div>
                <div className="code-block"><Highlight sql={result.sql} /></div>
              </div>
              <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>{result.explanation}</p>
              <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                <table className="table">
                  <thead>
                    <tr>{result.columns.map((c) => <th key={c}>{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row, i) => (
                      <tr key={i}>{row.map((cell, j) => <td key={j} className={typeof cell === "number" ? "mono" : ""}>{cell}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
