/* Phone navigation. A dock of 18 tiny icons that scrolls sideways is a desktop
   idea — on a phone you can't see what's there without hunting. This is the
   pattern phones actually use: four primary destinations plus "Apps", which
   opens a labelled full-screen grid of everything else. Rendered only below
   740px; the desktop taskbar is untouched. */
import { Grid3x3, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useOS } from "../store";
import type { AppId } from "../types";
import { APP_META, APP_ORDER, AppTile } from "./appRegistry";

/* The four people reach for constantly. Everything else lives in the sheet. */
const PRIMARY: AppId[] = ["chat", "knowledge", "tasks", "search"];

export default function MobileTabBar() {
  const { windows, open } = useOS();
  const [sheet, setSheet] = useState(false);
  const active = windows.filter((w) => !w.minimized).slice(-1)[0]?.id;

  // Close the sheet on Escape / when an app is chosen.
  useEffect(() => {
    if (!sheet) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSheet(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sheet]);

  function launch(id: AppId) {
    open(id);
    setSheet(false);
  }

  return (
    <>
      {sheet && (
        <div className="app-sheet" role="dialog" aria-label="All apps">
          <div className="app-sheet-head">
            <b>All apps</b>
            <button className="mb-item" onClick={() => setSheet(false)} aria-label="Close app list">
              <X size={18} />
            </button>
          </div>
          <div className="app-sheet-grid">
            {APP_ORDER.map((id) => (
              <button key={id} className={`app-sheet-item ${active === id ? "on" : ""}`}
                      onClick={() => launch(id)}>
                <AppTile id={id} />
                <span>{APP_META[id].name}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <nav className="tabbar" role="navigation" aria-label="Primary">
        {PRIMARY.map((id) => (
          <button key={id} className={`tabbar-item ${active === id ? "on" : ""}`}
                  onClick={() => launch(id)} aria-label={APP_META[id].name}
                  aria-current={active === id ? "page" : undefined}>
            <AppTile id={id} />
            <span>{APP_META[id].name}</span>
          </button>
        ))}
        <button className={`tabbar-item ${sheet ? "on" : ""}`} onClick={() => setSheet((v) => !v)}
                aria-label="All apps" aria-expanded={sheet}>
          <span className="tab-more"><Grid3x3 size={18} /></span>
          <span>Apps</span>
        </button>
      </nav>
    </>
  );
}
