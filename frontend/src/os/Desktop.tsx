import { useEffect } from "react";
import AdminApp from "../apps/AdminApp";
import AgentsApp from "../apps/AgentsApp";
import AnalyticsApp from "../apps/AnalyticsApp";
import AutomationsApp from "../apps/AutomationsApp";
import ChatApp from "../apps/ChatApp";
import GraphApp from "../apps/GraphApp";
import KnowledgeApp from "../apps/KnowledgeApp";
import MeetingApp from "../apps/MeetingApp";
import SettingsApp from "../apps/SettingsApp";
import SQLApp from "../apps/SQLApp";
import TerminalApp from "../apps/TerminalApp";
import TracesApp from "../apps/TracesApp";
import VideoApp from "../apps/VideoApp";
import { connectRealtime, disconnectRealtime } from "../lib/ws";
import { useOS } from "../store";
import type { AppId } from "../types";
import CommandPalette from "./CommandPalette";
import Dock from "./Dock";
import MenuBar from "./MenuBar";
import Toasts from "./Toasts";
import Window from "./Window";

const COMPONENTS: Record<AppId, () => JSX.Element> = {
  chat: ChatApp,
  knowledge: KnowledgeApp,
  agents: AgentsApp,
  graph: GraphApp,
  automations: AutomationsApp,
  traces: TracesApp,
  sql: SQLApp,
  analytics: AnalyticsApp,
  meeting: MeetingApp,
  video: VideoApp,
  admin: AdminApp,
  terminal: TerminalApp,
  settings: SettingsApp,
};

export default function Desktop() {
  const { windows, paletteOpen, setPalette, open } = useOS();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette(!useOS.getState().paletteOpen);
      }
      if (e.key === "Escape") setPalette(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPalette]);

  // Realtime: presence + live agent feed (live mode only; no-op in demo)
  useEffect(() => {
    connectRealtime();
    return () => disconnectRealtime();
  }, []);

  // First-run: open the chat app front and center
  useEffect(() => {
    if (useOS.getState().windows.length === 0) open("chat");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const allMinimized = windows.every((w) => w.minimized);

  return (
    <>
      <MenuBar />
      {(windows.length === 0 || allMinimized) && (
        <div className="empty" style={{ position: "fixed", inset: 0, pointerEvents: "none" }}>
          <div className="boot-logo" style={{ fontSize: 26, opacity: 0.7 }}>EAIOS</div>
          <div>
            Press <span className="kbd">Ctrl</span> + <span className="kbd">K</span> or pick an app from the dock
          </div>
        </div>
      )}
      <div style={{ position: "fixed", inset: 0, zIndex: "var(--z-window)" as unknown as number }}>
        {windows.map((win) => {
          const Component = COMPONENTS[win.id];
          return (
            <Window key={win.id} win={win}>
              <Component />
            </Window>
          );
        })}
      </div>
      <Dock />
      <Toasts />
      {paletteOpen && <CommandPalette />}
    </>
  );
}
