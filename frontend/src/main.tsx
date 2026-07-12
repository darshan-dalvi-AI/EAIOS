import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { useOS } from "./store";
import "./styles/system.css";

/* Crash shield: without this, any uncaught render error blanks the whole
   page (e.g. a window crashing after the backend process is closed).
   Instead we show a recovery screen: reload, or continue on mock data. */
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("EAIOS crashed:", error, info.componentStack);
  }

  private continueInDemo = () => {
    useOS.getState().setLive(false); // mock data — no backend required
    this.setState({ error: null });
  };

  render() {
    if (!this.state.error) return this.props.children;
    const box: React.CSSProperties = {
      position: "fixed", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
      background: "#05070f", color: "#e8edf7", fontFamily: "Inter, system-ui, sans-serif", zIndex: 99999,
    };
    const card: React.CSSProperties = {
      maxWidth: 460, padding: "34px 38px", borderRadius: 18, textAlign: "center",
      background: "rgba(13,18,32,0.85)", border: "1px solid rgba(148,163,184,0.2)",
      boxShadow: "0 30px 90px rgba(0,0,0,.6)",
    };
    const btn: React.CSSProperties = {
      padding: "9px 18px", borderRadius: 10, fontWeight: 600, fontSize: 13, cursor: "pointer",
      border: "1px solid rgba(34,211,238,.45)", margin: "0 6px",
    };
    return (
      <div style={box}>
        <div style={card}>
          <div style={{ fontSize: 34, marginBottom: 10 }}>⚠️</div>
          <h1 style={{ fontSize: 19, margin: "0 0 8px" }}>EAIOS hit a snag</h1>
          <p style={{ fontSize: 13, color: "#94a3b8", margin: "0 0 6px" }}>
            {String(this.state.error?.message || this.state.error)}
          </p>
          <p style={{ fontSize: 12.5, color: "#6b7d99", margin: "0 0 20px" }}>
            This usually means the backend process was closed. You can keep working
            in demo mode (mock data) — live mode restores automatically when the
            backend comes back.
          </p>
          <button style={{ ...btn, background: "linear-gradient(120deg,#0891b2,#7c3aed)", color: "#fff", border: "none" }}
                  onClick={this.continueInDemo}>
            Continue in demo mode
          </button>
          <button style={{ ...btn, background: "rgba(22,29,48,.8)", color: "#e8edf7" }}
                  onClick={() => location.reload()}>
            Reload
          </button>
        </div>
      </div>
    );
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);

// PWA: offline app shell (production builds over http(s) only — the
// single-file demo runs from file:// where service workers don't apply).
if (import.meta.env.PROD && "serviceWorker" in navigator && location.protocol.startsWith("http")) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {/* non-fatal */});
  });
}
