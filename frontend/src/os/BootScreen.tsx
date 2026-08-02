import { useEffect, useState } from "react";
import Mark from "./Mark";
import { useOS } from "../store";

const LINES = [
  ["kernel", "K-OS core 0.1.0 initializing"],
  ["auth", "JWT service armed · RBAC matrix loaded"],
  ["vectors", "vector store attached (hybrid retrieval ready)"],
  ["rag", "multimodal ingestion pipeline online"],
  ["agents", "9 agents registered → planner warm"],
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
      setTimeout(() => {
        // Only advance if the boot sequence is still what is on screen. A
        // restored session finishing mid-animation moves straight to the
        // desktop, and this timer must not drag it back to sign-in.
        if (useOS.getState().phase === "boot") setPhase("login");
      }, 480);
    }, 320 * LINES.length + 700);
    return () => {
      clearInterval(stepper);
      clearTimeout(done);
    };
  }, [setPhase]);

  return (
    <div className={`boot ${leaving ? "fade-out" : ""}`}>
      <div>
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 14 }}>
          <Mark size={72} />
        </div>
        <div className="boot-logo">K-OS</div>
        <div className="boot-sub" style={{ textAlign: "center", marginTop: 6 }}>Knowledge Operating System</div>
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
