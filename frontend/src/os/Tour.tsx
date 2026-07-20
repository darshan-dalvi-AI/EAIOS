/* First-run guided tour — spotlight overlay that walks new users through the
   OS. Shows once (localStorage flag); replay from Settings → "Replay tour". */
import { useEffect, useState } from "react";

const STEPS = [
  { target: "", title: "Welcome to EAIOS 👋", text: "Your enterprise AI operating system. This 30-second tour shows you around — you can skip any time." },
  { target: '[aria-label="Open AI Chat"]', title: "The dock", text: "Every app lives here — Chat, Knowledge, Search, Dashboards, Video calls and more. Click an icon to open it as a window." },
  { target: ".window .app-toolbar", title: "AI Chat", text: "Ask anything about your company knowledge. Answers come back with citations, a confidence score, and the plan of AI agents that ran." },
  { target: "#agent-select", title: "Route picker", text: "Let the planner choose an agent automatically — or route a question to a specific one, including agents you build in Agent Studio." },
  { target: '[aria-label="Open Knowledge"]', title: "Add your knowledge", text: "Upload PDFs, Word files or spreadsheets — or open Connectors to sync Gmail, Drive or a whole website into the knowledge base." },
  { target: ".mb-right", title: "System tray", text: "Theme toggle, notifications, presence and search live up here. Press Ctrl+K anywhere for the command palette. Enjoy!" },
];

export default function Tour({ onDone }: { onDone: () => void }) {
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const step = STEPS[i];

  useEffect(() => {
    if (!step.target) { setRect(null); return; }
    const el = document.querySelector(step.target);
    if (!el) { setRect(null); return; }
    const r = el.getBoundingClientRect();
    setRect(r);
  }, [i, step.target]);

  const next = () => (i + 1 < STEPS.length ? setI(i + 1) : onDone());

  const card: React.CSSProperties = rect
    ? { position: "fixed", zIndex: 100001, maxWidth: 320,
        top: Math.min(Math.max(rect.bottom + 14, 60), window.innerHeight - 190),
        left: Math.min(Math.max(rect.left - 40, 14), window.innerWidth - 340) }
    : { position: "fixed", zIndex: 100001, maxWidth: 360, top: "50%", left: "50%", transform: "translate(-50%,-50%)" };

  return (
    <div className="tour-overlay" role="dialog" aria-label="Guided tour">
      {rect && (
        <div className="tour-spot" style={{ top: rect.top - 8, left: rect.left - 8, width: rect.width + 16, height: rect.height + 16 }} />
      )}
      <div className="tour-card" style={card}>
        <span className="pill info" style={{ marginBottom: 8 }}>{i + 1} / {STEPS.length}</span>
        <h3 style={{ margin: "0 0 6px", fontSize: 15 }}>{step.title}</h3>
        <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.55, color: "var(--text-dim)" }}>{step.text}</p>
        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button className="btn primary sm" onClick={next} data-tour-next>{i + 1 < STEPS.length ? "Next" : "Finish"}</button>
          <button className="btn sm" onClick={onDone}>Skip tour</button>
        </div>
      </div>
    </div>
  );
}
