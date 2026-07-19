/* NL-to-BI Dashboards — describe a chart in plain English; the SQL agent
   writes the query, runs it, and the result is rendered as a chart you can
   pin to a persistent dashboard grid. */
import { BarChart3, Loader2, Pin, PinOff, Sparkles, Table2 } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { apiChart, apiListCharts, apiPinChart, apiUnpinChart, type ChartSpec, type SavedChartRow } from "../lib/api";

const COLORS = ["#22d3ee", "#8b5cf6", "#34d399", "#fbbf24", "#f87171", "#60a5fa", "#f472b6", "#a3e635"];
const tip = { background: "#0d1220", border: "1px solid rgba(148,163,184,.2)", borderRadius: 8, fontSize: 12 };
const EXAMPLES = ["Documents by type", "Users by role", "Regional sales by quarter", "Messages over time"];

function Chart({ spec }: { spec: ChartSpec }) {
  const data = spec.data ?? [];
  if (spec.type === "table" || !data.length) {
    return (
      <div className="card" style={{ padding: 0, overflow: "auto", maxHeight: 260 }}>
        <table className="table">
          <thead><tr>{spec.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>{spec.rows.slice(0, 30).map((r, i) => (
            <tr key={i}>{r.map((v, j) => <td key={j} className={typeof v === "number" ? "mono" : ""}>{v}</td>)}</tr>
          ))}</tbody>
        </table>
      </div>
    );
  }
  return (
    <div style={{ height: 240, width: "100%" }}>
    <ResponsiveContainer width="100%" height="100%">
      {spec.type === "line" ? (
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,.12)" />
          <XAxis dataKey="x" tick={{ fill: "var(--text-dim)", fontSize: 11 }} />
          <YAxis tick={{ fill: "var(--text-dim)", fontSize: 11 }} />
          <Tooltip contentStyle={tip} /><Legend wrapperStyle={{ fontSize: 11 }} />
          {spec.series.map((s, i) => <Line key={s} type="monotone" dataKey={s} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />)}
        </LineChart>
      ) : spec.type === "pie" ? (
        <PieChart>
          <Tooltip contentStyle={tip} />
          <Pie data={data} dataKey={spec.series[0]} nameKey="x" outerRadius={90} label={{ fontSize: 11 }}>
            {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Pie>
        </PieChart>
      ) : (
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,.12)" />
          <XAxis dataKey="x" tick={{ fill: "var(--text-dim)", fontSize: 11 }} />
          <YAxis tick={{ fill: "var(--text-dim)", fontSize: 11 }} />
          <Tooltip contentStyle={tip} /><Legend wrapperStyle={{ fontSize: 11 }} />
          {spec.series.map((s, i) => <Bar key={s} dataKey={s} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} />)}
        </BarChart>
      )}
    </ResponsiveContainer>
    </div>
  );
}

export default function DashboardsApp() {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [current, setCurrent] = useState<ChartSpec | null>(null);
  const [pins, setPins] = useState<SavedChartRow[]>([]);

  useEffect(() => { apiListCharts().then(setPins).catch(() => {}); }, []);

  async function run(q: string) {
    const clean = q.trim();
    if (!clean || busy) return;
    setBusy(true);
    setCurrent(null);
    try { setCurrent(await apiChart(clean)); } finally { setBusy(false); }
  }
  async function pin() {
    if (!current) return;
    const id = await apiPinChart(current);
    setPins((p) => [{ id, question: current.question, sql: current.sql, spec: current, created_at: new Date().toISOString() }, ...p]);
  }
  async function unpin(id: string) {
    await apiUnpinChart(id);
    setPins((p) => p.filter((c) => c.id !== id));
  }

  return (
    <div className="app-pane">
      <form className="app-toolbar" onSubmit={(e) => { e.preventDefault(); run(question); }}>
        <div className="field" style={{ flex: 1 }}>
          <input value={question} onChange={(e) => setQuestion(e.target.value)}
                 placeholder="Describe a chart… e.g. “revenue by region as a bar chart”" aria-label="Chart question" />
        </div>
        <button className="btn primary" disabled={busy || !question.trim()}>
          {busy ? <Loader2 size={14} className="spin" /> : <Sparkles size={14} />} Visualize
        </button>
      </form>

      <div className="app-content" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {!current && !busy && (
          <div className="empty">
            <BarChart3 size={26} />
            <p style={{ margin: 0 }}>Natural language → chart. Try:</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
              {EXAMPLES.map((e) => <button key={e} className="btn sm" onClick={() => { setQuestion(e); run(e); }}>{e}</button>)}
            </div>
          </div>
        )}
        {busy && <div className="empty"><Loader2 size={20} className="spin" /> Writing SQL & building the chart…</div>}

        {current && (
          <div className="card">
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span className="pill info">{current.type}</span>
              {current.warning && <span className="pill warn">⚠ {current.warning}</span>}
              <span className="faint" style={{ fontSize: 12 }}>{current.question}</span>
              <button className="btn sm" style={{ marginLeft: "auto" }} onClick={pin}><Pin size={12} /> Pin to dashboard</button>
            </div>
            <Chart spec={current} />
            {current.sql && <details style={{ marginTop: 8 }}><summary className="faint" style={{ fontSize: 11, cursor: "pointer" }}><Table2 size={11} /> generated SQL</summary>
              <div className="code-block" style={{ marginTop: 6 }}>{current.sql}</div></details>}
          </div>
        )}

        {pins.length > 0 && (
          <>
            <div className="palette-section">Pinned dashboard</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 12 }}>
              {pins.map((c) => (
                <div key={c.id} className="card">
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <span className="pill dim">{c.spec.type}</span>
                    <span style={{ fontSize: 12, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.question}</span>
                    <button className="mb-item" style={{ marginLeft: "auto" }} onClick={() => unpin(c.id)} aria-label="Unpin chart"><PinOff size={13} /></button>
                  </div>
                  <Chart spec={c.spec} />
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
