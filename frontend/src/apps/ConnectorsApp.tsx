/* Connectors — pull real enterprise data into the knowledge base. The Sample
   Workspace works instantly (bundled demo Gmail + Drive data). Google Drive
   and Gmail sync live data when given an OAuth access token. */
import { Check, Cloud, Loader2, Mail, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { apiConnectors, apiSyncConnector, type ConnectorRow } from "../lib/api";
import { useOS } from "../store";

const PROVIDERS = [
  { id: "sample", name: "Sample Workspace", Icon: Sparkles, hue: 200, blurb: "Bundled demo Gmail threads + Drive docs. No setup — great for a quick demo.", needsToken: false },
  { id: "google_drive", name: "Google Drive", Icon: Cloud, hue: 130, blurb: "Indexes your Drive documents and spreadsheets. Needs a Google OAuth token.", needsToken: true },
  { id: "gmail", name: "Gmail", Icon: Mail, hue: 350, blurb: "Indexes recent inbox threads. Needs a Google OAuth token.", needsToken: true },
];

export default function ConnectorsApp() {
  const live = useOS((s) => s.live);
  const [rows, setRows] = useState<ConnectorRow[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [tokens, setTokens] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string>("");

  useEffect(() => { apiConnectors().then(setRows).catch(() => {}); }, []);

  async function sync(provider: string, needsToken: boolean) {
    if (busy) return;
    setErr("");
    setBusy(provider);
    try {
      const r = await apiSyncConnector(provider, needsToken ? (tokens[provider] || "") : "");
      setRows((list) => [r, ...list.filter((c) => c.provider !== provider)]);
    } catch (e) {
      setErr(`${provider}: ${e instanceof Error ? e.message : e}`);
    } finally { setBusy(null); }
  }

  const statusOf = (id: string) => rows.find((r) => r.provider === id);

  return (
    <div className="app-pane">
      <div className="app-toolbar">
        <span className="pill info"><Cloud size={11} /> data connectors</span>
        <span className="faint" style={{ fontSize: 11.5 }}>Synced sources feed the same RAG pipeline as uploads — searchable, cited, entity-linked.</span>
        {err && <span className="pill warn" style={{ marginLeft: "auto" }}>⚠ {err}</span>}
      </div>

      <div className="app-content" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14, alignContent: "start" }}>
        {PROVIDERS.map((p) => {
          const st = statusOf(p.id);
          const connected = st?.status === "connected";
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

              {p.needsToken && (
                <div className="field">
                  <input type="password" value={tokens[p.id] || ""} onChange={(e) => setTokens({ ...tokens, [p.id]: e.target.value })}
                         placeholder="Paste Google OAuth access token" aria-label={`${p.name} token`} disabled={!live} />
                </div>
              )}
              {p.needsToken && !live && <span className="faint" style={{ fontSize: 10.5 }}>Live backend required for real Google sync.</span>}

              <button className="btn sm" style={{ justifyContent: "center", marginTop: "auto" }}
                      onClick={() => sync(p.id, p.needsToken)} disabled={busy === p.id || (p.needsToken && !live)}>
                {busy === p.id ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />}
                {busy === p.id ? " Syncing…" : connected ? " Re-sync" : " Connect & sync"}
              </button>
              {st?.detail && <span className="faint" style={{ fontSize: 10.5 }}>{st.detail}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
