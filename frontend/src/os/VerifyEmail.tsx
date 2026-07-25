/* Email verification gate.
   A workspace exists but is unusable until the person proves they can receive
   mail at the address they gave. Shown instead of the desktop, so there is no
   way to wander past it — and the server enforces the same rule, so this is
   the polite face of a real check rather than the check itself. */
import { ArrowRight, Loader2, MailCheck, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiResendCode, apiVerifyEmail } from "../lib/api";
import { useOS } from "../store";

export default function VerifyEmail() {
  const { user, orgName, login, logout } = useOS();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const clean = code.replace(/\D/g, "");
    if (clean.length < 6) { setError("Enter the six-digit code from your email."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      const s = await apiVerifyEmail(user!.email, clean);
      // Pass the server's answer rather than assuming success means verified:
      // it is the only party that knows, and if it ever says no we stay here.
      login(s.user, s.token, s.orgName, s.isOwner, s.industry, s.emailVerified !== false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "That code isn't right.");
      setCode("");
      inputRef.current?.focus();
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    if (cooldown > 0) return;
    setError(""); setNotice("");
    try {
      await apiResendCode(user!.email);
      setNotice("A new code is on its way. It expires in 15 minutes.");
      setCooldown(30);
    } catch {
      setNotice("If that address needs verifying, a new code is on its way.");
      setCooldown(30);
    }
  }

  return (
    <div className="login">
      <div className="boot-logo" style={{ fontSize: 30 }}>EAIOS</div>
      <form className="login-card" onSubmit={submit} noValidate>
        <div className="verify-icon"><MailCheck size={26} /></div>
        <div className="login-title" style={{ marginBottom: 2 }}>Check your email</div>
        <p className="faint" style={{ fontSize: 12.5, textAlign: "center", margin: "0 0 4px", lineHeight: 1.55 }}>
          We sent a six-digit code to <b style={{ color: "var(--text)" }}>{user?.email}</b>.
          Enter it to finish setting up {orgName || "your workspace"}.
        </p>

        <label className={`field code-field${error ? " invalid" : ""}`}>
          <input
            ref={inputRef}
            value={code}
            onChange={(e) => { setCode(e.target.value.replace(/\D/g, "").slice(0, 6)); setError(""); }}
            inputMode="numeric" autoComplete="one-time-code" placeholder="000000"
            aria-label="Verification code" aria-invalid={!!error} data-testid="verify-code"
          />
        </label>
        {error && <span className="field-error" role="alert">{error}</span>}
        {notice && <span className="field-note" role="status">{notice}</span>}

        <button className="btn primary" style={{ justifyContent: "center", padding: "10px" }}
                disabled={busy || code.length < 6}>
          {busy ? <><Loader2 size={15} className="spin" /> Verifying…</> : <>Verify and continue <ArrowRight size={15} /></>}
        </button>

        <div style={{ display: "flex", justifyContent: "center", gap: 14, fontSize: 11.5 }}>
          <button type="button" className="link-btn" onClick={resend} disabled={cooldown > 0}>
            <RefreshCw size={11} style={{ marginRight: 4, verticalAlign: -1 }} />
            {cooldown > 0 ? `Resend in ${cooldown}s` : "Send a new code"}
          </button>
          <button type="button" className="link-btn" onClick={logout}>Use a different email</button>
        </div>

        <div className="faint" style={{ fontSize: 11, textAlign: "center", lineHeight: 1.5 }}>
          Can't find it? Check spam. Signing in with Google skips this step entirely.
        </div>
      </form>
    </div>
  );
}
