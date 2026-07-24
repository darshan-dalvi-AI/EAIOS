/* "Download app" button — installs EAIOS as a standalone app (PWA).
   On Chromium (Windows/macOS/Android) it fires the native install prompt.
   Elsewhere (iOS Safari, Firefox) it shows manual add-to-home instructions. */
import { Download, Monitor, Share, Smartphone, X } from "lucide-react";
import { useEffect, useState } from "react";
import { canInstall, isIOS, isStandalone, onPwaChange, promptInstall } from "../lib/pwa";

export default function InstallButton({ className = "btn", label = "Download app" }: { className?: string; label?: string }) {
  const [, setTick] = useState(0);
  const [help, setHelp] = useState(false);
  useEffect(() => onPwaChange(() => setTick((t) => t + 1)), []);

  if (isStandalone()) return null; // already running as an installed app

  async function click() {
    const r = await promptInstall();
    if (r !== "accepted" && r !== "dismissed") setHelp(true); // no native prompt → show steps
  }

  return (
    <>
      <button type="button" className={className} onClick={click} title="Install EAIOS as an app on your device">
        <Download size={15} /> {label}
      </button>
      {help && (
        <div className="tour-overlay" style={{ background: "rgba(2,4,10,.6)", zIndex: 100002, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => setHelp(false)}>
          <div className="tour-card" style={{ maxWidth: 380 }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <Download size={16} style={{ color: "var(--accent)" }} />
              <b style={{ fontSize: 15 }}>Install EAIOS as an app</b>
              <button type="button" className="mb-item" style={{ marginLeft: "auto" }} onClick={() => setHelp(false)} aria-label="Close"><X size={14} /></button>
            </div>
            {isIOS() ? (
              <p style={{ fontSize: 12.5, lineHeight: 1.6, color: "var(--text-dim)", margin: 0 }}>
                <Smartphone size={13} /> On iPhone/iPad: tap the <b>Share</b> button <Share size={12} /> in Safari,
                then choose <b>“Add to Home Screen”</b>. EAIOS opens like a native app — no browser bar.
              </p>
            ) : (
              <p style={{ fontSize: 12.5, lineHeight: 1.6, color: "var(--text-dim)", margin: 0 }}>
                <Monitor size={13} /> On Chrome or Edge (Windows/Mac/Android): open the browser menu (or the
                install icon in the address bar) and choose <b>“Install EAIOS”</b>. It gets a desktop/home-screen
                icon and launches in its own window. <span className="faint">(Firefox/Safari desktop don’t support one-click install.)</span>
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
}

// re-export for callers that want to know if a one-click install is available
export { canInstall };
