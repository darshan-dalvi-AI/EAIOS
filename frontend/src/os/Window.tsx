import { useState, type ReactNode } from "react";
import { useOS } from "../store";
import type { Win } from "../types";
import { AppTile } from "./appRegistry";
import { APP_META } from "./appRegistry";

const MENUBAR_H = 34;
const IS_MAC = false as boolean; // Windows-only UI (project decision) — set back to platform detection to re-enable macOS chrome

export default function Window({ win, children }: { win: Win; children: ReactNode }) {
  const { focus, close, minimize, toggleMax, setRect } = useOS();
  const focused = useOS((s) => s.windows.every((w) => w.z <= win.z));
  const [closing, setClosing] = useState(false);

  function requestClose() {
    setClosing(true);
    setTimeout(() => close(win.id), 180);
  }

  function startDrag(e: React.PointerEvent) {
    if (win.maximized || (e.target as HTMLElement).closest(".light, .cap-btn")) return;
    focus(win.id);
    const startX = e.clientX;
    const startY = e.clientY;
    const origin = win.rect;
    const move = (ev: PointerEvent) => {
      const x = Math.min(Math.max(origin.x + ev.clientX - startX, 60 - origin.w), window.innerWidth - 60);
      const y = Math.min(Math.max(origin.y + ev.clientY - startY, MENUBAR_H), window.innerHeight - 60);
      setRect(win.id, { ...origin, x, y });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  function startResize(e: React.PointerEvent, dir: "se" | "e" | "s") {
    e.stopPropagation();
    focus(win.id);
    const startX = e.clientX;
    const startY = e.clientY;
    const origin = win.rect;
    const move = (ev: PointerEvent) => {
      const dw = dir !== "s" ? ev.clientX - startX : 0;
      const dh = dir !== "e" ? ev.clientY - startY : 0;
      setRect(win.id, {
        ...origin,
        w: Math.max(420, origin.w + dw),
        h: Math.max(280, origin.h + dh),
      });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  return (
    <section
      className={`window ${focused ? "focused" : ""} ${win.maximized ? "maximized" : ""} ${closing ? "closing" : ""}`}
      style={{
        left: win.rect.x,
        top: win.rect.y,
        width: win.rect.w,
        height: win.rect.h,
        zIndex: win.z,
        display: win.minimized ? "none" : "flex",
      }}
      onPointerDown={() => focus(win.id)}
      aria-label={`${APP_META[win.id].name} window`}
    >
      <header className="titlebar" onPointerDown={startDrag} onDoubleClick={() => toggleMax(win.id)}>
        {IS_MAC ? (
          <>
            <div className="lights">
              <button className="light c" onClick={requestClose} aria-label="Close window">
                <svg width="7" height="7" viewBox="0 0 8 8" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M1 1l6 6M7 1L1 7" /></svg>
              </button>
              <button className="light m" onClick={() => minimize(win.id)} aria-label="Minimize window">
                <svg width="7" height="7" viewBox="0 0 8 8" stroke="currentColor" strokeWidth="1.6"><path d="M1 4h6" /></svg>
              </button>
              <button className="light x" onClick={() => toggleMax(win.id)} aria-label="Maximize window">
                <svg width="7" height="7" viewBox="0 0 8 8" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M1.5 4.5v2h2M6.5 3.5v-2h-2" /></svg>
              </button>
            </div>
            <div className="win-title">
              <AppTile id={win.id} size="sm" />
              {APP_META[win.id].name}
            </div>
          </>
        ) : (
          <>
            <div className="win-title win">
              <AppTile id={win.id} size="sm" />
              {APP_META[win.id].name}
            </div>
            <div className="caption-controls">
              <button className="cap-btn" onClick={() => minimize(win.id)} aria-label="Minimize window">
                <svg width="10" height="10" viewBox="0 0 10 10" stroke="currentColor" strokeWidth="1.1"><path d="M0 5h10" /></svg>
              </button>
              <button className="cap-btn" onClick={() => toggleMax(win.id)} aria-label="Maximize window">
                {win.maximized
                  ? <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.1"><rect x="0.5" y="2.5" width="7" height="7" /><path d="M2.5 2.5v-2h7v7h-2" /></svg>
                  : <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.1"><rect x="0.5" y="0.5" width="9" height="9" /></svg>}
              </button>
              <button className="cap-btn close" onClick={requestClose} aria-label="Close window">
                <svg width="10" height="10" viewBox="0 0 10 10" stroke="currentColor" strokeWidth="1.1"><path d="M0 0l10 10M10 0L0 10" /></svg>
              </button>
            </div>
          </>
        )}
      </header>
      <div className="win-body">{children}</div>
      {!win.maximized && (
        <>
          <div className="resize-e" onPointerDown={(e) => startResize(e, "e")} />
          <div className="resize-s" onPointerDown={(e) => startResize(e, "s")} />
          <div className="resize-handle" onPointerDown={(e) => startResize(e, "se")} />
        </>
      )}
    </section>
  );
}
