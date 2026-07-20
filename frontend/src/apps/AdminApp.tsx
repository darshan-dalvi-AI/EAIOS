import { Check, Gauge, KeyRound, Lock, ScrollText, ShieldCheck, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { apiAiUsage, type AiUsage } from "../lib/api";
import { AUDIT_ROWS, MOCK_USERS } from "../lib/mock";
import { useOS } from "../store";

const TABS = [
  { id: "users", label: "Users", icon: <Users size={13} /> },
  { id: "audit", label: "Audit log", icon: <ScrollText size={13} /> },
  { id: "models", label: "Models", icon: <KeyRound size={13} /> },
  { id: "access", label: "Access", icon: <ShieldCheck size={13} /> },
  { id: "usage", label: "AI usage", icon: <Gauge size={13} /> },
] as const;

const PROVIDERS = [
  { id: "mock", name: "Mock Engine", detail: "Deterministic extractive engine — zero dependencies", ready: true },
  { id: "ollama", name: "Ollama (local)", detail: "llama3.1 · qwen2.5 · phi-3 on-prem", ready: true },
  { id: "openai", name: "OpenAI", detail: "gpt-4o-mini — API key required", ready: false },
  { id: "anthropic", name: "Anthropic", detail: "claude-sonnet-4-5 — API key required", ready: false },
];

const FEATURES = ["AI Chat", "Knowledge upload", "SQL Studio", "Analytics", "User management", "Model config"];
const MATRIX: Record<string, boolean[]> = {
  admin: [true, true, true, true, true, true],
  manager: [true, true, true, true, false, false],
  employee: [true, true, false, false, false, false],
};

export default function AdminApp() {
  const role = useOS((s) => s.user?.role ?? "employee");
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("users");
  const [users, setUsers] = useState(MOCK_USERS.map((u) => ({ ...u, active: true })));
  const [provider, setProvider] = useState("mock");

  // RBAC gate: the panel manages users, roles, audit and model keys —
  // only administrators get past this screen (mirrors the API's require_admin).
  if (role !== "admin") {
    return (
      <div className="app-pane">
        <div className="app-content" style={{ display: "flex" }}>
          <div className="empty" style={{ margin: "auto" }}>
            <Lock size={28} style={{ color: "var(--warn)" }} />
            <h3 style={{ margin: "6px 0 0" }}>Admin access required</h3>
            <p className="muted" style={{ margin: 0, maxWidth: 400, textAlign: "center", fontSize: 12.5 }}>
              This panel manages users, roles, audit logs and AI model configuration.
              You are signed in as <b>{role}</b> — ask an administrator if you need access.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-pane">
      <div className="app-toolbar">
        <div className="tabs">
          {TABS.map((t) => (
            <button key={t.id} className={`tab ${tab === t.id ? "on" : ""}`} onClick={() => setTab(t.id)}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>{t.icon}{t.label}</span>
            </button>
          ))}
        </div>
        <span className="pill warn" style={{ marginLeft: "auto" }}>admin only</span>
      </div>

      <div className="app-content" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {tab === "usage" && <UsagePanel />}
        {tab === "users" && (
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <table className="table">
              <thead>
                <tr><th>User</th><th>Email</th><th>Role</th><th>Status</th></tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <span style={{ display: "flex", alignItems: "center", gap: 9 }}>
                        <span className="avatar sm" style={{ "--hue": u.avatar_hue } as React.CSSProperties}>
                          {u.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
                        </span>
                        {u.full_name}
                      </span>
                    </td>
                    <td className="mono" style={{ fontSize: 11.5 }}>{u.email}</td>
                    <td>
                      <select
                        className="plain"
                        value={u.role}
                        onChange={(e) => setUsers((all) => all.map((x) => (x.id === u.id ? { ...x, role: e.target.value as typeof u.role } : x)))}
                        aria-label={`Role for ${u.full_name}`}
                      >
                        <option value="admin">admin</option>
                        <option value="manager">manager</option>
                        <option value="employee">employee</option>
                      </select>
                    </td>
                    <td>
                      <button
                        className={`toggle ${u.active ? "on" : ""}`}
                        onClick={() => setUsers((all) => all.map((x) => (x.id === u.id ? { ...x, active: !x.active } : x)))}
                        aria-label={`Toggle ${u.full_name} active`}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "audit" && (
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <table className="table">
              <thead>
                <tr><th>Time</th><th>User</th><th>Action</th><th>Detail</th></tr>
              </thead>
              <tbody>
                {AUDIT_ROWS.map((row, i) => (
                  <tr key={i}>
                    <td className="mono" style={{ fontSize: 11 }}>{row.time}</td>
                    <td className="mono" style={{ fontSize: 11 }}>{row.user}</td>
                    <td><span className="pill info">{row.action}</span></td>
                    <td className="faint">{row.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "models" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {PROVIDERS.map((p) => (
              <button
                key={p.id}
                className="card hover"
                style={{ textAlign: "left", cursor: "pointer", borderColor: provider === p.id ? "rgba(34,211,238,.5)" : undefined }}
                onClick={() => setProvider(p.id)}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontWeight: 600 }}>{p.name}</span>
                  {provider === p.id
                    ? <span className="pill good"><Check size={11} /> active</span>
                    : <span className={`pill ${p.ready ? "dim" : "warn"}`}>{p.ready ? "ready" : "key required"}</span>}
                </div>
                <p className="faint" style={{ margin: "7px 0 0", fontSize: 12 }}>{p.detail}</p>
              </button>
            ))}
            <p className="faint" style={{ gridColumn: "1 / -1", fontSize: 11.5, margin: 0 }}>
              Provider switching maps to <span className="mono">LLM_PROVIDER</span> in the backend .env — mock → ollama → cloud, zero code changes.
            </p>
          </div>
        )}

        {tab === "access" && (
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <table className="table">
              <thead>
                <tr><th>Capability</th><th style={{ textAlign: "center" }}>Admin</th><th style={{ textAlign: "center" }}>Manager</th><th style={{ textAlign: "center" }}>Employee</th></tr>
              </thead>
              <tbody>
                {FEATURES.map((feature, i) => (
                  <tr key={feature}>
                    <td>{feature}</td>
                    {(["admin", "manager", "employee"] as const).map((role) => (
                      <td key={role} style={{ textAlign: "center" }}>
                        {MATRIX[role][i]
                          ? <Check size={14} style={{ color: "var(--good)" }} aria-label={`${role} allowed`} />
                          : <span className="faint" aria-label={`${role} denied`}>—</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function UsagePanel() {
  const [data, setData] = useState<AiUsage | null>(null);
  useEffect(() => { apiAiUsage().then(setData).catch(() => {}); }, []);
  if (!data) return <p className="faint" style={{ fontSize: 12 }}>Loading usage…</p>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <p className="faint" style={{ fontSize: 11.5, margin: 0 }}>
        Last {data.window_days} days · {data.note}. Govern AI spend: who uses it, which models, and what it costs.
      </p>
      <div className="card" style={{ padding: 0, overflow: "auto" }}>
        <table className="table">
          <thead><tr><th>User</th><th>Requests</th><th>Tokens (est.)</th><th>Cost (est.)</th></tr></thead>
          <tbody>{data.by_user.map((r) => (
            <tr key={r.user}><td>{r.user}</td><td className="mono">{r.requests}</td>
              <td className="mono">{r.tokens.toLocaleString()}</td><td className="mono">${r.est_cost.toFixed(4)}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <div className="card" style={{ padding: 0, overflow: "auto" }}>
        <table className="table">
          <thead><tr><th>Model</th><th>Requests</th><th>Tokens (est.)</th><th>Cost (est.)</th></tr></thead>
          <tbody>{data.by_model.map((r) => (
            <tr key={r.model}><td className="mono" style={{ fontSize: 11.5 }}>{r.model}</td><td className="mono">{r.requests}</td>
              <td className="mono">{r.tokens.toLocaleString()}</td><td className="mono">${r.est_cost.toFixed(4)}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
