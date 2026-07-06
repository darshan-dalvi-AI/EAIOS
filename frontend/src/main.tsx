import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles/system.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// PWA: offline app shell (production builds over http(s) only — the
// single-file demo runs from file:// where service workers don't apply).
if (import.meta.env.PROD && "serviceWorker" in navigator && location.protocol.startsWith("http")) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {/* non-fatal */});
  });
}
