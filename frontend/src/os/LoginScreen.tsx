import { ArrowRight, Building2, Eye, EyeOff, Loader2, Lock, PlayCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError, apiAuthConfig, apiGoogleAuth, apiLogin, apiSignup, apiStartDemo, ping } from "../lib/api";
import { loadGis } from "../lib/gis";
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

/** Google's mark, inline so the button works with no network and no CSP hole. */
function GoogleMark() {
  return (
    <svg width="15" height="15" viewBox="0 0 48 48" aria-hidden>
      <path fill="#4285F4" d="M45 24c0-1.6-.1-2.7-.4-4H24v7.5h12c-.2 2-1.5 5-4.4 7l6.7 5.2C42.2 36 45 30.6 45 24z"/>
      <path fill="#34A853" d="M24 46c5.9 0 10.9-2 14.5-5.3l-6.7-5.2c-1.9 1.3-4.4 2.2-7.8 2.2-6 0-11-4-12.8-9.4l-7 5.4C7.9 41 15.4 46 24 46z"/>
      <path fill="#FBBC05" d="M11.2 28.3c-.5-1.4-.7-2.8-.7-4.3s.3-2.9.7-4.3l-7-5.4C2.9 17.2 2 20.5 2 24s.9 6.8 2.2 9.7l7-5.4z"/>
      <path fill="#EA4335" d="M24 10.6c3.4 0 6.4 1.2 8.8 3.4l6-6C35 4.6 30 2 24 2 15.4 2 7.9 7 4.2 14.3l7 5.4C13 14.3 18 10.6 24 10.6z"/>
    </svg>
  );
}

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

  const [googleId, setGoogleId] = useState("");
  const [googleBusy, setGoogleBusy] = useState(false);
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoOffered, setDemoOffered] = useState(false);

  /** A private throwaway workspace, no password. Everything in it is real; it
   *  is deleted when it expires, and reloading starts a fresh one. */
  async function tryDemo() {
    setFormError(""); setErrors({});
    setDemoBusy(true);
    try {
      const s = await apiStartDemo();
      setLive(s.live);
      login(s.user, s.token, s.orgName, s.isOwner, s.industry, s.emailVerified, s.demo, s.demoExpiresIn);
    } catch (err) {
      setFormError(err instanceof ApiError && err.status === 404
        ? "The demo isn't enabled on this deployment — sign in with an account instead."
        : "Couldn't open a demo workspace. Try again in a moment.");
    } finally {
      setDemoBusy(false);
    }
  }

  useEffect(() => {
    ping().then(setLive);
    apiAuthConfig()
      .then((c) => { setGoogleId(c.google_client_id || ""); setDemoOffered(!!c.demo_sandbox); })
      .catch(() => {});
  }, [setLive]);

  /** Google confirms the address, so there is no code to send or expire. */
  async function continueWithGoogle() {
    setFormError(""); setErrors({});
    if (isSignup && company.trim().length < 2) {
      setErrors({ company: "Enter your company name first — it names your workspace." });
      return;
    }
    setGoogleBusy(true);
    try {
      const gis = await loadGis(googleId);
      const credential = await gis.requestIdToken();
      const s = await apiGoogleAuth(credential, isSignup ? company.trim() : undefined);
      setLive(s.live);
      login(s.user, s.token, s.orgName, s.isOwner, s.industry, s.emailVerified, s.demo, s.demoExpiresIn);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Google sign-in didn't complete.";
      setFormError(msg.includes("popup") ? "The Google window was closed before finishing." : msg);
    } finally {
      setGoogleBusy(false);
    }
  }

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
      login(session.user, session.token, session.orgName, session.isOwner, session.industry,
            session.emailVerified, session.demo, session.demoExpiresIn);
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

        {googleId && (
          <>
            {isSignup && (
              <label className={fieldCls("company")}>
                <Building2 size={14} className="faint" />
                <input value={company} placeholder="Company name" data-testid="google-company"
                       aria-invalid={!!errors.company}
                       onChange={(e) => { setCompany(e.target.value); clear("company"); }} />
              </label>
            )}
            {isSignup && hint("company")}
            <button type="button" className="btn google-btn" data-testid="google-btn"
                    onClick={continueWithGoogle} disabled={googleBusy}>
              <GoogleMark />
              {googleBusy ? "Waiting for Google…" : "Continue with Google"}
            </button>
            <div className="or-rule"><span>or use a password</span></div>
          </>
        )}

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
            {!googleId && (
              <>
                <label className={fieldCls("company")}>
                  <Building2 size={14} className="faint" />
                  <input value={company} placeholder="Company name" autoFocus
                         aria-invalid={!!errors.company}
                         onChange={(e) => { setCompany(e.target.value); clear("company"); }} />
                </label>
                {hint("company")}
              </>
            )}

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
        {!isSignup && demoOffered && (
          <>
            <button type="button" className="btn" data-testid="try-demo"
                    style={{ justifyContent: "center", padding: "9px" }}
                    onClick={tryDemo} disabled={demoBusy}>
              {demoBusy ? <><Loader2 size={14} className="spin" /> Opening a workspace…</>
                        : <><PlayCircle size={14} /> Try the live demo — no signup</>}
            </button>
            <div className="faint" style={{ fontSize: 11, textAlign: "center", lineHeight: 1.5 }}>
              You get a private workspace that resets when you leave. Nothing you
              do in it is kept.
            </div>
          </>
        )}
        <div style={{ display: "flex", justifyContent: "center", marginTop: 2 }}>
          <InstallButton className="btn sm" label="Install as app" />
        </div>
      </form>
    </div>
  );
}
