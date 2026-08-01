import { LayoutGrid } from "lucide-react";
import { useEffect, useState } from "react";
import { apiWorkspaceApps } from "../lib/api";
import { useOS } from "../store";
import type { AppId } from "../types";
import { APP_META, APP_ORDER, AppTile } from "./appRegistry";

const IS_MAC = false as boolean; // Windows-only UI (project decision) — set back to platform detection to re-enable macOS chrome

export default function Dock() {
  const { windows, open, live, industry } = useOS();
  // The apps this workspace's field actually uses, in order. A consultancy gets
  // the code editor on its taskbar; a clinic gets the knowledge graph instead.
  // Everything else stays one click away in the drawer — this shapes the
  // default surface, it is not a permission boundary.
  const [fieldApps, setFieldApps] = useState<AppId[] | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    if (!live) { setFieldApps(null); return; }   // demo mode: show everything
    let cancelled = false;
    apiWorkspaceApps()
      .then((r) => { if (!cancelled) setFieldApps(r.apps as AppId[]); })
      .catch(() => { if (!cancelled) setFieldApps(null); });   // fall back to the full dock
    return () => { cancelled = true; };
    // Re-runs when the workspace picks a different field.
  }, [live, industry]);

  const known = new Set<AppId>(APP_ORDER);
  const primary: AppId[] = (fieldApps ?? APP_ORDER).filter((a) => known.has(a));
  const rest: AppId[] = APP_ORDER.filter((a) => !primary.includes(a));
  const shown = showAll ? [...primary, ...rest] : primary;

  return (
    <div className={IS_MAC ? "dock-zone" : "dock-zone tz"}>
      <div className={IS_MAC ? "dock" : "dock taskbar"} role="toolbar" aria-label={IS_MAC ? "Application dock" : "Taskbar"}>
        {shown.map((id, i) => {
          const running = windows.some((w) => w.id === id);
          const startsExtras = showAll && i === primary.length;
          return (
            <span key={id} style={{ display: "contents" }}>
              {(i === 3 || startsExtras) && <span className="dock-sep" aria-hidden />}
              <button className={`dock-item ${running ? "running" : ""}`} onClick={() => open(id)} aria-label={`Open ${APP_META[id].name}`}>
                <span className="dock-label">{APP_META[id].name}</span>
                <AppTile id={id} />
                <span className="dock-dot" />
              </button>
            </span>
          );
        })}
        {rest.length > 0 && (
          <>
            <span className="dock-sep" aria-hidden />
            <button
              className="dock-item"
              onClick={() => setShowAll((v) => !v)}
              aria-label={showAll ? "Show fewer apps" : `Show all apps, ${rest.length} more`}
              aria-expanded={showAll}
            >
              <span className="dock-label">{showAll ? "Show less" : `All apps (${rest.length})`}</span>
              <div className="app-icon" style={{ "--hue": 220 } as React.CSSProperties} role="img"
                   aria-label={showAll ? "Show fewer apps" : "Show all apps"}>
                <LayoutGrid size={24} strokeWidth={2.2} />
              </div>
              <span className="dock-dot" />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
