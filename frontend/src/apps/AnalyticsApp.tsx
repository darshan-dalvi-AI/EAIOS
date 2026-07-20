import { useEffect, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { apiRagEval } from "../lib/api";
import { AGENT_USAGE, DOCS_BY_TYPE, MESSAGES_DAILY } from "../lib/mock";

const PIE_COLORS = ["#22d3ee", "#8b5cf6", "#34d399", "#fbbf24", "#f87171", "#60a5fa", "#f472b6", "#a3e635"];

const tooltipStyle = {
  background: "#0d1220",
  border: "1px solid rgba(148,163,184,.25)",
  borderRadius: 9,
  fontSize: 12,
  color: "#e8edf7",
};

const STATS = [
  { label: "Queries · 14 days", value: MESSAGES_DAILY.reduce((s, d) => s + d.count, 0).toLocaleString(), delta: "+18%" },
  { label: "Documents indexed", value: "361", delta: "+24" },
  { label: "Active users", value: "47", delta: "+6" },
  { label: "Avg agent latency", value: "742 ms", delta: "−9%" },
];

export default function AnalyticsApp() {
  const [ev, setEv] = useState<{ queries: number; hit_rate: number | null; mrr: number | null; note: string } | null>(null);
  useEffect(() => { apiRagEval().then(setEv).catch(() => {}); }, []);
  return (
    <div className="app-pane">
      <div className="app-toolbar">
        <span style={{ fontWeight: 600, fontSize: 13 }}>Platform Analytics</span>
        <span className="pill dim">last 14 days</span>
      </div>
      <div className="app-content" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="stat-grid">
          {STATS.map((s) => (
            <div key={s.label} className="card">
              <div className="stat-value">{s.value}</div>
              <div className="stat-label">{s.label}</div>
              <span className={`pill ${s.delta.startsWith("−") ? "good" : "info"}`} style={{ marginTop: 8 }}>{s.delta}</span>
            </div>
          ))}
        </div>

        <div className="card" data-testid="rag-eval">
          <h3 className="h-display" style={{ fontSize: 13.5, marginBottom: 4 }}>Answer quality (live RAG eval)</h3>
          <p className="faint" style={{ fontSize: 11, margin: "0 0 12px" }}>{ev?.note ?? "Running the retrieval eval…"}</p>
          <div style={{ display: "flex", gap: 28, flexWrap: "wrap" }}>
            <div><div className="stat-value">{ev?.hit_rate != null ? `${Math.round(ev.hit_rate * 100)}%` : "—"}</div><div className="stat-label">Hit-rate @3</div></div>
            <div><div className="stat-value">{ev?.mrr != null ? ev.mrr.toFixed(2) : "—"}</div><div className="stat-label">MRR</div></div>
            <div><div className="stat-value">{ev?.queries ?? "—"}</div><div className="stat-label">Eval queries</div></div>
          </div>
        </div>

        <div className="card">
          <h3 className="h-display" style={{ fontSize: 13.5, marginBottom: 10 }}>AI queries per day</h3>
          <div style={{ height: 190 }}>
            <ResponsiveContainer>
              <AreaChart data={MESSAGES_DAILY} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                <defs>
                  <linearGradient id="gq" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(148,163,184,.08)" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#5b6b84", fontSize: 10.5 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#5b6b84", fontSize: 10.5 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ stroke: "rgba(148,163,184,.25)" }} />
                <Area type="monotone" dataKey="count" stroke="#22d3ee" strokeWidth={2} fill="url(#gq)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <div className="card">
            <h3 className="h-display" style={{ fontSize: 13.5, marginBottom: 10 }}>Documents by type</h3>
            <div style={{ height: 185 }}>
              <ResponsiveContainer>
                <BarChart data={DOCS_BY_TYPE} margin={{ top: 4, right: 8, left: -22, bottom: 0 }}>
                  <CartesianGrid stroke="rgba(148,163,184,.08)" vertical={false} />
                  <XAxis dataKey="type" tick={{ fill: "#5b6b84", fontSize: 10.5 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "#5b6b84", fontSize: 10.5 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(148,163,184,.06)" }} />
                  <Bar dataKey="count" radius={[5, 5, 0, 0]}>
                    {DOCS_BY_TYPE.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card">
            <h3 className="h-display" style={{ fontSize: 13.5, marginBottom: 10 }}>Agent workload</h3>
            <div style={{ height: 185, display: "flex", alignItems: "center" }}>
              <ResponsiveContainer width="55%" height="100%">
                <PieChart>
                  <Pie data={AGENT_USAGE} dataKey="value" nameKey="name" innerRadius={42} outerRadius={68} paddingAngle={3} stroke="none">
                    {AGENT_USAGE.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: "flex", flexDirection: "column", gap: 5, fontSize: 11.5 }}>
                {AGENT_USAGE.slice(0, 6).map((a, i) => (
                  <span key={a.name} style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: PIE_COLORS[i], flex: "none" }} />
                    <span className="muted">{a.name}</span>
                    <span className="faint mono" style={{ marginLeft: "auto" }}>{a.value.toLocaleString()}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
