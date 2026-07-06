import { Brain, Palette, ServerCog, Info } from "lucide-react";
import { useState } from "react";
import { MEMORIES } from "../lib/mock";
import { useOS } from "../store";

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
