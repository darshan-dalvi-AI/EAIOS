/* Marketing landing page — shown before the OS boots.
   Premium-SaaS look: animated aurora hero, feature grid, tech stack,
   live architecture diagram, footer. "Get Started" boots the OS. */
import {
  Activity, ArrowRight, BarChart3, Bot, BookOpen, Database, FileText, FolderSearch,
  Github, Image as ImageIcon, Mic, PlayCircle, Share2, Sparkles, Workflow,
} from "lucide-react";
import { useOS } from "../store";

const GITHUB_URL = "https://github.com/darshan-dalvi-AI/EAIOS";
const DOCS_ANCHOR = "#architecture";

const FEATURES = [
  { Icon: FolderSearch, hue: 155, title: "Hybrid Multimodal RAG", text: "BM25 + dense vectors fused with RRF. PDFs, Office docs, spreadsheets, images — cited answers with confidence scores." },
  { Icon: Bot, hue: 265, title: "Multi-Agent AI", text: "9 specialist agents behind a graph orchestrator: planner decomposes, agents execute, results merge — visible in real time." },
  { Icon: ImageIcon, hue: 30, title: "Vision AI", text: "OCR plus VLM captioning at ingest: charts, scans, and screenshots become searchable, answerable knowledge." },
  { Icon: Mic, hue: 330, title: "Voice Assistant", text: "Speak questions, hear answers. Web Speech in, speech synthesis out — hands-free enterprise Q&A." },
  { Icon: Sparkles, hue: 200, title: "Enterprise Search", text: "One query across policies, financials, manuals, contracts — grounded strictly in authorized company knowledge." },
  { Icon: Database, hue: 130, title: "SQL Assistant", text: "Natural language to safe, read-only SQL with guardrails, result tables, and schema explanations." },
  { Icon: BarChart3, hue: 38, title: "Analytics", text: "Usage KPIs, adoption trends, agent workloads — dashboards that narrate their own insights." },
  { Icon: FileText, hue: 210, title: "Report Generator", text: "Executive summaries and structured business reports assembled from cited sources." },
  { Icon: Share2, hue: 175, title: "Knowledge Graph", text: "Entities and relationships extracted automatically at ingest — explore the constellation, ask how things connect." },
  { Icon: Workflow, hue: 95, title: "Automations + MCP", text: "Drag-and-drop workflows on the agent runtime, upload triggers, and MCP tools for AI interoperability." },
];

const TECH = [
  "React 18", "TypeScript", "Vite", "Zustand", "FastAPI", "Python 3.12", "SQLAlchemy 2",
  "StateGraph", "PostgreSQL", "SQLite WAL", "Qdrant", "Redis", "Ollama", "Groq · Llama 3.1",
  "OpenAI", "Anthropic", "WebSockets", "OpenTelemetry", "Docker", "Kubernetes · Helm", "GitHub Actions", "MCP",
];

export default function LandingPage() {
  const setPhase = useOS((s) => s.setPhase);
  const launch = () => setPhase("boot");

  return (
    <div className="landing">
      {/* ── nav ── */}
      <nav className="land-nav">
        <span className="land-logo"><span className="orb" style={{ width: 16, height: 16 }} /> EAIOS</span>
        <div className="land-links">
          <a href="#features">Features</a>
          <a href="#tech">Technology</a>
          <a href="#architecture">Architecture</a>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub</a>
        </div>
        <button className="btn primary sm" onClick={launch}>Launch <ArrowRight size={13} /></button>
      </nav>

      {/* ── hero ── */}
      <header className="land-hero">
        <div className="land-badge"><span className="dot pulse" style={{ background: "var(--good)" }} /> v0.2 — graph agents · knowledge graph · automations · traces</div>
        <h1>
          The AI <span className="land-grad">Operating System</span><br />for your enterprise
        </h1>
        <p>
          Hybrid multimodal RAG, nine cooperating AI agents, enterprise search, automations, and
          observability — running inside a full desktop OS in your browser. Grounded. Cited. Auditable.
        </p>
        <div className="land-ctas">
          <button className="btn primary" onClick={launch}><PlayCircle size={15} /> Get Started</button>
          <button className="btn" onClick={launch}><Sparkles size={14} /> Live Demo</button>
          <a className="btn" href={GITHUB_URL} target="_blank" rel="noreferrer"><Github size={14} /> GitHub</a>
          <a className="btn" href={DOCS_ANCHOR}><BookOpen size={14} /> Documentation</a>
        </div>

        {/* mini OS preview */}
        <div className="land-preview" aria-hidden>
          <div className="lp-titlebar"><span /><span /><span /></div>
          <div className="lp-row">
            <div className="lp-msg user">How many annual leave days do we get?</div>
          </div>
          <div className="lp-row">
            <div className="lp-msg ai">
              <span className="plan-chip done"><Bot size={10} /> document</span>
              &nbsp;24 days of paid annual leave per year, credited monthly. Up to 10 unused days carry
              forward <span className="cite" style={{ display: "inline-flex" }}><FileText size={10} /> HR Leave Policy · §Annual</span>
              <span className="pill good" style={{ marginLeft: 6 }}>confidence 91%</span>
            </div>
          </div>
          <div className="lp-glow" />
        </div>
      </header>

      {/* ── features ── */}
      <section className="land-section" id="features">
        <h2>Everything an enterprise brain needs</h2>
        <p className="land-sub">Ten subsystems, one OS — every card below is a working app, not a mockup.</p>
        <div className="feature-grid">
          {FEATURES.map(({ Icon, hue, title, text }) => (
            <div key={title} className="feature-card" style={{ "--hue": hue } as React.CSSProperties}>
              <div className="app-icon md" style={{ "--hue": hue } as React.CSSProperties}><Icon size={16} /></div>
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── technology ── */}
      <section className="land-section" id="tech">
        <h2>Built on a production stack</h2>
        <p className="land-sub">Every dependency is isolated behind an interface with a working fallback.</p>
        <div className="tech-grid">
          {TECH.map((t) => <span key={t} className="tech-chip">{t}</span>)}
        </div>
      </section>

      {/* ── architecture ── */}
      <section className="land-section" id="architecture">
        <h2>Architecture at a glance</h2>
        <p className="land-sub">React OS shell → FastAPI → graph orchestrator → agents → hybrid RAG + knowledge graph → pluggable LLMs.</p>
        <svg className="arch-svg" viewBox="0 0 860 300" role="img" aria-label="EAIOS architecture diagram">
          <defs>
            <linearGradient id="lg" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="#22d3ee" /><stop offset="1" stopColor="#8b5cf6" />
            </linearGradient>
          </defs>
          {[
            { x: 20, y: 110, w: 150, h: 80, t1: "React OS Shell", t2: "windows · dock · ⌘K" },
            { x: 220, y: 110, w: 140, h: 80, t1: "FastAPI", t2: "REST · WS · SSE" },
            { x: 410, y: 30, w: 160, h: 70, t1: "Graph Orchestrator", t2: "planner → 9 agents" },
            { x: 410, y: 200, w: 160, h: 70, t1: "Hybrid RAG", t2: "BM25 + vectors · RRF" },
            { x: 640, y: 30, w: 200, h: 70, t1: "LLM Layer", t2: "Groq · Ollama · GPT · Claude" },
            { x: 640, y: 200, w: 200, h: 70, t1: "Stores", t2: "Postgres · Qdrant · KG" },
          ].map((b) => (
            <g key={b.t1}>
              <rect x={b.x} y={b.y} width={b.w} height={b.h} rx="12" fill="rgba(22,29,48,0.7)" stroke="url(#lg)" strokeWidth="1" />
              <text x={b.x + b.w / 2} y={b.y + 32} textAnchor="middle" fill="var(--text)" fontSize="13.5" fontWeight="600">{b.t1}</text>
              <text x={b.x + b.w / 2} y={b.y + 52} textAnchor="middle" fill="var(--text-dim)" fontSize="10.5">{b.t2}</text>
            </g>
          ))}
          {[
            "M170,150 H220", "M360,150 L410,70", "M360,150 L410,235",
            "M570,65 H640", "M570,235 H640", "M490,100 V200",
          ].map((d, i) => (
            <path key={i} d={d} className="arch-flow" stroke="url(#lg)" strokeWidth="1.6" fill="none" />
          ))}
        </svg>
      </section>

      {/* ── cta band ── */}
      <section className="land-cta-band">
        <h2>Boot the OS. Ask anything.</h2>
        <button className="btn primary" onClick={launch}><PlayCircle size={15} /> Launch EAIOS</button>
        <span className="faint" style={{ fontSize: 11.5 }}>Works fully offline in demo mode — no keys, no setup.</span>
      </section>

      {/* ── footer ── */}
      <footer className="land-footer">
        <span className="land-logo" style={{ fontSize: 14 }}><span className="orb" style={{ width: 12, height: 12 }} /> EAIOS</span>
        <div className="land-links">
          <a href={GITHUB_URL} target="_blank" rel="noreferrer"><Github size={12} /> GitHub</a>
          <a href={DOCS_ANCHOR}>Documentation</a>
          <a href="#features">Privacy</a>
          <a href="#features">Terms</a>
          <a href="mailto:darshanydalvi2005@gmail.com">Contact</a>
        </div>
        <span className="faint" style={{ fontSize: 11 }}>
          <Activity size={11} style={{ verticalAlign: -1.5 }} /> B.E. Computer Engineering capstone · © {new Date().getFullYear()} Darshan Dalvi
        </span>
      </footer>
    </div>
  );
}
