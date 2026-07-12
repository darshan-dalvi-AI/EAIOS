/* Marketing landing page — shown before the OS boots.
   Premium-SaaS look: animated aurora hero, feature grid, tech stack,
   live architecture diagram, footer. "Get Started" boots the OS. */
import {
  Activity, ArrowRight, BarChart3, Bot, BookOpen, Cpu, Database, FileText, FolderSearch,
  Github, Image as ImageIcon, Mic, Minus, Moon, PlayCircle, Share2, ShieldCheck, Sparkles,
  Square, Sun, Table2, Workflow, X,
} from "lucide-react";
import { useOS } from "../store";

const GITHUB_URL = "https://github.com/darshan-dalvi-AI/EAIOS";
const DOCS_ANCHOR = "#architecture";

const FEATURES = [
  { Icon: FolderSearch, hue: 155, title: "Hybrid Multimodal RAG", text: "BM25 + dense vectors fused with RRF. PDFs, Office docs, spreadsheets, images — cited answers with confidence scores." },
  { Icon: Bot, hue: 265, title: "Multi-Agent AI", text: "9 specialist agents behind a graph orchestrator: an LLM router fans independent tasks out in parallel, and checkpointed state lets interrupted runs resume mid-graph." },
  { Icon: Table2, hue: 15, title: "Structured Table → SQL", text: "Complex, nested tables in PDFs, Word files and spreadsheets become real SQL tables at ingest — the SQL agent queries structured data directly, bypassing text chunking." },
  { Icon: ImageIcon, hue: 30, title: "Vision AI", text: "OCR plus VLM captioning at ingest: charts, scans, and screenshots become searchable, answerable knowledge." },
  { Icon: Mic, hue: 330, title: "Voice Assistant", text: "Speak questions, hear answers. Web Speech in, speech synthesis out — hands-free enterprise Q&A." },
  { Icon: Sparkles, hue: 200, title: "Enterprise Search", text: "One query across policies, financials, manuals, contracts — grounded strictly in authorized company knowledge." },
  { Icon: Database, hue: 130, title: "SQL Assistant", text: "Natural language to safe, read-only SQL with self-correcting retries, a live schema explorer, and direct queries over tables extracted from your documents." },
  { Icon: Cpu, hue: 285, title: "Any Model, One Key", text: "GPT, Claude, Gemini, DeepSeek, Qwen, Llama and Phi through a single OpenRouter key — switch live in Settings, or run fully local with Ollama." },
  { Icon: BarChart3, hue: 38, title: "Analytics", text: "Usage KPIs, adoption trends, agent workloads — dashboards that narrate their own insights." },
  { Icon: FileText, hue: 210, title: "Report Generator", text: "Executive summaries and structured business reports assembled from cited sources." },
  { Icon: ShieldCheck, hue: 358, title: "Security & PII Audit", text: "Sensitive entities — people, emails, phone numbers — are classified at ingest; every agent access is flagged to the append-only audit log and the live security feed." },
  { Icon: Share2, hue: 175, title: "Knowledge Graph", text: "Entities and relationships extracted automatically at ingest — explore the constellation, ask how things connect." },
  { Icon: Workflow, hue: 95, title: "Automations + MCP", text: "Drag-and-drop workflows with human-in-the-loop approval nodes, upload triggers, and MCP tools for AI interoperability." },
];

const TECH = [
  "React 18", "TypeScript", "Vite", "Zustand", "FastAPI", "Python 3.12", "SQLAlchemy 2",
  "StateGraph", "PostgreSQL", "SQLite WAL", "Qdrant", "Redis", "Ollama", "OpenRouter · 7 families",
  "Llama 3.3", "OpenAI", "Anthropic", "WebSockets", "OpenTelemetry", "Docker", "Kubernetes · Helm", "GitHub Actions", "MCP",
];

export default function LandingPage() {
  const setPhase = useOS((s) => s.setPhase);
  const theme = useOS((s) => s.theme);
  const setTheme = useOS((s) => s.setTheme);
  const launch = () => setPhase("boot");

  return (
    <div className="landing">
      {/* ── nav ── */}
      <nav className="land-nav">
        <span className="land-logo"><span className="orb" style={{ width: 16, height: 16 }} /> EAIOS</span>
        <div className="land-links">
          <a href="#features">Features</a>
          <a href="#how-it-works">How it works</a>
          <a href="#tech">Technology</a>
          <a href="#architecture">Architecture</a>
          <a href="#faq">FAQ</a>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub</a>
        </div>
        <button
          className="btn sm"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          title={`${theme === "dark" ? "Light" : "Dark"} mode`}
        >
          {theme === "dark" ? <Sun size={13} /> : <Moon size={13} />}
        </button>
        <button className="btn primary sm" onClick={launch}>Launch <ArrowRight size={13} /></button>
      </nav>

      {/* ── hero ── */}
      <header className="land-hero">
        <div className="land-badge"><span className="dot pulse" style={{ background: "var(--good)" }} /> v0.3 — parallel agents · table→SQL · PII audit · checkpointed runs · OpenRouter</div>
        <h1>
          The AI <span className="land-grad">Operating System</span><br />for your enterprise
        </h1>
        <p>
          Hybrid multimodal RAG, nine parallel AI agents, structured table-to-SQL extraction, enterprise
          search, automations and observability — running inside a full desktop OS in your browser.
          Grounded. Cited. Audited. Resumable.
        </p>
        <div className="land-ctas">
          <button className="btn primary" onClick={launch}><PlayCircle size={15} /> Get Started</button>
          <button className="btn" onClick={launch}><Sparkles size={14} /> Live Demo</button>
          <a className="btn" href={GITHUB_URL} target="_blank" rel="noreferrer"><Github size={14} /> GitHub</a>
          <a className="btn" href={DOCS_ANCHOR}><BookOpen size={14} /> Documentation</a>
        </div>

        {/* mini OS preview — Windows-style caption bar (title left, controls right) */}
        <div className="land-preview" aria-hidden>
          <div className="lp-titlebar">
            <span className="lp-title"><Bot size={11} /> AI Chat</span>
            <span className="lp-caps"><Minus size={11} /><Square size={9} /><X size={11} /></span>
          </div>
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
        <p className="land-sub">One OS, thirteen subsystems — every card below is a working feature, not a mockup.</p>
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

      {/* ── how it works ── */}
      <section className="land-section" id="how-it-works">
        <h2>How the enterprise AI operating system works</h2>
        <p className="land-sub">Three loops — add knowledge, ask anything, automate the rest — all grounded, cited and auditable.</p>
        <div className="land-prose">
          <p>
            <b>Add knowledge.</b> Upload PDFs, Word documents, spreadsheets, presentations or images into the
            Knowledge app. The hybrid multimodal RAG pipeline parses every file (with OCR and vision captioning
            for images), splits it into semantic chunks, embeds them, and indexes everything twice — a BM25
            keyword index and a vector index. At the same time, an entity extractor builds a knowledge graph of
            the people, organisations, amounts and concepts inside your documents, so enterprise search
            understands not just words but relationships. Complex and nested tables get special treatment: they
            are lifted out as structured data and materialised into real SQL tables the SQL agent can query
            directly, while sensitive entities — people, email addresses, phone numbers — are classified as PII
            so any later access to them is flagged in the audit log.
          </p>
          <p>
            <b>Ask anything.</b> Every question flows through a graph orchestrator: an LLM semantic router reads
            the request and fans independent subtasks out to specialist AI agents — document, SQL, research,
            email, report, analytics, memory and coding — which run in parallel where possible. Retrieval fuses
            keyword and vector results with Reciprocal Rank Fusion, augments relational questions with
            knowledge-graph paths, and the answer streams back in real time with citations, a confidence score
            and the exact plan of agents that ran. The SQL agent repairs its own failed queries with a reflection
            loop, and every run is checkpointed per conversation, so an interrupted request resumes exactly where
            it stopped. The LLM layer speaks to GPT, Claude, Gemini, DeepSeek, Qwen, Llama and Phi through a
            single OpenRouter key — or fully local models via Ollama — and degrades gracefully so a demo can
            never crash.
          </p>
          <p>
            <b>Automate and observe.</b> The Automations app turns the same agents into drag-and-drop workflows —
            trigger, agent, condition, notify, plus human-in-the-loop approval nodes that pause high-stakes
            pipelines for an admin — firing on upload or on demand. A WebSocket hub streams presence
            and live agent activity to every window, and the Traces app records a span waterfall for each request,
            so latency and behaviour are never a mystery. Everything is protected by JWT authentication,
            role-based access control, rate limiting and an append-only audit log.
          </p>
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
            { x: 410, y: 30, w: 160, h: 70, t1: "Graph Orchestrator", t2: "router → parallel agents" },
            { x: 410, y: 200, w: 160, h: 70, t1: "Hybrid RAG", t2: "BM25 + vectors · tables→SQL" },
            { x: 640, y: 30, w: 200, h: 70, t1: "LLM Layer", t2: "OpenRouter · Ollama · mock" },
            { x: 640, y: 200, w: 200, h: 70, t1: "Stores", t2: "Postgres · Qdrant · KG · checkpoints" },
          ].map((b) => (
            <g key={b.t1}>
              {/* boxes are always dark navy → label colors are fixed light values so
                  they stay readable in BOTH themes (var(--text) is dark in light mode) */}
              <rect x={b.x} y={b.y} width={b.w} height={b.h} rx="12" fill="rgba(22,29,48,0.85)" stroke="url(#lg)" strokeWidth="1" />
              <text x={b.x + b.w / 2} y={b.y + 32} textAnchor="middle" fill="#e8edf7" fontSize="13.5" fontWeight="600">{b.t1}</text>
              <text x={b.x + b.w / 2} y={b.y + 52} textAnchor="middle" fill="#9fb0c8" fontSize="10.5">{b.t2}</text>
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

      {/* ── faq ── */}
      <section className="land-section" id="faq">
        <h2>Frequently asked questions</h2>
        <p className="land-sub">Short answers about the platform, the AI agents and running it yourself.</p>
        <div className="faq-list">
          <details open>
            <summary>What is EAIOS?</summary>
            <p>
              EAIOS is an enterprise AI operating system that runs in the browser. It combines hybrid multimodal
              RAG, nine cooperating AI agents, a knowledge graph, enterprise search, visual automations and
              observability behind a desktop-style interface with windows, a taskbar and a command palette.
            </p>
          </details>
          <details open>
            <summary>How does the hybrid RAG engine answer questions?</summary>
            <p>
              Uploaded documents are parsed, chunked, embedded and indexed twice — a BM25 keyword index and a
              vector index. At question time both are searched and fused with Reciprocal Rank Fusion, and the
              best passages are given to a large language model which must answer with citations and a
              confidence score.
            </p>
          </details>
          <details>
            <summary>What happens to tables inside my documents?</summary>
            <p>
              Complex and nested tables in PDFs, Word files, spreadsheets and slides are extracted as structured
              data and materialised into real SQL tables at ingest. The SQL agent queries them directly — precise
              aggregations instead of fuzzy text retrieval — and each table stays citable in search.
            </p>
          </details>
          <details>
            <summary>What do the nine AI agents do?</summary>
            <p>
              An LLM semantic router reads each request and fans independent subtasks out to specialists —
              document, SQL, research, email, report, analytics, memory and coding — which run in parallel where
              possible. Their results are merged into one cited answer, and every run is checkpointed so an
              interrupted request resumes where it stopped.
            </p>
          </details>
          <details>
            <summary>What is the knowledge graph used for?</summary>
            <p>
              At ingest time EAIOS extracts entities such as people, organisations, amounts and concepts, and
              links them by co-occurrence. The graph can be explored visually and is used to answer relational
              questions like how two entities are connected, with evidence passages.
            </p>
          </details>
          <details>
            <summary>Which language models does EAIOS support?</summary>
            <p>
              One OpenRouter key unlocks GPT, Claude, Gemini, DeepSeek, Qwen, Llama and Phi — switchable live
              from Settings. EAIOS also runs fully local models through Ollama and keeps a deterministic mock
              fallback so the platform always answers.
            </p>
          </details>
          <details>
            <summary>How does EAIOS protect sensitive data?</summary>
            <p>
              Every request passes JWT authentication, role-based access control and rate limiting. Sensitive
              entities in the knowledge graph — people, email addresses, phone numbers — are classified as PII,
              and any agent or API access to them is flagged in an append-only audit log and on the live
              security feed.
            </p>
          </details>
          <details>
            <summary>Is EAIOS open source and can I run it myself?</summary>
            <p>
              Yes. The full source is on <a href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub</a> with
              one-command local start, Docker Compose, a Render blueprint for free cloud deployment and a Helm
              chart for Kubernetes.
            </p>
          </details>
        </div>
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
