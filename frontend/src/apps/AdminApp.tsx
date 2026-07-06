import { Check, KeyRound, ScrollText, ShieldCheck, Users } from "lucide-react";
import { useState } from "react";
import { AUDIT_ROWS, MOCK_USERS } from "../lib/mock";

const TABS = [
  { id: "users", label: "Users", icon: <Users size={13} /> },
  { id: "audit", label: "Audit log", icon: <ScrollText size={13} /> },
  { id: "models", label: "Models", icon: <KeyRound size={13} /> },
  { id: "access", label: "Access", icon: <ShieldCheck size={13} /> },
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
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("users");
  const [users, setUsers] = useState(MOCK_USERS.map((u) => ({ ...u, active: true })));
  const [provider, setProvider] = useState("mock");

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
