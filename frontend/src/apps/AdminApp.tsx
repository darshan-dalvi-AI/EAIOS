import { AlertTriangle, Building2, Check, Copy, Gauge, KeyRound, Loader2, Lock, PauseCircle, PlayCircle, RefreshCw, ScrollText, ShieldCheck, Trash2, UserPlus, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { apiAiUsage, apiCreateUser, apiDeleteOwnWorkspace, apiDeleteWorkspace, apiSetWorkspaceStatus, apiUpdateUser, apiUsers, apiWorkspaces, type AdminUser, type AiUsage, type Workspace } from "../lib/api";
import { AUDIT_ROWS } from "../lib/mock";
import { useOS } from "../store";

const TABS = [
  { id: "users", label: "Users", icon: <Users size={13} /> },
  { id: "audit", label: "Audit log", icon: <ScrollText size={13} /> },
  { id: "models", label: "Models", icon: <KeyRound size={13} /> },
  { id: "access", label: "Access", icon: <ShieldCheck size={13} /> },
  { id: "usage", label: "AI usage", icon: <Gauge size={13} /> },
  { id: "workspaces", label: "Workspaces", icon: <Building2 size={13} /> },
] as const;

const PROVIDERS = [
  { id: "mock", name: "Mock Engine", detail: "Deterministic extractive engine — zero dependencies", ready: true },
  { id: "ollama", name: "Ollama (local)", detail: "llama3.1 · qwen2.5 · phi-3 on-prem", ready: true },
  { id: "openai", name: "OpenAI", detail: "gpt-4o-mini — API key required", ready: false },
  { id: "anthropic", name: "Anthropic", detail: "claude-sonnet-4-5 — API key required", ready: false },
];

// HR gets a scoped "people operations" view — Users + the Access matrix only.
const HR_TABS = new Set(["users", "access"]);

const FEATURES = ["AI Chat", "Knowledge upload", "SQL Studio", "Analytics", "Hire & manage staff", "Model config / keys"];
const MATRIX: Record<string, boolean[]> = {
  admin:    [true, true, true, true, true,  true],
  hr:       [true, true, false, false, true, false],
  manager:  [true, true, true, true, false, false],
  employee: [true, true, false, false, false, false],
};

export default function AdminApp() {
  const role = useOS((s) => s.user?.role ?? "employee");
  const isHR = role === "hr";
  const isOwner = useOS((s) => s.isOwner);
  // "Workspaces" is the platform-owner console (every tenant on this
  // deployment). Everyone else — including company admins — never sees it.
  const visibleTabs = TABS.filter((t) =>
    (t.id === "workspaces" ? isOwner : role === "admin" || HR_TABS.has(t.id)));
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("users");

  const [provider, setProvider] = useState("mock");

  // RBAC gate: admins get the full panel; HR gets the people-operations subset
  // (hire/manage staff + view the permission matrix). Everyone else is blocked,
  // mirroring the API's require_admin / require_admin_or_hr guards.
  if (role !== "admin" && role !== "hr") {
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

  const activeTab = visibleTabs.some((t) => t.id === tab) ? tab : "users";

  return (
    <div className="app-pane">
      <div className="app-toolbar">
        <div className="tabs">
          {visibleTabs.map((t) => (
            <button key={t.id} className={`tab ${activeTab === t.id ? "on" : ""}`} onClick={() => setTab(t.id)}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>{t.icon}{t.label}</span>
            </button>
          ))}
        </div>
        <span className="pill warn" style={{ marginLeft: "auto" }}>{isHR ? "HR console" : "admin only"}</span>
      </div>

      <div className="app-content" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {activeTab === "usage" && <UsagePanel />}
        {activeTab === "workspaces" && <WorkspacesPanel />}
        {activeTab === "users" && (
          <>
            <UsersPanel isHR={isHR} />
            {role === "admin" && <DangerZone />}
          </>
        )}

        {activeTab === "audit" && (
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

        {activeTab === "models" && (
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

        {activeTab === "access" && (
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <table className="table">
              <thead>
                <tr><th>Capability</th><th style={{ textAlign: "center" }}>Admin</th><th style={{ textAlign: "center" }}>HR</th><th style={{ textAlign: "center" }}>Manager</th><th style={{ textAlign: "center" }}>Employee</th></tr>
              </thead>
              <tbody>
                {FEATURES.map((feature, i) => (
                  <tr key={feature}>
                    <td>{feature}</td>
                    {(["admin", "hr", "manager", "employee"] as const).map((role) => (
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

function genPassword(): string {
  // readable but strong: 3 syllable-ish chunks + digits, no ambiguous chars
  const cons = "bcdfghjkmnpqrstvwxz", vow = "aeiou", dig = "23456789";
  const pick = (s: string) => s[Math.floor(Math.random() * s.length)];
  let p = "";
  for (let i = 0; i < 3; i++) p += pick(cons).toUpperCase() + pick(vow) + pick(cons) + pick(dig);
  return p;
}

// Admins may assign any role; HR is scoped to line staff (mirrors the API).
const ROLE_OPTS = ["admin", "hr", "manager", "employee"] as const;
const HR_ROLE_OPTS = ["manager", "employee"] as const;

function UsersPanel({ isHR = false }: { isHR?: boolean }) {
  const roleOpts = isHR ? HR_ROLE_OPTS : ROLE_OPTS;
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ full_name: "", email: "", role: "employee", password: genPassword() });
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState("");
  const [created, setCreated] = useState<{ email: string; password: string; full_name: string; role: string } | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => { apiUsers().then(setUsers).finally(() => setLoading(false)); }, []);

  async function hire() {
    setErr("");
    if (form.full_name.trim().length < 2) return setErr("Enter the person's full name.");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email)) return setErr("Enter a valid email address.");
    if (form.password.length < 8) return setErr("Password must be at least 8 characters.");
    setCreating(true);
    try {
      const u = await apiCreateUser({ email: form.email.trim(), full_name: form.full_name.trim(), password: form.password, role: form.role });
      setUsers((list) => [u, ...list]);
      setCreated({ email: u.email, password: form.password, full_name: u.full_name, role: u.role });
      setForm({ full_name: "", email: "", role: "employee", password: genPassword() });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally { setCreating(false); }
  }

  async function changeRole(u: AdminUser, role: string) {
    setUsers((list) => list.map((x) => (x.id === u.id ? { ...x, role: role as AdminUser["role"] } : x)));
    await apiUpdateUser(u.id, { role }).catch(() => {});
  }
  async function toggleActive(u: AdminUser) {
    const next = !u.is_active;
    setUsers((list) => list.map((x) => (x.id === u.id ? { ...x, is_active: next } : x)));
    await apiUpdateUser(u.id, { is_active: next }).catch(() => {});
  }
  function copyCreds() {
    if (!created) return;
    const text = `Hi ${created.full_name},\n\nYour EAIOS account is ready.\n\nSign in at: https://eaios.onrender.com\nEmail: ${created.email}\nTemporary password: ${created.password}\nRole: ${created.role}\n\nPlease sign in and change your password.`;
    navigator.clipboard?.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Hire / create teammate */}
      <div className="card">
        <div className="palette-section" style={{ padding: "0 0 10px", display: "flex", gap: 6, alignItems: "center" }}>
          <UserPlus size={13} /> Add a teammate {isHR ? "(manager / employee)" : "(any role)"}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1.4fr 0.9fr", gap: 8 }}>
          <div className="field"><input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder="Full name" aria-label="Full name" /></div>
          <div className="field"><input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="work email" aria-label="Email" /></div>
          <select className="plain" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} aria-label="Role">
            {roleOpts.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center", flexWrap: "wrap" }}>
          <div className="field" style={{ flex: 1, minWidth: 180 }}>
            <input value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="password" aria-label="Password" style={{ fontFamily: "var(--font-mono)" }} />
          </div>
          <button className="btn sm" onClick={() => setForm({ ...form, password: genPassword() })} title="Generate a password"><RefreshCw size={12} /> Generate</button>
          <button className="btn primary sm" onClick={hire} disabled={creating}>
            {creating ? <Loader2 size={13} className="spin" /> : <UserPlus size={13} />} Create account
          </button>
        </div>
        {err && <span className="pill warn" style={{ marginTop: 10, whiteSpace: "normal", height: "auto", padding: "5px 10px" }}>⚠ {err}</span>}
        {created && (
          <div className="card" style={{ marginTop: 12, background: "var(--accent-soft)", borderColor: "var(--accent)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Check size={14} style={{ color: "var(--good)" }} />
              <b style={{ fontSize: 12.5 }}>Account created for {created.full_name}</b>
              <span className="pill dim">{created.role}</span>
              <button className="btn sm" style={{ marginLeft: "auto" }} onClick={copyCreds}>
                {copied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy invite</>}
              </button>
            </div>
            <div className="code-block" style={{ fontSize: 12 }}>
              Email: {created.email}{"\n"}Password: {created.password}
            </div>
            <p className="faint" style={{ fontSize: 10.5, margin: "8px 0 0" }}>
              Send these credentials to the person's real inbox — “Copy invite” copies a ready-to-send message. Ask them to change the password after first sign-in.
            </p>
          </div>
        )}
      </div>

      {/* Existing users */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="table">
          <thead><tr><th>User</th><th>Email</th><th>Role</th><th>Active</th></tr></thead>
          <tbody>
            {loading && <tr><td colSpan={4} className="faint" style={{ textAlign: "center", padding: 18 }}><Loader2 size={14} className="spin" /> Loading users…</td></tr>}
            {users.map((u) => (
              <tr key={u.id}>
                <td>
                  <span style={{ display: "flex", alignItems: "center", gap: 9 }}>
                    <span className="avatar sm" style={{ "--hue": u.avatar_hue } as React.CSSProperties}>{u.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("")}</span>
                    {u.full_name}
                  </span>
                </td>
                <td className="mono" style={{ fontSize: 11.5 }}>{u.email}</td>
                <td>
                  {isHR && (u.role === "admin" || u.role === "hr") ? (
                    <span className="pill dim">{u.role}</span>
                  ) : (
                    <select className="plain" value={u.role} onChange={(e) => changeRole(u, e.target.value)} aria-label={`Role for ${u.full_name}`}>
                      {roleOpts.map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  )}
                </td>
                <td><button className={`toggle ${u.is_active ? "on" : ""}`} onClick={() => toggleActive(u)} disabled={isHR && (u.role === "admin" || u.role === "hr")} aria-label={`Toggle ${u.full_name} active`} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Platform-owner console: every workspace on this deployment ─────────
   Only rendered for accounts listed in PLATFORM_OWNER_EMAILS server-side;
   the API refuses everyone else regardless of what the UI shows. */
function WorkspacesPanel() {
  const orgName = useOS((s) => s.orgName);
  const [rows, setRows] = useState<Workspace[] | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmFor, setConfirmFor] = useState<Workspace | null>(null);
  const [typed, setTyped] = useState("");
  const [msg, setMsg] = useState("");

  const load = () =>
    apiWorkspaces().then((w) => { setRows(w); setErr(""); })
      .catch((e) => setErr(e instanceof Error ? e.message : "Couldn't load workspaces"));
  useEffect(() => { load(); }, []);

  async function toggle(w: Workspace) {
    setBusy(w.id);
    try {
      await apiSetWorkspaceStatus(w.id, w.status === "active" ? "suspended" : "active");
      setMsg(`${w.name} ${w.status === "active" ? "suspended" : "reactivated"}.`);
      await load();
    } catch (e) { setErr(e instanceof Error ? e.message : "Action failed"); }
    finally { setBusy(null); }
  }

  async function doDelete() {
    if (!confirmFor) return;
    setBusy(confirmFor.id);
    try {
      const r = await apiDeleteWorkspace(confirmFor.id, typed.trim());
      setMsg(`Deleted ${r.deleted} — ${Object.values(r.rows).reduce((a, b) => a + b, 0)} rows removed.`);
      setConfirmFor(null); setTyped("");
      await load();
    } catch (e) { setErr(e instanceof Error ? e.message : "Delete failed"); }
    finally { setBusy(null); }
  }

  if (err && !rows) return <p className="pill bad" style={{ fontSize: 12 }}>{err}</p>;
  if (!rows) return <p className="faint" style={{ fontSize: 12 }}>Loading workspaces…</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <p className="faint" style={{ fontSize: 11.5, margin: 0 }}>
        Every company workspace on this deployment. <b>Suspend</b> locks members out but keeps all data;
        <b> Delete</b> removes the workspace and everything in it, permanently.
      </p>
      {msg && <p className="pill good" style={{ fontSize: 11.5 }}>{msg}</p>}
      {err && <p className="pill bad" style={{ fontSize: 11.5 }}>{err}</p>}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="table">
          <thead>
            <tr><th>Workspace</th><th>Status</th><th style={{ textAlign: "right" }}>Users</th>
              <th style={{ textAlign: "right" }}>Docs</th><th style={{ textAlign: "right" }}>Chats</th>
              <th style={{ textAlign: "right" }}>Tasks</th><th style={{ textAlign: "right" }}>Actions</th></tr>
          </thead>
          <tbody>
            {rows.map((w) => {
              const mine = w.name === orgName;
              return (
                <tr key={w.id} data-ws={w.slug}>
                  <td>
                    <b>{w.name}</b>{mine && <span className="pill info" style={{ marginLeft: 6 }}>you</span>}
                    <div className="faint" style={{ fontSize: 10.5 }}>{w.slug}</div>
                  </td>
                  <td><span className={`pill ${w.status === "active" ? "good" : "warn"}`}>{w.status}</span></td>
                  <td style={{ textAlign: "right" }}>{w.stats?.users ?? 0}</td>
                  <td style={{ textAlign: "right" }}>{w.stats?.documents ?? 0}</td>
                  <td style={{ textAlign: "right" }}>{w.stats?.conversations ?? 0}</td>
                  <td style={{ textAlign: "right" }}>{w.stats?.tasks ?? 0}</td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {mine ? <span className="faint" style={{ fontSize: 11 }}>current</span> : (
                      <>
                        <button className="btn sm" disabled={busy === w.id} onClick={() => toggle(w)}
                                title={w.status === "active" ? "Suspend" : "Reactivate"}>
                          {w.status === "active" ? <PauseCircle size={13} /> : <PlayCircle size={13} />}
                          {w.status === "active" ? "Suspend" : "Activate"}
                        </button>{" "}
                        <button className="btn sm danger" disabled={busy === w.id}
                                onClick={() => { setConfirmFor(w); setTyped(""); setErr(""); }}>
                          <Trash2 size={13} /> Delete
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {confirmFor && (
        <div className="card danger-card">
          <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <AlertTriangle size={16} style={{ color: "var(--bad)", flex: "none", marginTop: 2 }} />
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontWeight: 650, fontSize: 13 }}>Delete “{confirmFor.name}” permanently?</div>
              <p className="faint" style={{ fontSize: 11.5, margin: "4px 0 10px" }}>
                This removes {confirmFor.stats?.users ?? 0} user(s), {confirmFor.stats?.documents ?? 0} document(s),
                {" "}{confirmFor.stats?.conversations ?? 0} chat(s) and every other row it owns. This cannot be undone.
                Type <b>{confirmFor.name}</b> to confirm.
              </p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <input className="input" style={{ maxWidth: 260 }} value={typed} autoFocus
                       placeholder={confirmFor.name} onChange={(e) => setTyped(e.target.value)} />
                <button className="btn sm danger" disabled={typed.trim() !== confirmFor.name || busy !== null}
                        onClick={doDelete}>
                  {busy ? <Loader2 size={13} className="spin" /> : <Trash2 size={13} />} Delete forever
                </button>
                <button className="btn sm" onClick={() => { setConfirmFor(null); setTyped(""); }}>Cancel</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── A company admin closing their own workspace ─────────────────────── */
function DangerZone() {
  const { orgName, logout } = useOS();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function doDelete() {
    setBusy(true); setErr("");
    try {
      await apiDeleteOwnWorkspace(typed.trim());
      logout();   // the account no longer exists — drop straight to the login screen
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Delete failed");
      setBusy(false);
    }
  }

  return (
    <div className="card danger-card" data-testid="danger-zone">
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
        <AlertTriangle size={16} style={{ color: "var(--bad)", flex: "none", marginTop: 2 }} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontWeight: 650, fontSize: 13 }}>Danger zone</div>
          <p className="faint" style={{ fontSize: 11.5, margin: "4px 0 10px" }}>
            Deleting <b>{orgName || "this workspace"}</b> removes every user, document, chat, task and
            uploaded file it owns. This cannot be undone.
          </p>
          {!open ? (
            <button className="btn sm danger" onClick={() => setOpen(true)}>
              <Trash2 size={13} /> Delete this workspace
            </button>
          ) : (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input className="input" style={{ maxWidth: 260 }} value={typed} autoFocus
                     placeholder={`Type “${orgName || ""}” to confirm`}
                     onChange={(e) => setTyped(e.target.value)} />
              <button className="btn sm danger" disabled={!typed.trim() || busy} onClick={doDelete}>
                {busy ? <Loader2 size={13} className="spin" /> : <Trash2 size={13} />} Delete forever
              </button>
              <button className="btn sm" onClick={() => { setOpen(false); setTyped(""); setErr(""); }}>Cancel</button>
            </div>
          )}
          {err && <p className="pill bad" style={{ fontSize: 11.5, marginTop: 8 }}>{err}</p>}
        </div>
      </div>
    </div>
  );
}
