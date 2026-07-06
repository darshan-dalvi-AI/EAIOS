import { useOS } from "../store";
import { APP_META, APP_ORDER, AppTile } from "./appRegistry";

const IS_MAC = false as boolean; // Windows-only UI (project decision) — set back to platform detection to re-enable macOS chrome

export default function Dock() {
  const { windows, open } = useOS();

  return (
    <div className={IS_MAC ? "dock-zone" : "dock-zone tz"}>
      <div className={IS_MAC ? "dock" : "dock taskbar"} role="toolbar" aria-label={IS_MAC ? "Application dock" : "Taskbar"}>
        {APP_ORDER.map((id, i) => {
          const running = windows.some((w) => w.id === id);
          return (
            <span key={id} style={{ display: "contents" }}>
              {i === 6 && <span className="dock-sep" aria-hidden />}
              <button className={`dock-item ${running ? "running" : ""}`} onClick={() => open(id)} aria-label={`Open ${APP_META[id].name}`}>
                <span className="dock-label">{APP_META[id].name}</span>
                <AppTile id={id} />
                <span className="dock-dot" />
              </button>
            </span>
          );
        })}
      </div>
    </div>
  );
}
