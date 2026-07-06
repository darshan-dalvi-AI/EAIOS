import { useEffect, useState } from "react";
import { useOS } from "../store";

const LINES = [
  ["kernel", "EAIOS core 0.1.0 initializing"],
  ["auth", "JWT service armed · RBAC matrix loaded"],
  ["vectors", "vector store attached (hybrid retrieval ready)"],
  ["rag", "multimodal ingestion pipeline online"],
  ["agents", "8 agents registered → planner warm"],
  ["llm", "model layer connected"],
  ["ui", "compositing desktop…"],
] as const;

export default function BootScreen() {
  const setPhase = useOS((s) => s.setPhase);
  const [shown, setShown] = useState(0);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const stepper = setInterval(() => setShown((n) => Math.min(n + 1, LINES.length)), 320);
    const done = setTimeout(() => {
      setLeaving(true);
      setTimeout(() => setPhase("login"), 480);
    }, 320 * LINES.length + 700);
    return () => {
      clearInterval(stepper);
      clearTimeout(done);
    };
  }, [setPhase]);

  return (
    <div className={`boot ${leaving ? "fade-out" : ""}`}>
      <div>
        <div className="boot-logo">EAIOS</div>
        <div className="boot-sub" style={{ textAlign: "center", marginTop: 6 }}>Enterprise AI Operating System</div>
      </div>
      <div className="boot-log" aria-hidden>
        {LINES.slice(0, shown).map(([mod, text], i) => (
          <div key={i}>
            <span className="ok">[ ok ]</span> {mod.padEnd(8, " ")} {text}
          </div>
        ))}
      </div>
      <div className="boot-bar">
        <i style={{ width: `${(shown / LINES.length) * 100}%` }} />
      </div>
    </div>
  );
}
