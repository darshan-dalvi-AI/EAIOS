import { ArrowRight, Building2, Lock } from "lucide-react";
import { useEffect, useState } from "react";
import { apiLogin, apiSignup, ping } from "../lib/api";
import { MOCK_USERS } from "../lib/mock";
import { useOS } from "../store";
import InstallButton from "./InstallButton";

export default function LoginScreen() {
  const { login, live, setLive } = useOS();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState(MOCK_USERS[0].email);
  const [password, setPassword] = useState("");
  const [company, setCompany] = useState("");
  const [fullName, setFullName] = useState("");
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
      const session = mode === "signup"
        ? await apiSignup(company.trim(), fullName.trim(), email.trim(), password)
        : await apiLogin(email, password);
      setLive(session.live);
      login(session.user, session.token, session.orgName, session.isOwner, session.industry);
    } catch (err) {
      setError(mode === "signup"
        ? (err instanceof Error ? err.message : "Couldn't create workspace")
        : "Invalid credentials — try admin12345 or demo12345");
    } finally {
      setBusy(false);
    }
  }

  const isSignup = mode === "signup";

  return (
    <div className="login">
      <div className="boot-logo" style={{ fontSize: 30 }}>EAIOS</div>
      <form className="login-card" onSubmit={submit}>
        <div className="login-title">{isSignup ? "Create your company workspace" : "Sign in to your workspace"}</div>

        {!isSignup && (
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
        )}

        {isSignup && (
          <>
            <label className="field">
              <Building2 size={14} className="faint" />
              <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Company name" autoFocus />
            </label>
            <label className="field">
              <span className="faint" style={{ fontSize: 11, width: 52 }}>Name</span>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Your full name" />
            </label>
          </>
        )}

        <label className="field">
          <span className="faint" style={{ fontSize: 11, width: 52 }}>Email</span>
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder={isSignup ? "work email" : ""} autoComplete="username" />
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
          {busy ? (isSignup ? "Creating workspace…" : "Authenticating…") : (isSignup ? "Create workspace" : "Log in")} <ArrowRight size={15} />
        </button>

        <div className="faint" style={{ fontSize: 11.5, textAlign: "center" }}>
          {isSignup ? (
            <>Already have a workspace? <button type="button" className="link-btn" onClick={() => { setMode("signin"); setError(""); }}>Sign in</button></>
          ) : (
            <>New company? <button type="button" className="link-btn" onClick={() => { setMode("signup"); setError(""); setEmail(""); }}>Create your workspace →</button></>
          )}
        </div>

        <div className="mode-chip">
          <span className={`dot ${live ? "pulse" : "off"}`} />
          {live ? "Live backend connected" : "Demo mode — backend offline, mock data active"}
        </div>
        {!isSignup && (
          <div className="faint" style={{ fontSize: 11, textAlign: "center" }}>
            Demo: admin@eaios.dev / admin12345 · others / demo12345
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "center", marginTop: 2 }}>
          <InstallButton className="btn sm" label="Install as app" />
        </div>
      </form>
    </div>
  );
}
