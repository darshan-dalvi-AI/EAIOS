import { Brain, Cpu, Download, Mic, Palette, PlayCircle, ServerCog, ShieldCheck, Info, Swords, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { apiCompare, apiDeleteMyData, apiExportMyData, apiModelConfig, apiSetModel, type CompareResult, type ModelConfig } from "../lib/api";
import { MEMORIES } from "../lib/mock";
import { useOS } from "../store";

// Curated OpenRouter model catalog — one key, every major family.
const OPENROUTER = "https://openrouter.ai/api/v1";
// IDs verified against the live OpenRouter catalog (2026-07). The :free tier
// costs nothing but can hit upstream 429s at peak — paid IDs need credits.
const MODEL_CATALOG: { label: string; family: string; model: string }[] = [
  { label: "Llama 3.3 70B · free", family: "Llama", model: "meta-llama/llama-3.3-70b-instruct:free" },
  { label: "GPT-4o mini", family: "GPT", model: "openai/gpt-4o-mini" },
  { label: "Claude Sonnet 5", family: "Claude", model: "anthropic/claude-sonnet-5" },
  { label: "Gemini 3.5 Flash", family: "Gemini", model: "google/gemini-3.5-flash" },
  { label: "DeepSeek V4 Flash", family: "DeepSeek", model: "deepseek/deepseek-v4-flash" },
  { label: "Qwen 3.6 Flash", family: "Qwen", model: "qwen/qwen3.6-flash" },
  { label: "Llama 3.3 70B", family: "Llama", model: "meta-llama/llama-3.3-70b-instruct" },
  { label: "Phi-4", family: "Phi", model: "microsoft/phi-4" },
];

const ACCENTS = [
  { name: "Aurora Cyan", accent: "#22d3ee", accent2: "#8b5cf6" },
  { name: "Violet Storm", accent: "#a78bfa", accent2: "#22d3ee" },
  { name: "Emerald Grid", accent: "#34d399", accent2: "#22d3ee" },
  { name: "Solar Amber", accent: "#fbbf24", accent2: "#f87171" },
  { name: "Rose Signal", accent: "#fb7185", accent2: "#a78bfa" },
];

const STACK = ["React 18", "TypeScript", "Vite", "Zustand", "Recharts", "FastAPI", "SQLAlchemy", "Qdrant", "PostgreSQL", "Redis", "Docker", "Ollama"];

export default function SettingsApp() {
  const { user, live } = useOS();
  const [accent, setAccent] = useState(0);

  const isAdmin = user?.role === "admin";
  const [cfg, setCfg] = useState<ModelConfig | null>(null);
  const [temp, setTemp] = useState(0.3);
  const [switching, setSwitching] = useState<string | null>(null);

  // Model Arena state
  const [arenaA, setArenaA] = useState(MODEL_CATALOG[0].model);
  const [arenaB, setArenaB] = useState(MODEL_CATALOG[1].model);
  const [arenaPrompt, setArenaPrompt] = useState("Summarize what an enterprise AI operating system does in two sentences.");
  const [arenaBusy, setArenaBusy] = useState(false);
  const [arena, setArena] = useState<{ prompt: string; results: CompareResult[] } | null>(null);

  async function runArena() {
    if (arenaBusy || arenaPrompt.trim().length < 3) return;
    setArenaBusy(true);
    setArena(null);
    try {
      setArena(await apiCompare(arenaPrompt.trim(), [arenaA, arenaB]));
    } catch (e) {
      setArena({ prompt: arenaPrompt, results: [
        { model: arenaA, ms: 0, answer: "", error: e instanceof Error ? e.message : String(e) },
        { model: arenaB, ms: 0, answer: "", error: "—" },
      ] });
    } finally {
      setArenaBusy(false);
    }
  }

  useEffect(() => {
    if (!isAdmin) return;
    apiModelConfig().then((c) => { setCfg(c); setTemp(c.temperature); }).catch(() => {});
  }, [isAdmin]);

  async function pickModel(model: string) {
    setSwitching(model);
    try {
      const r = await apiSetModel({ provider: "openai", base_url: OPENROUTER, model, temperature: temp });
      setCfg((c) => (c ? { ...c, ...r, openai_base_url: OPENROUTER } : c));
    } catch (e) {
      alert(`Model switch failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      setSwitching(null);
    }
  }

  async function commitTemp(v: number) {
    setTemp(v);
    try {
      await apiSetModel({ temperature: v });
      setCfg((c) => (c ? { ...c, temperature: v } : c));
    } catch { /* ignore */ }
  }

  function applyAccent(i: number) {
    setAccent(i);
    const root = document.documentElement.style;
    root.setProperty("--accent", ACCENTS[i].accent);
    root.setProperty("--accent-2", ACCENTS[i].accent2);
    root.setProperty("--accent-soft", `${ACCENTS[i].accent}1f`);
    root.setProperty("--glow", `0 0 24px ${ACCENTS[i].accent}40`);
  }

  return (
    <div className="app-pane">
      <div className="app-content" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <section className="card">
          <h3 className="h-display" style={{ fontSize: 13.5, display: "flex", alignItems: "center", gap: 8 }}>
            <Palette size={14} style={{ color: "var(--accent)" }} /> Appearance
          </h3>
          <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
            {ACCENTS.map((a, i) => (
              <button
                key={a.name}
                onClick={() => applyAccent(i)}
                className="card hover"
                style={{ padding: "10px 13px", display: "flex", alignItems: "center", gap: 9, borderColor: accent === i ? a.accent : undefined, cursor: "pointer" }}
              >
                <span style={{ width: 18, height: 18, borderRadius: "50%", background: `linear-gradient(135deg, ${a.accent}, ${a.accent2})`, flex: "none" }} />
                <span style={{ fontSize: 12 }}>{a.name}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="card">
          <h3 className="h-display" style={{ fontSize: 13.5, display: "flex", alignItems: "center", gap: 8 }}>
            <ServerCog size={14} style={{ color: "#c4b5fd" }} /> Connection
          </h3>
          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            <span className={`pill ${live ? "good" : "warn"}`}>{live ? "FastAPI backend · live" : "Demo mode · mock data"}</span>
            <span className="pill dim">vector: {live ? "qdrant / in-memory" : "simulated"}</span>
            <span className="pill dim">llm: {live ? "backend-configured" : "mock engine"}</span>
          </div>
          <p className="faint" style={{ fontSize: 12, margin: "10px 0 0" }}>
            Start the backend (<span className="mono">uvicorn app.main:app</span>) and reload — the OS auto-detects it and switches every app to live data.
          </p>
        </section>

        {isAdmin && (
          <section className="card">
            <h3 className="h-display" style={{ fontSize: 13.5, display: "flex", alignItems: "center", gap: 8 }}>
              <Cpu size={14} style={{ color: "#22d3ee" }} /> AI Model
              <span className="pill dim" style={{ marginLeft: 4 }}>admin</span>
              {cfg && (
                <span className={`pill ${cfg.active_provider === "mock" ? "warn" : "good"}`} style={{ marginLeft: "auto" }}>
                  {cfg.active_provider}{cfg.active_model ? ` · ${cfg.active_model.split("/").pop()}` : ""}
                </span>
              )}
            </h3>
            <p className="faint" style={{ fontSize: 12, margin: "8px 0 0" }}>
              One OpenRouter key serves every family. {live
                ? (cfg?.openai_key_set ? "Key detected — switching is instant." : "Set OPENAI_API_KEY (OpenRouter) on the server, then pick a model.")
                : "Demo mode previews the switch; connect the backend to route real calls."}
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
              {MODEL_CATALOG.map((m) => {
                const activeModel = cfg?.active_model === m.model;
                return (
                  <button
                    key={m.model}
                    onClick={() => pickModel(m.model)}
                    disabled={switching !== null}
                    className="card hover"
                    style={{ padding: "9px 12px", display: "flex", flexDirection: "column", gap: 2, cursor: "pointer",
                             borderColor: activeModel ? "var(--accent)" : undefined,
                             boxShadow: activeModel ? "var(--glow)" : undefined, minWidth: 120 }}
                  >
                    <span style={{ fontSize: 12.5, fontWeight: 600 }}>{m.family}</span>
                    <span className="faint" style={{ fontSize: 10.5 }}>{switching === m.model ? "switching…" : m.label}</span>
                  </button>
                );
              })}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 14 }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>Temperature</span>
              <input type="range" min={0} max={1} step={0.1} value={temp}
                     onChange={(e) => setTemp(parseFloat(e.target.value))}
                     onMouseUp={(e) => commitTemp(parseFloat((e.target as HTMLInputElement).value))}
                     onTouchEnd={(e) => commitTemp(parseFloat((e.target as HTMLInputElement).value))}
                     style={{ flex: 1, accentColor: "var(--accent)" }} />
              <span className="pill dim mono" style={{ minWidth: 42, justifyContent: "center" }}>{temp.toFixed(1)}</span>
            </div>
            <p className="faint" style={{ fontSize: 10.5, margin: "6px 0 0" }}>
              Lower = precise & deterministic · higher = creative. Applies to every agent + the semantic router.
            </p>

            {/* ── Model Arena: same prompt, two models, side by side ── */}
            <div className="palette-section" style={{ padding: "14px 0 6px" }}>Model Arena — compare two models</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <select className="input sm" value={arenaA} onChange={(e) => setArenaA(e.target.value)} aria-label="Arena model A" style={{ maxWidth: 190 }}>
                {MODEL_CATALOG.map((m) => <option key={m.model} value={m.model}>{m.label}</option>)}
              </select>
              <span className="faint" style={{ fontSize: 11 }}>vs</span>
              <select className="input sm" value={arenaB} onChange={(e) => setArenaB(e.target.value)} aria-label="Arena model B" style={{ maxWidth: 190 }}>
                {MODEL_CATALOG.map((m) => <option key={m.model} value={m.model}>{m.label}</option>)}
              </select>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <div className="field" style={{ flex: 1 }}>
                <input value={arenaPrompt} onChange={(e) => setArenaPrompt(e.target.value)}
                       placeholder="Ask both models the same question…" aria-label="Arena prompt"
                       onKeyDown={(e) => e.key === "Enter" && runArena()} />
              </div>
              <button className="btn primary sm" onClick={runArena} disabled={arenaBusy || arenaPrompt.trim().length < 3}>
                <Swords size={13} /> {arenaBusy ? "Running…" : "Compare"}
              </button>
            </div>
            {arena && (
              <div className="arena-grid">
                {arena.results.map((r) => (
                  <div key={r.model} className="card arena-card">
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <b style={{ fontSize: 12 }}>{r.model.split("/").pop()}</b>
                      <span className="pill dim mono" style={{ marginLeft: "auto" }}>{r.ms} ms</span>
                    </div>
                    {r.error
                      ? <p className="arena-answer" style={{ color: "var(--bad)" }}>{r.error}</p>
                      : <p className="arena-answer">{r.answer}</p>}
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        <section className="card">
          <h3 className="h-display" style={{ fontSize: 13.5, display: "flex", alignItems: "center", gap: 8 }}>
            <Brain size={14} style={{ color: "var(--good)" }} /> Long-term memory
          </h3>
          <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
            {MEMORIES.map((m) => (
              <div key={m.id} style={{ display: "flex", gap: 9, alignItems: "center", fontSize: 12.5 }}>
                <span className={`pill ${m.kind === "preference" ? "info" : m.kind === "project" ? "warn" : "dim"}`}>{m.kind}</span>
                <span className="muted">{m.content}</span>
                <span className="faint mono" style={{ marginLeft: "auto", fontSize: 10.5 }}>{m.created_at}</span>
              </div>
            ))}
          </div>
        </section>

        <PrivacySection />

        <section className="card">
          <h3 className="h-display" style={{ fontSize: 13.5, display: "flex", alignItems: "center", gap: 8 }}>
            <Info size={14} className="muted" /> About EAIOS
          </h3>
          <p className="muted" style={{ fontSize: 12.5, margin: "10px 0" }}>
            Enterprise AI Operating System 0.1.0 “Aurora” — hybrid multimodal RAG, 8-agent orchestration, and an OS-metaphor
            workspace. Signed in as {user?.full_name} ({user?.role}).
          </p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {STACK.map((s) => <span key={s} className="pill dim">{s}</span>)}
          </div>
        </section>
      </div>
    </div>
  );
}

function PrivacySection() {
  const [wake, setWake] = useState(() => localStorage.getItem("eaios-wake") === "1");
  const [busy, setBusy] = useState<"export" | "erase" | null>(null);
  const [msg, setMsg] = useState("");
  const [confirming, setConfirming] = useState(false);

  function toggleWake() {
    const next = !wake;
    setWake(next);
    localStorage.setItem("eaios-wake", next ? "1" : "0");
    window.dispatchEvent(new Event("eaios:wake-changed"));
  }
  async function doExport() {
    setBusy("export"); setMsg("");
    try { await apiExportMyData(); setMsg("Export downloaded ✓"); }
    catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  }
  async function doErase() {
    if (!confirming) { setConfirming(true); return; }
    setConfirming(false); setBusy("erase"); setMsg("");
    try {
      const r = await apiDeleteMyData();
      setMsg(`Erased: ${Object.entries(r.removed).map(([k, v]) => `${v} ${k}`).join(", ")} ✓`);
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  }

  return (
    <section className="card">
      <h3 className="h-display" style={{ fontSize: 13.5, display: "flex", alignItems: "center", gap: 8 }}>
        <ShieldCheck size={14} style={{ color: "var(--accent)" }} /> Privacy & data
      </h3>
      <p className="muted" style={{ fontSize: 12, margin: "8px 0 12px" }}>
        GDPR-style self-service: take your data with you, or erase your conversations, tasks and usage
        history. Admins can also set <span className="mono">RETENTION_DAYS</span> to auto-purge old chats.
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn sm" onClick={doExport} disabled={busy !== null}>
          <Download size={13} /> {busy === "export" ? "Exporting…" : "Export my data (JSON)"}
        </button>
        <button className={`btn sm ${confirming ? "primary" : ""}`} onClick={doErase} disabled={busy !== null}>
          <Trash2 size={13} /> {busy === "erase" ? "Erasing…" : confirming ? "Click again to confirm erase" : "Delete my data"}
        </button>
        <button className="btn sm" onClick={() => window.dispatchEvent(new Event("eaios:replay-tour"))}>
          <PlayCircle size={13} /> Replay the guided tour
        </button>
        <button className={`btn sm ${wake ? "primary" : ""}`} onClick={toggleWake} title="Say “Hey EAIOS” to open the assistant">
          <Mic size={13} /> Wake word: {wake ? "on" : "off"}
        </button>
      </div>
      {msg && <p className="faint" style={{ fontSize: 11.5, margin: "10px 0 0" }}>{msg}</p>}
    </section>
  );
}
