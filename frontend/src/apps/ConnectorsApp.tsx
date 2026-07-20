/* Connectors — pull real enterprise data into the knowledge base.
   · Sample Workspace: bundled demo data, zero setup.
   · Google Drive / Gmail: ONE-CLICK "Connect with Google" (popup consent via
     Google Identity Services) when the admin has set GOOGLE_CLIENT_ID —
     otherwise a paste-an-OAuth-token fallback (OAuth Playground, ~30s). */
import { Check, Cloud, Globe, KeyRound, Loader2, Mail, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiConnectorConfig, apiConnectors, apiSyncConnector, type ConnectorRow } from "../lib/api";
import { useOS } from "../store";

const PROVIDERS = [
  { id: "sample", name: "Sample Workspace", Icon: Sparkles, hue: 200, blurb: "Bundled demo Gmail threads + Drive docs. No setup — great for a quick demo.", scope: "", url: false },
  { id: "website", name: "Website / Docs", Icon: Globe, hue: 260, blurb: "Paste any site URL — a company wiki, docs site or blog. EAIOS crawls up to 8 same-domain pages into the knowledge base.", scope: "", url: true },
  { id: "google_drive", name: "Google Drive", Icon: Cloud, hue: 130, blurb: "Indexes your Drive documents and spreadsheets.", scope: "https://www.googleapis.com/auth/drive.readonly", url: false },
  { id: "gmail", name: "Gmail", Icon: Mail, hue: 350, blurb: "Indexes recent inbox threads.", scope: "https://www.googleapis.com/auth/gmail.readonly", url: false },
];

/* Google Identity Services (loaded on demand) */
interface TokenClient { requestAccessToken: () => void }
interface GisGlobal {
  google?: { accounts?: { oauth2?: { initTokenClient: (cfg: {
    client_id: string; scope: string;
    callback: (resp: { access_token?: string; error?: string }) => void;
    error_callback?: (err: { type?: string; message?: string }) => void;
  }) => TokenClient } } };
}
let gisLoading: Promise<void> | null = null;
function loadGis(): Promise<void> {
  const w = window as unknown as GisGlobal;
  if (w.google?.accounts?.oauth2) return Promise.resolve();
  gisLoading ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => { gisLoading = null; reject(new Error("Couldn't load Google sign-in (network/ad-blocker?). Paste a token instead.")); };
    document.head.appendChild(s);
  });
  return gisLoading;
}

export default function ConnectorsApp() {
  const live = useOS((s) => s.live);
  const [rows, setRows] = useState<ConnectorRow[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [tokens, setTokens] = useState<Record<string, string>>({});
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [okMsg, setOkMsg] = useState<Record<string, string>>({});
  const [clientId, setClientId] = useState("");
  const busyRef = useRef<string | null>(null);

  useEffect(() => {
    apiConnectors().then(setRows).catch(() => {});
    apiConnectorConfig().then((c) => setClientId(c.google_client_id || "")).catch(() => {});
  }, []);

  const note = (provider: string, err: string, good = "") => {
    setErrs((e) => ({ ...e, [provider]: err }));
    setOkMsg((m) => ({ ...m, [provider]: good }));
  };

  async function runSync(provider: string, token: string) {
    setBusy(provider); busyRef.current = provider;
    note(provider, "");
    try {
      const r = await apiSyncConnector(provider, token);
      setRows((list) => [r, ...list.filter((c) => c.provider !== provider)]);
      note(provider, "", `Synced ${r.ingested ?? r.synced_count} item(s) into the knowledge base ✓`);
    } catch (e) {
      note(provider, e instanceof Error ? e.message : String(e));
    } finally { setBusy(null); busyRef.current = null; }
  }

  /* one-click: popup consent → access token → sync */
  async function connectWithGoogle(provider: string, scope: string) {
    if (busy) return;
    note(provider, "");
    setBusy(provider); busyRef.current = provider;
    try {
      await loadGis();
      const w = window as unknown as GisGlobal;
      const tc = w.google!.accounts!.oauth2!.initTokenClient({
        client_id: clientId,
        scope,
        callback: (resp) => {
          if (resp.access_token) void runSync(provider, resp.access_token);
          else { note(provider, resp.error || "Google didn't return a token — try again."); setBusy(null); busyRef.current = null; }
        },
        error_callback: (err) => {
          note(provider, err?.type === "popup_closed" ? "Popup closed before finishing — try again." : (err?.message || "Google sign-in failed."));
          setBusy(null); busyRef.current = null;
        },
      });
      tc.requestAccessToken(); // opens the Google consent popup
    } catch (e) {
      note(provider, e instanceof Error ? e.message : String(e));
      setBusy(null); busyRef.current = null;
    }
  }

  function pasteSync(provider: string) {
    if (busy) return;
    const tok = (tokens[provider] || "").trim();
    if (!tok) { note(provider, "Paste a token first — get one from the OAuth Playground link above."); return; }
    void runSync(provider, tok);
  }

  const statusOf = (id: string) => rows.find((r) => r.provider === id);
  const oneClick = live && !!clientId;

  return (
    <div className="app-pane">
      <div className="app-toolbar">
        <span className="pill info"><Cloud size={11} /> data connectors</span>
        <span className="faint" style={{ fontSize: 11.5 }}>Synced sources feed the same RAG pipeline as uploads — searchable, cited, entity-linked.</span>
      </div>

      <div className="app-content" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14, alignContent: "start" }}>
        {PROVIDERS.map((p) => {
          const st = statusOf(p.id);
          const connected = st?.status === "connected";
          const isGoogle = !!p.scope;
          return (
            <div key={p.id} className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="app-icon md" style={{ "--hue": p.hue } as React.CSSProperties}><p.Icon size={16} /></span>
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: "block", fontWeight: 600, fontSize: 13 }}>{p.name}</span>
                  {connected
                    ? <span className="pill good" style={{ marginTop: 2 }}><Check size={10} /> {st!.synced_count} synced</span>
                    : <span className="pill dim" style={{ marginTop: 2 }}>not connected</span>}
                </span>
              </div>
              <p className="faint" style={{ fontSize: 11.5, margin: 0, lineHeight: 1.5 }}>{p.blurb}</p>

              {/* ── website: URL input + crawl ── */}
              {p.url && (
                <>
                  <div className="field">
                    <input value={tokens[p.id] || ""} onChange={(e) => { setTokens({ ...tokens, [p.id]: e.target.value }); note(p.id, ""); }}
                           placeholder="https://docs.your-company.com" aria-label="Website URL" disabled={!live} />
                  </div>
                  {!live && <span className="faint" style={{ fontSize: 10.5 }}>Live backend required to crawl real sites.</span>}
                  <button className="btn sm" style={{ justifyContent: "center", marginTop: "auto" }}
                          onClick={() => { const u = (tokens[p.id] || "").trim(); if (!u) { note(p.id, "Paste a website URL first — e.g. https://docs.python.org"); return; } void runSync(p.id, u); }}
                          disabled={busy === p.id || !live}>
                    {busy === p.id ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />}
                    {busy === p.id ? " Crawling…" : connected ? " Re-crawl" : " Crawl & index"}
                  </button>
                </>
              )}

              {/* ── sample: plain sync ── */}
              {!isGoogle && !p.url && (
                <button className="btn sm" style={{ justifyContent: "center", marginTop: "auto" }}
                        onClick={() => runSync(p.id, "")} disabled={busy === p.id}>
                  {busy === p.id ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />}
                  {busy === p.id ? " Syncing…" : connected ? " Re-sync" : " Connect & sync"}
                </button>
              )}

              {/* ── google: one-click if configured, else token paste ── */}
              {isGoogle && oneClick && (
                <button className="btn primary sm" style={{ justifyContent: "center", marginTop: "auto" }}
                        onClick={() => connectWithGoogle(p.id, p.scope)} disabled={busy === p.id}>
                  {busy === p.id ? <Loader2 size={13} className="spin" /> : (
                    <svg width="13" height="13" viewBox="0 0 48 48" aria-hidden="true"><path fill="currentColor" d="M44.5 20H24v8.5h11.8C34.7 33.9 30.1 37 24 37c-7.2 0-13-5.8-13-13s5.8-13 13-13c3.1 0 5.9 1.1 8.1 2.9l6.4-6.4C34.6 4.1 29.6 2 24 2 11.8 2 2 11.8 2 24s9.8 22 22 22c11 0 21-8 21-22 0-1.3-.2-2.7-.5-4z"/></svg>
                  )}
                  {busy === p.id ? " Connecting…" : connected ? " Re-sync with Google" : " Connect with Google"}
                </button>
              )}
              {isGoogle && !oneClick && (
                <>
                  <div className="field">
                    <input type="password" value={tokens[p.id] || ""} onChange={(e) => { setTokens({ ...tokens, [p.id]: e.target.value }); note(p.id, ""); }}
                           placeholder="Paste Google OAuth access token" aria-label={`${p.name} token`} disabled={!live} />
                  </div>
                  <span className="faint" style={{ fontSize: 10.5, lineHeight: 1.55 }}>
                    {live
                      ? <><KeyRound size={10} /> Get a token in ~30s: <a href="https://developers.google.com/oauthplayground/" target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>OAuth Playground</a> → authorize <code style={{ fontSize: 10 }}>{p.id === "gmail" ? "gmail.readonly" : "drive.readonly"}</code> → copy the access token. Admins: set <code style={{ fontSize: 10 }}>GOOGLE_CLIENT_ID</code> to enable one-click connect (docs/DEPLOY.md).</>
                      : "Live backend required for real Google sync."}
                  </span>
                  <button className="btn sm" style={{ justifyContent: "center", marginTop: "auto" }}
                          onClick={() => pasteSync(p.id)} disabled={busy === p.id || !live}>
                    {busy === p.id ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />}
                    {busy === p.id ? " Syncing…" : connected ? " Re-sync" : " Connect & sync"}
                  </button>
                </>
              )}

              {errs[p.id] && <span className="pill warn" style={{ whiteSpace: "normal", lineHeight: 1.45, height: "auto", padding: "5px 10px" }}>{errs[p.id]}</span>}
              {!errs[p.id] && okMsg[p.id] && <span className="pill good" style={{ whiteSpace: "normal", height: "auto", padding: "5px 10px" }}>{okMsg[p.id]}</span>}
              {!errs[p.id] && !okMsg[p.id] && st?.detail && <span className="faint" style={{ fontSize: 10.5 }}>{st.detail}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
