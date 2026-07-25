import { ArrowRight, Building2, Eye, EyeOff, Lock } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError, apiLogin, apiSignup, ping } from "../lib/api";
import { MOCK_USERS } from "../lib/mock";
import { useOS } from "../store";
import InstallButton from "./InstallButton";

type Field = "company" | "fullName" | "email" | "password";

/** Checks we can run before touching the network, so the person is told what
 *  is wrong while they are still looking at the field. */
function validate(mode: "signin" | "signup", v: Record<Field, string>): Partial<Record<Field, string>> {
  const e: Partial<Record<Field, string>> = {};
  if (!v.email.trim()) e.email = "Enter your email address.";
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.email.trim()))
    e.email = "That doesn't look like a valid email address.";

  if (!v.password) e.password = "Enter your password.";
  else if (mode === "signup" && v.password.length < 8)
    e.password = `Password must be at least 8 characters — yours is ${v.password.length}.`;

  if (mode === "signup") {
    if (!v.company.trim()) e.company = "Enter your company name.";
    else if (v.company.trim().length < 2) e.company = "Company name must be at least 2 characters.";
    if (!v.fullName.trim()) e.fullName = "Enter your name.";
    else if (v.fullName.trim().length < 2) e.fullName = "Your name must be at least 2 characters.";
  }
  return e;
}

/** Map a server field name onto the input it belongs to. */
const SERVER_FIELD: Record<string, Field> = {
  company_name: "company", full_name: "fullName", email: "email", password: "password",
};

export default function LoginScreen() {
  const { login, live, setLive } = useOS();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState(MOCK_USERS[0].email);
  const [password, setPassword] = useState("");
  const [company, setCompany] = useState("");
  const [fullName, setFullName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    ping().then(setLive);
  }, [setLive]);

  const isSignup = mode === "signup";
  const values: Record<Field, string> = { company, fullName, email, password };

  /** Clear a field's error as soon as the person starts fixing it. */
  const clear = (f: Field) => setErrors((prev) => (prev[f] ? { ...prev, [f]: undefined } : prev));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setFormError("");

    const found = validate(mode, values);
    setErrors(found);
    if (Object.keys(found).length) return;      // say what's wrong before a round trip

    setBusy(true);
    try {
      const session = isSignup
        ? await apiSignup(company.trim(), fullName.trim(), email.trim(), password)
        : await apiLogin(email.trim(), password);
      setLive(session.live);
      login(session.user, session.token, session.orgName, session.isOwner, session.industry);
    } catch (err) {
      // A validation failure names its field; attach the message to that input.
      if (err instanceof ApiError && err.fields.length) {
        const mapped: Partial<Record<Field, string>> = {};
        for (const f of err.fields) {
          const key = SERVER_FIELD[f.field];
          if (key) mapped[key] = f.problem.charAt(0).toUpperCase() + f.problem.slice(1);
        }
        setErrors(mapped);
        if (!Object.keys(mapped).length) setFormError(err.message);
      } else if (err instanceof ApiError && err.status === 409) {
        setErrors({ email: "That email is already registered — sign in instead." });
      } else if (err instanceof ApiError && err.status === 401) {
        // Deliberately does NOT reveal which half was wrong: confirming that an
        // email exists would let anyone test a list of addresses against us.
        setFormError("Email or password is incorrect. Check both and try again.");
      } else if (err instanceof ApiError && (err.status === 429 || err.status === 403)) {
        setFormError(err.message);   // rate limit, backoff or suspended workspace explains itself
      } else {
        setFormError(err instanceof Error ? err.message
          : isSignup ? "Couldn't create your workspace." : "Couldn't sign you in.");
      }
    } finally {
      setBusy(false);
    }
  }

  const fieldCls = (f: Field) => `field${errors[f] ? " invalid" : ""}`;
  const hint = (f: Field) =>
    errors[f] ? <span className="field-error" role="alert" data-error={f}>{errors[f]}</span> : null;

  return (
    <div className="login">
      <div className="boot-logo" style={{ fontSize: 30 }}>EAIOS</div>
      <form className="login-card" onSubmit={submit} noValidate>
        <div className="login-title">{isSignup ? "Create your company workspace" : "Sign in to your workspace"}</div>

        {!isSignup && (
          <div className="login-users">
            {MOCK_USERS.map((u) => (
              <button
                type="button"
                key={u.id}
                className={`login-user ${u.email === email ? "sel" : ""}`}
                onClick={() => { setEmail(u.email); clear("email"); }}
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
            <label className={fieldCls("company")}>
              <Building2 size={14} className="faint" />
              <input value={company} placeholder="Company name" autoFocus
                     aria-invalid={!!errors.company}
                     onChange={(e) => { setCompany(e.target.value); clear("company"); }} />
            </label>
            {hint("company")}

            <label className={fieldCls("fullName")}>
              <span className="faint" style={{ fontSize: 11, width: 52 }}>Name</span>
              <input value={fullName} placeholder="Your full name"
                     aria-invalid={!!errors.fullName}
                     onChange={(e) => { setFullName(e.target.value); clear("fullName"); }} />
            </label>
            {hint("fullName")}
          </>
        )}

        <label className={fieldCls("email")}>
          <span className="faint" style={{ fontSize: 11, width: 52 }}>Email</span>
          <input value={email} placeholder={isSignup ? "work email" : ""} autoComplete="username"
                 inputMode="email" aria-invalid={!!errors.email}
                 onChange={(e) => { setEmail(e.target.value); clear("email"); }} />
        </label>
        {hint("email")}

        <label className={fieldCls("password")}>
          <Lock size={14} className="faint" />
          <input
            type={showPassword ? "text" : "password"}
            placeholder="Password"
            value={password}
            autoComplete={isSignup ? "new-password" : "current-password"}
            aria-invalid={!!errors.password}
            autoFocus={!isSignup}
            onChange={(e) => { setPassword(e.target.value); clear("password"); }}
          />
          <button type="button" className="peek" data-testid="toggle-password"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword} title={showPassword ? "Hide password" : "Show password"}>
            {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        </label>
        {hint("password")}
        {isSignup && !errors.password && (
          <span className="field-note">Use at least 8 characters.</span>
        )}

        {formError && <div className="form-error" role="alert">{formError}</div>}

        <button className="btn primary" style={{ justifyContent: "center", padding: "10px" }} disabled={busy}>
          {busy ? (isSignup ? "Creating workspace…" : "Signing in…") : (isSignup ? "Create workspace" : "Log in")}
          <ArrowRight size={15} />
        </button>

        <div className="faint" style={{ fontSize: 11.5, textAlign: "center" }}>
          {isSignup ? (
            <>Already have a workspace? <button type="button" className="link-btn"
              onClick={() => { setMode("signin"); setErrors({}); setFormError(""); }}>Sign in</button></>
          ) : (
            <>New company? <button type="button" className="link-btn"
              onClick={() => { setMode("signup"); setErrors({}); setFormError(""); setEmail(""); }}>
              Create your workspace →</button></>
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
