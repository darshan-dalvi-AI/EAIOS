import { ArrowRight, Lock } from "lucide-react";
import { useEffect, useState } from "react";
import { apiLogin, ping } from "../lib/api";
import { MOCK_USERS } from "../lib/mock";
import { useOS } from "../store";

export default function LoginScreen() {
  const { login, live, setLive } = useOS();
  const [email, setEmail] = useState(MOCK_USERS[0].email);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    ping().then(setLive);
  }, [setLive]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const session = await apiLogin(email, password);
      setLive(session.live);
      login(session.user, session.token);
    } catch {
      setError("Invalid credentials — try admin12345 or demo12345");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="boot-logo" style={{ fontSize: 30 }}>EAIOS</div>
      <form className="login-card" onSubmit={submit}>
        <div className="login-title">Sign in to your workspace</div>

        <div className="login-users">
          {MOCK_USERS.map((u) => (
            <button
              type="button"
              key={u.id}
              className={`login-user ${u.email === email ? "sel" : ""}`}
              onClick={() => setEmail(u.email)}
            >
              <div className="avatar" style={{ "--hue": u.avatar_hue } as React.CSSProperties}>
                {u.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
              </div>
              {u.full_name.split(" ")[0]}
              <span className="faint" style={{ fontSize: 10 }}>{u.role}</span>
            </button>
          ))}
        </div>

        <label className="field">
          <span className="faint" style={{ fontSize: 11, width: 52 }}>Email</span>
          <input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
        </label>
        <label className="field">
          <Lock size={14} className="faint" />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            autoFocus
          />
        </label>

        {error && <div style={{ color: "var(--bad)", fontSize: 12, textAlign: "center" }}>{error}</div>}

        <button className="btn primary" style={{ justifyContent: "center", padding: "10px" }} disabled={busy}>
          {busy ? "Authenticating…" : "Log in"} <ArrowRight size={15} />
        </button>

        <div className="mode-chip">
          <span className={`dot ${live ? "pulse" : "off"}`} />
          {live ? "Live backend connected" : "Demo mode — backend offline, mock data active"}
        </div>
        <div className="faint" style={{ fontSize: 11, textAlign: "center" }}>
          Demo: admin@eaios.dev / admin12345 · others / demo12345
        </div>
      </form>
    </div>
  );
}
